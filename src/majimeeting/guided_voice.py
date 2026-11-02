"""Few-example voice proposals, using local embeddings, never Whisper decoding."""
import hashlib
import json
import math
import time
import uuid
from concurrent.futures import CancelledError
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from majimeeting.analysis_cache import cached_stage, fingerprint
from majimeeting.audio_first_pipeline import model_fingerprint, runtime_fingerprint
from majimeeting.audio_preparation import PreparationOptions, merge_intervals, prepare_meeting
from majimeeting.diarization import run_worker
from majimeeting.guided_store import references, snapshot
from majimeeting.speakers import latest_run
from majimeeting.transcription import check_cancel

EMBEDDING_WORKER = r'''
import json, os, socket, sys, wave
os.environ.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                  PYANNOTE_METRICS_ENABLED='false', OTEL_SDK_DISABLED='true')
def offline(*args, **kwargs):
    raise RuntimeError('Network disabled for guided voice embeddings')
socket.socket.connect = offline
socket.create_connection = offline
import numpy as np
import torch
from pathlib import Path
from pyannote.audio.pipelines.speaker_verification import PyannoteAudioPretrainedSpeakerEmbedding
request = json.load(open(sys.argv[1], encoding='utf-8'))
if request['device'] == 'cuda' and not torch.cuda.is_available():
    raise RuntimeError('CUDA PyTorch indisponible pour les références vocales.')
print('MAJI:Chargement des empreintes vocales locales…', flush=True)
embedding = PyannoteAudioPretrainedSpeakerEmbedding(str(Path(request['model']) / 'embedding/pytorch_model.bin'),
                                      device=torch.device(request['device']))
actual = str(embedding.device)
if request['device'] == 'cuda' and not actual.startswith('cuda'):
    raise RuntimeError('Le modèle vocal est resté sur CPU.')
if embedding.sample_rate != 16000:
    raise RuntimeError('Le modèle vocal doit accepter 16 kHz.')
windows = request['windows']
dimension = embedding.dimension
if len(windows) > 20000 or not 1 <= dimension <= 2048 or len(windows) * dimension * 4 > 128*1024**2:
    raise ValueError('Volume d’empreintes trop important ; limitez le groupe à corriger.')
vectors = np.full((len(windows), dimension), np.nan, dtype=np.float32)
buckets = {}
for index, window in enumerate(windows):
    start, end = round(window[0]*16000), round(window[1]*16000)
    if start < 0 or not 24000 <= end-start <= 320000:
        raise ValueError('Fenêtre d’empreinte invalide.')
    buckets.setdefault(end-start, []).append((index,start,end))
count = 0
with wave.open(request['audio'], 'rb') as audio:
    if audio.getframerate()!=16000 or audio.getnchannels()!=1 or audio.getsampwidth()!=2:
        raise ValueError('Audio vocal non PCM mono 16 kHz.')
    for size, items in buckets.items():
        for first in range(0,len(items),16):
            batch, indices = [], []
            for index,start,end in items[first:first+16]:
                if end > audio.getnframes():
                    raise ValueError('Fenêtre hors audio.')
                audio.setpos(start)
                samples = np.frombuffer(audio.readframes(size), dtype='<i2').astype(np.float32)/32768
                if np.sqrt(np.mean(samples*samples)) > 1e-5:
                    indices.append(index)
                    batch.append(samples)
            if batch:
                values = embedding(torch.from_numpy(np.stack(batch)[:,None,:]))
                if values.shape != (len(indices),dimension):
                    raise ValueError('Dimensions d’empreintes incompatibles.')
                vectors[indices] = values
            count += len(items[first:first+16])
            print('MAJI:Empreintes vocales '+str(count)+'/'+str(len(windows))+' sur '+actual, flush=True)
np.save(Path(request['result']).with_name('vectors.npy'), vectors, allow_pickle=False)
metadata = dict(device=actual, devices=dict(embedding=actual), count=len(windows), dimension=dimension,
                invalid=int((~np.isfinite(vectors).all(axis=1)).sum()))
if request['device']=='cuda':
    metadata.update(gpu=torch.cuda.get_device_name(), cuda_peak_allocated_mb=torch.cuda.max_memory_allocated()/1024**2)
with open(request['result'],'w',encoding='utf-8') as output:
    json.dump(metadata,output)
'''


