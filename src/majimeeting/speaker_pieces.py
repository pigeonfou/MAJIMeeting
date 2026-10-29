"""Derived speaker turns at word boundaries. Original segments never change."""
import json
import math
from datetime import UTC, datetime

from majimeeting.word_alignment import words_for


def coverage(intervals):
    total, last = 0., -math.inf
    for first, end in sorted(intervals):
        total += max(0., end - max(first, last))
        last = max(last, end)
    return total


def attribute_word(word, turns):
    start, end = word['start'], word['end']
    spans = {}
    for turn in turns:
        left, right = max(start, turn['start']), min(end, turn['end'])
        if right > left:
            spans.setdefault(turn['label'], []).append((left, right))
    scores = sorted(((coverage(values), label) for label, values in spans.items()), reverse=True)
    candidates = sorted(spans)
    # An actually simultaneous region is different from a sequential change of voice.
    for index, label in enumerate(candidates):
        for other in candidates[index + 1:]:
            overlaps = [(max(a, c), min(b, d)) for a, b in spans[label] for c, d in spans[other]
                        if min(b, d) > max(a, c)]
            if coverage(overlaps) > max(.02, (end - start) * .2):
                return '', 'overlap', candidates
    if not scores or scores[0][0] < (end - start) * .5:
        return '', 'uncovered', candidates
    if len(scores) > 1 and (scores[0][0] < (end - start) * .65 or
                           scores[0][0] - scores[1][0] < (end - start) * .2):
        return '', 'voice_boundary', candidates
    if word.get('probability') is not None and word['probability'] < .35:
        return '', 'low_alignment_confidence', candidates
    return scores[0][1], '', candidates


def split_words(segment, words, turns):
    pieces = []
    prefix = ''
    for word in words:
        if word['start'] == word['end'] and not pieces:
            prefix += word['word']
            continue
        word = dict(word)
        word['word'], prefix = prefix + word['word'], ''
        if word['start'] == word['end'] and pieces:
            pieces[-1]['text'] += word['word']
            continue
        label, reason, candidates = attribute_word(word, turns)
        if pieces and (pieces[-1]['label'], pieces[-1]['reason'], pieces[-1]['candidates']) == (
                label, reason, candidates) and word['start'] - pieces[-1]['end'] < 1.:
            pieces[-1]['end'] = word['end']
            pieces[-1]['text'] += word['word']
        else:
            pieces.append(dict(start=word['start'], end=word['end'], text=word['word'],
                               label=label, reason=reason, candidates=candidates))
    if ''.join(p['text'] for p in pieces).strip() != segment['text'].strip():
        raise ValueError('Le découpage a modifié le texte source.')
    return pieces


def write_pieces(db, run, segment, turns, label, ambiguous):
    words = words_for(db, segment['id'])
    if words:
        pieces = split_words(segment, words, turns)
    else:
        pieces = [dict(start=segment['start'], end=segment['end'], text=segment['text'],
                       label=label, reason='word_alignment_missing' if ambiguous else '',
                       candidates=sorted({t['label'] for t in turns if
                           t['start'] < segment['end'] and t['end'] > segment['start']}))]
    for piece in pieces:
        group = segment['track'] + ':' + piece['label'] if piece['label'] else ''
        candidates = [segment['track'] + ':' + name for name in piece['candidates']]
        cursor = db.execute('INSERT INTO speaker_pieces(run_id,segment_id,start,end,text,group_id,'
                   'ambiguous,reason,candidates) VALUES(?,?,?,?,?,?,?,?,?)',
                   (run, segment['id'], piece['start'], piece['end'], piece['text'], group,
                    int(bool(piece['reason'])), piece['reason'], json.dumps(candidates)))
        # Reuse a human correction only when its source span and original text
        # are unchanged. Never redistribute edited words across changed boundaries.
        previous = db.execute('''SELECT e.* FROM piece_edits e JOIN speaker_pieces p ON p.id=e.piece_id
                                 JOIN diarization_runs r ON r.id=p.run_id
                                 WHERE p.segment_id=? AND p.start=? AND p.end=? AND p.text=?
                                 AND r.status='completed' ORDER BY e.id DESC LIMIT 1''',
                              (segment['id'], piece['start'], piece['end'], piece['text'])).fetchone()
        if previous:
            db.execute('INSERT INTO piece_edits(piece_id,created,text,speaker,source_edit_id) VALUES(?,?,?,?,?)',
                       (cursor.lastrowid, datetime.now(UTC).isoformat(), previous['text'],
                        previous['speaker'], previous['id']))


def project_segments(db, rows, run):
    names = {}
    for row in db.execute('SELECT group_id,name FROM speaker_names WHERE run_id=? ORDER BY id', (run,)):
        names[row['group_id']] = row['name']
    by_segment = {}
    for row in db.execute('''SELECT p.*,e.id AS edit_id,e.text AS edit_text,e.speaker AS edit_speaker
                             FROM speaker_pieces p LEFT JOIN piece_edits e ON e.id=(
                               SELECT MAX(id) FROM piece_edits WHERE piece_id=p.id)
                             WHERE run_id=? ORDER BY p.start,p.id''', (run,)):
        by_segment.setdefault(row['segment_id'], []).append(row)
    result = []
    for source in rows:
        original = dict(source)
        pieces = by_segment.get(source['id'], [])
        if not pieces or source['manually_edited']:
            original.update(piece_id=None, speaker_reason=(
                'manual_source_correction' if source['manually_edited'] and source['speaker_ambiguous']
                else 'word_alignment_missing' if source['speaker_ambiguous'] else ''), speaker_candidates=[])
            result.append(original)
            continue
        for piece in pieces:
            row = dict(original)
            row.update(piece_id=piece['id'], start=piece['start'], end=piece['end'],
                       text=piece['text'], original_text=piece['text'],
                       corrected_text=piece['edit_text'] if piece['edit_id'] is not None else piece['text'],
                       speaker=piece['edit_speaker'] if piece['edit_id'] is not None else (
                           names.get(piece['group_id']) or piece['group_id']),
                       speaker_group=piece['group_id'], speaker_ambiguous=piece['ambiguous'],
                       speaker_reason=piece['reason'],
                       speaker_candidates=[names.get(g) or g for g in json.loads(piece['candidates'])],
                       manually_edited=piece['edit_id'] is not None)
            result.append(row)
    return sorted(result, key=lambda r: (r['start'], r['track'], r.get('piece_id') or 0))


def edit_piece(store, piece, text, speaker):
    text, speaker = text.strip(), speaker.strip()
    if not text or len(speaker) > 200:
        raise ValueError('Texte requis et nom limité à 200 caractères.')
    with store.connect() as db:
        if not db.execute("SELECT 1 FROM speaker_pieces p JOIN diarization_runs r ON r.id=p.run_id "
                          "WHERE p.id=? AND r.status='completed'", (piece,)).fetchone():
            raise ValueError('Passage terminé introuvable.')
        db.execute('INSERT INTO piece_edits(piece_id,created,text,speaker) VALUES(?,?,?,?)',
                   (piece, datetime.now(UTC).isoformat(), text, speaker))


def piece_history(store, piece):
    with store.connect() as db:
        return db.execute('SELECT * FROM piece_edits WHERE piece_id=? ORDER BY id', (piece,)).fetchall()
