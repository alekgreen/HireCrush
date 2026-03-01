import sqlite3

from flask import current_app, g
from interview_app.migrations import MIGRATIONS
from interview_app.utils import iso, now_utc


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_error) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _ensure_schema_migrations_table(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def list_known_migrations() -> list[str]:
    return [version for version, _migration_fn in MIGRATIONS]


def list_applied_migrations() -> list[tuple[str, str]]:
    db = get_db()
    _ensure_schema_migrations_table(db)
    rows = db.execute(
        "SELECT version, applied_at FROM schema_migrations ORDER BY applied_at ASC, version ASC"
    ).fetchall()
    return [(str(row["version"]), str(row["applied_at"])) for row in rows]


def list_pending_migrations() -> list[str]:
    applied_versions = {version for version, _applied_at in list_applied_migrations()}
    return [version for version in list_known_migrations() if version not in applied_versions]


def run_migrations() -> list[str]:
    db = get_db()
    _ensure_schema_migrations_table(db)
    applied_versions = {version for version, _applied_at in list_applied_migrations()}
    applied_now: list[str] = []

    for version, migration_fn in MIGRATIONS:
        if version in applied_versions:
            continue
        migration_fn(db)
        db.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, iso(now_utc())),
        )
        applied_now.append(version)

    db.commit()
    return applied_now
