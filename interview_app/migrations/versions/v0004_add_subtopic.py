import sqlite3

from interview_app.migrations.helpers import ensure_column

VERSION = "0004_add_subtopic"


def apply(db: sqlite3.Connection) -> None:
    ensure_column(db, "questions", "subtopic", "TEXT")
