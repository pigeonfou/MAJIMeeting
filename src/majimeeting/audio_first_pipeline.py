"""Experimental audio -> VAD -> global voices -> Whisper -> dialogue workflow."""
import time
from dataclasses import asdict
from pathlib import Path

from majimeeting.analysis_cache import cached_stage, file_digest, fingerprint
from majimeeting.audio_preparation import PreparedBatches, prepare_meeting, stage_summary
from majimeeting.diarization import WORKER, crop_turns, run_worker
from majimeeting.diarization_options import DiarizationOptions
from majimeeting.speakers import complete_run, start_run
from majimeeting.transcription import check_cancel, transcribe_meeting


def model_fingerprint(model, cancel=None):
    paths = [p for p in model.rglob('*') if p.is_file()
             and not any(part.startswith('.') for part in p.relative_to(model).parts)]
    if not paths:
        raise ValueError('Modèle Community-1 vide.')
    return fingerprint(paths, model, cancel)


def runtime_fingerprint(python, cancel=None):
    """Include installed distribution metadata as well as the worker implementation."""
    import hashlib
    root = python.parent.parent if python.parent.name.lower() in {'scripts', 'bin'} else python.parent
    paths = {python}
    sites = [root / 'Lib/site-packages', *root.glob('lib/python*/site-packages')]
    for site in sites:
        paths.update(site.glob('*.dist-info/METADATA'))
    return dict(python=str(python.resolve()),
                files=[(str(p), file_digest(p, cancel)) for p in sorted(paths)],
                worker=hashlib.sha256(WORKER.encode()).hexdigest())


def analyze_voices(store, meeting, prepared, python, model, device, speakers, tuning,
                   cancel=None, progress=lambda _: None, worker=run_worker):
    root = store.root / meeting / 'analysis-cache/v1'
    progress('Vérification du modèle Community-1 et du runtime locaux…')
    model_key = model_fingerprint(model, cancel)
    runtime_key = runtime_fingerprint(python, cancel)
    voices = []
    for track in prepared:
        check_cancel(cancel)
        name = track['track']
        effective = tuning.for_track(name, speakers)
        inputs = dict(schema=1, audio=track['audio']['key'], has_speech=bool(track['speech']['result']['regions']),
                      model=model_key, runtime=runtime_key, device=device, tuning=effective)
        def build(stage, track=track, effective=effective):
            if not track['speech']['result']['regions']:
                return dict(turns=[], exclusive_turns=[], effective=dict(skipped_no_speech=True),
                            boundary_adjustments={})
            response = worker(python, model.resolve(), track['audio']['path'] / 'audio.wav',
                              stage / 'voices.json', device, speakers, cancel, progress, effective)
            if isinstance(response, list):
                response = dict(turns=response)
            duration = track['audio']['result']['duration']
            regular, audit = crop_turns(response['turns'], duration)
            exclusive, exclusive_audit = crop_turns(response.get('exclusive_turns', []), duration)
            result = dict(turns=regular, exclusive_turns=exclusive,
                          effective=response.get('effective', {}),
                          boundary_adjustments=dict(regular=audit, exclusive=exclusive_audit))
            # Worker logs may contain environment paths; only the bounded result is cached.
            for item in stage.iterdir():
                item.unlink()
            return result
        progress(f'{name} : diarisation globale avant Whisper…')
        stage = cached_stage(root, 'voices', inputs, build, cancel, progress)
        voices.append(dict(track=name, origin=track['audio']['result']['origin'], stage=stage))
    return voices


def process_audio_first(store, meeting, options, python, model, device, speakers, tuning,
                        preparation, cancel=None, progress=lambda _: None, *,
                        detector=None, worker=run_worker, model_factory=None,
                        pipeline_factory=None, cuda_prepare=None):
    started = time.monotonic()
    options.validate()
    preparation.validate()
    tuning = (tuning or DiarizationOptions()).validate(speakers)
    python, model = Path(python), Path(model)
    if not python.is_file() or not (model / 'config.yaml').is_file():
        raise ValueError('Préparez le runtime et Community-1 local avant le parcours audio.')
    if device not in {'cpu', 'cuda'}:
        raise ValueError('Calcul de diarisation invalide.')
    prepared = prepare_meeting(store, meeting, preparation, cancel, progress, detector)
    voices = analyze_voices(store, meeting, prepared, python, model, device, speakers, tuning,
                            cancel, progress, worker)
    # Each isolated PyTorch process has exited before CTranslate2 can load on the GPU.
    check_cancel(cancel)
    batches = PreparedBatches(prepared, voices)
    metadata = dict(mode='audio_first_v1', preparation=asdict(preparation),
                    stages=stage_summary(prepared), no_speech=not batches.has_audio,
                    voices=[dict(track=v['track'], key=v['stage']['key'],
                                 reused=v['stage']['reused'], seconds=v['stage']['seconds']) for v in voices],
                    pre_transcription_seconds=time.monotonic() - started,
                    internal_whisper_vad=False)
    progress('Analyse des voix conservée ; transcription des fenêtres de parole…')
    job = transcribe_meeting(store, meeting, options, cancel, progress,
                             model_factory=model_factory, pipeline_factory=pipeline_factory,
                             cuda_prepare=cuda_prepare, batch_source=batches, pipeline_metadata=metadata)
    attach_voices(store, job, voices, python, model, device, speakers, tuning, metadata,
                  started, cancel, progress)
    return job


