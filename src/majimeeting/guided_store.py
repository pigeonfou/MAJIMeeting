"""Local references and reviewable, versioned speaker corrections."""
import hashlib
import json
import math
import uuid
from datetime import UTC, datetime

from majimeeting.speakers import latest_run
from majimeeting.transcription import check_cancel


def schema(db):
    db.executescript('''
      CREATE TABLE IF NOT EXISTS voice_references (
        id TEXT PRIMARY KEY,job_id TEXT NOT NULL,track TEXT NOT NULL,start REAL NOT NULL,
        end REAL NOT NULL,name TEXT NOT NULL,created TEXT NOT NULL,removed INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS guided_runs (
        id TEXT PRIMARY KEY,job_id TEXT NOT NULL,base_run TEXT NOT NULL,created TEXT NOT NULL,
        status TEXT NOT NULL,options TEXT NOT NULL,error TEXT NOT NULL DEFAULT '');
      CREATE TABLE IF NOT EXISTS guided_decisions (
        id INTEGER PRIMARY KEY,run_id TEXT NOT NULL,segment_id INTEGER NOT NULL,
        start REAL NOT NULL,end REAL NOT NULL,text TEXT NOT NULL,group_id TEXT NOT NULL,
        reason TEXT NOT NULL,candidates TEXT NOT NULL,score REAL,margin REAL,target INTEGER NOT NULL);
      CREATE INDEX IF NOT EXISTS guided_job ON guided_runs(job_id);
      CREATE INDEX IF NOT EXISTS guided_decision_run ON guided_decisions(run_id);
      CREATE INDEX IF NOT EXISTS voice_reference_job ON voice_references(job_id,removed);
    ''')


def references(store, job, track=None):
    with store.connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM voice_references WHERE job_id=? '
            'AND removed=0 AND (? IS NULL OR track=?) ORDER BY created,id', (job, track, track))]


def add_reference(store, job, track, start, end, name):
    name = name.strip()
    if not name or len(name) > 200:
        raise ValueError('Indiquez un nom de 1 à 200 caractères.')
    if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end and 3 <= end - start <= 20):
        raise ValueError('Choisissez un extrait propre de 3 à 20 secondes.')
    if '/' in track or '\\' in track or not track.startswith('track-'):
        raise ValueError('Piste invalide.')
    with store.connect() as db:
        record = db.execute('SELECT status FROM transcription_jobs WHERE id=?', (job,)).fetchone()
        if record is None or record['status'] != 'completed' or not db.execute(
                'SELECT 1 FROM transcript_segments WHERE job_id=? AND track=?', (job, track)).fetchone():
            raise ValueError('Choisissez une piste d’une transcription terminée.')
        if db.execute('SELECT COUNT(*) FROM voice_references WHERE job_id=? AND removed=0', (job,)).fetchone()[0] >= 60:
            raise ValueError('Limite de 60 extraits de référence par transcription.')
        others = db.execute('SELECT * FROM voice_references WHERE job_id=? AND track=? AND removed=0', (job, track))
        for other in others:
            if other['name'].casefold() != name.casefold() and other['start'] < end and other['end'] > start:
                raise ValueError('Deux personnes ne peuvent pas avoir des références audio qui se chevauchent.')
        rid = uuid.uuid4().hex
        db.execute('INSERT INTO voice_references VALUES(?,?,?,?,?,?,?,0)',
                   (rid, job, track, start, end, name, datetime.now(UTC).isoformat()))
    return rid


def remove_reference(store, job, rid):
    with store.connect() as db:
        db.execute('UPDATE voice_references SET removed=1 WHERE id=? AND job_id=?', (rid, job))


