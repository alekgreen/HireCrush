import sqlite3

from interview_app.migrations.helpers import ensure_column

VERSION = "0007_add_subtopic_color"


def apply(db: sqlite3.Connection) -> None:
    ensure_column(db, "questions", "subtopic_color", "TEXT")
    db.execute(
        """
        UPDATE questions
        SET subtopic_color = topic_color
        WHERE subtopic IS NOT NULL
          AND TRIM(subtopic) <> ''
          AND (subtopic_color IS NULL OR TRIM(subtopic_color) = '')
          AND topic_color IS NOT NULL
          AND TRIM(topic_color) <> ''
        """
    )
