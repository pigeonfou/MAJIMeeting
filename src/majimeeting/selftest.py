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
from majimeeting.transcription import TranscriptionOptions, import_audio, transcribe_meeting


def inference_smoke(model_path):
    # Force the decoder to run even on silence, rather than only testing model import.
    model = WhisperModel(model_path, device='cpu', compute_type='int8', local_files_only=True)
    segments, _ = model.transcribe(np.zeros(16000, dtype=np.float32), language='fr',
                                   vad_filter=False, beam_size=1)
    list(segments)
    del model
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
