import os

import requests
from flask import redirect, request, url_for

from interview_app.application.runtime_facade import RuntimeCallables, RuntimeFacade
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
from interview_app.presentation.deps_factory import build_handler_deps_bundle
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


_runtime = RuntimeFacade(
    app=app,
    os_getenv=os.getenv,
    requests_module=requests,
    gemini_service_module=gemini_service,
    generation_service_module=generation_service,
    question_service_module=question_service,
    review_service_module=review_service,
    parse_json_from_text_fn=parse_json_from_text,
    parse_gemini_questions_fn=parse_gemini_questions,
    get_db_fn=get_db,
    get_generation_context_questions_fn=get_generation_context_questions,
    get_question_by_id_fn=get_question_by_id,
    clean_question_text_fn=clean_question_text,
    question_hash_fn=question_hash,
    now_utc_fn=now_utc,
    iso_fn=iso,
    gemini_model_fallbacks=GEMINI_MODEL_FALLBACKS,
    questions_json_schema=QUESTIONS_JSON_SCHEMA,
    answer_json_schema=ANSWER_JSON_SCHEMA,
    feedback_json_schema=FEEDBACK_JSON_SCHEMA,
    default_topic_tag_color_code=DEFAULT_TOPIC_TAG_COLOR_CODE,
    max_inline_audio_bytes=MAX_INLINE_AUDIO_BYTES,
    runtime_callables=RuntimeCallables(
        get_gemini_generate_json=lambda: _runtime.gemini_generate_json,
        get_normalize_audio_mime_type=lambda: _runtime.normalize_audio_mime_type,
        get_call_gemini_for_questions=lambda: _runtime.call_gemini_for_questions,
        get_call_gemini_for_answer=lambda: _runtime.call_gemini_for_answer,
    ),
)


def review_redirect(
    topics: list[str] | None = None,
    randomize: bool = False,
    qid: int | None = None,
    show_feedback: bool = False,
    skip_qid: int | None = None,
):
    return _runtime.review_redirect(
        topics=topics,
        randomize=randomize,
        qid=qid,
        show_feedback=show_feedback,
        skip_qid=skip_qid,
        redirect_fn=redirect,
        url_for_fn=url_for,
    )


def extract_review_filters_from_referrer() -> tuple[list[str], bool]:
    return _runtime.extract_review_filters_from_referrer(request.referrer or "")


_default_handler_deps_bundle = build_handler_deps_bundle(
    get_stats_fn=get_stats,
    get_recent_questions_fn=get_recent_questions,
    get_existing_topics_fn=get_existing_topics,
    add_questions_fn=_runtime.add_questions,
    format_http_error_fn=_runtime.format_http_error,
    get_recent_topic_color_fn=get_recent_topic_color,
    get_question_by_id_fn=get_question_by_id,
    get_due_question_fn=get_due_question,
    get_next_upcoming_fn=get_next_upcoming,
    get_latest_feedback_fn=get_latest_feedback,
    apply_review_fn=_runtime.apply_review,
    normalize_topic_filters_fn=_runtime.normalize_topic_filters,
    is_randomized_review_fn=_runtime.is_randomized_review,
    extract_review_filters_from_referrer_fn=extract_review_filters_from_referrer,
    review_redirect_fn=review_redirect,
    generate_answer_for_question_fn=_runtime.generate_answer_for_question,
    call_gemini_for_feedback_fn=_runtime.call_gemini_for_feedback,
    save_feedback_fn=save_feedback,
    normalize_audio_mime_type_fn=_runtime.normalize_audio_mime_type,
    call_gemini_for_transcription_fn=_runtime.call_gemini_for_transcription,
    list_questions_fn=list_questions,
    list_questions_by_topic_fn=list_questions_by_topic,
    list_topics_with_stats_fn=list_topics_with_stats,
    default_generation_language_code=DEFAULT_GENERATION_LANGUAGE_CODE,
    generation_language_by_code=GENERATION_LANGUAGE_BY_CODE,
    generation_languages=GENERATION_LANGUAGES,
    topic_tag_colors=TOPIC_TAG_COLORS,
    topic_tag_color_by_code=TOPIC_TAG_COLOR_BY_CODE,
    default_topic_tag_color_code=DEFAULT_TOPIC_TAG_COLOR_CODE,
    max_inline_audio_bytes=MAX_INLINE_AUDIO_BYTES,
)


def build_handler_deps():
    override = app.config.get("HANDLER_DEPS_OVERRIDE")
    if override is not None:
        return override
    return _default_handler_deps_bundle


register_routes(app, build_handler_deps)

with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
