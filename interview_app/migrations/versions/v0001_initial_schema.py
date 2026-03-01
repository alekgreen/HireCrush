import sqlite3

VERSION = "0001_initial_schema"


def apply(db: sqlite3.Connection) -> None:
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

