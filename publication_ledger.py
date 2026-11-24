"""Small SQLite ledger used to avoid accidental repeated Telegram posts."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class PublicationLedger:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS publications (
                    publication_key TEXT PRIMARY KEY,
                    published_at TEXT NOT NULL,
                    telegram_message_id INTEGER
                )
                """
            )

    def was_published(self, publication_key: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM publications WHERE publication_key = ?",
                (publication_key,),
            ).fetchone()
        return row is not None

    def mark_published(self, publication_key: str, message_id: int | None) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO publications (publication_key, published_at, telegram_message_id) VALUES (?, ?, ?)",
                (publication_key, datetime.now(UTC).isoformat(), message_id),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

