from collections.abc import Callable
import sqlite3

from flask import current_app, g
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


def _ensure_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    cols = db.execute(f"PRAGMA table_info({table})").fetchall()
    names = {row["name"] for row in cols}
    if column not in names:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _apply_migration_0001_initial_schema(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            text_hash TEXT NOT NULL UNIQUE,
            topic TEXT,
            created_at TEXT NOT NULL,
            last_reviewed_at TEXT,
            next_review_at TEXT NOT NULL,
            repetitions INTEGER NOT NULL DEFAULT 0,
            interval_days INTEGER NOT NULL DEFAULT 0,
            ease_factor REAL NOT NULL DEFAULT 2.5
        );

        CREATE TABLE IF NOT EXISTS review_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL,
            old_interval_days INTEGER NOT NULL,
            new_interval_days INTEGER NOT NULL,
            old_ease_factor REAL NOT NULL,
            new_ease_factor REAL NOT NULL,
            FOREIGN KEY (question_id) REFERENCES questions(id)
        );

        CREATE TABLE IF NOT EXISTS review_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            user_answer TEXT NOT NULL,
            score INTEGER NOT NULL,
            feedback TEXT NOT NULL,
            improved_answer TEXT NOT NULL,
            strengths_json TEXT,
            gaps_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (question_id) REFERENCES questions(id)
        );
        """
    )


def _apply_migration_0002_add_suggested_answer(db: sqlite3.Connection) -> None:
    _ensure_column(db, "questions", "suggested_answer", "TEXT")


def _apply_migration_0003_add_topic_color(db: sqlite3.Connection) -> None:
    _ensure_column(db, "questions", "topic_color", "TEXT")


MIGRATIONS: tuple[tuple[str, Callable[[sqlite3.Connection], None]], ...] = (
    ("0001_initial_schema", _apply_migration_0001_initial_schema),
    ("0002_add_suggested_answer", _apply_migration_0002_add_suggested_answer),
    ("0003_add_topic_color", _apply_migration_0003_add_topic_color),
)


def run_migrations() -> list[str]:
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    applied_rows = db.execute("SELECT version FROM schema_migrations").fetchall()
    applied_versions = {str(row["version"]) for row in applied_rows}
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


def init_db() -> None:
    # Backward-compatible alias used by tests and older callers.
    run_migrations()
