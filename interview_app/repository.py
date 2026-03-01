import json

from .db import get_db
from .utils import iso, now_utc


def get_stats() -> dict:
    db = get_db()
    current = iso(now_utc())
    total = db.execute("SELECT COUNT(*) AS c FROM questions").fetchone()["c"]
    due = db.execute(
        "SELECT COUNT(*) AS c FROM questions WHERE next_review_at <= ?", (current,)
    ).fetchone()["c"]
    return {"total": total, "due": due}


def get_existing_topics(limit: int = 100) -> list[str]:
    db = get_db()
    rows = db.execute(
        """
        SELECT topic, COUNT(*) AS usage_count
        FROM questions
        WHERE topic IS NOT NULL AND TRIM(topic) <> ''
        GROUP BY topic
        ORDER BY usage_count DESC, topic ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [str(row["topic"]).strip() for row in rows if str(row["topic"]).strip()]


def get_generation_context_questions(topic: str, limit: int = 120) -> list[str]:
    db = get_db()
    topic_clean = topic.strip()
    if not topic_clean:
        return []

    same_topic_rows = db.execute(
        """
        SELECT text
        FROM questions
        WHERE LOWER(COALESCE(topic, '')) = LOWER(?)
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (topic_clean, limit),
    ).fetchall()
    context = [str(row["text"]).strip() for row in same_topic_rows if str(row["text"]).strip()]

    if len(context) < limit:
        remaining = limit - len(context)
        other_rows = db.execute(
            """
            SELECT text
            FROM questions
            WHERE LOWER(COALESCE(topic, '')) != LOWER(?)
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (topic_clean, remaining),
        ).fetchall()
        context.extend(str(row["text"]).strip() for row in other_rows if str(row["text"]).strip())
    return context


def _normalize_topic_filters(topics: list[str] | None) -> list[str]:
    if not topics:
        return []
    cleaned = []
    for topic in topics:
        value = str(topic).strip()
        if value:
            cleaned.append(value.lower())
    return cleaned


def get_due_question(topics: list[str] | None = None, randomize: bool = False):
    db = get_db()
    current = iso(now_utc())
    filters = _normalize_topic_filters(topics)

    base_query = """
        SELECT *
        FROM questions
        WHERE next_review_at <= ?
    """
    params: list[str] = [current]
    if filters:
        placeholders = ", ".join("?" for _ in filters)
        base_query += (
            f" AND LOWER(COALESCE(topic, '')) IN ({placeholders})"
        )
        params.extend(filters)

    if randomize:
        base_query += " ORDER BY RANDOM() LIMIT 1"
    else:
        base_query += " ORDER BY next_review_at ASC LIMIT 1"
    return db.execute(base_query, tuple(params)).fetchone()


def get_question_by_id(question_id: int):
    db = get_db()
    return db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()


def get_next_upcoming(topics: list[str] | None = None):
    db = get_db()
    filters = _normalize_topic_filters(topics)
    query = """
        SELECT *
        FROM questions
    """
    params: list[str] = []
    if filters:
        placeholders = ", ".join("?" for _ in filters)
        query += f" WHERE LOWER(COALESCE(topic, '')) IN ({placeholders})"
        params.extend(filters)

    query += " ORDER BY next_review_at ASC LIMIT 1"
    return db.execute(query, tuple(params)).fetchone()


def get_latest_feedback(question_id: int):
    db = get_db()
    row = db.execute(
        """
        SELECT user_answer, score, feedback, improved_answer, strengths_json, gaps_json, created_at
        FROM review_feedback
        WHERE question_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (question_id,),
    ).fetchone()
    if row is None:
        return None

    def parse_list(value: str | None) -> list[str]:
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item).strip() for item in parsed if str(item).strip()]

    return {
        "user_answer": row["user_answer"],
        "score": row["score"],
        "feedback": row["feedback"],
        "improved_answer": row["improved_answer"],
        "strengths": parse_list(row["strengths_json"]),
        "gaps": parse_list(row["gaps_json"]),
        "created_at": row["created_at"],
    }


def save_feedback(question_id: int, user_answer: str, result: dict) -> None:
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
            int(result["score"]),
            result["feedback"],
            result["improved_answer"],
            json.dumps(result.get("strengths", []), ensure_ascii=True),
            json.dumps(result.get("gaps", []), ensure_ascii=True),
            iso(now_utc()),
        ),
    )
    db.commit()


def get_recent_questions(limit: int = 10):
    db = get_db()
    return db.execute(
        """
        SELECT id, text, topic, created_at
        FROM questions
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def list_questions(limit: int = 200):
    db = get_db()
    return db.execute(
        """
        SELECT id, text, topic, created_at, next_review_at, interval_days, repetitions, suggested_answer
        FROM questions
        ORDER BY next_review_at ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
