"""One deferred action, with GPU models released between stages."""
from concurrent.futures import CancelledError

from majimeeting.diarization import diarize
from majimeeting.transcription import transcribe_meeting


def process_meeting(store, meeting, options, python, model, device, speakers, tuning,
                    cancel=None, progress=lambda _: None):
    job = transcribe_meeting(store, meeting, options, cancel, progress)
    try:
        diarize(store, job, python, model, device, speakers, cancel, progress,
                tuning=tuning, whisper_model_path=options.model_path)
    except CancelledError:
        raise
    except Exception as exc:
        raise RuntimeError('La transcription est sauvegardée. Analyse des voix interrompue : '
                           + str(exc) + ' — rouvrez cette transcription pour réessayer sans refaire Whisper.') from exc
    return job
