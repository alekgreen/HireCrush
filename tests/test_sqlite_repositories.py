from datetime import timedelta

from app import app as flask_app
from interview_app.adapters.persistence.sqlite.repositories import (
    SQLiteFeedbackRepository,
    SQLiteQuestionRepository,
)
from interview_app.db import get_db
from interview_app.utils import iso, now_utc

from tests.support import insert_question


def _set_question_times(question_id: int, *, created_at=None, next_review_at=None) -> None:
    with flask_app.app_context():
        db = get_db()
        if created_at is not None:
            db.execute(
                "UPDATE questions SET created_at = ? WHERE id = ?",
                (iso(created_at), question_id),
            )
        if next_review_at is not None:
            db.execute(
                "UPDATE questions SET next_review_at = ? WHERE id = ?",
                (iso(next_review_at), question_id),
            )
        db.commit()


def test_question_repo_get_stats_counts_due_questions(client):
    repo = SQLiteQuestionRepository()
    due_id = insert_question("Explain CAP theorem?", topic="distributed")
    upcoming_id = insert_question("Explain ACID transactions?", topic="databases")
    now = now_utc()
    _set_question_times(due_id, next_review_at=now - timedelta(minutes=5))
    _set_question_times(upcoming_id, next_review_at=now + timedelta(days=2))

    with flask_app.app_context():
        stats = repo.get_stats()

    assert stats == {"total": 2, "due": 1}


def test_question_repo_get_due_question_respects_topic_and_exclusion(client):
    repo = SQLiteQuestionRepository()
    first_python = insert_question("What is Python GIL?", topic="python")
    second_python = insert_question("What are Python descriptors?", topic="python")
    insert_question("What is a SQL index?", topic="sql")

    now = now_utc()
    _set_question_times(first_python, next_review_at=now - timedelta(minutes=10))
    _set_question_times(second_python, next_review_at=now - timedelta(minutes=5))

    with flask_app.app_context():
        selected = repo.get_due_question(topics=["python"], randomize=False)
        skipped = repo.get_due_question(
            topics=["python"],
            randomize=False,
            exclude_question_id=first_python,
        )

    assert selected["id"] == first_python
    assert skipped["id"] == second_python
    assert skipped["topic"] == "python"


def test_question_repo_get_due_question_respects_subtopic_filter(client):
    repo = SQLiteQuestionRepository()
    k8s_id = insert_question(
        "What is a Kubernetes deployment strategy?",
        topic="devops",
        subtopic="kubernetes",
    )
    terraform_id = insert_question(
        "How does Terraform refresh work?",
        topic="devops",
        subtopic="terraform",
    )

    now = now_utc()
    _set_question_times(k8s_id, next_review_at=now - timedelta(minutes=10))
    _set_question_times(terraform_id, next_review_at=now - timedelta(minutes=5))

    with flask_app.app_context():
        selected = repo.get_due_question(
            subtopics=[("devops", "kubernetes")],
            randomize=False,
        )

    assert selected["id"] == k8s_id
    assert selected["subtopic"] == "kubernetes"


def test_question_repo_get_next_upcoming_respects_topic_filter(client):
    repo = SQLiteQuestionRepository()
    soonest_python = insert_question("How does asyncio work?", topic="python")
    later_python = insert_question("What is monkey patching?", topic="python")
    soonest_any = insert_question("What is normalization?", topic="sql")

    now = now_utc()
    _set_question_times(soonest_python, next_review_at=now + timedelta(hours=6))
    _set_question_times(later_python, next_review_at=now + timedelta(days=1))
    _set_question_times(soonest_any, next_review_at=now + timedelta(hours=2))

    with flask_app.app_context():
        upcoming_python = repo.get_next_upcoming(topics=["python"])
        upcoming_any = repo.get_next_upcoming()

    assert upcoming_python["id"] == soonest_python
    assert upcoming_any["id"] == soonest_any


