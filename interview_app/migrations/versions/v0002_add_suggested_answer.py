import sqlite3

from interview_app.migrations.helpers import ensure_column

VERSION = "0002_add_suggested_answer"


def apply(db: sqlite3.Connection) -> None:
    ensure_column(db, "questions", "suggested_answer", "TEXT")

