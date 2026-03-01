import app as app_module


def insert_question(
    text="What is polymorphism in OOP?",
    topic="python",
    suggested_answer=None,
    topic_color=None,
):
    with app_module.app.app_context():
        db = app_module.get_db()
        now = app_module.now_utc()
        db.execute(
            """
            INSERT INTO questions (
                text, text_hash, topic, topic_color, created_at, next_review_at,
                suggested_answer, repetitions, interval_days, ease_factor
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 2.5)
            """,
            (
                text,
                app_module.question_hash(text),
                topic,
                topic_color,
                app_module.iso(now),
                app_module.iso(now),
                suggested_answer,
            ),
        )
        db.commit()
        return db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

