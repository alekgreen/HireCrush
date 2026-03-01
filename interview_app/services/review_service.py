from datetime import timedelta
from urllib.parse import parse_qsl


def _compute_review_outcome(
    *,
    rating: int,
    repetitions: int,
    interval_days: int,
    ease_factor: float,
    now,
) -> dict:
    if rating <= 2:
        return {
            "repetitions": 0,
            "interval_days": 0,
            "ease_factor": ease_factor,
            "next_due": now + timedelta(minutes=10),
        }

    new_ease_factor = max(
        1.3,
        ease_factor + (0.1 - (5 - rating) * (0.08 + (5 - rating) * 0.02)),
    )
    if repetitions == 0:
        new_interval_days = 1
    elif repetitions == 1:
        new_interval_days = 6
    else:
        new_interval_days = max(1, round(interval_days * new_ease_factor))
    if rating == 5:
        new_interval_days = max(new_interval_days + 1, round(new_interval_days * 1.3))

    return {
        "repetitions": repetitions + 1,
        "interval_days": new_interval_days,
        "ease_factor": new_ease_factor,
        "next_due": now + timedelta(days=new_interval_days),
    }


def _format_reappearance_label(*, rating: int, interval_days: int) -> str:
    if rating <= 2:
        return "10 min"
    if interval_days == 1:
        return "1 day"
    if interval_days >= 7 and interval_days % 7 == 0:
        weeks = interval_days // 7
        return f"{weeks} week" if weeks == 1 else f"{weeks} weeks"
    return f"{interval_days} days"


def get_review_reappearance_labels(question, now_utc_fn) -> dict[str, str]:
    now = now_utc_fn()
    current_repetitions = int(question["repetitions"])
    current_interval_days = int(question["interval_days"])
    current_ease_factor = float(question["ease_factor"])

    labels: dict[str, str] = {}
    for grade, rating in (("again", 2), ("hard", 3), ("good", 4), ("easy", 5)):
        outcome = _compute_review_outcome(
            rating=rating,
            repetitions=current_repetitions,
            interval_days=current_interval_days,
            ease_factor=current_ease_factor,
            now=now,
        )
        labels[grade] = _format_reappearance_label(
            rating=rating,
            interval_days=int(outcome["interval_days"]),
        )
    return labels


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
    current_ef = float(question["ease_factor"])
    current_reps = int(question["repetitions"])
    current_interval = int(question["interval_days"])
    old_ef = current_ef
    old_interval = current_interval

    outcome = _compute_review_outcome(
        rating=rating,
        repetitions=current_reps,
        interval_days=current_interval,
        ease_factor=current_ef,
        now=now,
    )
    reps = int(outcome["repetitions"])
    interval = int(outcome["interval_days"])
    ef = float(outcome["ease_factor"])
    next_due = outcome["next_due"]

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
