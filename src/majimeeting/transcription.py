"""Deferred, local-only transcription; one model per job, bounded audio batches."""
import gc
import json
import math
import tempfile
import uuid
import wave
from concurrent.futures import CancelledError
from dataclasses import dataclass, replace
from pathlib import Path

from majimeeting.cuda_runtime import is_cuda_error, prepare_cuda
from majimeeting.model_download import download_model  # noqa: F401 (public compatibility import)
from majimeeting.storage import FragmentWriter


@dataclass(frozen=True)
class TranscriptionOptions:
    model_path: str
    device: str = 'cpu'
    compute_type: str = 'int8'
    language: str = 'fr'
    allow_cpu_fallback: bool = True
    cuda_library_path: str = ''

    def validate(self):
        folder = Path(self.model_path)
        if not folder.is_dir() or not all((folder / f).is_file() for f in
                                          ('model.bin', 'config.json', 'tokenizer.json')):
            raise ValueError('Sélectionnez un modèle faster-whisper local complet.')
        allowed = {'cpu': {'int8', 'float32'}, 'cuda': {'float16', 'int8_float16'}}
        if self.device not in allowed or self.compute_type not in allowed[self.device]:
            raise ValueError('Combinaison appareil/quantification non prise en charge.')


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise CancelledError('Traitement annulé ; résultats déjà enregistrés conservés.')


def import_audio(store, source, cancel=None, progress=lambda message: None):
    """Keep original, decode in streaming mode to 16 kHz mono recoverable fragments."""
    import av
    source = Path(source)
    if source.suffix.lower() not in {'.wav', '.mp3', '.flac', '.m4a'}:
        raise ValueError('Formats acceptés : WAV, MP3, FLAC et M4A.')
    if not source.is_file():
        raise ValueError('Le fichier audio est introuvable.')
    meeting_id = store.create(source.stem)
    folder = store.root / meeting_id
    writer = None
    try:
        original = folder / ('original' + source.suffix.lower())
        with source.open('rb') as input_file, original.with_suffix('.part').open('wb') as output:
            while block := input_file.read(1024 * 1024):
                check_cancel(cancel)
                output.write(block)
        original.with_suffix('.part').replace(original)
        writer = FragmentWriter(folder / 'track-00', 16000, 1,
                                {'name': source.name, 'imported': True})
        samples = 0
        resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)

        def write(frame):
            nonlocal samples
            data = frame.to_ndarray().tobytes()
            writer.write(data, samples / 16000)
            samples += len(data) // 2

        with av.open(str(original)) as container:
            if not container.streams.audio:
                raise ValueError('Le fichier ne contient aucune piste audio.')
            for frame in container.decode(audio=0):
                check_cancel(cancel)
                for converted in resampler.resample(frame):
                    write(converted)
                progress(f'Import : {samples / 16000:.0f} s décodées')
            for converted in resampler.resample(None):
                write(converted)
        if not samples:
            raise ValueError('Le fichier audio est vide.')
        writer.close()
        store.finish(meeting_id, 'completed')
        return meeting_id
    except Exception as exc:
        if writer:
            try:
                writer.close()
            except OSError:
                pass  # Retain the original failure and mark the catalogue explicitly.
        store.finish(meeting_id, 'interrupted' if isinstance(exc, CancelledError) else 'failed',
                     str(exc))
        raise
    finally:
        (folder / 'original.part').unlink(missing_ok=True)


def audio_batches(track, destination, cancel=None, max_seconds=300):
    """Assemble bounded contiguous batches; preserve offsets, including recovered tracks."""
    info = json.loads((track / 'track.json').read_text(encoding='utf-8'))
    fragments = sorted(track.glob('*.wav'))
    index = 0
    while index < len(fragments):
        check_cancel(cancel)
        first = json.loads(fragments[index].with_suffix('.json').read_text())
        offset, frames = first['start_seconds'], 0
        with wave.open(str(destination), 'wb') as output:
            output.setnchannels(info['channels'])
            output.setsampwidth(info['sample_width'])
            output.setframerate(info['rate'])
            while index < len(fragments):
                path = fragments[index]
                timing = json.loads(path.with_suffix('.json').read_text())
                if frames and (frames / info['rate'] >= max_seconds or
                               abs(timing['start_seconds'] - offset - frames / info['rate']) > .01):
                    break
                check_cancel(cancel)
                with wave.open(str(path), 'rb') as audio:
                    if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (
                            info['rate'], info['channels'], info['sample_width']):
                        raise ValueError('Format audio incohérent dans les fragments.')
                    if audio.getnframes() != timing['frames']:
                        raise ValueError('Fragment audio incomplet.')
                    while block := audio.readframes(65536):
                        output.writeframesraw(block)
                    frames += audio.getnframes()
                index += 1
        yield offset, frames / info['rate']