@dataclass(frozen=True)
class GuidedOptions:
    minimum_similarity: float = .65
    minimum_margin: float = .08
    window_seconds: float = 3.

    def validate(self):
        for value, low, high in ((self.minimum_similarity, .1, .95),
                                 (self.minimum_margin, .01, .5), (self.window_seconds, 1.5, 5.)):
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError('Réglages de comparaison vocale hors limites.')
        return self


def audio_fingerprint(track, cancel=None):
    data = fingerprint(set([track / 'track.json', *track.glob('*.wav'), *track.glob('*.json')]), track, cancel)
    return hashlib.sha256(json.dumps(data).encode()).hexdigest()


def extract_vectors(python, model, audio, windows, stage, device, cancel, progress):
    response = run_worker(python, model, audio, stage / 'result.json', device, 0, cancel, progress,
                          worker_code=EMBEDDING_WORKER, extra={'windows': windows})
    for path in stage.iterdir():
        if path.name != 'vectors.npy':
            path.unlink()
    return response


def vector_stage(root, stage_name, audio, windows, identity, python, model, device,
                 cancel, progress, extractor):
    inputs = dict(schema=1, audio=audio['key'], windows=windows, identity=identity, device=device,
                  worker=hashlib.sha256(EMBEDDING_WORKER.encode()).hexdigest())
    def build(stage):
        metadata = extractor(python, model, audio['path'] / 'audio.wav', windows, stage, device, cancel, progress)
        load_vectors(stage / 'vectors.npy', len(windows))
        return metadata
    return cached_stage(root, stage_name, inputs, build, cancel, progress)


def load_vectors(path, count):
    if path.stat().st_size > 128 * 1024**2:
        raise ValueError('Fichier d’empreintes trop volumineux.')
    values = np.load(path, mmap_mode='r', allow_pickle=False)
    if values.ndim != 2 or values.shape[0] != count or not 1 <= values.shape[1] <= 2048 or values.dtype != np.float32:
        raise ValueError('Empreintes vocales invalides.')
    return values


def unit(vector):
    norm = np.linalg.norm(vector)
    return vector / norm if np.isfinite(vector).all() and math.isfinite(float(norm)) and norm > 1e-8 else None


def known_overlaps(turns, track):
    local = sorted((t for t in turns if t['track'] == track), key=lambda t: t['start'])
    overlaps = []
    for i, left in enumerate(local):
        for right in local[i+1:]:
            if right['start'] >= left['end']:
                break
            if right['label'] != left['label']:
                overlaps.append((max(left['start'], right['start']), min(left['end'], right['end'])))
    return merge_intervals(overlaps)


def intersects(first, last, spans):
    return any(a < last and b > first for a, b in spans)


def reference_windows(refs, origin, duration, overlaps):
    windows, owners, names = [], [], {}
    for ref in refs:
        if ref['start'] < origin or ref['end'] > origin + duration:
            raise ValueError('Une référence dépasse les limites de sa piste.')
        if intersects(ref['start'], ref['end'], overlaps):
            raise ValueError('Une référence traverse des paroles simultanées détectées. Choisissez un extrait isolé.')
        label = 'guide-' + hashlib.sha256(ref['name'].casefold().encode()).hexdigest()[:32]
        group = ref.get('group_id', ref['track'] + ':' + label)
        names.setdefault(group, ref['name'])
        first, last = ref['start'] - origin, ref['end'] - origin
        positions = list(np.arange(first, last - 3 + .001, 3.))
        positions.append(last - 3)
        for start in sorted(set(round(float(p), 6) for p in positions)):
            windows.append([start, start + 3.])
            owners.append(group)
    if not 2 <= len(names) <= 20:
        raise ValueError('Ajoutez des références pour au moins deux personnes distinctes sur cette piste (20 maximum).')
    return windows, owners, names


