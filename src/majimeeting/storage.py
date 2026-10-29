"""Local meeting catalogue and atomically committed, bounded-size WAV fragments."""
import json
import os
import sqlite3
import uuid
import wave
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


class MeetingStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS meetings (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, created TEXT NOT NULL,
                status TEXT NOT NULL, error TEXT NOT NULL DEFAULT '')""")
            db.execute("""CREATE TABLE IF NOT EXISTS transcription_jobs (
                id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL, created TEXT NOT NULL,
                status TEXT NOT NULL, options TEXT NOT NULL, error TEXT NOT NULL DEFAULT '')""")
            db.execute("""CREATE TABLE IF NOT EXISTS transcript_segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                track TEXT NOT NULL, start REAL NOT NULL, end REAL NOT NULL, text TEXT NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS segments_job ON transcript_segments(job_id)")
            db.execute("""CREATE TABLE IF NOT EXISTS transcription_warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                track TEXT NOT NULL, batch_offset REAL NOT NULL, raw_start TEXT NOT NULL,
                raw_end TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL)""")
            db.execute('CREATE INDEX IF NOT EXISTS warnings_job ON transcription_warnings(job_id)')
            db.execute('''CREATE TABLE IF NOT EXISTS segment_edits (
                id INTEGER PRIMARY KEY AUTOINCREMENT, segment_id INTEGER NOT NULL,
                created TEXT NOT NULL, text TEXT NOT NULL, speaker TEXT NOT NULL)''')
            db.execute('CREATE INDEX IF NOT EXISTS edits_segment ON segment_edits(segment_id,id)')
            from majimeeting.speakers import schema
            schema(db)
            from majimeeting.word_alignment import schema as word_schema
            word_schema(db)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / "meetings.sqlite3", timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, title):
        if not title.strip():
            raise ValueError("Le titre est obligatoire.")
        meeting_id = uuid.uuid4().hex
        folder = self.root / meeting_id
        folder.mkdir()
        with self.connect() as db:
            db.execute("INSERT INTO meetings VALUES (?, ?, ?, 'recording', '')",
                       (meeting_id, title.strip(), datetime.now(UTC).isoformat()))
        return meeting_id

    def finish(self, meeting_id, status, error=""):
        if status not in {"completed", "interrupted", "failed"}:
            raise ValueError("Invalid meeting status")
        with self.connect() as db:
            db.execute("UPDATE meetings SET status=?, error=? WHERE id=?",
                       (status, error, meeting_id))

    def recover(self):
        # Call once at application startup, before creating any capture session.
        with self.connect() as db:
            result = db.execute("UPDATE meetings SET status='interrupted' "
                                "WHERE status='recording'")
            db.execute("UPDATE transcription_jobs SET status='interrupted' WHERE status='running'")
            db.execute("UPDATE diarization_runs SET status='interrupted' WHERE status='running'")
            return result.rowcount

    def start_transcription(self, job, meeting_id, options):
        from dataclasses import asdict
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM meetings WHERE id=?", (meeting_id,)).fetchone():
                raise ValueError('Réunion introuvable.')
            db.execute("INSERT INTO transcription_jobs VALUES (?, ?, ?, 'running', ?, '')",
                       (job, meeting_id, datetime.now(UTC).isoformat(), json.dumps(asdict(options))))

    def add_segment(self, job, track, start, end, text, words=None, word_offset=0.):
        with self.connect() as db:
            cursor = db.execute("INSERT INTO transcript_segments(job_id,track,start,end,text) "
                                "VALUES (?, ?, ?, ?, ?)", (job, track, start, end, text))
            if words:
                from majimeeting.word_alignment import save_words
                save_words(db, dict(id=cursor.lastrowid, start=start, end=end, text=text), words,
                           word_offset)
            return cursor.lastrowid

    def finish_transcription(self, job, state, error=''):
        with self.connect() as db:
            db.execute("UPDATE transcription_jobs SET status=?,error=? WHERE id=?",
                       (state, error, job))

    def set_execution(self, job, device, compute_type, fallback_reason='', reset_segments=False,
                      batched=False, batch_size=1, beam_size=5, flash_attention=False,
                      gpu_workers=1, window_seconds=300):
        with self.connect() as db:
            row = db.execute('SELECT options FROM transcription_jobs WHERE id=?', (job,)).fetchone()
            if row is None:
                raise ValueError('Traitement introuvable.')
            options = json.loads(row['options'])
            options['execution'] = {'device': device, 'compute_type': compute_type,
                                    'fallback_reason': fallback_reason, 'batched': batched,
                                    'batch_size': batch_size, 'beam_size': beam_size,
                                    'flash_attention': flash_attention, 'gpu_workers': gpu_workers,
                                    'window_seconds': window_seconds, 'word_timestamps': True}
            if reset_segments:
                db.execute('DELETE FROM transcript_words WHERE segment_id IN '
                           '(SELECT id FROM transcript_segments WHERE job_id=?)', (job,))
                db.execute('DELETE FROM transcript_segments WHERE job_id=?', (job,))
                db.execute('DELETE FROM transcription_warnings WHERE job_id=?', (job,))
            db.execute('UPDATE transcription_jobs SET options=? WHERE id=?',
                       (json.dumps(options), job))

    def set_transcription_metrics(self, job, metrics):
        with self.connect() as db:
            row = db.execute('SELECT options FROM transcription_jobs WHERE id=?', (job,)).fetchone()
            options = json.loads(row['options'])
            options['metrics'] = metrics
            db.execute('UPDATE transcription_jobs SET options=? WHERE id=?',
                       (json.dumps(options), job))

    def add_transcription_warning(self, job, track, offset, start, end, kind, text):
        with self.connect() as db:
            db.execute('INSERT INTO transcription_warnings '
                       '(job_id,track,batch_offset,raw_start,raw_end,kind,text) VALUES (?,?,?,?,?,?,?)',
                       (job, track, offset, str(start), str(end), kind, text))

    def warning_counts(self, job):
        with self.connect() as db:
            return {row['kind']: row['count'] for row in db.execute(
                'SELECT kind,COUNT(*) AS count FROM transcription_warnings WHERE job_id=? '
                'GROUP BY kind', (job,))}

    def transcription_warnings(self, job, limit=None):
        with self.connect() as db:
            return db.execute('SELECT * FROM transcription_warnings WHERE job_id=? ORDER BY id '
                              'LIMIT ?', (job, -1 if limit is None else limit)).fetchall()

    def transcription_jobs(self, meeting_id):
        with self.connect() as db:
            return db.execute("SELECT * FROM transcription_jobs WHERE meeting_id=? "
                              "ORDER BY rowid DESC", (meeting_id,)).fetchall()

    def segments(self, job):
        from majimeeting.speakers import latest_run
        with self.connect() as db:
            run = latest_run(db, job)
            rows = db.execute('''SELECT s.*, s.text AS original_text,
                              COALESCE(e.text,s.text) AS corrected_text,
                              CASE WHEN e.id IS NOT NULL THEN e.speaker
                                   ELSE COALESCE(NULLIF(n.name,''),a.group_id,'') END AS speaker,
                              COALESCE(a.group_id,'') AS speaker_group,
                              COALESCE(a.ambiguous,0) AS speaker_ambiguous,
                              e.id IS NOT NULL AS manually_edited
                              FROM transcript_segments s
                              LEFT JOIN segment_edits e ON e.id=(
                                  SELECT MAX(id) FROM segment_edits WHERE segment_id=s.id)
                              LEFT JOIN speaker_assignments a ON a.segment_id=s.id AND a.run_id=?
                              LEFT JOIN speaker_names n ON n.id=(
                                  SELECT MAX(id) FROM speaker_names
                                  WHERE run_id=a.run_id AND group_id=a.group_id)
                              WHERE s.job_id=? ORDER BY s.start,s.track,s.id''', (run, job)).fetchall()
            from majimeeting.speaker_pieces import project_segments
            return project_segments(db, rows, run)

    def edit_segment(self, segment_id, text, speaker):
        text, speaker = text.strip(), speaker.strip()
        if not text:
            raise ValueError('Le texte ne peut pas être vide.')
        if len(speaker) > 200:
            raise ValueError('Le nom est limité à 200 caractères.')
        with self.connect() as db:
            row = db.execute('''SELECT j.status FROM transcript_segments s
                              JOIN transcription_jobs j ON j.id=s.job_id WHERE s.id=?''',
                             (segment_id,)).fetchone()
            if row is None:
                raise ValueError('Segment introuvable.')
            if row['status'] == 'running':
                raise ValueError('Attendez la fin du traitement avant de corriger.')
            db.execute('INSERT INTO segment_edits(segment_id,created,text,speaker) VALUES(?,?,?,?)',
                       (segment_id, datetime.now(UTC).isoformat(), text, speaker))

    def segment_history(self, segment_id):
        with self.connect() as db:
            return db.execute('SELECT * FROM segment_edits WHERE segment_id=? ORDER BY id',
                              (segment_id,)).fetchall()

    def list(self):
        with self.connect() as db:
            return db.execute("SELECT * FROM meetings ORDER BY created DESC").fetchall()


