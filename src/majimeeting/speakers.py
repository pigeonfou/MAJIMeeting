"""Versioned diarization evidence, separate from human transcript corrections."""
import json
import math
import uuid
from datetime import UTC, datetime


def schema(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS diarization_runs (
          id TEXT PRIMARY KEY, job_id TEXT NOT NULL, created TEXT NOT NULL,
          status TEXT NOT NULL, options TEXT NOT NULL, error TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS speaker_turns (
          id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, track TEXT NOT NULL,
          start REAL NOT NULL, end REAL NOT NULL, label TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS speaker_assignments (
          run_id TEXT NOT NULL, segment_id INTEGER NOT NULL, group_id TEXT NOT NULL,
          ambiguous INTEGER NOT NULL, PRIMARY KEY(run_id,segment_id));
        CREATE TABLE IF NOT EXISTS speaker_names (
          id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, group_id TEXT NOT NULL,
          name TEXT NOT NULL, created TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS diarization_job ON diarization_runs(job_id);
        CREATE INDEX IF NOT EXISTS speaker_names_group ON speaker_names(run_id,group_id,id);
    ''')


def latest_run(db, job):
    row = db.execute("SELECT id FROM diarization_runs WHERE job_id=? AND status='completed' "
                     'ORDER BY rowid DESC LIMIT 1', (job,)).fetchone()
    return row['id'] if row else ''


def start_run(store, job, options):
    run = uuid.uuid4().hex
    with store.connect() as db:
        record = db.execute('SELECT status FROM transcription_jobs WHERE id=?', (job,)).fetchone()
        if record is None or record['status'] != 'completed':
            raise ValueError('Choisissez une transcription terminée.')
        db.execute('INSERT INTO diarization_runs VALUES(?,?,?,?,?,?)',
                   (run, job, datetime.now(UTC).isoformat(), 'running', json.dumps(options), ''))
    return run


def match_turns(start, end, turns):
    """Conservative segment-level assignment; a change of voice remains ambiguous."""
    spans = {}
    for turn in turns:
        left, right = max(start, turn['start']), min(end, turn['end'])
        if right > left:
            spans.setdefault(turn['label'], []).append((left, right))
    scores = []
    for label, intervals in spans.items():
        total, last = 0, -math.inf
        for left, right in sorted(intervals):
            total += max(0, right - max(left, last))
            last = max(last, right)
        scores.append((total, label))
    scores.sort(reverse=True)
    if not scores:
        return '', False
    ambiguous = len(scores) > 1  # never conceal a second voice within the segment
    if ambiguous or scores[0][0] < (end - start) * .5:
        return '', True
    return scores[0][1], False


def complete_run(store, run, turns):
    clean = []
    for turn in turns:
        start, end = float(turn['start']), float(turn['end'])
        label, track = str(turn['label']), str(turn['track'])
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
            raise ValueError('Horodatage de locuteur invalide.')
        if not label or len(label) > 200 or not track.startswith('track-') or '/' in track or '\\' in track:
            raise ValueError('Locuteur ou piste invalide.')
        clean.append(dict(track=track, start=start, end=end, label=label))
    with store.connect() as db:
        record = db.execute('SELECT job_id,status FROM diarization_runs WHERE id=?', (run,)).fetchone()
        if record is None or record['status'] != 'running':
            raise ValueError('Analyse introuvable ou déjà terminée.')
        segments = db.execute('SELECT * FROM transcript_segments WHERE job_id=?',
                              (record['job_id'],)).fetchall()
        tracks = {row['track'] for row in segments}
        if any(t['track'] not in tracks for t in clean):
            raise ValueError('Piste étrangère à cette transcription.')
        db.executemany('INSERT INTO speaker_turns(run_id,track,start,end,label) VALUES(?,?,?,?,?)',
                       [(run, t['track'], t['start'], t['end'], t['label']) for t in clean])
        by_track = {track: [t for t in clean if t['track'] == track] for track in tracks}
        for segment in segments:
            label, ambiguous = match_turns(segment['start'], segment['end'], by_track[segment['track']])
            group = segment['track'] + ':' + label if label else ''
            db.execute('INSERT INTO speaker_assignments VALUES(?,?,?,?)',
                       (run, segment['id'], group, int(ambiguous)))
        db.execute("UPDATE diarization_runs SET status='completed' WHERE id=?", (run,))
    return run


def name_group(store, job, group, name):
    name = name.strip()
    if len(name) > 200:
        raise ValueError('Le nom est limité à 200 caractères.')
    with store.connect() as db:
        run = latest_run(db, job)
        if not group or not db.execute('SELECT 1 FROM speaker_assignments WHERE run_id=? AND group_id=?',
                                      (run, group)).fetchone():
            raise ValueError('Groupe de locuteurs introuvable.')
        db.execute('INSERT INTO speaker_names(run_id,group_id,name,created) VALUES(?,?,?,?)',
                   (run, group, name, datetime.now(UTC).isoformat()))


def history(store, job):
    with store.connect() as db:
        runs = [dict(r) for r in db.execute('SELECT * FROM diarization_runs WHERE job_id=? ORDER BY rowid', (job,))]
        for run in runs:
            run['turns'] = [dict(r) for r in db.execute('SELECT * FROM speaker_turns WHERE run_id=?', (run['id'],))]
            run['names'] = [dict(r) for r in db.execute('SELECT * FROM speaker_names WHERE run_id=? ORDER BY id', (run['id'],))]
        return runs
