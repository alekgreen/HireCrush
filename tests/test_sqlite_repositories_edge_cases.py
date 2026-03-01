from datetime import timedelta

from app import app as flask_app
from interview_app.adapters.persistence.sqlite.repositories import (
    SQLiteFeedbackRepository,
    SQLiteQuestionRepository,
)
from interview_app.db import get_db
from interview_app.utils import iso, now_utc

from tests.support import insert_question


def _set_question_created_at(question_id: int, created_at) -> None:
    with flask_app.app_context():
        db = get_db()
        db.execute(
            "UPDATE questions SET created_at = ? WHERE id = ?",
            (iso(created_at), question_id),
        )
        db.commit()


def _set_question_next_review_at(question_id: int, next_review_at) -> None:
    with flask_app.app_context():
        db = get_db()
        db.execute(
            "UPDATE questions SET next_review_at = ? WHERE id = ?",
            (iso(next_review_at), question_id),
        )
        db.commit()


def _insert_feedback_row(
    *,
    question_id: int,
    created_at: str,
    user_answer: str = "sample",
    score: int = 5,
    feedback: str = "feedback",
    improved_answer: str = "improved",
    strengths_json: str = "[]",
    gaps_json: str = "[]",
) -> None:
    with flask_app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO review_feedback (
                question_id, user_answer, score, feedback, improved_answer,
                strengths_json, gaps_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                question_id,
                user_answer,
                score,
                feedback,
                improved_answer,
                strengths_json,
                gaps_json,
                created_at,
            ),
        )
        db.commit()


def test_list_questions_by_topic_is_case_insensitive_and_empty_topic_returns_none(client):
    repo = SQLiteQuestionRepository()
    insert_question("Explain Python dict internals?", topic="Python")
    insert_question("What are Python generators?", topic="PYTHON")
    insert_question("Explain SQL indexes?", topic="sql")

    with flask_app.app_context():
        rows = list(repo.list_questions_by_topic("python"))
        empty = repo.list_questions_by_topic("   ")

    assert len(rows) == 2
    assert all(str(row["topic"]).lower() == "python" for row in rows)
    assert empty == []


def test_get_recent_topic_color_ignores_blank_values_and_returns_lowercase(client):
    repo = SQLiteQuestionRepository()
    base = now_utc()
    valid_color = insert_question("Question A?", topic="python", topic_color="Emerald")
    blank_color = insert_question("Question B?", topic="python", topic_color="   ")
    null_color = insert_question("Question C?", topic="python", topic_color=None)

    _set_question_created_at(valid_color, base - timedelta(days=2))
    _set_question_created_at(blank_color, base - timedelta(days=1))
    _set_question_created_at(null_color, base)

    with flask_app.app_context():
        color = repo.get_recent_topic_color("python")

    assert color == "emerald"


def test_get_existing_topics_excludes_blank_and_orders_by_usage_then_name(client):
    repo = SQLiteQuestionRepository()
    insert_question("Q1?", topic="python")
    insert_question("Q2?", topic="python")
    insert_question("Q3?", topic="sql")
    insert_question("Q4?", topic="sql")
    insert_question("Q5?", topic="algorithms")
    insert_question("Q6?", topic="   ")

    with flask_app.app_context():
        topics = repo.get_existing_topics()

    assert "algorithms" in topics
    assert "   " not in topics
    assert topics[:2] == ["python", "sql"]


def test_get_due_question_randomized_respects_topic_filter_and_due_state(client):
    repo = SQLiteQuestionRepository()
    now = now_utc()
    due_python_1 = insert_question("What is GIL?", topic="python")
    due_python_2 = insert_question("What is MRO?", topic="python")
    due_sql = insert_question("What is a hash index?", topic="sql")
    future_python = insert_question("What is a metaclass?", topic="python")

    _set_question_next_review_at(due_python_1, now - timedelta(minutes=10))
    _set_question_next_review_at(due_python_2, now - timedelta(minutes=5))
    _set_question_next_review_at(due_sql, now - timedelta(minutes=20))
    _set_question_next_review_at(future_python, now + timedelta(days=1))

    allowed = {due_python_1, due_python_2}
    with flask_app.app_context():
        for _ in range(15):
            row = repo.get_due_question(topics=[" PYTHON "], randomize=True)
            assert row is not None
            assert row["id"] in allowed


def test_get_generation_context_respects_limit_and_fills_from_other_topics(client):
    repo = SQLiteQuestionRepository()
    base = now_utc()
    p1 = insert_question("What is CPython?", topic="python")
    p2 = insert_question("What is PyPy?", topic="python")
    s1 = insert_question("What is a B-tree?", topic="sql")

    _set_question_created_at(p1, base - timedelta(days=2))
    _set_question_created_at(p2, base - timedelta(days=1))
    _set_question_created_at(s1, base)

    with flask_app.app_context():
        context = repo.get_generation_context_questions("python", limit=2)
        context_with_fallback = repo.get_generation_context_questions("python", limit=3)

    assert context == ["What is PyPy?", "What is CPython?"]
    assert context_with_fallback == ["What is PyPy?", "What is CPython?", "What is a B-tree?"]


def test_feedback_repo_returns_latest_entry_by_created_at(client):
    repo = SQLiteFeedbackRepository()
    question_id = insert_question("How does replication work?", topic="databases")

    older_ts = iso(now_utc() - timedelta(days=1))
    newer_ts = iso(now_utc())
    _insert_feedback_row(
        question_id=question_id,
        created_at=older_ts,
        score=4,
        feedback="Old feedback",
        improved_answer="Old answer",
        strengths_json='["old"]',
        gaps_json='["gap"]',
    )
    _insert_feedback_row(
        question_id=question_id,
        created_at=newer_ts,
        score=9,
        feedback="New feedback",
        improved_answer="New answer",
        strengths_json='["new"]',
        gaps_json="[]",
    )

    with flask_app.app_context():
        latest = repo.get_latest_feedback(question_id)

    assert latest is not None
    assert latest["score"] == 9
    assert latest["feedback"] == "New feedback"
    assert latest["strengths"] == ["new"]
    assert latest["gaps"] == []


def test_feedback_repo_handles_malformed_strengths_and_gaps_json(client):
    repo = SQLiteFeedbackRepository()
    question_id = insert_question("Explain denormalization tradeoffs?", topic="databases")

    _insert_feedback_row(
        question_id=question_id,
        created_at=iso(now_utc()),
        strengths_json='{"not":"a-list"}',
        gaps_json="not-json",
    )

    with flask_app.app_context():
        latest = repo.get_latest_feedback(question_id)

    assert latest is not None
    assert latest["strengths"] == []
    assert latest["gaps"] == []

