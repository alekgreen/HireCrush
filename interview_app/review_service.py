from datetime import timedelta
from urllib.parse import parse_qsl


def apply_review(
    question_id: int,
    rating: int,
    get_db_fn,
    now_utc_fn,
    iso_fn,
) -> None:
    db = get_db_fn()
    question = db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    if question is None:
        return

    now = now_utc_fn()
    ef = float(question["ease_factor"])
    reps = int(question["repetitions"])
    interval = int(question["interval_days"])
    old_ef = ef
    old_interval = interval

    if rating <= 2:
        reps = 0
        interval = 0
        next_due = now + timedelta(minutes=10)
    else:
        ef = max(1.3, ef + (0.1 - (5 - rating) * (0.08 + (5 - rating) * 0.02)))
        if reps == 0:
            interval = 1
        elif reps == 1:
            interval = 6
        else:
            interval = max(1, round(interval * ef))
        if rating == 5:
            interval = max(interval + 1, round(interval * 1.3))
        reps += 1
        next_due = now + timedelta(days=interval)

    db.execute(
        """
        UPDATE questions
        SET repetitions = ?,
            interval_days = ?,
            ease_factor = ?,
            last_reviewed_at = ?,
            next_review_at = ?
        WHERE id = ?
        """,
        (reps, interval, ef, iso_fn(now), iso_fn(next_due), question_id),
    )
    db.execute(
        """
        INSERT INTO review_history (
            question_id, rating, reviewed_at, old_interval_days,
            new_interval_days, old_ease_factor, new_ease_factor
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (question_id, rating, iso_fn(now), old_interval, interval, old_ef, ef),
    )
    db.commit()


def normalize_topic_filters(raw_values: list[str]) -> list[str]:
    topics: list[str] = []
    for value in raw_values:
        topic = str(value).strip()
        if topic and topic not in topics:
            topics.append(topic)
    return topics


def is_randomized_review(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def extract_review_filters_from_referrer(referrer: str) -> tuple[list[str], bool]:
    if not referrer:
        return [], False

    try:
        query = referrer.split("?", 1)[1]
    except IndexError:
        return [], False

    parsed = parse_qsl(query, keep_blank_values=False)
    topics = normalize_topic_filters([value for key, value in parsed if key == "topics"])
    randomize = any(key == "randomize" and is_randomized_review(value) for key, value in parsed)
    return topics, randomize
