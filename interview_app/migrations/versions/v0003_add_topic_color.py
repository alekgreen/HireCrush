import sqlite3

from interview_app.migrations.helpers import ensure_column

VERSION = "0003_add_topic_color"


def apply(db: sqlite3.Connection) -> None:
    ensure_column(db, "questions", "topic_color", "TEXT")

