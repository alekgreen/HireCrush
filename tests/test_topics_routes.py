from datetime import datetime, timezone

from app import app as flask_app
from interview_app.db import get_db
from interview_app.utils import format_datetime, iso

from tests.support import insert_question


def test_topics_route_lists_topic_cards(client):
    insert_question("Explain Python decorators.", topic="python", topic_color="emerald")
    insert_question("What is a SQL index?", topic="sql", topic_color="rose")

    res = client.get("/topics")
    body = res.data.decode("utf-8")

    assert res.status_code == 200
    assert "Topics" in body
    assert "python" in body
    assert "sql" in body
    assert "Open topic" in body


def test_topics_route_detail_filters_by_topic(client):
    insert_question("Explain Python decorators.", topic="python")
    insert_question("What is a SQL index?", topic="sql")

    res = client.get("/topics?topic=python")
    body = res.data.decode("utf-8")

    assert res.status_code == 200
    assert "Viewing questions for this topic." in body
    assert "Explain Python decorators." in body
    assert "What is a SQL index?" not in body


def test_topics_route_detail_formats_next_review_datetime(client):
    question_id = insert_question("Explain event sourcing.", topic="python")
    dt = datetime(2026, 3, 1, 16, 11, 1, tzinfo=timezone.utc)

    with flask_app.app_context():
        db = get_db()
        db.execute(
            "UPDATE questions SET next_review_at = ? WHERE id = ?",
            (iso(dt), question_id),
        )
        db.commit()

    res = client.get("/topics?topic=python")
    body = res.data.decode("utf-8")

    assert res.status_code == 200
    assert f"Next review: {format_datetime(iso(dt))}" in body
    assert "2026-03-01T16:11:01+00:00" not in body
