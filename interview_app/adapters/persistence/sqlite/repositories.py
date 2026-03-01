from typing import Any

from interview_app.application.ports.repositories import FeedbackRepository, QuestionRepository
from interview_app import repository as sqlite_repo


class SQLiteQuestionRepository(QuestionRepository):
    def get_stats(self) -> dict:
        return sqlite_repo.get_stats()

    def get_existing_topics(self, limit: int = 100) -> list[str]:
        return sqlite_repo.get_existing_topics(limit=limit)

    def get_recent_topic_color(self, topic: str) -> str | None:
        return sqlite_repo.get_recent_topic_color(topic)

    def get_generation_context_questions(self, topic: str, limit: int = 120) -> list[str]:
        return sqlite_repo.get_generation_context_questions(topic, limit=limit)

    def get_due_question(
        self,
        topics: list[str] | None = None,
        randomize: bool = False,
        exclude_question_id: int | None = None,
    ) -> Any:
        return sqlite_repo.get_due_question(
            topics=topics,
            randomize=randomize,
            exclude_question_id=exclude_question_id,
        )

    def get_question_by_id(self, question_id: int) -> Any:
        return sqlite_repo.get_question_by_id(question_id)

    def get_next_upcoming(self, topics: list[str] | None = None) -> Any:
        return sqlite_repo.get_next_upcoming(topics=topics)

    def get_recent_questions(self, limit: int = 10) -> Any:
        return sqlite_repo.get_recent_questions(limit=limit)

    def list_questions(self, limit: int = 200) -> Any:
        return sqlite_repo.list_questions(limit=limit)

    def list_topics_with_stats(self, limit: int = 200) -> Any:
        return sqlite_repo.list_topics_with_stats(limit=limit)

    def list_questions_by_topic(self, topic: str, limit: int = 400) -> Any:
        return sqlite_repo.list_questions_by_topic(topic, limit=limit)


class SQLiteFeedbackRepository(FeedbackRepository):
    def get_latest_feedback(self, question_id: int) -> Any:
        return sqlite_repo.get_latest_feedback(question_id)

    def save_feedback(self, question_id: int, user_answer: str, result: dict) -> None:
        sqlite_repo.save_feedback(question_id, user_answer, result)

