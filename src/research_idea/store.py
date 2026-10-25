"""Transactional project memory and resumable task journal."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(encode(value).encode()).hexdigest()


class Store:
    def __init__(self, project: Path, *, readonly: bool = False):
        self.project = project.resolve()
        if readonly:
            uri = (self.project / "research.sqlite3").as_uri() + "?mode=ro"
            self.db = sqlite3.connect(uri, uri=True)
            self.db.row_factory = sqlite3.Row
            # WAL readers can inspect a consistent snapshot during a run.
            self.db.execute("BEGIN")
            return
        self.project.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.project / "research.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS papers (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS evidence (id TEXT PRIMARY KEY, paper_id TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS candidates (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, stage TEXT NOT NULL, status TEXT NOT NULL,
                output TEXT, error TEXT, attempts INTEGER NOT NULL DEFAULT 0,
                started TEXT, finished TEXT, usage TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
                kind TEXT NOT NULL, payload TEXT NOT NULL
            );
        """)
        # Folder identity belongs to the project, not the launch working directory.
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO meta VALUES (?, ?)',
                ('output_folder', encode('idea-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))))

    def close(self):
        self.db.close()

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        self.set_many({key: value})

    def set_many(self, values):
        """Commit a dialogue revision and its provenance together."""
        with self.db:
            self.db.executemany("INSERT INTO meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                                [(key, encode(value)) for key, value in values.items()])

    def event(self, kind, payload):
        with self.db:
            self.db.execute("INSERT INTO events(timestamp,kind,payload) VALUES (?,?,?)", (now(), kind, encode(payload)))

    def rows(self, table):
        if table not in {"papers", "evidence", "candidates"}:
            raise ValueError("Unknown entity table")
        return [json.loads(row[0]) for row in self.db.execute(f"SELECT payload FROM {table} ORDER BY id")]

    def put(self, table, record):
        if table not in {"papers", "candidates"}:
            raise ValueError("Unknown entity table")
        with self.db:
            self.db.execute(f"INSERT INTO {table} VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (record["id"], encode(record)))

    def replace_evidence(self, paper_id, records):
        with self.db:
            self.db.execute("DELETE FROM evidence WHERE paper_id=?", (paper_id,))
            self.db.executemany("INSERT INTO evidence VALUES (?,?,?)", [(x["id"], paper_id, encode(x)) for x in records])

    def replace_candidates(self, records):
        with self.db:
            self.db.execute("DELETE FROM candidates")
            self.db.executemany("INSERT INTO candidates VALUES (?,?)", [(x["id"], encode(x)) for x in records])

    def task(self, task_id):
        row = self.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def begin_task(self, task_id, stage):
        with self.db:
            self.db.execute("""INSERT INTO tasks(id,stage,status,attempts,started) VALUES (?,?,'running',1,?)
                ON CONFLICT(id) DO UPDATE SET status='running',attempts=attempts+1,started=excluded.started,error=NULL,finished=NULL""", (task_id, stage, now()))

    def finish_task(self, task_id, output, usage):
        with self.db:
            self.db.execute("UPDATE tasks SET status='succeeded',output=?,usage=?,finished=? WHERE id=?", (encode(output), encode(usage), now(), task_id))

    def fail_task(self, task_id, error):
        with self.db:
            self.db.execute("UPDATE tasks SET status='failed',error=?,finished=? WHERE id=?", (str(error), now(), task_id))

    def interrupt_running_tasks(self):
        """Close unfinished journal entries while the caller owns the project lock."""
        with self.db:
            result = self.db.execute(
                "UPDATE tasks SET status='failed',error=?,finished=? WHERE status='running'",
                ('Interrupted: execution ended before completion; task can be resumed', now()))
        return result.rowcount

    def task_summary(self):
        return {r[0]: r[1] for r in self.db.execute("SELECT status,COUNT(*) FROM tasks GROUP BY status")}

    def recent_events(self, limit=30):
        return [{"timestamp": r[0], "kind": r[1], "payload": json.loads(r[2])} for r in self.db.execute("SELECT timestamp,kind,payload FROM events ORDER BY id DESC LIMIT ?", (limit,))]
