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


def test_topics_route_detail_filters_by_subtopic(client):
    insert_question("How do Kubernetes pods get scheduled?", topic="devops", subtopic="kubernetes")
    insert_question("What is Terraform state locking?", topic="devops", subtopic="terraform")

    res = client.get("/topics?topic=devops&subtopic=kubernetes")
    body = res.data.decode("utf-8")

    assert res.status_code == 200
    assert "Viewing questions for this topic and subtopic." in body
    assert "How do Kubernetes pods get scheduled?" in body
    assert "What is Terraform state locking?" not in body


def test_questions_page_renders_topic_and_subtopic_with_different_colors(client):
    insert_question(
        "How do Kubernetes pods get scheduled?",
        topic="devops",
        subtopic="kubernetes",
        topic_color="blue",
        subtopic_color="rose",
    )

    res = client.get("/questions")
    body = res.data.decode("utf-8")

    assert res.status_code == 200
    assert "--topic-text: #1d4ed8" in body
    assert "--topic-text: #be123c" in body


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


def test_topics_route_can_rename_topic(client):
    insert_question("Explain Python decorators.", topic="python")

    response = client.post(
        "/topics/edit",
        data={"topic": "python", "new_topic": "python-core", "next": "/topics?topic=python"},
        follow_redirects=True,
    )
    body = response.data.decode("utf-8")

    assert response.status_code == 200
    assert "Renamed topic for 1 question(s)." in body
    assert "python-core" in body


def test_topics_route_can_update_topic_color(client):
    insert_question("Explain Python decorators.", topic="python", topic_color="blue")

    response = client.post(
        "/topics/edit",
        data={"topic": "python", "new_topic": "python", "topic_color": "emerald", "next": "/topics?topic=python"},
        follow_redirects=True,
    )
    body = response.data.decode("utf-8")

    assert response.status_code == 200
    assert "Updated topic color for 1 question(s)." in body


def test_topics_route_can_rename_and_delete_subtopic(client):
    insert_question("How do Kubernetes pods get scheduled?", topic="devops", subtopic="kubernetes")

    rename_response = client.post(
        "/subtopics/edit",
        data={
            "topic": "devops",
            "subtopic": "kubernetes",
            "new_subtopic": "orchestration",
            "next": "/topics?topic=devops&subtopic=kubernetes",
        },
        follow_redirects=True,
    )
    rename_body = rename_response.data.decode("utf-8")
    assert rename_response.status_code == 200
    assert "Renamed subtopic for 1 question(s)." in rename_body
    assert "orchestration" in rename_body

    delete_response = client.post(
        "/subtopics/delete",
        data={
            "topic": "devops",
            "subtopic": "orchestration",
            "next": "/topics?topic=devops&subtopic=orchestration",
        },
        follow_redirects=True,
    )
    delete_body = delete_response.data.decode("utf-8")
    assert delete_response.status_code == 200
    assert "Deleted 1 question(s) from subtopic." in delete_body
    assert "No questions found for this selection." in delete_body


def test_topics_route_can_update_subtopic_color(client):
    insert_question(
        "How do Kubernetes pods get scheduled?",
        topic="devops",
        subtopic="kubernetes",
        topic_color="blue",
        subtopic_color="blue",
    )

    response = client.post(
        "/subtopics/edit",
        data={
            "topic": "devops",
            "subtopic": "kubernetes",
            "new_subtopic": "kubernetes",
            "subtopic_color": "rose",
            "next": "/topics?topic=devops&subtopic=kubernetes",
        },
        follow_redirects=True,
    )
    body = response.data.decode("utf-8")

    assert response.status_code == 200
    assert "Updated subtopic color for 1 question(s)." in body


def test_topics_route_can_edit_and_delete_question(client):
    question_id = insert_question("Explain Python decorators.", topic="python")

    edit_response = client.post(
        f"/questions/{question_id}/edit",
        data={
            "text": "Explain Python decorators with practical use cases.",
            "topic": "python",
            "subtopic": "metaprogramming",
            "next": "/topics?topic=python",
        },
        follow_redirects=True,
    )
    edit_body = edit_response.data.decode("utf-8")
    assert edit_response.status_code == 200
    assert "Question updated." in edit_body
    assert "Explain Python decorators with practical use cases." in edit_body

    delete_response = client.post(
        f"/questions/{question_id}/delete",
        data={"next": "/topics?topic=python"},
        follow_redirects=True,
    )
    delete_body = delete_response.data.decode("utf-8")
    assert delete_response.status_code == 200
    assert "Question deleted." in delete_body
    assert "No questions found for this selection." in delete_body