class FragmentWriter:
    """Each committed WAV is self-contained; no meeting-length in-memory buffers."""
    def __init__(self, folder, rate, channels, source):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=False)
        self.rate, self.channels = rate, channels
        self.frames = 0
        self.index = 0
        self.buffer = bytearray()
        self.offset = None
        self.chunk_bytes = rate * channels * 2
        metadata = {"rate": rate, "channels": channels, "sample_width": 2, "source": source}
        self._atomic("track.json", json.dumps(metadata, ensure_ascii=False).encode())

    def _atomic(self, name, data):
        temp = self.folder / (name + ".part")
        with temp.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, self.folder / name)

    def write(self, data, offset):
        if len(data) % (self.channels * 2):
            raise ValueError("Incomplete PCM frame")
        if self.offset is None:
            self.offset = offset
        self.buffer.extend(data)
        while len(self.buffer) >= self.chunk_bytes:
            self._commit(bytes(self.buffer[:self.chunk_bytes]))
            del self.buffer[:self.chunk_bytes]

    def _commit(self, data):
        import io
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(self.channels)
            wav.setsampwidth(2)
            wav.setframerate(self.rate)
            wav.writeframes(data)
        name = f"{self.index:08d}"
        # Timing precedes WAV: a committed WAV always has timing metadata.
        timing = {"start_seconds": self.offset + self.frames / self.rate,
                  "frames": len(data) // (self.channels * 2)}
        self._atomic(name + ".json", json.dumps(timing).encode())
        self._atomic(name + ".wav", output.getvalue())
        self.frames += timing["frames"]
        self.index += 1

    def close(self):
        if self.buffer:
            self._commit(bytes(self.buffer))
            self.buffer.clear()


def export_track(folder, destination):
    """Stream committed fragments without loading the entire recording."""
    folder, destination = Path(folder), Path(destination)
    info = json.loads((folder / "track.json").read_text(encoding="utf-8"))
    fragments = sorted(folder.glob("*.wav"))
    if not fragments:
        raise ValueError("Aucun fragment audio récupérable.")
    frames = sum(json.loads(p.with_suffix(".json").read_text())["frames"] for p in fragments)
    if frames * info["channels"] * 2 > 0xFFFFFFFF - 36:
        raise ValueError("La piste dépasse 4 Go : conservez les fragments WAV séparés.")
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with wave.open(str(temporary), "wb") as output:
            output.setnchannels(info["channels"])
            output.setsampwidth(2)
            output.setframerate(info["rate"])
            for path in fragments:
                with wave.open(str(path), "rb") as fragment:
                    while block := fragment.readframes(65536):
                        output.writeframesraw(block)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
