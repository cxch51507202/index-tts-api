from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    sequence INTEGER,
                    status TEXT NOT NULL,
                    voice TEXT NOT NULL,
                    text TEXT NOT NULL,
                    settings TEXT NOT NULL,
                    output_path TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT
                )
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(tasks)").fetchall()}
            if "sequence" not in columns:
                db.execute("ALTER TABLE tasks ADD COLUMN sequence INTEGER")
            db.execute("UPDATE tasks SET sequence=rowid WHERE sequence IS NULL")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_sequence ON tasks(sequence)")
            db.execute("UPDATE tasks SET status='failed', error='service restarted during generation', completed_at=? WHERE status IN ('queued','running')", (utc_now(),))

    def create(self, task_id: str, voice: str, text: str, settings: dict[str, Any], output_path: str) -> dict[str, Any]:
        created_at = utc_now()
        with self._lock, self._connect() as db:
            sequence = db.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM tasks").fetchone()[0]
            db.execute("INSERT INTO tasks (id,sequence,status,voice,text,settings,output_path,created_at) VALUES (?,?,?,?,?,?,?,?)",
                       (task_id, sequence, "queued", voice, text, json.dumps(settings), output_path, created_at))
        return self.get(task_id)

    def update(self, task_id: str, **values: Any) -> None:
        if not values:
            return
        assignments = ", ".join(f"{key}=?" for key in values)
        with self._lock, self._connect() as db:
            db.execute(f"UPDATE tasks SET {assignments} WHERE id=?", (*values.values(), task_id))

    def get(self, task_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        result = dict(row)
        result["settings"] = json.loads(result["settings"])
        return result

    def counts(self) -> dict[str, int]:
        with self._connect() as db:
            rows = db.execute("SELECT status, COUNT(*) AS count FROM tasks GROUP BY status").fetchall()
        return {row["status"]: row["count"] for row in rows}

    def cleanup(self, retention_days: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT id, output_path FROM tasks WHERE completed_at IS NOT NULL AND completed_at < ?",
                (cutoff,),
            ).fetchall()
            for row in rows:
                if row["output_path"]:
                    Path(row["output_path"]).unlink(missing_ok=True)
            db.execute("DELETE FROM tasks WHERE completed_at IS NOT NULL AND completed_at < ?", (cutoff,))
        return len(rows)