def snapshot(db, job):
    """Bind a preview to its words, active analysis, names, corrections and references."""
    run = latest_run(db, job)
    queries = [
        ('SELECT * FROM transcript_segments WHERE job_id=? ORDER BY id', (job,)),
        ('SELECT w.* FROM transcript_words w JOIN transcript_segments s ON s.id=w.segment_id '
         'WHERE s.job_id=? ORDER BY w.segment_id,w.position', (job,)),
        ('SELECT e.* FROM segment_edits e JOIN transcript_segments s ON s.id=e.segment_id '
         'WHERE s.job_id=? ORDER BY e.id', (job,)),
        ('SELECT * FROM speaker_pieces WHERE run_id=? ORDER BY id', (run,)),
        ('SELECT e.* FROM piece_edits e JOIN speaker_pieces p ON p.id=e.piece_id '
         'WHERE p.run_id=? ORDER BY e.id', (run,)),
        ('SELECT * FROM speaker_names WHERE run_id=? ORDER BY id', (run,)),
        ('SELECT * FROM speaker_turns WHERE run_id=? ORDER BY id', (run,)),
        ('SELECT * FROM voice_references WHERE job_id=? AND removed=0 ORDER BY id', (job,))]
    data = [run, *[[dict(r) for r in db.execute(q, args)] for q, args in queries]]
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def decisions(store, run):
    with store.connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM guided_decisions WHERE run_id=? ORDER BY start,id', (run,))]


def guided_history(store, job):
    with store.connect() as db:
        result = [dict(r) for r in db.execute('SELECT * FROM guided_runs WHERE job_id=? ORDER BY rowid', (job,))]
        for row in result:
            row['decisions'] = [dict(r) for r in db.execute('SELECT * FROM guided_decisions WHERE run_id=? ORDER BY id', (row['id'],))]
        return result


def _clone_pieces(db, base, run, segment):
    for piece in db.execute('SELECT * FROM speaker_pieces WHERE run_id=? AND segment_id=? ORDER BY id', (base, segment)).fetchall():
        cursor = db.execute('INSERT INTO speaker_pieces(run_id,segment_id,start,end,text,group_id,ambiguous,reason,candidates) '
            'VALUES(?,?,?,?,?,?,?,?,?)', (run, segment, piece['start'], piece['end'], piece['text'],
                piece['group_id'], piece['ambiguous'], piece['reason'], piece['candidates']))
        edit = db.execute('SELECT * FROM piece_edits WHERE piece_id=? ORDER BY id DESC LIMIT 1', (piece['id'],)).fetchone()
        if edit:
            db.execute('INSERT INTO piece_edits(piece_id,created,text,speaker,source_edit_id) VALUES(?,?,?,?,?)',
                (cursor.lastrowid, datetime.now(UTC).isoformat(), edit['text'], edit['speaker'], edit['id']))