def candidate_windows(targets, origin, duration, overlaps, seconds):
    cells = set()
    for word in targets:
        if word['start'] == word['end']:
            continue
        cell = math.floor(((word['start'] + word['end']) / 2 - origin) / .75)
        cells.update((cell - 1, cell, cell + 1))
    if len(cells) > 20000:
        raise ValueError('Trop de fenêtres : choisissez un groupe plus précis à corriger.')
    windows, indices, lookup = [], {}, {}
    for cell in sorted(cells):
        center = origin + (cell + .5) * .75
        if not origin <= center <= origin + duration or intersects(center, center + .0001, overlaps):
            continue
        first, last = origin, origin + duration
        for a, b in overlaps:
            if b <= center:
                first = max(first, b)
            elif a >= center:
                last = min(last, a)
        length = min(seconds, last - first)
        if length < 1.5:
            continue
        start = min(max(first, center - length / 2), last - length)
        window = [round(start - origin, 6), round(start - origin + length, 6)]
        key = tuple(window)
        if key not in lookup:
            lookup[key] = len(windows)
            windows.append(window)
        indices[cell] = lookup[key]
    return windows, indices


def compare_vectors(candidates, exemplars, owners, names):
    profiles = {}
    warnings = []
    for group in names:
        examples = [unit(np.asarray(v)) for v, owner in zip(exemplars, owners, strict=True) if owner == group]
        examples = [v for v in examples if v is not None]
        if not examples:
            raise ValueError('Aucune empreinte exploitable pour '+names[group]+'. Choisissez des extraits audibles.')
        prototype = unit(np.mean(examples, axis=0))
        if prototype is None:
            raise ValueError('Références contradictoires pour '+names[group])
        if any(float(v @ prototype) < .4 for v in examples):
            warnings.append('Références peu cohérentes pour '+names[group]+' : vérifiez qu’elles contiennent la même voix.')
        profiles[group] = prototype
    groups = list(profiles)
    prototypes = np.stack(list(profiles.values()))
    too_close = set()
    for i, left in enumerate(groups):
        for j in range(i+1, len(groups)):
            similarity = float(prototypes[i] @ prototypes[j])
            if similarity >= .85:
                warnings.append(f"Références proches : {names[left]} / {names[groups[j]]} (cosinus {similarity:.3f}).")
            if similarity >= .98:
                warnings.append('Ces références sont presque identiques : aucune propagation entre ces personnes hors des extraits confirmés.')
                too_close.update((left, groups[j]))
    scores = []
    for vector in candidates:
        normalized = unit(np.asarray(vector))
        if normalized is None:
            scores.append(None)
            continue
        ranked = sorted(zip((normalized @ prototypes.T).tolist(), groups, strict=True), reverse=True)
        scores.append(dict(group=ranked[0][1], score=ranked[0][0], margin=ranked[0][0]-ranked[1][0],
                           candidates=[r[1] for r in ranked[:2]]))
    return scores, warnings, too_close


def choose_word(word, refs, scores, indices, origin, overlaps, options, too_close):
    center = (word['start'] + word['end']) / 2
    if intersects(word['start'], word['end'], overlaps):
        return dict(group_id='', reason='overlap', candidates=[], score=None, margin=None)
    for ref in refs:
        if ref['start'] <= word['start'] and word['end'] <= ref['end']:
            group = ref.get('group_id', ref['track'] + ':guide-' + hashlib.sha256(ref['name'].casefold().encode()).hexdigest()[:32])
            return dict(group_id=group, reason='', candidates=[group], score=None, margin=None)
    cell = math.floor((center - origin) / .75)
    current = scores[indices[cell]] if cell in indices else None
    if current is None:
        return dict(group_id='', reason='guided_no_embedding', candidates=[], score=None, margin=None)
    reason = ''
    neighbors = [scores[indices[c]] for c in (cell-1, cell+1) if c in indices and scores[indices[c]] is not None]
    matching = [s for s in neighbors if s['group']==current['group']]
    if current['group'] in too_close:
        reason = 'guided_close_references'
    elif not matching or any(s['group']!=current['group'] and s['score']>=options.minimum_similarity
                             and s['margin']>=options.minimum_margin for s in neighbors):
        reason = 'guided_transition'
    elif current['score'] < options.minimum_similarity or current['margin'] < options.minimum_margin:
        reason = 'guided_uncertain'
    elif not any(s['score'] >= options.minimum_similarity and s['margin'] >= options.minimum_margin for s in matching):
        reason = 'guided_transition'
    return dict(group_id=current['group'] if not reason else '', reason=reason,
                candidates=current['candidates'], score=current['score'], margin=current['margin'])


