from datetime import datetime, timedelta, timezone

import pytest

from app import app as flask_app
from interview_app.db import get_db
from interview_app.services import review_service
from interview_app.utils import iso

from tests.support import insert_question


def _set_scheduler_state(
    question_id: int,
    *,
    repetitions: int,
    interval_days: int,
    ease_factor: float,
) -> None:
    with flask_app.app_context():
        db = get_db()
        db.execute(
            """
            UPDATE questions
            SET repetitions = ?, interval_days = ?, ease_factor = ?
            WHERE id = ?
            """,
            (repetitions, interval_days, ease_factor, question_id),
        )
        db.commit()


def _fetch_question(question_id: int):
    with flask_app.app_context():
        return get_db().execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()


def _fetch_latest_history(question_id: int):
    with flask_app.app_context():
        return get_db().execute(
            """
            SELECT question_id, rating, reviewed_at, old_interval_days, new_interval_days, old_ease_factor, new_ease_factor
            FROM review_history
            WHERE question_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (question_id,),
        ).fetchone()


def test_apply_review_hard_on_new_question_sets_one_day_interval(client):
    question_id = insert_question("Explain horizontal scaling.")
    fixed_now = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    with flask_app.app_context():
        review_service.apply_review(
            question_id=question_id,
            rating=3,
            get_db_fn=get_db,
            now_utc_fn=lambda: fixed_now,
            iso_fn=iso,
        )

    row = _fetch_question(question_id)
    history = _fetch_latest_history(question_id)

    assert row["repetitions"] == 1
    assert row["interval_days"] == 1
    assert row["ease_factor"] == pytest.approx(2.36)
    assert row["last_reviewed_at"] == iso(fixed_now)
    assert row["next_review_at"] == iso(fixed_now + timedelta(days=1))

    assert history["rating"] == 3
    assert history["old_interval_days"] == 0
    assert history["new_interval_days"] == 1
    assert history["old_ease_factor"] == pytest.approx(2.5)
    assert history["new_ease_factor"] == pytest.approx(2.36)
    assert history["reviewed_at"] == iso(fixed_now)


def test_apply_review_good_second_repetition_sets_six_day_interval(client):
    question_id = insert_question("What is eventual consistency?")
    fixed_now = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
    _set_scheduler_state(question_id, repetitions=1, interval_days=1, ease_factor=2.0)

    with flask_app.app_context():
        review_service.apply_review(
            question_id=question_id,
            rating=4,
            get_db_fn=get_db,
            now_utc_fn=lambda: fixed_now,
            iso_fn=iso,
        )

    row = _fetch_question(question_id)
    history = _fetch_latest_history(question_id)

    assert row["repetitions"] == 2
    assert row["interval_days"] == 6
    assert row["ease_factor"] == pytest.approx(2.0)
    assert row["next_review_at"] == iso(fixed_now + timedelta(days=6))

    assert history["old_interval_days"] == 1
    assert history["new_interval_days"] == 6
    assert history["old_ease_factor"] == pytest.approx(2.0)
    assert history["new_ease_factor"] == pytest.approx(2.0)


def test_apply_review_easy_after_two_repetitions_applies_easy_bonus(client):
    question_id = insert_question("Explain write-ahead logging.")
    fixed_now = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
    _set_scheduler_state(question_id, repetitions=2, interval_days=6, ease_factor=2.5)

    with flask_app.app_context():
        review_service.apply_review(
            question_id=question_id,
            rating=5,
            get_db_fn=get_db,
            now_utc_fn=lambda: fixed_now,
            iso_fn=iso,
        )

    row = _fetch_question(question_id)
    history = _fetch_latest_history(question_id)

    assert row["repetitions"] == 3
    assert row["interval_days"] == 21
    assert row["ease_factor"] == pytest.approx(2.6)
    assert row["next_review_at"] == iso(fixed_now + timedelta(days=21))

    assert history["old_interval_days"] == 6
    assert history["new_interval_days"] == 21
    assert history["old_ease_factor"] == pytest.approx(2.5)
    assert history["new_ease_factor"] == pytest.approx(2.6)


def test_apply_review_again_resets_progress_and_keeps_ease_factor(client):
    question_id = insert_question("How do secondary indexes work?")
    fixed_now = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
    _set_scheduler_state(question_id, repetitions=3, interval_days=21, ease_factor=2.6)

    with flask_app.app_context():
        review_service.apply_review(
            question_id=question_id,
            rating=2,
            get_db_fn=get_db,
            now_utc_fn=lambda: fixed_now,
            iso_fn=iso,
        )

    row = _fetch_question(question_id)
    history = _fetch_latest_history(question_id)

    assert row["repetitions"] == 0
    assert row["interval_days"] == 0
    assert row["ease_factor"] == pytest.approx(2.6)
    assert row["next_review_at"] == iso(fixed_now + timedelta(minutes=10))

    assert history["old_interval_days"] == 21
    assert history["new_interval_days"] == 0
    assert history["old_ease_factor"] == pytest.approx(2.6)
    assert history["new_ease_factor"] == pytest.approx(2.6)


def test_apply_review_hard_enforces_minimum_ease_factor(client):
    question_id = insert_question("What is quorum in distributed systems?")
    fixed_now = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
    _set_scheduler_state(question_id, repetitions=4, interval_days=10, ease_factor=1.31)

    with flask_app.app_context():
        review_service.apply_review(
            question_id=question_id,
            rating=3,
            get_db_fn=get_db,
            now_utc_fn=lambda: fixed_now,
            iso_fn=iso,
        )

    row = _fetch_question(question_id)
    history = _fetch_latest_history(question_id)

    assert row["repetitions"] == 5
    assert row["interval_days"] == 13
    assert row["ease_factor"] == pytest.approx(1.3)
    assert row["next_review_at"] == iso(fixed_now + timedelta(days=13))

    assert history["old_interval_days"] == 10
    assert history["new_interval_days"] == 13
    assert history["old_ease_factor"] == pytest.approx(1.31)
    assert history["new_ease_factor"] == pytest.approx(1.3)


def test_apply_review_missing_question_is_noop(client):
    with flask_app.app_context():
        review_service.apply_review(
            question_id=999_999,
            rating=5,
            get_db_fn=get_db,
            now_utc_fn=lambda: datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc),
            iso_fn=iso,
        )
        history_count = get_db().execute("SELECT COUNT(*) AS c FROM review_history").fetchone()["c"]

    assert history_count == 0


def test_get_review_reappearance_labels_formats_days_and_weeks(client):
    question_id = insert_question("How do read replicas work?")
    _set_scheduler_state(question_id, repetitions=2, interval_days=6, ease_factor=2.5)
    row = _fetch_question(question_id)

    labels = review_service.get_review_reappearance_labels(
        question=row,
        now_utc_fn=lambda: datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc),
    )

    assert labels == {
        "again": "10 min",
        "hard": "2 weeks",
        "good": "15 days",
        "easy": "3 weeks",
    }


def test_get_review_reappearance_labels_for_new_card(client):
    question_id = insert_question("Explain consistent hashing.")
    row = _fetch_question(question_id)

    labels = review_service.get_review_reappearance_labels(
        question=row,
        now_utc_fn=lambda: datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc),
    )

    assert labels == {
        "again": "10 min",
        "hard": "1 day",
        "good": "1 day",
        "easy": "2 days",
    }