def attach_voices(store, job, voices, python, model, device, speakers, tuning, metadata,
                  started, cancel=None, progress=lambda _: None, word_alignment=None, scope='complete_pipeline'):
    with store.connect() as db:
        tracks = {r['track'] for r in db.execute('SELECT DISTINCT track FROM transcript_segments '
                                               'WHERE job_id=?', (job,))}
    turns, exclusive, details = [], [], []
    for voice in voices:
        result = voice['stage']['result']
        for target, source in ((turns, result['turns']), (exclusive, result['exclusive_turns'])):
            target.extend(dict(track=voice['track'], start=voice['origin'] + t['start'],
                               end=voice['origin'] + t['end'], label=t['label']) for t in source
                          if voice['track'] in tracks)
        details.append(dict(track=voice['track'], effective=result['effective'],
                            groups=len({t['label'] for t in result['turns']}),
                            cache_key=voice['stage']['key'], reused=voice['stage']['reused']))
    analysis = dict(engine='pyannote.audio/Community-1', mode='audio_first_v1', scope=scope,
                    model=str(model), python=str(python), device=device, speakers=speakers,
                    tuning=asdict(tuning), tracks=details, exclusive_turns=exclusive,
                    segmentation_method='word_timestamps', total_seconds=time.monotonic() - started,
                    pipeline=metadata, word_alignment=word_alignment or {})
    run = start_run(store, job, analysis)
    try:
        check_cancel(cancel)
        complete_run(store, run, turns)
    except Exception as exc:
        from concurrent.futures import CancelledError
        with store.connect() as db:
            db.execute('UPDATE diarization_runs SET status=?,error=? WHERE id=?',
                       ('cancelled' if isinstance(exc, CancelledError) else 'failed', str(exc), run))
        if isinstance(exc, CancelledError):
            raise
        raise RuntimeError('Transcription sauvegardée ; reconstruction non terminée : ' + str(exc)) from exc
    progress('Dialogue reconstruit ; nommez les groupes à partir des extraits proposés.')
    return run


def reanalyze_audio_first(store, job, meeting, pipeline, python, model, device, speakers, tuning,
                          cancel=None, progress=lambda _: None, worker=run_worker,
                          whisper_model_path=None):
    from majimeeting.audio_preparation import PreparationOptions
    from majimeeting.word_alignment import align_existing
    started = time.monotonic()
    preparation = PreparationOptions(**pipeline['preparation'])
    prepared = prepare_meeting(store, meeting, preparation, cancel, progress)
    original_keys = {s['track']: s['audio_key'] for s in pipeline['stages']}
    if {p['track']: p['audio']['key'] for p in prepared} != original_keys:
        raise ValueError('Les pistes originales ont changé depuis la transcription. '
                         'Créez une nouvelle transcription avant de réattribuer les voix.')
    voices = analyze_voices(store, meeting, prepared, python, model, device, speakers, tuning,
                            cancel, progress, worker)
    turns = [dict(track=v['track'], start=v['origin'] + t['start'],
                  end=v['origin'] + t['end'], label=t['label'])
             for v in voices for t in v['stage']['result']['turns']]
    alignment = align_existing(store, job, turns, whisper_model_path, cancel, progress,
                               prepared_audio={p['track']: (p['audio']['path'] / 'audio.wav',
                                   p['audio']['result']['origin']) for p in prepared})
    metadata = dict(pipeline, stages=stage_summary(prepared),
                    voices=[dict(track=v['track'], key=v['stage']['key'],
                                 reused=v['stage']['reused'], seconds=v['stage']['seconds']) for v in voices])
    return attach_voices(store, job, voices, python, model, device, speakers, tuning, metadata,
                         started, cancel, progress, alignment, scope='voice_reanalysis')
