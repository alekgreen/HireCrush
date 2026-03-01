import sqlite3

from flask import current_app, g


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_error) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def ensure_column(table: str, column: str, definition: str) -> None:
    db = get_db()
    cols = db.execute(f"PRAGMA table_info({table})").fetchall()
    names = {row["name"] for row in cols}
    if column not in names:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            text_hash TEXT NOT NULL UNIQUE,
            topic TEXT,
            topic_color TEXT,
            created_at TEXT NOT NULL,
            last_reviewed_at TEXT,
            next_review_at TEXT NOT NULL,
            suggested_answer TEXT,
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
    ensure_column("questions", "suggested_answer", "TEXT")
    ensure_column("questions", "topic_color", "TEXT")
    db.commit()