def test_question_repo_get_generation_context_prioritizes_same_topic(client):
    repo = SQLiteQuestionRepository()
    base = now_utc()
    p_old = insert_question("What is inheritance?", topic="python")
    p_new = insert_question("What is composition?", topic="python")
    other = insert_question("What is a clustered index?", topic="sql")

    _set_question_times(p_old, created_at=base - timedelta(days=2))
    _set_question_times(p_new, created_at=base - timedelta(days=1))
    _set_question_times(other, created_at=base - timedelta(hours=1))

    with flask_app.app_context():
        context = repo.get_generation_context_questions("python", limit=3)

    assert context[0] == "What is composition?"
    assert context[1] == "What is inheritance?"
    assert context[2] == "What is a clustered index?"


def test_question_repo_get_generation_context_prioritizes_same_subtopic(client):
    repo = SQLiteQuestionRepository()
    base = now_utc()
    k8s_old = insert_question(
        "What is a Kubernetes pod?",
        topic="devops",
        subtopic="kubernetes",
    )
    k8s_new = insert_question(
        "How do Kubernetes services route traffic?",
        topic="devops",
        subtopic="kubernetes",
    )
    terraform = insert_question(
        "What is Terraform state?",
        topic="devops",
        subtopic="terraform",
    )
    other_topic = insert_question(
        "What is a SQL clustered index?",
        topic="sql",
    )

    _set_question_times(k8s_old, created_at=base - timedelta(days=3))
    _set_question_times(k8s_new, created_at=base - timedelta(days=2))
    _set_question_times(terraform, created_at=base - timedelta(days=1))
    _set_question_times(other_topic, created_at=base - timedelta(hours=4))

    with flask_app.app_context():
        context = repo.get_generation_context_questions("devops", subtopic="kubernetes", limit=4)

    assert context[0] == "How do Kubernetes services route traffic?"
    assert context[1] == "What is a Kubernetes pod?"
    assert context[2] == "What is Terraform state?"
    assert context[3] == "What is a SQL clustered index?"


def test_question_repo_list_topics_with_stats_returns_latest_color(client):
    repo = SQLiteQuestionRepository()
    base = now_utc()
    py_old = insert_question("What is memoization?", topic="python", topic_color="blue")
    py_new = insert_question("What is duck typing?", topic="python", topic_color="rose")
    insert_question("What is a join?", topic="sql", topic_color="emerald")

    _set_question_times(py_old, created_at=base - timedelta(days=2), next_review_at=base + timedelta(days=2))
    _set_question_times(py_new, created_at=base - timedelta(days=1), next_review_at=base - timedelta(minutes=1))

    with flask_app.app_context():
        topics = list(repo.list_topics_with_stats(limit=10))

    by_topic = {row["topic"]: row for row in topics}
    assert by_topic["python"]["total_questions"] == 2
    assert by_topic["python"]["due_questions"] == 1
    assert by_topic["python"]["topic_color"] == "rose"
    assert by_topic["sql"]["total_questions"] == 1


def test_feedback_repo_save_and_read_roundtrip(client):
    repo = SQLiteFeedbackRepository()
    question_id = insert_question("How does sharding work?", topic="databases")
    payload = {
        "score": 8,
        "feedback": "Strong explanation, add tradeoffs.",
        "improved_answer": "Sharding partitions data horizontally across nodes.",
        "strengths": ["Clear definition"],
        "gaps": ["Missing rebalancing strategy"],
    }

    with flask_app.app_context():
        repo.save_feedback(question_id, "It splits data across servers.", payload)
        latest = repo.get_latest_feedback(question_id)

    assert latest is not None
    assert latest["score"] == 8
    assert latest["feedback"].startswith("Strong explanation")
    assert latest["strengths"] == ["Clear definition"]
    assert latest["gaps"] == ["Missing rebalancing strategy"]


def test_feedback_repo_get_latest_feedback_returns_none_without_rows(client):
    repo = SQLiteFeedbackRepository()

    with flask_app.app_context():
        latest = repo.get_latest_feedback(question_id=999999)

    assert latest is None