def transcribe_meeting(store, meeting_id, options, cancel=None, progress=lambda message: None,
                       model_factory=None, cuda_prepare=None):
    options.validate()
    check_cancel(cancel)
    tracks = sorted((store.root / meeting_id).glob('track-*'))
    tracks = [t for t in tracks if (t / 'track.json').is_file() and any(t.glob('*.wav'))]
    if not tracks:
        raise ValueError('Aucune piste audio finalisée à transcrire.')
    job = uuid.uuid4().hex
    store.start_transcription(job, meeting_id, options)
    effective = options
    retry_cpu = False
    try:
        store.set_execution(job, options.device, options.compute_type)
        try:
            if options.device == 'cuda':
                (cuda_prepare or prepare_cuda)(options.cuda_library_path)
            _run_inference(store, job, tracks, effective, cancel, progress, model_factory)
        except (RuntimeError, OSError) as exc:
            if options.device != 'cuda' or not is_cuda_error(exc):
                raise
            if not options.allow_cpu_fallback:
                raise RuntimeError(f'CUDA indisponible : {exc} '
                                   'Choisissez CPU/int8 ou configurez les bibliothèques NVIDIA.') from exc
            check_cancel(cancel)
            reason = str(exc)
            progress(f'CUDA indisponible : {reason} Reprise complète sur CPU/int8.')
            effective = replace(options, device='cpu', compute_type='int8')
            # Delete only this attempt's GPU segments, avoiding duplicates on full restart.
            store.set_execution(job, 'cpu', 'int8', reason, reset_segments=True)
            retry_cpu = True
        if retry_cpu:
            # Exit the exception handler first: its traceback may retain the failed GPU model.
            gc.collect()
            _run_inference(store, job, tracks, effective, cancel, progress, model_factory)
        check_cancel(cancel)
        store.finish_transcription(job, 'completed')
        return job
    except Exception as exc:
        state = 'cancelled' if isinstance(exc, CancelledError) else 'failed'
        store.finish_transcription(job, state, str(exc))
        raise


def _run_inference(store, job, tracks, options, cancel, progress, model_factory):
    model = None
    segments = None
    try:
        if model_factory is None:
            from faster_whisper import WhisperModel
            model_factory = WhisperModel
        progress(f'Chargement du modèle local sur {options.device}/{options.compute_type}…')
        model = model_factory(options.model_path, device=options.device,
                              compute_type=options.compute_type, local_files_only=True)
        with tempfile.TemporaryDirectory(prefix='majimeeting-') as temp:
            batch_path = Path(temp) / 'batch.wav'
            for track in tracks:
                for offset, duration in audio_batches(track, batch_path, cancel):
                    check_cancel(cancel)
                    progress(f'{track.name} : transcription à partir de {offset:.0f} s')
                    segments, _ = model.transcribe(str(batch_path), language=options.language,
                                                   beam_size=5, vad_filter=True)
                    for segment in segments:
                        check_cancel(cancel)
                        start, end = float(segment.start), float(segment.end)
                        if not (math.isfinite(start) and math.isfinite(end) and
                                0 <= start <= duration and start <= end <= duration + 1):
                            raise ValueError('Horodatage de transcription invalide.')
                        if segment.text.strip():
                            store.add_segment(job, track.name, offset + start,
                                              offset + min(end, duration),
                                              segment.text.strip())
                        progress(f'{track.name} : {offset + end:.0f} s traitées')
    finally:
        # Close the lazy iterator too: it can otherwise retain the failed GPU model.
        if segments is not None and hasattr(segments, 'close'):
            segments.close()
        segments = None
        model = None
        gc.collect()
