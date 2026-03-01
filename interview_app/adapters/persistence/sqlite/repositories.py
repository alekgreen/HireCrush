import json
from collections.abc import Callable
from typing import Any

from interview_app.application.ports.repositories import FeedbackRepository, QuestionRepository
from interview_app.db import get_db
from interview_app.utils import clean_question_text, iso, now_utc, question_hash


class SQLiteQuestionRepository(QuestionRepository):
    def __init__(
        self,
        *,
        get_db_fn: Callable[..., Any] = get_db,
        now_utc_fn: Callable[..., Any] = now_utc,
        iso_fn: Callable[..., str] = iso,
    ):
        self._get_db = get_db_fn
        self._now_utc = now_utc_fn
        self._iso = iso_fn

    def get_stats(self) -> dict:
        db = self._get_db()
        current = self._iso(self._now_utc())
        total = db.execute("SELECT COUNT(*) AS c FROM questions").fetchone()["c"]
        due = db.execute(
            "SELECT COUNT(*) AS c FROM questions WHERE next_review_at <= ?", (current,)
        ).fetchone()["c"]
        return {"total": total, "due": due}

    def get_existing_topics(self, limit: int = 100) -> list[str]:
        db = self._get_db()
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

    def list_topic_subtopics(self, limit: int = 400):
        db = self._get_db()
        return db.execute(
            """
            SELECT topic, subtopic, COUNT(*) AS usage_count
            FROM questions
            WHERE topic IS NOT NULL AND TRIM(topic) <> ''
              AND subtopic IS NOT NULL AND TRIM(subtopic) <> ''
            GROUP BY topic, subtopic
            ORDER BY usage_count DESC, topic ASC, subtopic ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def get_recent_topic_color(self, topic: str) -> str | None:
        db = self._get_db()
        topic_clean = topic.strip()
        if not topic_clean:
            return None

        row = db.execute(
            """
            SELECT topic_color
            FROM questions
            WHERE LOWER(COALESCE(topic, '')) = LOWER(?)
              AND topic_color IS NOT NULL
              AND TRIM(topic_color) <> ''
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (topic_clean,),
        ).fetchone()
        if row is None:
            return None
        color = str(row["topic_color"]).strip().lower()
        return color or None

    def get_generation_context_questions(
        self,
        topic: str,
        subtopic: str | None = None,
        limit: int = 120,
    ) -> list[str]:
        db = self._get_db()
        topic_clean = topic.strip()
        if not topic_clean:
            return []

        context: list[str] = []
        seen: set[str] = set()

        def append_rows(rows) -> None:
            for row in rows:
                text = str(row["text"]).strip()
                if not text or text in seen:
                    continue
                context.append(text)
                seen.add(text)
                if len(context) >= limit:
                    break

        subtopic_clean = (subtopic or "").strip()
        if subtopic_clean:
            same_subtopic_rows = db.execute(
                """
                SELECT text
                FROM questions
                WHERE LOWER(COALESCE(topic, '')) = LOWER(?)
                  AND LOWER(COALESCE(subtopic, '')) = LOWER(?)
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (topic_clean, subtopic_clean, limit),
            ).fetchall()
            append_rows(same_subtopic_rows)

        if len(context) < limit:
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
            append_rows(same_topic_rows)

        if len(context) < limit:
            other_rows = db.execute(
                """
                SELECT text
                FROM questions
                WHERE LOWER(COALESCE(topic, '')) != LOWER(?)
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (topic_clean, limit - len(context)),
            ).fetchall()
            append_rows(other_rows)
        return context

    @staticmethod
    def _normalize_topic_filters(topics: list[str] | None) -> list[str]:
        if not topics:
            return []
        cleaned = []
        for topic in topics:
            value = str(topic).strip()
            if value:
                cleaned.append(value.lower())
        return cleaned

    @staticmethod
    def _normalize_subtopic_filters(
        subtopics: list[tuple[str, str]] | None,
    ) -> list[tuple[str, str]]:
        if not subtopics:
            return []
        cleaned: list[tuple[str, str]] = []
        for topic, subtopic in subtopics:
            topic_value = str(topic).strip().lower()
            subtopic_value = str(subtopic).strip().lower()
            if not topic_value or not subtopic_value:
                continue
            pair = (topic_value, subtopic_value)
            if pair not in cleaned:
                cleaned.append(pair)
        return cleaned

    @staticmethod
    def _build_topic_scope_filter(
        *,
        topics: list[str],
        subtopics: list[tuple[str, str]],
    ) -> tuple[str, list[str]]:
        parts: list[str] = []
        params: list[str] = []
        if topics:
            placeholders = ", ".join("?" for _ in topics)
            parts.append(f"LOWER(COALESCE(topic, '')) IN ({placeholders})")
            params.extend(topics)
        if subtopics:
            pair_clauses = []
            for topic, subtopic in subtopics:
                pair_clauses.append("(LOWER(COALESCE(topic, '')) = ? AND LOWER(COALESCE(subtopic, '')) = ?)")
                params.extend([topic, subtopic])
            parts.append("(" + " OR ".join(pair_clauses) + ")")
        if not parts:
            return "", []
        return " AND (" + " OR ".join(parts) + ")", params

    def get_due_question(
        self,
        topics: list[str] | None = None,
        subtopics: list[tuple[str, str]] | None = None,
        randomize: bool = False,
        exclude_question_id: int | None = None,
    ):
        db = self._get_db()
        current = self._iso(self._now_utc())
        filters = self._normalize_topic_filters(topics)
        subtopic_filters = self._normalize_subtopic_filters(subtopics)

        base_query = """
            SELECT *
            FROM questions
            WHERE next_review_at <= ?
        """
        params: list[str | int] = [current]
        scope_clause, scope_params = self._build_topic_scope_filter(
            topics=filters,
            subtopics=subtopic_filters,
        )
        if scope_clause:
            base_query += scope_clause
            params.extend(scope_params)
        if exclude_question_id is not None:
            base_query += " AND id != ?"
            params.append(int(exclude_question_id))

        if randomize:
            base_query += " ORDER BY RANDOM() LIMIT 1"
        else:
            base_query += " ORDER BY next_review_at ASC LIMIT 1"
        return db.execute(base_query, tuple(params)).fetchone()

    def get_question_by_id(self, question_id: int):
        db = self._get_db()
        return db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()

    def get_next_upcoming(
        self,
        topics: list[str] | None = None,
        subtopics: list[tuple[str, str]] | None = None,
    ):
        db = self._get_db()
        filters = self._normalize_topic_filters(topics)
        subtopic_filters = self._normalize_subtopic_filters(subtopics)
        query = """
            SELECT *
            FROM questions
        """
        params: list[str] = []
        scope_clause, scope_params = self._build_topic_scope_filter(
            topics=filters,
            subtopics=subtopic_filters,
        )
        if scope_clause:
            query += f" WHERE {scope_clause.removeprefix(' AND ')}"
            params.extend(scope_params)

        query += " ORDER BY next_review_at ASC LIMIT 1"
        return db.execute(query, tuple(params)).fetchone()

    def get_recent_questions(self, limit: int = 10):
        db = self._get_db()
        return db.execute(
            """
            SELECT id, text, topic, subtopic, topic_color, created_at
            FROM questions
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def list_questions(self, limit: int = 200):
        db = self._get_db()
        return db.execute(
            """
            SELECT id, text, topic, subtopic, topic_color, created_at, next_review_at, interval_days, repetitions, suggested_answer
            FROM questions
            ORDER BY next_review_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def list_topics_with_stats(self, limit: int = 200):
        db = self._get_db()
        current = self._iso(self._now_utc())
        return db.execute(
            """
            SELECT
                q.topic AS topic,
                COUNT(*) AS total_questions,
                SUM(CASE WHEN q.next_review_at <= ? THEN 1 ELSE 0 END) AS due_questions,
                (
                    SELECT qq.topic_color
                    FROM questions qq
                    WHERE LOWER(COALESCE(qq.topic, '')) = LOWER(COALESCE(q.topic, ''))
                      AND qq.topic_color IS NOT NULL
                      AND TRIM(qq.topic_color) <> ''
                    ORDER BY qq.created_at DESC
                    LIMIT 1
                ) AS topic_color
            FROM questions q
            WHERE q.topic IS NOT NULL AND TRIM(q.topic) <> ''
            GROUP BY q.topic
            ORDER BY total_questions DESC, q.topic ASC
            LIMIT ?
            """,
            (current, limit),
        ).fetchall()

    def list_subtopics_with_stats(self, topic: str | None = None, limit: int = 400):
        db = self._get_db()
        current = self._iso(self._now_utc())
        params: list[str | int] = [current]
        query = """
            SELECT
                q.topic AS topic,
                q.subtopic AS subtopic,
                COUNT(*) AS total_questions,
                SUM(CASE WHEN q.next_review_at <= ? THEN 1 ELSE 0 END) AS due_questions,
                (
                    SELECT qq.topic_color
                    FROM questions qq
                    WHERE LOWER(COALESCE(qq.topic, '')) = LOWER(COALESCE(q.topic, ''))
                      AND qq.topic_color IS NOT NULL
                      AND TRIM(qq.topic_color) <> ''
                    ORDER BY qq.created_at DESC
                    LIMIT 1
                ) AS topic_color
            FROM questions q
            WHERE q.topic IS NOT NULL AND TRIM(q.topic) <> ''
              AND q.subtopic IS NOT NULL AND TRIM(q.subtopic) <> ''
        """
        topic_clean = (topic or "").strip()
        if topic_clean:
            query += " AND LOWER(COALESCE(q.topic, '')) = LOWER(?)"
            params.append(topic_clean)

        query += """
            GROUP BY q.topic, q.subtopic
            ORDER BY total_questions DESC, q.topic ASC, q.subtopic ASC
            LIMIT ?
        """
        params.append(limit)
        return db.execute(query, tuple(params)).fetchall()

    def list_questions_by_topic(self, topic: str, limit: int = 400):
        db = self._get_db()
        topic_clean = topic.strip()
        if not topic_clean:
            return []
        return db.execute(
            """
            SELECT id, text, topic, subtopic, topic_color, created_at, next_review_at, interval_days, repetitions, suggested_answer
            FROM questions
            WHERE LOWER(COALESCE(topic, '')) = LOWER(?)
            ORDER BY next_review_at ASC
            LIMIT ?
            """,
            (topic_clean, limit),
        ).fetchall()

    def list_questions_by_subtopic(self, topic: str, subtopic: str, limit: int = 400):
        db = self._get_db()
        topic_clean = topic.strip()
        subtopic_clean = subtopic.strip()
        if not topic_clean or not subtopic_clean:
            return []
        return db.execute(
            """
            SELECT id, text, topic, subtopic, topic_color, created_at, next_review_at, interval_days, repetitions, suggested_answer
            FROM questions
            WHERE LOWER(COALESCE(topic, '')) = LOWER(?)
              AND LOWER(COALESCE(subtopic, '')) = LOWER(?)
            ORDER BY next_review_at ASC
            LIMIT ?
            """,
            (topic_clean, subtopic_clean, limit),
        ).fetchall()

    def _delete_questions_by_ids(self, question_ids: list[int]) -> int:
        if not question_ids:
            return 0
        db = self._get_db()
        placeholders = ", ".join("?" for _ in question_ids)
        params = tuple(question_ids)
        db.execute(
            f"DELETE FROM review_feedback WHERE question_id IN ({placeholders})",
            params,
        )
        db.execute(
            f"DELETE FROM review_history WHERE question_id IN ({placeholders})",
            params,
        )
        cursor = db.execute(
            f"DELETE FROM questions WHERE id IN ({placeholders})",
            params,
        )
        db.commit()
        return max(0, int(cursor.rowcount or 0))

    def update_question(
        self,
        question_id: int,
        *,
        text: str,
        topic: str | None,
        subtopic: str | None,
    ) -> bool:
        db = self._get_db()
        text_clean = clean_question_text(str(text or ""))
        if len(text_clean) < 10:
            raise ValueError("Question text must be at least 10 characters.")

        topic_clean = str(topic or "").strip()
        subtopic_clean = str(subtopic or "").strip()
        if not topic_clean:
            topic_value = None
            subtopic_value = None
        else:
            topic_value = topic_clean
            subtopic_value = subtopic_clean or None

        cursor = db.execute(
            """
            UPDATE questions
            SET text = ?, text_hash = ?, topic = ?, subtopic = ?
            WHERE id = ?
            """,
            (
                text_clean,
                question_hash(text_clean),
                topic_value,
                subtopic_value,
                int(question_id),
            ),
        )
        db.commit()
        return cursor.rowcount > 0

    def delete_question(self, question_id: int) -> bool:
        deleted = self._delete_questions_by_ids([int(question_id)])
        return deleted > 0

    def rename_topic(self, topic: str, new_topic: str) -> int:
        db = self._get_db()
        topic_clean = str(topic or "").strip()
        new_topic_clean = str(new_topic or "").strip()
        if not topic_clean:
            raise ValueError("Topic is required.")
        if not new_topic_clean:
            raise ValueError("New topic is required.")

        cursor = db.execute(
            """
            UPDATE questions
            SET topic = ?
            WHERE LOWER(COALESCE(topic, '')) = LOWER(?)
            """,
            (new_topic_clean, topic_clean),
        )
        db.commit()
        return max(0, int(cursor.rowcount or 0))

    def delete_topic(self, topic: str) -> int:
        db = self._get_db()
        topic_clean = str(topic or "").strip()
        if not topic_clean:
            raise ValueError("Topic is required.")

        rows = db.execute(
            """
            SELECT id
            FROM questions
            WHERE LOWER(COALESCE(topic, '')) = LOWER(?)
            """,
            (topic_clean,),
        ).fetchall()
        question_ids = [int(row["id"]) for row in rows]
        return self._delete_questions_by_ids(question_ids)

    def rename_subtopic(self, topic: str, subtopic: str, new_subtopic: str) -> int:
        db = self._get_db()
        topic_clean = str(topic or "").strip()
        subtopic_clean = str(subtopic or "").strip()
        new_subtopic_clean = str(new_subtopic or "").strip()
        if not topic_clean:
            raise ValueError("Topic is required.")
        if not subtopic_clean:
            raise ValueError("Subtopic is required.")
        if not new_subtopic_clean:
            raise ValueError("New subtopic is required.")

        cursor = db.execute(
            """
            UPDATE questions
            SET subtopic = ?
            WHERE LOWER(COALESCE(topic, '')) = LOWER(?)
              AND LOWER(COALESCE(subtopic, '')) = LOWER(?)
            """,
            (new_subtopic_clean, topic_clean, subtopic_clean),
        )
        db.commit()
        return max(0, int(cursor.rowcount or 0))

    def delete_subtopic(self, topic: str, subtopic: str) -> int:
        db = self._get_db()
        topic_clean = str(topic or "").strip()
        subtopic_clean = str(subtopic or "").strip()
        if not topic_clean:
            raise ValueError("Topic is required.")
        if not subtopic_clean:
            raise ValueError("Subtopic is required.")

        rows = db.execute(
            """
            SELECT id
            FROM questions
            WHERE LOWER(COALESCE(topic, '')) = LOWER(?)
              AND LOWER(COALESCE(subtopic, '')) = LOWER(?)
            """,
            (topic_clean, subtopic_clean),
        ).fetchall()
        question_ids = [int(row["id"]) for row in rows]
        return self._delete_questions_by_ids(question_ids)


class SQLiteFeedbackRepository(FeedbackRepository):
    def __init__(
        self,
        *,
        get_db_fn: Callable[..., Any] = get_db,
        now_utc_fn: Callable[..., Any] = now_utc,
        iso_fn: Callable[..., str] = iso,
    ):
        self._get_db = get_db_fn
        self._now_utc = now_utc_fn
        self._iso = iso_fn

    def get_latest_feedback(self, question_id: int):
        db = self._get_db()
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

    def save_feedback(self, question_id: int, user_answer: str, result: dict) -> None:
        db = self._get_db()
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
                self._iso(self._now_utc()),
            ),
        )
        db.commit()
