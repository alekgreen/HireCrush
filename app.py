import os
import sys

import requests
from flask import redirect, request, url_for

from interview_app.constants import (
    ANSWER_JSON_SCHEMA,
    DEFAULT_GENERATION_LANGUAGE_CODE,
    DEFAULT_TOPIC_TAG_COLOR_CODE,
    FEEDBACK_JSON_SCHEMA,
    GEMINI_MODEL_FALLBACKS,
    GENERATION_LANGUAGES,
    GENERATION_LANGUAGE_BY_CODE,
    QUESTIONS_JSON_SCHEMA,
    TOPIC_TAG_COLORS,
    TOPIC_TAG_COLOR_BY_CODE,
)
from interview_app.db import get_db, init_db
from interview_app.presentation.app_factory import create_flask_app
from interview_app.presentation.deps_factory import build_handler_deps_from_namespace
from interview_app.presentation.routes import register_routes
from interview_app.repository import (
    get_due_question,
    get_existing_topics,
    get_generation_context_questions,
    get_latest_feedback,
    get_next_upcoming,
    get_question_by_id,
    get_recent_topic_color,
    get_recent_questions,
    get_stats,
    list_questions,
    list_questions_by_topic,
    list_topics_with_stats,
    save_feedback,
)
from interview_app.services import (
    gemini_service,
    generation_service,
    question_service,
    review_service,
)
from interview_app.utils import (
    clean_question_text,
    iso,
    now_utc,
    parse_gemini_questions,
    parse_iso,
    parse_json_from_text,
    question_hash,
)

app = create_flask_app(__name__)

SUPPORTED_AUDIO_MIME_TYPES = gemini_service.SUPPORTED_AUDIO_MIME_TYPES
MAX_INLINE_AUDIO_BYTES = gemini_service.MAX_INLINE_AUDIO_BYTES


def gemini_model_candidates() -> list[str]:
    return gemini_service.build_model_candidates(
        configured_model=str(app.config.get("GEMINI_MODEL", "")),
        env_fallback_models=os.getenv("GEMINI_FALLBACK_MODELS", ""),
        default_models=GEMINI_MODEL_FALLBACKS,
    )


def gemini_generate_json(prompt: str, response_schema: dict, temperature: float = 0.8):
    parsed, model = gemini_service.generate_json(
        prompt=prompt,
        response_schema=response_schema,
        temperature=temperature,
        api_key=app.config["GEMINI_API_KEY"],
        model_candidates=gemini_model_candidates(),
        parse_json_from_text_fn=parse_json_from_text,
        http_client=requests,
    )
    app.config["LAST_WORKING_GEMINI_MODEL"] = model
    return parsed


normalize_audio_mime_type = gemini_service.normalize_audio_mime_type


def call_gemini_for_transcription(audio_bytes: bytes, mime_type: str) -> str:
    transcript, model = gemini_service.transcribe_audio(
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        api_key=app.config["GEMINI_API_KEY"],
        model_candidates=gemini_model_candidates(),
        http_client=requests,
        normalize_audio_mime_type_fn=normalize_audio_mime_type,
        max_inline_audio_bytes=MAX_INLINE_AUDIO_BYTES,
    )
    app.config["LAST_WORKING_GEMINI_MODEL"] = model
    return transcript


def call_gemini_for_questions(
    topic: str,
    count: int,
    language: str = "English",
    existing_questions: list[str] | None = None,
    additional_context: str | None = None,
) -> list[str]:
    return generation_service.call_for_questions(
        topic=topic,
        count=count,
        language=language,
        existing_questions=existing_questions,
        additional_context=additional_context,
        generate_json_fn=gemini_generate_json,
        questions_json_schema=QUESTIONS_JSON_SCHEMA,
        parse_gemini_questions_fn=parse_gemini_questions,
    )


def call_gemini_for_answer(question: str, topic: str | None = None) -> str:
    return generation_service.call_for_answer(
        question=question,
        topic=topic,
        generate_json_fn=gemini_generate_json,
        answer_json_schema=ANSWER_JSON_SCHEMA,
    )


def call_gemini_for_feedback(question: str, reference_answer: str, user_answer: str) -> dict:
    return generation_service.call_for_feedback(
        question=question,
        reference_answer=reference_answer,
        user_answer=user_answer,
        generate_json_fn=gemini_generate_json,
        feedback_json_schema=FEEDBACK_JSON_SCHEMA,
    )


def add_questions(
    topic: str,
    requested_count: int,
    language: str = "English",
    additional_context: str | None = None,
    topic_color: str = DEFAULT_TOPIC_TAG_COLOR_CODE,
) -> tuple[int, int]:
    return question_service.add_questions(
        topic=topic,
        requested_count=requested_count,
        language=language,
        additional_context=additional_context,
        topic_color=topic_color,
        get_db_fn=get_db,
        get_generation_context_questions_fn=get_generation_context_questions,
        call_gemini_for_questions_fn=call_gemini_for_questions,
        clean_question_text_fn=clean_question_text,
        question_hash_fn=question_hash,
        now_utc_fn=now_utc,
        iso_fn=iso,
        auto_generate_answers=bool(app.config.get("AUTO_GENERATE_ANSWERS", True)),
        call_gemini_for_answer_fn=call_gemini_for_answer,
    )


def generate_answer_for_question(question_id: int) -> str:
    return question_service.generate_answer_for_question(
        question_id=question_id,
        get_db_fn=get_db,
        get_question_by_id_fn=get_question_by_id,
        call_gemini_for_answer_fn=call_gemini_for_answer,
    )


format_http_error = question_service.format_http_error


def apply_review(question_id: int, rating: int) -> None:
    review_service.apply_review(
        question_id=question_id,
        rating=rating,
        get_db_fn=get_db,
        now_utc_fn=now_utc,
        iso_fn=iso,
    )


normalize_topic_filters = review_service.normalize_topic_filters
is_randomized_review = review_service.is_randomized_review


def review_redirect(
    topics: list[str] | None = None,
    randomize: bool = False,
    qid: int | None = None,
    show_feedback: bool = False,
    skip_qid: int | None = None,
):
    params: dict[str, object] = {}
    if qid is not None:
        params["qid"] = qid
    if show_feedback:
        params["show_feedback"] = 1
    if skip_qid is not None:
        params["skip_qid"] = int(skip_qid)
    if randomize:
        params["randomize"] = 1
    if topics:
        params["topics"] = topics
    return redirect(url_for("review", **params))


def extract_review_filters_from_referrer() -> tuple[list[str], bool]:
    return review_service.extract_review_filters_from_referrer(request.referrer or "")


def build_handler_deps():
    return build_handler_deps_from_namespace(sys.modules[__name__])


register_routes(app, build_handler_deps)

with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
