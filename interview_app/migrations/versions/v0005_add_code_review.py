import sqlite3

from interview_app.migrations.helpers import ensure_column

VERSION = "0005_add_code_review"


def apply(db: sqlite3.Connection) -> None:
    ensure_column(db, "questions", "question_type", "TEXT NOT NULL DEFAULT 'theory'")
    ensure_column(db, "questions", "code_snippet", "TEXT")
    ensure_column(db, "questions", "code_language", "TEXT")
