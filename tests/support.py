from app import app as flask_app
from interview_app.db import get_db
from interview_app.utils import iso, now_utc, question_hash


def insert_question(
    text="What is polymorphism in OOP?",
    topic="python",
    subtopic=None,
    suggested_answer=None,
    topic_color=None,
    subtopic_color=None,
):
    with flask_app.app_context():
        db = get_db()
        now = now_utc()
        db.execute(
            """
            INSERT INTO questions (
                text, text_hash, topic, subtopic, topic_color, subtopic_color, created_at, next_review_at,
                suggested_answer, repetitions, interval_days, ease_factor
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 2.5)
            """,
            (
                text,
                question_hash(text),
                topic,
                subtopic,
                topic_color,
                subtopic_color,
                iso(now),
                iso(now),
                suggested_answer,
            ),
        )
        db.commit()
        return db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
