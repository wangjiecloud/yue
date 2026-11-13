from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .config import Settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS uploads (
  upload_id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  mime TEXT NOT NULL,
  bytes INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY,
  upload_id TEXT,
  status TEXT NOT NULL,
  stage TEXT NOT NULL,
  progress REAL NOT NULL DEFAULT 0,
  error TEXT,
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  demo INTEGER NOT NULL DEFAULT 0,
  meta_json TEXT NOT NULL DEFAULT '{}',
  plan_path TEXT,
  video_path TEXT,
  package_path TEXT,
  subtitle_path TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
  asset_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  path TEXT NOT NULL,
  source_note TEXT NOT NULL DEFAULT '',
  rights_status TEXT NOT NULL DEFAULT '未确认',
  allowed_uses TEXT NOT NULL DEFAULT '',
  transcript TEXT NOT NULL DEFAULT '',
  language TEXT NOT NULL DEFAULT '',
  emotion TEXT NOT NULL DEFAULT '',
  duration_ms INTEGER,
  checksum TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
"""

TERMINAL = {"succeeded", "failed", "cancelled", "waitingReview"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


class JobStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.path = settings.data_dir / "yue.sqlite3"
        self._lock = threading.Lock()
        self.init()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(_SCHEMA)
            interrupted = connection.execute(
                "UPDATE jobs SET status='failed', error='interrupted by server restart', updated_at=? "
                "WHERE status='running'",
                (_now(),),
            ).rowcount
            del interrupted

    def create_upload(self, path: Path, mime: str, size: int, digest: str) -> str:
        upload_id = f"up-{uuid.uuid4().hex[:16]}"
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO uploads (upload_id, path, mime, bytes, sha256, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (upload_id, str(path), mime, size, digest, _now()),
            )
        return upload_id

    def get_upload(self, upload_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM uploads WHERE upload_id=?", (upload_id,)
            ).fetchone()
        return dict(row) if row else None

    def create_job(
        self,
        *,
        upload_id: str,
        grade: int | None,
        subject_hint: str | None,
        demo: bool,
        extra_feedback: str | None = None,
        regeneration_of: str | None = None,
    ) -> dict:
        job_id = f"job-{uuid.uuid4().hex[:16]}"
        meta = {"grade": grade, "subjectHint": subject_hint}
        if extra_feedback:
            meta["extraFeedback"] = extra_feedback
        if regeneration_of:
            meta["regenerationOf"] = regeneration_of
        now = _now()
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO jobs (job_id, upload_id, status, stage, progress, demo, meta_json, "
                "created_at, updated_at) VALUES (?, ?, 'queued', 'queued', 0, ?, ?, ?, ?)",
                (job_id, upload_id, int(demo), json.dumps(meta, ensure_ascii=False), now, now),
            )
        return self.get_job(job_id) or {}

    def get_job(self, job_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["meta"] = json.loads(data.pop("meta_json") or "{}")
        data["demo"] = bool(data["demo"])
        data["cancel_requested"] = bool(data["cancel_requested"])
        return data

    def list_jobs(self, limit: int = 50) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def update_job(self, job_id: str, **fields) -> None:
        allowed = {
            "status",
            "stage",
            "progress",
            "error",
            "plan_path",
            "video_path",
            "package_path",
            "subtitle_path",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return
        updates["updated_at"] = _now()
        assignments = ", ".join(f"{key}=?" for key in updates)
        with self._lock, self.connect() as connection:
            connection.execute(
                f"UPDATE jobs SET {assignments} WHERE job_id=?",
                (*updates.values(), job_id),
            )

    def request_cancel(self, job_id: str) -> bool:
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                "UPDATE jobs SET cancel_requested=1, updated_at=? WHERE job_id=? "
                "AND status NOT IN ('succeeded','failed','cancelled')",
                (_now(), job_id),
            )
            if not cursor.rowcount:
                return False
            row = connection.execute("SELECT status FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row and row["status"] == "queued":
                connection.execute(
                    "UPDATE jobs SET status='cancelled', stage='cancelled', updated_at=? "
                    "WHERE job_id=?",
                    (_now(), job_id),
                )
            return True

    def cancel_requested(self, job_id: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT cancel_requested FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        return bool(row and row["cancel_requested"])

    def next_queued(self) -> dict | None:
        with self._lock, self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            connection.execute(
                "UPDATE jobs SET status='running', stage='preprocess', updated_at=? WHERE job_id=?",
                (_now(), row["job_id"]),
            )
        return self.get_job(row["job_id"])

    def add_asset(self, **fields) -> None:
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO assets (asset_id, kind, path, source_note, rights_status, "
                "allowed_uses, transcript, language, emotion, duration_ms, checksum, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fields["asset_id"],
                    fields["kind"],
                    fields["path"],
                    fields.get("source_note", ""),
                    fields.get("rights_status", "未确认"),
                    fields.get("allowed_uses", ""),
                    fields.get("transcript", ""),
                    fields.get("language", ""),
                    fields.get("emotion", ""),
                    fields.get("duration_ms"),
                    fields.get("checksum", ""),
                    _now(),
                ),
            )

    def list_assets(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM assets ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]
