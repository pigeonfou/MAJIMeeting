"""Offline Community-1 adapter in an isolated Python runtime; no Torch in the GUI."""
import json
import os
import subprocess
import tempfile
import time
import wave
from concurrent.futures import CancelledError
from pathlib import Path

from majimeeting.speakers import complete_run, start_run
from majimeeting.transcription import check_cancel

# Passed as code, with all paths in a separate JSON file (never shell interpolation).
WORKER = r'''
import json, os, socket, sys, wave
os.environ.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                  PYANNOTE_METRICS_ENABLED='false', OTEL_SDK_DISABLED='true')
def offline(*args, **kwargs):
    raise RuntimeError('Network access disabled during local diarization')
socket.socket.connect = offline
socket.create_connection = offline
import numpy as np
import torch
from pyannote.audio import Pipeline
request = json.load(open(sys.argv[1], encoding='utf-8'))
pipeline = Pipeline.from_pretrained(request['model'])
if request['device'] == 'cuda' and not torch.cuda.is_available():
    raise RuntimeError('CUDA PyTorch indisponible. Choisissez CPU ou installez le runtime CUDA.')
pipeline.to(torch.device(request['device']))
with wave.open(request['audio'], 'rb') as audio:
    samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').astype(np.float32) / 32768
waveform = torch.from_numpy(samples).unsqueeze(0)
kwargs = {'num_speakers': request['speakers']} if request['speakers'] else {}
output = pipeline({'waveform': waveform, 'sample_rate': 16000}, **kwargs)
turns = []
for turn, _, label in output.speaker_diarization.itertracks(yield_label=True):
    turns.append({'start': turn.start, 'end': turn.end, 'label': str(label)})
with open(request['result'], 'w', encoding='utf-8') as target:
    json.dump(turns, target)
'''


def prepare_track(track, destination, cancel=None):
    """Stream mono 16 kHz PCM, preserving gaps, with a separate absolute origin."""
    import av
    fragments = sorted(track.glob('*.wav'))
    if not fragments:
        raise ValueError('Aucun fragment finalisé.')
    origin = json.loads(fragments[0].with_suffix('.json').read_text())['start_seconds']
    if origin < 0:
        raise ValueError('Origine audio invalide.')
    position = 0
    previous_end = origin
    with wave.open(str(destination), 'wb') as target:
        target.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        for fragment in fragments:
            check_cancel(cancel)
            timing = json.loads(fragment.with_suffix('.json').read_text())
            with wave.open(str(fragment), 'rb') as source:
                if source.getnframes() != timing['frames'] or source.getsampwidth() != 2:
                    raise ValueError('Fragment incomplet ou format invalide.')
                duration = source.getnframes() / source.getframerate()
            start, end = timing['start_seconds'], timing['start_seconds'] + duration
            if start < previous_end - .001:
                raise ValueError('Fragments en chevauchement.')
            if end - origin > 4 * 3600:
                raise ValueError('Cette première version de diarisation accepte 4 heures par piste.')
            first, last = round((start - origin) * 16000), round((end - origin) * 16000)
            while position < first:
                check_cancel(cancel)
                count = min(65536, first - position)
                target.writeframesraw(b'\0\0' * count)
                position += count
            resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
            with av.open(str(fragment)) as container:
                def write(frames):
                    nonlocal position
                    for converted in frames:
                        pcm = converted.to_ndarray().tobytes()[:max(0, last - position) * 2]
                        target.writeframesraw(pcm)
                        position += len(pcm) // 2
                for frame in container.decode(audio=0):
                    check_cancel(cancel)
                    write(resampler.resample(frame))
                write(resampler.resample(None))
            if position < last:
                target.writeframesraw(b'\0\0' * (last - position))
                position = last
            previous_end = end
    return origin, position / 16000


def run_worker(python, model, audio, result, device, speakers, cancel, progress):
    request = result.with_suffix('.request.json')
    request.write_text(json.dumps(dict(model=str(model), audio=str(audio), result=str(result),
                                      device=device, speakers=speakers)), encoding='utf-8')
    environment = os.environ.copy()
    # A frozen app's Python paths/DLL search hints must not contaminate the runtime.
    for key in ('PYTHONHOME', 'PYTHONPATH'):
        environment.pop(key, None)
    environment.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                       PYANNOTE_METRICS_ENABLED='false', OTEL_SDK_DISABLED='true')
    log = result.with_suffix('.log')
    with log.open('w', encoding='utf-8') as output:
        process = subprocess.Popen([str(python), '-I', '-c', WORKER, str(request)],
                                   stdout=output, stderr=output, env=environment,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            tick = time.monotonic()
            while process.poll() is None:
                check_cancel(cancel)
                try:
                    process.wait(timeout=.2)
                except subprocess.TimeoutExpired:
                    pass
                if time.monotonic() - tick > 5:
                    progress('Diarisation locale en cours…')
                    tick = time.monotonic()
            if process.returncode:
                raise RuntimeError('Diarisation impossible : ' + log.read_text(
                    encoding='utf-8', errors='replace')[-4000:])
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    if result.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('Résultat de diarisation trop volumineux.')
    return json.loads(result.read_text(encoding='utf-8'))


def diarize(store, job, python, model, device='cpu', speakers=0, cancel=None,
            progress=lambda message: None, worker=run_worker):
    python, model = Path(python), Path(model)
    if not python.is_file() or not (model / 'config.yaml').is_file():
        raise ValueError('Choisissez le Python du runtime et le dossier Community-1 local complet.')
    if device not in {'cpu', 'cuda'} or not isinstance(speakers, int) or not 0 <= speakers <= 50:
        raise ValueError('Paramètres de diarisation invalides.')
    with store.connect() as db:
        record = db.execute('SELECT meeting_id FROM transcription_jobs WHERE id=?', (job,)).fetchone()
    if record is None:
        raise ValueError('Transcription introuvable.')
    rows = store.segments(job)
    tracks = sorted({r['track'] for r in rows})
    if not tracks:
        raise ValueError('Cette transcription ne contient aucun passage.')
    run = start_run(store, job, dict(model=str(model), device=device, speakers=speakers,
                                    engine='pyannote.audio/Community-1', grouping='per_track'))
    try:
        all_turns = []
        with tempfile.TemporaryDirectory(prefix='majimeeting-speakers-') as temp:
            for track in tracks:
                check_cancel(cancel)
                if Path(track).name != track or not track.startswith('track-'):
                    raise ValueError('Piste invalide.')
                progress(f'{track} : préparation pour la diarisation…')
                audio, result = Path(temp) / 'audio.wav', Path(temp) / 'result.json'
                origin, duration = prepare_track(store.root / record['meeting_id'] / track, audio, cancel)
                result.unlink(missing_ok=True)
                turns = worker(python, model.resolve(), audio, result, device, speakers, cancel, progress)
                for turn in turns:
                    start, end = float(turn['start']), float(turn['end'])
                    if not (0 <= start < end <= duration + .01):
                        raise ValueError('Tour de parole hors de la piste audio.')
                    all_turns.append(dict(track=track, start=origin + start,
                                          end=origin + min(end, duration), label=turn['label']))
        check_cancel(cancel)
        return complete_run(store, run, all_turns)
    except Exception as exc:
        with store.connect() as db:
            db.execute('UPDATE diarization_runs SET status=?,error=? WHERE id=?',
                       ('cancelled' if isinstance(exc, CancelledError) else 'failed', str(exc), run))
        raise
