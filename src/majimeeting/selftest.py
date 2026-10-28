"""Small-model CPU integration check for CI and the packaged executable."""
import tempfile
import wave
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

from majimeeting.storage import MeetingStore
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
    return 0
