"""Deferred, local-only transcription; one model per job, bounded audio batches."""
import gc
import json
import math
import tempfile
import time
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
    batched: bool = False
    batch_size: int = 8
    beam_size: int = 5

    def validate(self):
        folder = Path(self.model_path)
        if not folder.is_dir() or not all((folder / f).is_file() for f in
                                          ('model.bin', 'config.json', 'tokenizer.json')):
            raise ValueError('Sélectionnez un modèle faster-whisper local complet.')
        allowed = {'cpu': {'int8', 'float32'}, 'cuda': {'float16', 'int8_float16'}}
        if self.device not in allowed or self.compute_type not in allowed[self.device]:
            raise ValueError('Combinaison appareil/quantification non prise en charge.')
        if self.batch_size not in {1, 2, 4, 8, 16} or self.beam_size not in {1, 5}:
            raise ValueError('Taille de lot ou profil de qualité invalide.')


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
                       model_factory=None, cuda_prepare=None, pipeline_factory=None):
    options.validate()
    check_cancel(cancel)
    tracks = sorted((store.root / meeting_id).glob('track-*'))
    tracks = [t for t in tracks if (t / 'track.json').is_file() and any(t.glob('*.wav'))]
    if not tracks:
        raise ValueError('Aucune piste audio finalisée à transcrire.')
    job = uuid.uuid4().hex
    store.start_transcription(job, meeting_id, options)
    effective, reason = options, ''
    started = time.perf_counter()
    metrics = {'attempts': []}
    try:
        while True:
            check_cancel(cancel)
            attempt = {'device': effective.device, 'batched': effective.batched,
                       'batch_size': effective.batch_size if effective.batched else 1,
                       'model_load_seconds': 0.0, 'prepare_seconds': 0.0,
                       'inference_seconds': 0.0, 'save_seconds': 0.0,
                       'completed_audio_seconds': 0.0}
            metrics['attempts'].append(attempt)
            store.set_execution(job, effective.device, effective.compute_type, reason,
                                reset_segments=len(metrics['attempts']) > 1,
                                batched=effective.batched,
                                batch_size=attempt['batch_size'], beam_size=effective.beam_size)
            retry = False
            try:
                if effective.device == 'cuda':
                    (cuda_prepare or prepare_cuda)(effective.cuda_library_path)
                _run_inference(store, job, tracks, effective, cancel, progress, model_factory,
                               pipeline_factory, attempt)
            except (RuntimeError, OSError) as exc:
                oom = any(token in str(exc).lower() for token in (
                    'out of memory', 'cuda_error_out_of_memory', 'cublas_status_alloc_failed'))
                if effective.device != 'cuda' or not (oom or is_cuda_error(exc)):
                    raise
                check_cancel(cancel)
                if oom and effective.batched and effective.batch_size > 1:
                    size = max(1, effective.batch_size // 2)
                    reason = f'Mémoire GPU insuffisante : réduction du lot à {size}.'
                    effective = replace(effective, batch_size=size)
                elif oom and effective.batched:
                    reason = 'Mémoire GPU insuffisante : reprise CUDA séquentielle.'
                    effective = replace(effective, batched=False, batch_size=1)
                elif effective.allow_cpu_fallback:
                    reason = str(exc)
                    effective = replace(effective, device='cpu', compute_type='int8',
                                        batched=False, batch_size=1)
                    progress(f'CUDA indisponible : {reason} Reprise complète sur CPU/int8.')
                else:
                    raise RuntimeError(f'CUDA indisponible : {exc} '
                                       'Choisissez CPU/int8 ou configurez les bibliothèques NVIDIA.') from exc
                attempt['error'] = str(exc)
                progress(reason + ' Reprise depuis le début ; anciennes tentatives conservées.')
                retry = True
            if not retry:
                break
            # Exit the exception handler first: tracebacks can retain the failed GPU pipeline.
            gc.collect()
        check_cancel(cancel)
        store.finish_transcription(job, 'completed')
        return job
    except Exception as exc:
        state = 'cancelled' if isinstance(exc, CancelledError) else 'failed'
        store.finish_transcription(job, state, str(exc))
        raise
    finally:
        metrics['total_seconds'] = time.perf_counter() - started
        store.set_transcription_metrics(job, metrics)


def _run_inference(store, job, tracks, options, cancel, progress, model_factory,
                   pipeline_factory, metrics):
    model = runner = segments = None
    try:
        if model_factory is None:
            from faster_whisper import WhisperModel
            model_factory = WhisperModel
        progress(f'Chargement du modèle local sur {options.device}/{options.compute_type}…')
        before = time.perf_counter()
        try:
            model = model_factory(options.model_path, device=options.device,
                                  compute_type=options.compute_type, local_files_only=True)
            runner = model
            if options.batched:
                if pipeline_factory is None:
                    from faster_whisper import BatchedInferencePipeline
                    pipeline_factory = BatchedInferencePipeline
                runner = pipeline_factory(model=model)
        finally:
            metrics['model_load_seconds'] += time.perf_counter() - before
        with tempfile.TemporaryDirectory(prefix='majimeeting-') as temp:
            batch_path = Path(temp) / 'batch.wav'
            for track in tracks:
                batches = iter(audio_batches(track, batch_path, cancel))
                while True:
                    check_cancel(cancel)
                    before = time.perf_counter()
                    try:
                        offset, duration = next(batches)
                    except StopIteration:
                        break
                    finally:
                        metrics['prepare_seconds'] += time.perf_counter() - before
                    progress(f'{track.name} : transcription à partir de {offset:.0f} s '
                             f"({'lots de ' + str(options.batch_size) if options.batched else 'séquentiel'}, "
                             f'beam={options.beam_size})')
                    kwargs = {'language': options.language, 'beam_size': options.beam_size,
                              'vad_filter': True, 'without_timestamps': False}
                    if options.batched:
                        kwargs['batch_size'] = options.batch_size
                    before = time.perf_counter()
                    try:
                        segments, _ = runner.transcribe(str(batch_path), **kwargs)
                        segments = iter(segments)
                    finally:
                        metrics['inference_seconds'] += time.perf_counter() - before
                    while True:
                        check_cancel(cancel)
                        before = time.perf_counter()
                        try:
                            segment = next(segments)
                        except StopIteration:
                            break
                        finally:
                            metrics['inference_seconds'] += time.perf_counter() - before
                        check_cancel(cancel)
                        text = segment.text.strip()
                        if not text:
                            continue
                        bounds, warning = normalize_timestamps(segment.start, segment.end, duration)
                        before = time.perf_counter()
                        try:
                            if warning:
                                store.add_transcription_warning(job, track.name, offset,
                                                                segment.start, segment.end,
                                                                warning, text)
                            if bounds is not None:
                                start, end = bounds
                                store.add_segment(job, track.name, offset + start, offset + end, text)
                        finally:
                            metrics['save_seconds'] += time.perf_counter() - before
                        if bounds is not None:
                            progress(f'{track.name} : {offset + end:.0f} s traitées')
                    metrics['completed_audio_seconds'] += duration
                    progress(f'{track.name} : {offset + duration:.0f} s traitées')
    finally:
        # A lazy iterator or pipeline can otherwise retain the failed GPU model.
        if segments is not None and hasattr(segments, 'close'):
            segments.close()
        segments = runner = model = None
        gc.collect()


def normalize_timestamps(start, end, duration):
    """Keep source-backed intervals only; Whisper can timestamp padded tail audio."""
    try:
        start, end = float(start), float(end)
    except (TypeError, ValueError, OverflowError):
        return None, 'invalid_timestamp'
    if not (math.isfinite(start) and math.isfinite(end)) or end < start:
        return None, 'invalid_timestamp'
    if end <= 0 or start >= duration or start == end:
        return None, 'outside_audio'
    bounded = max(0.0, start), min(duration, end)
    if bounded[0] >= bounded[1]:
        return None, 'outside_audio'
    return bounded, 'clipped' if bounded != (start, end) else None
