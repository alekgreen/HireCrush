from datetime import timedelta

import app as app_module
from interview_app.services import generation_service, question_service, review_service
from interview_app.utils import parse_gemini_questions

from tests.support import insert_question


def test_parse_gemini_questions_json_array():
    raw = '["Question one?", "Question two?"]'
    assert parse_gemini_questions(raw) == ["Question one?", "Question two?"]


def test_add_questions_skips_duplicates_and_short(client):
    responses = [
        [
            "1) What is polymorphism in OOP?",
            "What is polymorphism in OOP?",
            "tiny",
            "How do you design resilient APIs?",
        ]
    ]

    def fake_call(
        _topic,
        _count,
        language="English",
        existing_questions=None,
        additional_context=None,
    ):
        return responses[0]

    with app_module.app.app_context():
        inserted, remaining = question_service.add_questions(
            topic="backend",
            requested_count=2,
            language="English",
            additional_context=None,
            topic_color="blue",
            get_db_fn=app_module.get_db,
            get_generation_context_questions_fn=app_module.get_generation_context_questions,
            call_gemini_for_questions_fn=fake_call,
            clean_question_text_fn=app_module.clean_question_text,
            question_hash_fn=app_module.question_hash,
            now_utc_fn=app_module.now_utc,
            iso_fn=app_module.iso,
            auto_generate_answers=False,
            call_gemini_for_answer_fn=lambda _question, _topic=None: "",
        )
        total = app_module.get_db().execute(
            "SELECT COUNT(*) AS c FROM questions"
        ).fetchone()["c"]

    assert inserted == 2
    assert remaining == 0
    assert total == 2


def test_add_questions_returns_unfilled_when_not_enough_unique(client):
    def fake_call(
        _topic,
        _count,
        language="English",
        existing_questions=None,
        additional_context=None,
    ):
        return ["What is Python?", "What is Python?"]

    with app_module.app.app_context():
        inserted, remaining = question_service.add_questions(
            topic="python",
            requested_count=3,
            language="English",
            additional_context=None,
            topic_color="blue",
            get_db_fn=app_module.get_db,
            get_generation_context_questions_fn=app_module.get_generation_context_questions,
            call_gemini_for_questions_fn=fake_call,
            clean_question_text_fn=app_module.clean_question_text,
            question_hash_fn=app_module.question_hash,
            now_utc_fn=app_module.now_utc,
            iso_fn=app_module.iso,
            auto_generate_answers=False,
            call_gemini_for_answer_fn=lambda _question, _topic=None: "",
        )

    assert inserted == 1
    assert remaining == 2


def test_apply_review_again_sets_quick_retry(client):
    question_id = insert_question("Explain database indexing.")

    with app_module.app.app_context():
        before = app_module.now_utc()
        review_service.apply_review(
            question_id=question_id,
            rating=2,
            get_db_fn=app_module.get_db,
            now_utc_fn=app_module.now_utc,
            iso_fn=app_module.iso,
        )
        row = app_module.get_db().execute(
            "SELECT repetitions, interval_days, next_review_at FROM questions WHERE id = ?",
            (question_id,),
        ).fetchone()
        history_count = app_module.get_db().execute(
            "SELECT COUNT(*) AS c FROM review_history WHERE question_id = ?",
            (question_id,),
        ).fetchone()["c"]
        next_due = app_module.parse_iso(row["next_review_at"])

    assert row["repetitions"] == 0
    assert row["interval_days"] == 0
    assert timedelta(minutes=9) <= (next_due - before) <= timedelta(minutes=11)
    assert history_count == 1


def test_call_gemini_for_questions_includes_existing_context():
    captured = {}

    def fake_generate_json(prompt, _schema, temperature=0.9):
        captured["prompt"] = prompt
        captured["temperature"] = temperature
        return ["Question A?"]

    out = generation_service.call_for_questions(
        topic="backend",
        count=2,
        language="English",
        existing_questions=["What is dependency injection?", "Explain CAP theorem?"],
        additional_context="Senior backend role. Focus on microservices tradeoffs.",
        generate_json_fn=fake_generate_json,
        questions_json_schema=app_module.QUESTIONS_JSON_SCHEMA,
        parse_gemini_questions_fn=parse_gemini_questions,
    )

    assert out == ["Question A?"]
    assert captured["temperature"] == 0.9
    assert "Existing questions already stored in the system" in captured["prompt"]
    assert "What is dependency injection?" in captured["prompt"]
    assert "Explain CAP theorem?" in captured["prompt"]
    assert "Additional user context to follow when generating questions" in captured["prompt"]
    assert "Focus on microservices tradeoffs." in captured["prompt"]
    assert "Do not repeat or paraphrase any existing question" in captured["prompt"]