def coalesce(words):
    result = []
    prefix = ''
    for word in words:
        word = dict(word)
        if word['start'] == word['end'] and not result:
            prefix += word['text']
            continue
        word['text'], prefix = prefix + word['text'], ''
        if word['start'] == word['end'] and result:
            result[-1]['text'] += word['text']
            continue
        if result and all(result[-1][k] == word[k] for k in ('group_id', 'reason', 'candidates', 'target')) \
                and word['start'] - result[-1]['end'] < .75:
            result[-1]['end'] = word['end']
            result[-1]['text'] += word['text']
            for key in ('score', 'margin'):
                values = [v for v in (result[-1][key], word[key]) if v is not None]
                result[-1][key] = min(values) if values else None
        else:
            result.append(dict(word))
    return result


def propose_guided(store, job, track, scope, python, model, device, options=GuidedOptions(),
                   cancel=None, progress=lambda _: None, extractor=extract_vectors):
    started = time.monotonic()
    options.validate()
    python, model = Path(python), Path(model)
    if device not in {'cpu','cuda'} or not python.is_file() or not (model/'embedding/pytorch_model.bin').is_file():
        raise ValueError('Choisissez un runtime Python valide et Community-1 complet avec son modèle d’empreintes.')
    refs = references(store, job, track)
    with store.connect() as db:
        record = db.execute('SELECT * FROM transcription_jobs WHERE id=?', (job,)).fetchone()
        base = latest_run(db, job)
        if record is None or record['status'] != 'completed' or not base:
            raise ValueError('Choisissez une transcription et une analyse des voix terminées.')
        signature = snapshot(db, job)
        turns = [dict(r) for r in db.execute('SELECT * FROM speaker_turns WHERE run_id=?', (base,))]
        segments = [dict(r) for r in db.execute('SELECT * FROM transcript_segments WHERE job_id=? AND track=? ORDER BY start', (job,track))]
        protected = {r[0] for r in db.execute('SELECT e.segment_id FROM segment_edits e JOIN transcript_segments s '
            'ON s.id=e.segment_id WHERE s.job_id=? UNION SELECT p.segment_id FROM piece_edits e '
            'JOIN speaker_pieces p ON p.id=e.piece_id WHERE p.run_id=?', (job,base))}
        pieces = [dict(r) for r in db.execute('SELECT * FROM speaker_pieces WHERE run_id=? ORDER BY start', (base,))]
        word_rows = [dict(r) for r in db.execute('SELECT w.* FROM transcript_words w JOIN transcript_segments s '
            'ON s.id=w.segment_id WHERE s.job_id=? AND s.track=? ORDER BY w.segment_id,w.position', (job,track))]
    if '/' in track or '\\' in track or not track.startswith('track-'):
        raise ValueError('Piste invalide.')
    if len(word_rows) > 200000:
        raise ValueError('Transcription trop volumineuse pour cet aperçu.')
    pieces_by_segment = {}
    for piece in pieces:
        pieces_by_segment.setdefault(piece['segment_id'], []).append(piece)
    by_segment = {}
    for word in word_rows:
        local = [p for p in pieces_by_segment.get(word['segment_id'], []) if p['segment_id']==word['segment_id'] and p['start']<= (word['start']+word['end'])/2 <= p['end']]
        piece = local[0] if local else None
        word.update(target=word['segment_id'] not in protected and (not scope or bool(piece and piece['group_id']==scope)),
                    base_piece=piece)
        by_segment.setdefault(word['segment_id'], []).append(word)
    targets = [w for w in word_rows if w['target']]
    if not targets:
        raise ValueError('Aucun mot modifiable dans ce groupe : corrections protégées ou horodatages de mots manquants.')
    gid = uuid.uuid4().hex
    for ref in refs:
        ref['group_id'] = ref['track'] + ':guide-' + gid + '-' + hashlib.sha256(ref['name'].casefold().encode()).hexdigest()[:32]
    metadata = dict(snapshot=signature, track=track, scope=scope, python=str(python), model=str(model),
                    device=device, references=refs, protected_segments=len(protected), **asdict(options))
    with store.connect() as db:
        db.execute('INSERT INTO guided_runs VALUES(?,?,?,?,?,?,?)', (gid,job,base,datetime.now(UTC).isoformat(),
                   'running',json.dumps(metadata),''))
    try:
        progress('Préparation et vérification des copies audio pour les références…')
        preparation = PreparationOptions(**json.loads(record['options']).get('pipeline',{}).get('preparation',{}))
        prepared = prepare_meeting(store, record['meeting_id'], preparation, cancel, progress)
        selected = next(p for p in prepared if p['track']==track)
        if json.loads(record['options']).get('pipeline',{}).get('mode')=='audio_first_v1':
            original = {s['track']:s['audio_key'] for s in json.loads(record['options'])['pipeline']['stages']}
            if selected['audio']['key'] != original[track]:
                raise ValueError('Les sources ont changé depuis la transcription : créez un nouveau résultat.')
        audio = selected['audio']
        origin, duration = audio['result']['origin'], audio['result']['duration']
        overlaps = known_overlaps(turns, track)
        ref_windows, owners, names = reference_windows(refs, origin, duration, overlaps)
        windows, indices = candidate_windows(targets, origin, duration, overlaps, options.window_seconds)
        root = store.root / record['meeting_id'] / 'analysis-cache/v1'
        progress('Vérification du modèle vocal et de son runtime…')
        identity = dict(model=model_fingerprint(model,cancel), runtime=runtime_fingerprint(python,cancel))
        ref_stage = vector_stage(root,'guide-refs',audio,ref_windows,identity,python,model,device,cancel,progress,extractor)
        stage = vector_stage(root,'guide-clips',audio,windows,identity,python,model,device,cancel,progress,extractor)
        exemplar_vectors = load_vectors(ref_stage['path']/'vectors.npy',len(ref_windows))
        vectors = load_vectors(stage['path']/'vectors.npy',len(windows))
        if vectors.shape[1] != exemplar_vectors.shape[1]:
            raise ValueError('Dimensions de références et passages incompatibles.')
        scores, warnings, too_close = compare_vectors(vectors,exemplar_vectors,owners,names)
        missing = sum(s['id'] not in protected and s['id'] not in by_segment
                      and (not scope or any(p['group_id']==scope for p in pieces_by_segment.get(s['id'], [])))
                      for s in segments)
        if missing:
            warnings.append(f'{missing} passage(s) sans mots horodatés laissés inchangés : réalignez le texte existant pour les traiter.')
        proposed = []
        for segment in segments:
            check_cancel(cancel)
            words = by_segment.get(segment['id'],[])
            if not any(w['target'] for w in words):
                continue
            rows = []
            for word in words:
                if word['target']:
                    choice = choose_word(word,refs,scores,indices,origin,overlaps,options,too_close)
                else:
                    piece = word['base_piece'] or {}
                    choice = dict(group_id=piece.get('group_id',''), reason=piece.get('reason','uncovered'),
                                  candidates=json.loads(piece.get('candidates','[]')),score=None,margin=None)
                rows.append(dict(segment_id=segment['id'],start=word['start'],end=word['end'],
                                 text=word['word'],target=int(word['target']),**choice))
            if ''.join(r['text'] for r in rows).strip()!=segment['text'].strip():
                raise ValueError('Les mots ne reproduisent pas le texte source. Réalignez cette transcription.')
            proposed.extend(coalesce(rows))
        metadata.update(names=names,warnings=warnings,audio_key=audio['key'],
            audio_fingerprint=audio_fingerprint(store.root/record['meeting_id']/track,cancel),
            effective=stage['result'],clips_key=stage['key'],references_key=ref_stage['key'],
            clips_reused=stage['reused'],references_reused=ref_stage['reused'],
            total_seconds=time.monotonic()-started)
        check_cancel(cancel)
        with store.connect() as db:
            if snapshot(db,job)!=signature:
                raise ValueError('La transcription a changé pendant le calcul. Recommencez l’aperçu.')
            db.executemany('INSERT INTO guided_decisions(run_id,segment_id,start,end,text,group_id,reason,candidates,score,margin,target) '
                'VALUES(?,?,?,?,?,?,?,?,?,?,?)', [(gid,r['segment_id'],r['start'],r['end'],r['text'],r['group_id'],r['reason'],
                    json.dumps(r['candidates']),r['score'],r['margin'],r['target']) for r in proposed])
            check_cancel(cancel)
            db.execute("UPDATE guided_runs SET status='ready',options=? WHERE id=?",(json.dumps(metadata),gid))
        return gid
    except Exception as exc:
        with store.connect() as db:
            db.execute('UPDATE guided_runs SET status=?,error=? WHERE id=?',
                       ('cancelled' if isinstance(exc,CancelledError) else 'failed',str(exc),gid))
        raise