def apply_proposals(store, run, accepted, cancel=None):
    """Single transaction: add an analysis, never rewrite source text or existing corrections."""
    accepted = set(accepted)
    from majimeeting.guided_voice import audio_fingerprint
    with store.connect() as db:
        source = db.execute('SELECT g.options,j.meeting_id FROM guided_runs g JOIN transcription_jobs j '
                            'ON j.id=g.job_id WHERE g.id=?', (run,)).fetchone()
    if source is None:
        raise ValueError('Aperçu introuvable.')
    expected = json.loads(source['options'])
    if audio_fingerprint(store.root/source['meeting_id']/expected['track'], cancel) != expected.get('audio_fingerprint'):
        raise ValueError('Les fichiers audio ont changé. Recalculez l’aperçu.')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        record = db.execute('SELECT * FROM guided_runs WHERE id=?', (run,)).fetchone()
        if record is None or record['status'] != 'ready':
            raise ValueError('Choisissez un aperçu prêt et non déjà appliqué.')
        options = json.loads(record['options'])
        if snapshot(db, record['job_id']) != options['snapshot']:
            raise ValueError('La transcription, ses références ou son analyse ont changé. Recalculez l’aperçu.')
        rows = [dict(r) for r in db.execute('SELECT * FROM guided_decisions WHERE run_id=? ORDER BY start,id', (run,))]
        valid = {r['id'] for r in rows if r['target'] and r['group_id'] and not r['reason']}
        if not accepted or not accepted <= valid:
            raise ValueError('Retenez au moins une proposition suffisamment distincte.')
        check_cancel(cancel)
        analysis = uuid.uuid4().hex
        metadata = dict(engine='guided-references/Community-1', guided_run=run, device=options['device'],
            total_seconds=options.get('total_seconds'),
            model=options['model'], python=options['python'], tracks=[dict(track=options['track'],
            effective=options.get('effective', {}))], references=options['references'],
            minimum_similarity=options['minimum_similarity'], minimum_margin=options['minimum_margin'],
            accepted=len(accepted), warnings=options.get('warnings', []))
        db.execute('INSERT INTO diarization_runs VALUES(?,?,?,?,?,?)', (analysis, record['job_id'],
                   datetime.now(UTC).isoformat(), 'completed', json.dumps(metadata), ''))
        db.execute('INSERT INTO speaker_names(run_id,group_id,name,created) '
                   'SELECT ?,group_id,name,created FROM speaker_names WHERE run_id=?', (analysis, record['base_run']))
        for group, name in options['names'].items():
            db.execute('INSERT INTO speaker_names(run_id,group_id,name,created) VALUES(?,?,?,?)',
                       (analysis, group, name, datetime.now(UTC).isoformat()))
        by_segment = {}
        for row in rows:
            by_segment.setdefault(row['segment_id'], []).append(row)
        segments = db.execute('SELECT * FROM transcript_segments WHERE job_id=? ORDER BY id', (record['job_id'],)).fetchall()
        corrected = []
        for segment in segments:
            check_cancel(cancel)
            proposed = by_segment.get(segment['id'])
            if not proposed:
                _clone_pieces(db, record['base_run'], analysis, segment['id'])
                db.execute('INSERT INTO speaker_assignments SELECT ?,segment_id,group_id,ambiguous '
                           'FROM speaker_assignments WHERE run_id=? AND segment_id=?',
                           (analysis, record['base_run'], segment['id']))
                continue
            if ''.join(r['text'] for r in proposed).strip() != segment['text'].strip():
                raise ValueError('Les propositions ne reproduisent pas le texte source.')
            groups = set()
            uncertain = False
            for row in proposed:
                group, reason = row['group_id'], row['reason']
                if row['target']:
                    if row['id'] not in accepted:
                        group = ''
                        reason = reason or 'guided_unselected'
                    if group:
                        corrected.append(dict(track=options['track'], start=row['start'], end=row['end'],
                                              label=group.split(':', 1)[1]))
                groups.add(group)
                uncertain |= bool(reason)
                db.execute('INSERT INTO speaker_pieces(run_id,segment_id,start,end,text,group_id,ambiguous,reason,candidates) '
                    'VALUES(?,?,?,?,?,?,?,?,?)', (analysis, segment['id'], row['start'], row['end'], row['text'],
                    group, int(bool(reason)), reason, row['candidates']))
            group = next(iter(groups)) if len(groups) == 1 else ''
            db.execute('INSERT INTO speaker_assignments VALUES(?,?,?,?)',
                       (analysis, segment['id'], group, int(uncertain or len(groups) > 1)))
        # Remove old coarse labels only on spans confidently replaced; retain true overlaps.
        turns = [dict(r) for r in db.execute('SELECT * FROM speaker_turns WHERE run_id=?', (record['base_run'],))]
        for turn in turns:
            check_cancel(cancel)
            spans = [(turn['start'], turn['end'])]
            for item in corrected:
                if item['track'] != turn['track']:
                    continue
                spans = [(a, b) for first, last in spans for a, b in (
                    (first, min(last, item['start'])), (max(first, item['end']), last)) if b > a]
            for first, last in spans:
                db.execute('INSERT INTO speaker_turns(run_id,track,start,end,label) VALUES(?,?,?,?,?)',
                           (analysis, turn['track'], first, last, turn['label']))
        db.executemany('INSERT INTO speaker_turns(run_id,track,start,end,label) VALUES(?,?,?,?,?)',
                       [(analysis, t['track'], t['start'], t['end'], t['label']) for t in corrected])
        check_cancel(cancel)
        db.execute('INSERT OR REPLACE INTO diarization_selection VALUES(?,?)', (record['job_id'], analysis))
        options['applied_analysis'] = analysis
        options['accepted_decisions'] = sorted(accepted)
        db.execute("UPDATE guided_runs SET status='applied',options=? WHERE id=?", (json.dumps(options), run))
    return analysis
