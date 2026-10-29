"""Small-model CPU integration check for CI and the packaged executable."""
import json
import tempfile
import wave
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from faster_whisper import WhisperModel

from majimeeting.cuda_runtime import CudaUnavailableError
from majimeeting.storage import FragmentWriter, MeetingStore
from majimeeting.transcription import (
    TranscriptionOptions,
    import_audio,
    measured_pipeline,
    normalize_timestamps,
    transcribe_meeting,
)


def inference_smoke(model_path):
    # Force the decoder to run even on silence, rather than only testing model import.
    model = WhisperModel(model_path, device='cpu', compute_type='int8', local_files_only=True)
    segments, _ = model.transcribe(np.zeros(16000, dtype=np.float32), language='fr',
                                   vad_filter=False, beam_size=1)
    list(segments)
    # Exercise a real batch of two decoder requests, even though silence is removed by VAD.
    pipeline = measured_pipeline(model)
    batch_shapes = []
    original_encode = model.encode

    def counted_encode(features, *args, _encode=original_encode, **kwargs):
        batch_shapes.append(features.shape[0])
        return _encode(features, *args, **kwargs)

    model.encode = counted_encode
    batch_segments, info = pipeline.transcribe(
        np.zeros(32 * 16000, dtype=np.float32), language='fr', beam_size=1,
        batch_size=2, vad_filter=False, without_timestamps=False,
        clip_timestamps=[{'start': 0, 'end': 1}, {'start': 31, 'end': 32}])
    decoded = list(batch_segments)
    assert batch_shapes == [2], batch_shapes
    assert pipeline.observed_batch_sizes == [2]
    assert info.transcription_options.without_timestamps is False
    # Raw Whisper timestamps may extend into padding, as in the 0.2.3 regression.
    # Apply the production guard rather than requiring perfect timestamps from silence.
    for segment in decoded:
        bounds, _ = normalize_timestamps(segment.start, segment.end, 32)
        if bounds is not None:
            assert 0 <= bounds[0] < bounds[1] <= 32
    model.encode = original_encode
    del pipeline, original_encode, counted_encode, batch_segments, segments
    del model
    native_parallel_smoke(model_path)
    with tempfile.TemporaryDirectory(prefix='majimeeting-selftest-') as temp:
        folder = Path(temp)
        audio = folder / 'silence.wav'
        with wave.open(str(audio), 'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(b'\0\0' * 16000 * 3)
        store = MeetingStore(folder / 'data')
        meeting = import_audio(store, audio)
        job = transcribe_meeting(store, meeting, TranscriptionOptions(model_path))
        assert store.transcription_jobs(meeting)[0]['status'] == 'completed'
        assert not store.segments(job), 'Silence must not produce a transcript with VAD enabled'
        batched_job = transcribe_meeting(store, meeting, replace(
            TranscriptionOptions(model_path), batched=True, batch_size=2, beam_size=1))
        assert store.transcription_jobs(meeting)[0]['status'] == 'completed'
        assert not store.segments(batched_job)
        batch_details = json.loads(store.transcription_jobs(meeting)[0]['options'])
        assert batch_details['execution']['batched'] is True
        assert batch_details['metrics']['attempts'][0]['completed_audio_seconds'] == 3
        second = FragmentWriter(store.root / meeting / 'track-01', 16000, 1, {})
        second.write(b'\0\0' * 16000 * 3, .25)
        second.close()
        parallel_job = transcribe_meeting(store, meeting, replace(
            TranscriptionOptions(model_path), batched=True, batch_size=2, beam_size=1,
            gpu_workers=2))
        assert not store.segments(parallel_job)
        parallel_details = json.loads(store.transcription_jobs(meeting)[0]['options'])
        assert parallel_details['execution']['gpu_workers'] == 2
        assert parallel_details['metrics']['attempts'][0]['completed_audio_seconds'] == 6
        # Reproduce the reported missing-cuBLAS failure, then use the real CPU engine.
        def missing_cublas(path):
            raise CudaUnavailableError('cublas64_12.dll is not found or cannot be loaded')

        cuda_options = replace(TranscriptionOptions(model_path), device='cuda',
                               compute_type='float16')
        fallback_job = transcribe_meeting(store, meeting, cuda_options,
                                          cuda_prepare=missing_cublas)
        row = store.transcription_jobs(meeting)[0]
        assert row['id'] == fallback_job and row['status'] == 'completed'
        execution = json.loads(row['options'])['execution']
        assert execution['device'] == 'cpu' and execution['compute_type'] == 'int8'
        assert 'cublas64_12.dll' in execution['fallback_reason']
        timestamp_boundary_smoke(store, TranscriptionOptions(model_path))
    return 0


def timestamp_boundary_smoke(store, options, model_factory=None):
    """Reproduce four full 5-minute lots followed by a short, padded final lot."""
    meeting = store.create('Régression à 1200 secondes')
    folder = store.root / meeting / 'track-00'
    FragmentWriter(folder, 16, 1, {'name': 'synthetic timing test'})
    duration = 17.25
    for index, seconds in enumerate([300, 300, 300, 300, duration]):
        frames = round(seconds * 16)
        name = f'{index:08d}'
        with wave.open(str(folder / (name + '.wav')), 'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16)
            output.writeframes(b'\0\0' * frames)
        (folder / (name + '.json')).write_text(json.dumps(
            {'frames': frames, 'start_seconds': .5 + index * 300}))
    store.finish(meeting, 'completed')

    class Model:
        def __init__(self, *args, **kwargs):
            self.batch = 0

        def transcribe(self, *args, **kwargs):
            self.batch += 1
            if self.batch <= 4:
                data = [(0, 300, f'Lot {self.batch}')]
            else:
                data = [(2, 8, 'Parole valide'), (16.5, 30, 'Dernière parole'),
                        (duration, 30, 'Texte du padding sans source audio'),
                        (float('nan'), 5, 'Temps invalide à vérifier'),
                        (float('inf'), -1, '   ')]
            return iter(SimpleNamespace(start=a, end=b, text=text) for a, b, text in data), None

    job = transcribe_meeting(store, meeting, options, model_factory=model_factory or Model)
    segments = store.segments(job)
    assert len(segments) == 6
    assert segments[-1]['start'] == 1217
    assert segments[-1]['end'] == 1217.75
    assert segments[-1]['text'] == 'Dernière parole'
    assert all(0 <= row['start'] < row['end'] <= 1217.75 for row in segments)
    assert store.transcription_jobs(meeting)[0]['status'] == 'completed'
    assert store.warning_counts(job) == {'clipped': 1, 'outside_audio': 1, 'invalid_timestamp': 1}
    warnings = store.transcription_warnings(job)
    assert warnings[0]['raw_end'] == '30'
    assert warnings[1]['text'] == 'Texte du padding sans source audio'
    return job



def editor_smoke():
    """Exercise editor persistence and Qt WAV decoding without a physical sound device."""
    import math
    import struct
    import tempfile
    from pathlib import Path

    from PySide6.QtCore import QEventLoop, QTimer, QUrl
    from PySide6.QtMultimedia import QAudioDecoder
    from PySide6.QtWidgets import QApplication

    from majimeeting.editor_ui import TranscriptEditor
    from majimeeting.playback import make_excerpt
    from majimeeting.storage import FragmentWriter, MeetingStore
    from majimeeting.transcription import TranscriptionOptions

    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix='majimeeting-editor-test-') as directory:
        folder = Path(directory)
        store = MeetingStore(folder / 'data')
        meeting = store.create('Editor integration smoke')
        track = store.root / meeting / 'track-00'
        writer = FragmentWriter(track, 16000, 1, {})
        pcm = b''.join(struct.pack('<h', int(3000 * math.sin(i * 440 * 2 * math.pi / 16000)))
                       for i in range(16000))
        writer.write(pcm, 1)
        writer.close()
        store.finish(meeting, 'completed')
        store.start_transcription('editor-smoke', meeting, TranscriptionOptions('unused'))
        store.add_segment('editor-smoke', 'track-00', 1.2, 1.7, 'Original')
        store.finish_transcription('editor-smoke', 'completed')
        from majimeeting.diarization_ui import DiarizationDialog
        from majimeeting.speakers import complete_run, name_group, start_run
        from majimeeting.transcript_library import TranscriptLibrary
        configuration = DiarizationDialog(tracks=['track-00'])
        configuration.controls.speakers.setValue(2)
        assert configuration.controls.values()['threshold'] is None
        configuration.controls.clustering.setChecked(True)
        configuration.controls.threshold.setValue(.7)
        assert configuration.controls.values()['threshold'] == .7
        configuration.close()
        catalogue = TranscriptLibrary(store)
        assert catalogue.job() == 'editor-smoke'
        catalogue.close()
        run = start_run(store, 'editor-smoke', {'engine': 'synthetic-packaging-check'})
        complete_run(store, run, [dict(track='track-00', start=1, end=2, label='SPEAKER_00')])
        name_group(store, 'editor-smoke', 'track-00:SPEAKER_00', 'Groupe témoin')
        assert store.segments('editor-smoke')[0]['speaker'] == 'Groupe témoin'
        editor = TranscriptEditor(store, 'editor-smoke')
        editor.show()
        editor.text.setPlainText('Texte corrigé')
        editor.speaker.setText('Alice')
        editor.save_edit()
        assert store.segments('editor-smoke')[0]['speaker'] == 'Alice'
        editor.accept()
        app.processEvents()
        path = folder / 'excerpt.wav'
        assert make_excerpt(track, 1.2, 1.7, path) == .5
        loop = QEventLoop()
        decoder = QAudioDecoder()
        buffers, errors = [], []

        def consume():
            buffer = decoder.read()
            if buffer.isValid():
                buffers.append(buffer.frameCount())

        def failed(*_):
            errors.append(decoder.errorString())
            loop.quit()

        decoder.bufferReady.connect(consume)
        decoder.finished.connect(loop.quit)
        decoder.error.connect(failed)
        decoder.setSource(QUrl.fromLocalFile(str(path)))
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        timeout.start(15000)
        decoder.start()
        loop.exec()
        decoder.stop()
        assert timeout.isActive(), 'Qt WAV decoder timed out'
        timeout.stop()
        assert not errors, errors
        assert sum(buffers) == 8000, buffers
    print('Editor corrections and Qt WAV decoder smoke passed')
    return 0


def native_parallel_smoke(model_path):
    """Real concurrent decoder requests on two CPU workers sharing one model."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    model = WhisperModel(model_path, device='cpu', compute_type='int8',
                         local_files_only=True, num_workers=2)
    barrier = threading.Barrier(2)

    def decode():
        pipeline = measured_pipeline(model)
        barrier.wait(timeout=15)
        segments, _ = pipeline.transcribe(np.zeros(16000, dtype=np.float32), language='fr',
            vad_filter=False, without_timestamps=False, beam_size=1, batch_size=1,
            max_new_tokens=16)
        list(segments)
        return pipeline.observed_batch_sizes

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(decode) for _ in range(2)]
        assert [future.result(timeout=60) for future in futures] == [[1], [1]]
