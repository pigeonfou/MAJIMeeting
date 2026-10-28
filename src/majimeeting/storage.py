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
            return result.rowcount

    def start_transcription(self, job, meeting_id, options):
        from dataclasses import asdict
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM meetings WHERE id=?", (meeting_id,)).fetchone():
                raise ValueError('Réunion introuvable.')
            db.execute("INSERT INTO transcription_jobs VALUES (?, ?, ?, 'running', ?, '')",
                       (job, meeting_id, datetime.now(UTC).isoformat(), json.dumps(asdict(options))))

    def add_segment(self, job, track, start, end, text):
        with self.connect() as db:
            db.execute("INSERT INTO transcript_segments(job_id,track,start,end,text) "
                       "VALUES (?, ?, ?, ?, ?)", (job, track, start, end, text))

    def finish_transcription(self, job, state, error=''):
        with self.connect() as db:
            db.execute("UPDATE transcription_jobs SET status=?,error=? WHERE id=?",
                       (state, error, job))

    def set_execution(self, job, device, compute_type, fallback_reason='', reset_segments=False):
        with self.connect() as db:
            row = db.execute('SELECT options FROM transcription_jobs WHERE id=?', (job,)).fetchone()
            if row is None:
                raise ValueError('Traitement introuvable.')
            options = json.loads(row['options'])
            options['execution'] = {'device': device, 'compute_type': compute_type,
                                    'fallback_reason': fallback_reason}
            if reset_segments:
                db.execute('DELETE FROM transcript_segments WHERE job_id=?', (job,))
            db.execute('UPDATE transcription_jobs SET options=? WHERE id=?',
                       (json.dumps(options), job))

    def transcription_jobs(self, meeting_id):
        with self.connect() as db:
            return db.execute("SELECT * FROM transcription_jobs WHERE meeting_id=? "
                              "ORDER BY rowid DESC", (meeting_id,)).fetchall()

    def segments(self, job):
        with self.connect() as db:
            return db.execute("SELECT * FROM transcript_segments WHERE job_id=? "
                              "ORDER BY start,track,id", (job,)).fetchall()

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
