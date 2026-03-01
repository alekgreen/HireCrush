from collections.abc import Callable
from typing import Any

from interview_app.db import get_db
from interview_app.utils import iso, now_utc


class SQLiteSettingsRepository:
    def __init__(
        self,
        *,
        get_db_fn: Callable[..., Any] = get_db,
        now_utc_fn: Callable[..., Any] = now_utc,
        iso_fn: Callable[..., str] = iso,
    ):
        self._get_db = get_db_fn
        self._now_utc = now_utc_fn
        self._iso = iso_fn

    def _ensure_table(self) -> None:
        db = self._get_db()
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        db.commit()

    def get_value(self, key: str) -> str | None:
        self._ensure_table()
        db = self._get_db()
        row = db.execute(
            """
            SELECT value
            FROM app_settings
            WHERE key = ?
            LIMIT 1
            """,
            (key,),
        ).fetchone()
        if row is None:
            return None
        value = str(row["value"]).strip()
        return value or None

    def set_value(self, key: str, value: str) -> None:
        self._ensure_table()
        db = self._get_db()
        db.execute(
            """
            INSERT INTO app_settings(key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value, self._iso(self._now_utc())),
        )
        db.commit()
