"""SQLite-backed dictation history."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HistoryEntry:
    app_name: str | None
    raw_text: str
    cleaned_text: str
    mode: str
    profile: str
    duration_seconds: float | None
    model: str


@dataclass(frozen=True)
class HistoryRow:
    id: int
    created_at: str
    app_name: str | None
    raw_text: str
    cleaned_text: str
    mode: str
    profile: str
    duration_seconds: float | None
    model: str


def default_history_path(local_appdata: str | os.PathLike[str] | None = None) -> Path:
    base = Path(local_appdata) if local_appdata is not None else _default_local_appdata()
    return base / "VoiceTray" / "history.db"


class DictationHistoryStore:
    def __init__(self, db_path: str | os.PathLike[str] | None = None):
        self.db_path = Path(db_path) if db_path is not None else default_history_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def append(self, entry: HistoryEntry) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO dictations (
                    app_name,
                    raw_text,
                    cleaned_text,
                    mode,
                    profile,
                    duration_seconds,
                    model
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.app_name,
                    entry.raw_text,
                    entry.cleaned_text,
                    entry.mode,
                    entry.profile,
                    entry.duration_seconds,
                    entry.model,
                ),
            )
            return int(cursor.lastrowid)

    def list_recent(self, *, limit: int = 100) -> list[HistoryRow]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    created_at,
                    app_name,
                    raw_text,
                    cleaned_text,
                    mode,
                    profile,
                    duration_seconds,
                    model
                FROM dictations
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [HistoryRow(*row) for row in rows]

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dictations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    app_name TEXT,
                    raw_text TEXT NOT NULL,
                    cleaned_text TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    duration_seconds REAL,
                    model TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)


def _default_local_appdata() -> Path:
    configured = os.environ.get("LOCALAPPDATA")
    if configured:
        return Path(configured)
    return Path.home() / "AppData" / "Local"
