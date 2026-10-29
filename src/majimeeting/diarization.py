"""Offline Community-1 adapter in an isolated Python runtime; no Torch in the GUI."""
import json
import math
import os
import subprocess
import tempfile
import time
import wave
from concurrent.futures import CancelledError
from dataclasses import asdict
from pathlib import Path

from majimeeting.diarization_options import RUNTIME_CONFIGURATION, DiarizationOptions
from majimeeting.speakers import complete_run, start_run
from majimeeting.transcription import check_cancel

# Passed as code, with all paths in a separate JSON file (never shell interpolation).
WORKER = r'''
import json, os, socket, sys, time, wave
os.environ.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                  PYANNOTE_METRICS_ENABLED='false', OTEL_SDK_DISABLED='true')
def offline(*args, **kwargs):
    raise RuntimeError('Network access disabled during local diarization')
socket.socket.connect = offline
socket.create_connection = offline
import numpy as np
import torch
from pyannote.audio import Pipeline
''' + RUNTIME_CONFIGURATION + r'''
request = json.load(open(sys.argv[1], encoding='utf-8'))
print('MAJI:Chargement du modèle Community-1 local…', flush=True)
pipeline = Pipeline.from_pretrained(request['model'])
if request['device'] == 'cuda' and not torch.cuda.is_available():
    raise RuntimeError('CUDA PyTorch indisponible. Choisissez CPU ou installez le runtime CUDA.')
pipeline.to(torch.device(request['device']))
devices = dict(pipeline=str(pipeline.device),
               segmentation=str(pipeline._segmentation.model.device),
               embedding=str(pipeline._embedding.device))
if request['device'] == 'cuda' and any(not v.startswith('cuda') for v in devices.values()):
    raise RuntimeError('Un réseau de diarisation est resté sur CPU : ' + str(devices))
gpu = torch.cuda.get_device_name() if request['device'] == 'cuda' else ''
print('MAJI:Réseaux de diarisation : ' + str(devices) + (' — ' + gpu if gpu else ''), flush=True)

with wave.open(request['audio'], 'rb') as audio:
    samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').astype(np.float32) / 32768
waveform = torch.from_numpy(samples).unsqueeze(0)
kwargs, effective = configure_pipeline(pipeline, request['tuning'])
effective.update(devices=devices, gpu=gpu)
phase_times = {}
last_phase, last_time = '', time.monotonic()
last_message = 0.
def hook(step_name, artifact, total=None, completed=None, **unused):
    global last_phase, last_time, last_message
    now = time.monotonic()
    if step_name != last_phase:
        if last_phase:
            phase_times[last_phase] = phase_times.get(last_phase, 0.) + now - last_time
        last_phase, last_time = step_name, now
        last_message = 0.
    if now - last_message >= 2. or (total and completed == total):
        suffix = f' {completed}/{total}' if total is not None else ''
        print('MAJI:' + step_name + suffix + ' — réseaux ' + str(devices), flush=True)
        last_message = now
    if step_name == 'embeddings' and (total is None or completed == total):
        print('MAJI:Empreintes terminées ; regroupement des voix et consolidation (CPU)…', flush=True)
output = pipeline({'waveform': waveform, 'sample_rate': 16000}, hook=hook, **kwargs)
if last_phase:
    phase_times[last_phase] = phase_times.get(last_phase, 0.) + time.monotonic() - last_time
effective['hook_intervals_seconds'] = phase_times
if request['device'] == 'cuda':
    effective['cuda_peak_allocated_mb'] = torch.cuda.max_memory_allocated() / 1024**2
turns = []
for turn, _, label in output.speaker_diarization.itertracks(yield_label=True):
    turns.append({'start': turn.start, 'end': turn.end, 'label': str(label)})
with open(request['result'], 'w', encoding='utf-8') as target:
    json.dump(dict(turns=turns, effective=effective), target)
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


def run_worker(python, model, audio, result, device, speakers, cancel, progress, tuning=None):
    request = result.with_suffix('.request.json')
    request.write_text(json.dumps(dict(model=str(model), audio=str(audio), result=str(result),
                                      device=device, speakers=speakers,
                                      tuning=tuning or DiarizationOptions().for_track('', speakers))), encoding='utf-8')
    environment = os.environ.copy()
    # A frozen app's Python paths/DLL search hints must not contaminate the runtime.
    for key in ('PYTHONHOME', 'PYTHONPATH'):
        environment.pop(key, None)
    environment.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                       PYANNOTE_METRICS_ENABLED='false', OTEL_SDK_DISABLED='true')
    log = result.with_suffix('.log')
    with log.open('w', encoding='utf-8') as output, log.open('r', encoding='utf-8', errors='replace') as events:
        process = subprocess.Popen([str(python), '-I', '-c', WORKER, str(request)],
                                   stdout=output, stderr=output, env=environment,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            tick = time.monotonic()
            phase = f'Initialisation du runtime de diarisation ({device})…'
            while process.poll() is None:
                check_cancel(cancel)
                try:
                    process.wait(timeout=.2)
                except subprocess.TimeoutExpired:
                    pass
                for line in events:
                    if line.startswith('MAJI:'):
                        phase = line[5:].strip()
                        progress(phase)
                        tick = time.monotonic()
                if time.monotonic() - tick > 5:
                    progress(phase)
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


def crop_turns(turns, duration):
    """Intersect frame-based model output with the actual PCM support.

    Pyannote annotations describe model frames, whose edges can extend past the
    waveform. Never shift all timestamps or create speech outside the recording.
    Keep a bounded audit summary; malformed/non-finite intervals remain errors.
    """
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Durée audio invalide.')
    result = []
    audit = dict(clipped=0, discarded=0, max_before_seconds=0., max_after_seconds=0.)
    for turn in turns:
        start, end = float(turn['start']), float(turn['end'])
        if not (math.isfinite(start) and math.isfinite(end) and start < end):
            raise ValueError(f'Tour de parole invalide : début={start}, fin={end}.')
        audit['max_before_seconds'] = max(audit['max_before_seconds'], -start)
        audit['max_after_seconds'] = max(audit['max_after_seconds'], end - duration)
        first, last = max(0., start), min(duration, end)
        if first >= last:
            audit['discarded'] += 1
            continue
        if first != start or last != end:
            audit['clipped'] += 1
        result.append(dict(start=first, end=last, label=turn['label']))
    return result, audit


def diarize(store, job, python, model, device='cpu', speakers=0, cancel=None,
            progress=lambda message: None, worker=run_worker, tuning=None):
    tuning = (tuning or DiarizationOptions()).validate(speakers)
    started = time.monotonic()
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
    options = dict(model=str(model), python=str(python), device=device, speakers=speakers,
                   tuning=asdict(tuning), tracks=[],
                   engine='pyannote.audio/Community-1', grouping='per_track',
                   boundary_adjustments=[])
    run = start_run(store, job, options)
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
                response = worker(python, model.resolve(), audio, result, device, speakers, cancel, progress,
                                  tuning.for_track(track, speakers))
                turns = response['turns'] if isinstance(response, dict) else response
                options['tracks'].append(dict(
                    track=track, duration=duration,
                    groups=len({t['label'] for t in turns}),
                    effective=response.get('effective', {}) if isinstance(response, dict) else {}))
                normalized, audit = crop_turns(turns, duration)
                if audit['clipped'] or audit['discarded']:
                    options['boundary_adjustments'].append(dict(track=track, **audit))
                    progress(f"{track} : bornes audio ajustées : {audit['clipped']} tour(s), "
                             f"{audit['discarded']} hors audio ignoré(s).")
                for turn in normalized:
                    all_turns.append(dict(track=track, start=origin + turn['start'],
                                          end=origin + turn['end'], label=turn['label']))
        options['total_seconds'] = time.monotonic() - started
        with store.connect() as db:
            db.execute('UPDATE diarization_runs SET options=? WHERE id=?',
                       (json.dumps(options), run))
        check_cancel(cancel)
        return complete_run(store, run, all_turns)
    except Exception as exc:
        with store.connect() as db:
            db.execute('UPDATE diarization_runs SET status=?,error=? WHERE id=?',
                       ('cancelled' if isinstance(exc, CancelledError) else 'failed', str(exc), run))
        raise
