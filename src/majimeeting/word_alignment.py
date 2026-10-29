"""Word timing evidence and non-destructive alignment of an existing transcript."""
import json
import math
from pathlib import Path


def schema(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS transcript_words (
          segment_id INTEGER NOT NULL, position INTEGER NOT NULL,
          start REAL NOT NULL,end REAL NOT NULL,word TEXT NOT NULL,probability REAL,
          PRIMARY KEY(segment_id,position));
        CREATE TABLE IF NOT EXISTS speaker_pieces (
          id INTEGER PRIMARY KEY,run_id TEXT NOT NULL,segment_id INTEGER NOT NULL,
          start REAL NOT NULL,end REAL NOT NULL,text TEXT NOT NULL,
          group_id TEXT NOT NULL,ambiguous INTEGER NOT NULL,reason TEXT NOT NULL,candidates TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS pieces_run ON speaker_pieces(run_id,segment_id);
        CREATE TABLE IF NOT EXISTS piece_edits (
          id INTEGER PRIMARY KEY,piece_id INTEGER NOT NULL,created TEXT NOT NULL,
          text TEXT NOT NULL,speaker TEXT NOT NULL,source_edit_id INTEGER);
        CREATE INDEX IF NOT EXISTS piece_edit ON piece_edits(piece_id,id);
    ''')


def save_words(db, segment, words, offset=0.):
    """Accept only monotonic, bounded words reproducing the exact source text."""
    normalized = []
    previous = segment['start']
    for word in words:
        get = word.get if isinstance(word, dict) else lambda k, default=None: getattr(word, k, default)
        try:
            start, end = float(get('start')) + offset, float(get('end')) + offset
        except (TypeError, ValueError, OverflowError):
            return False
        text = str(get('word', ''))
        probability = get('probability')
        if not (math.isfinite(start) and math.isfinite(end) and start <= end):
            return False
        start, end = max(segment['start'], start), min(segment['end'], end)
        if start < previous - .02 or end < start or not text:
            return False
        # Punctuation may have zero duration; retain it without inventing timings.
        start = max(start, previous)
        if end < start:
            return False
        if probability is not None:
            try:
                probability = float(probability)
            except (TypeError, ValueError, OverflowError):
                probability = math.nan
            if not math.isfinite(probability) or not 0 <= probability <= 1:
                probability = None
        normalized.append((segment['id'], len(normalized), start, end, text, probability))
        previous = end
    if not normalized or not any(w[2] < w[3] for w in normalized) or ''.join(w[4] for w in normalized).strip() != segment['text'].strip():
        return False
    db.execute('DELETE FROM transcript_words WHERE segment_id=?', (segment['id'],))
    db.executemany('INSERT INTO transcript_words VALUES(?,?,?,?,?,?)', normalized)
    return True


def words_for(db, segment):
    return [dict(row) for row in db.execute(
        'SELECT * FROM transcript_words WHERE segment_id=? ORDER BY position', (segment,))]


def align_text(model, tokenizer, audio, text):
    """Force-align supplied tokens with CTranslate2's attention alignment API."""
    from faster_whisper.audio import pad_or_trim
    features = model.feature_extractor(audio)
    count = min(features.shape[-1], model.feature_extractor.nb_max_frames)
    encoded = model.encode(pad_or_trim(features))
    try:
        return model.find_alignment(tokenizer, [tokenizer.encode(text)], encoded, count)[0]
    finally:
        del encoded, features


def align_existing(store, job, turns, model_path=None, cancel=None, progress=lambda _: None,
                   model_factory=None, prepared_audio=None):
    """Attention alignment of the known original text, not a second ASR decoding.

    Only segments crossing voices and lacking word evidence need this repair.
    Corrections are never replaced. Failed/unsupported alignments remain explicit.
    """
    from majimeeting.speakers import match_turns
    from majimeeting.transcription import check_cancel
    with store.connect() as db:
        options = json.loads(db.execute('SELECT options FROM transcription_jobs WHERE id=?',
                                       (job,)).fetchone()['options'])
        rows = [dict(row) for row in db.execute(
            'SELECT * FROM transcript_segments WHERE job_id=? ORDER BY start', (job,))]
        pending = [row for row in rows if not words_for(db, row['id']) and
                   match_turns(row['start'], row['end'],
                               [t for t in turns if t['track'] == row['track']])[1]]
        meeting = db.execute('SELECT meeting_id FROM transcription_jobs WHERE id=?', (job,)).fetchone()[0]
    if not pending:
        return dict(aligned=0, unresolved=0)
    path = Path(model_path or options.get('model_path', ''))
    if model_factory is None and not (path / 'config.json').is_file():
        progress('Alignement mot à mot indisponible : sélectionnez le modèle Whisper local. '
                 'Les segments concernés restent à vérifier.')
        return dict(aligned=0, unresolved=len(pending), reason='whisper_model_missing')
    if model_factory is None:
        from faster_whisper import WhisperModel
        model_factory = WhisperModel
    from faster_whisper.audio import decode_audio
    from faster_whisper.tokenizer import Tokenizer

    from majimeeting.playback import make_excerpt
    # Import only while the previous Community-1 child has already exited.
    device = options.get('execution', {}).get('device', options.get('device', 'cpu'))
    compute = options.get('execution', {}).get('compute_type', options.get('compute_type', 'int8'))
    if device == 'cuda':
        from majimeeting.cuda_runtime import prepare_cuda
        prepare_cuda(options.get('cuda_library_path', ''))
    progress(f'Alignement du texte existant sur {device}/{compute} — aucun nouveau décodage du texte…')
    model = None
    aligned = 0
    try:
        model = model_factory(str(path), device=device, compute_type=compute, local_files_only=True)
        tokenizer = Tokenizer(model.hf_tokenizer, model.model.is_multilingual,
                              task='transcribe', language=options.get('language', 'fr'))
        import tempfile
        with tempfile.TemporaryDirectory(prefix='majimeeting-align-') as temp:
            target = Path(temp) / 'excerpt.wav'
            for index, row in enumerate(pending):
                check_cancel(cancel)
                progress(f'Alignement du texte existant : {index + 1}/{len(pending)} passages…')
                duration = row['end'] - row['start']
                tokens = tokenizer.encode(row['text'])
                if duration > 30 or len(tokens) > 400:
                    continue  # never truncate text or fake a proportional allocation
                track = row['track']
                if Path(track).name != track or not track.startswith('track-'):
                    raise ValueError('Piste invalide.')
                if prepared_audio and track in prepared_audio:
                    import wave

                    import numpy as np
                    source, origin = prepared_audio[track]
                    with wave.open(str(source), 'rb') as pcm:
                        first = round((row['start'] - origin) * 16000)
                        last = round((row['end'] - origin) * 16000)
                        if first < 0 or last > pcm.getnframes() or first >= last:
                            continue
                        pcm.setpos(first)
                        audio = np.frombuffer(pcm.readframes(last - first), dtype='<i2').astype(np.float32) / 32768
                else:
                    make_excerpt(store.root / meeting / track, row['start'], row['end'], target)
                    audio = decode_audio(str(target), sampling_rate=16000)
                alignment = align_text(model, tokenizer, audio, row['text'])
                # Keep the original lexical sequence; do not run a text generator.
                with store.connect() as db:
                    aligned += int(save_words(db, row, alignment, row['start']))
                del audio
    finally:
        del model
    return dict(aligned=aligned, unresolved=len(pending) - aligned, device=device, compute_type=compute)
