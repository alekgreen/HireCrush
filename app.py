import os

import requests
from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from interview_app.handlers import catalog_handler, generation_handler, home_handler, review_handler
from interview_app.handlers.deps import HandlerDeps
from interview_app.services import (
    gemini_service,
    generation_service,
    question_service,
    review_service,
)
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
    TOPIC_TAG_STYLE_BY_CODE,
)
from interview_app.db import close_db, get_db, init_db
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
from interview_app.utils import (
    clean_question_text,
    iso,
    now_utc,
    parse_gemini_questions,
    parse_iso,
    parse_json_from_text,
    question_hash,
)

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
app.config["DATABASE"] = os.getenv("DATABASE_PATH", "interview.db")
app.config["GEMINI_API_KEY"] = os.getenv("GEMINI_API_KEY", "")
app.config["GEMINI_MODEL"] = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
app.config["AUTO_GENERATE_ANSWERS"] = (
    os.getenv("AUTO_GENERATE_ANSWERS", "true").strip().lower() in {"1", "true", "yes", "on"}
)
app.teardown_appcontext(close_db)

SUPPORTED_AUDIO_MIME_TYPES = gemini_service.SUPPORTED_AUDIO_MIME_TYPES
MAX_INLINE_AUDIO_BYTES = gemini_service.MAX_INLINE_AUDIO_BYTES


@app.context_processor
def inject_topic_tag_style():
    return {
        "topic_tag_styles": TOPIC_TAG_STYLE_BY_CODE,
        "default_topic_tag_color": DEFAULT_TOPIC_TAG_COLOR_CODE,
    }


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


def normalize_audio_mime_type(mime_type: str) -> str | None:
    return gemini_service.normalize_audio_mime_type(mime_type)


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


def format_http_error(exc: requests.HTTPError) -> str:
    return question_service.format_http_error(exc)


def apply_review(question_id: int, rating: int) -> None:
    review_service.apply_review(
        question_id=question_id,
        rating=rating,
        get_db_fn=get_db,
        now_utc_fn=now_utc,
        iso_fn=iso,
    )


def normalize_topic_filters(raw_values: list[str]) -> list[str]:
    return review_service.normalize_topic_filters(raw_values)


def is_randomized_review(value: str) -> bool:
    return review_service.is_randomized_review(value)


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


def build_handler_deps() -> HandlerDeps:
    return HandlerDeps(
        get_stats_fn=get_stats,
        get_recent_questions_fn=get_recent_questions,
        get_existing_topics_fn=get_existing_topics,
        add_questions_fn=add_questions,
        format_http_error_fn=format_http_error,
        get_recent_topic_color_fn=get_recent_topic_color,
        get_question_by_id_fn=get_question_by_id,
        get_due_question_fn=get_due_question,
        get_next_upcoming_fn=get_next_upcoming,
        get_latest_feedback_fn=get_latest_feedback,
        apply_review_fn=apply_review,
        normalize_topic_filters_fn=normalize_topic_filters,
        is_randomized_review_fn=is_randomized_review,
        extract_review_filters_from_referrer_fn=extract_review_filters_from_referrer,
        review_redirect_fn=review_redirect,
        generate_answer_for_question_fn=generate_answer_for_question,
        call_gemini_for_feedback_fn=call_gemini_for_feedback,
        save_feedback_fn=save_feedback,
        normalize_audio_mime_type_fn=normalize_audio_mime_type,
        call_gemini_for_transcription_fn=call_gemini_for_transcription,
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


@app.route("/")
def index():
    return home_handler.index_page(
        deps=build_handler_deps(),
        render_template_fn=render_template,
    )


@app.route("/generate", methods=["GET", "POST"])
def generate():
    return generation_handler.generate_page(
        deps=build_handler_deps(),
        request_obj=request,
        flash_fn=flash,
        redirect_fn=redirect,
        url_for_fn=url_for,
        render_template_fn=render_template,
    )


@app.route("/review", methods=["GET"])
def review():
    return review_handler.review_page(
        deps=build_handler_deps(),
        request_obj=request,
        render_template_fn=render_template,
    )


@app.route("/review/<int:question_id>", methods=["POST"])
def review_submit(question_id: int):
    return review_handler.review_submit_action(
        deps=build_handler_deps(),
        question_id=question_id,
        request_obj=request,
        flash_fn=flash,
        redirect_fn=redirect,
        url_for_fn=url_for,
    )


@app.route("/review/<int:question_id>/skip", methods=["POST"])
def review_skip(question_id: int):
    return review_handler.review_skip_action(
        deps=build_handler_deps(),
        question_id=question_id,
        request_obj=request,
    )


@app.route("/review/<int:question_id>/answer", methods=["POST"])
def review_answer(question_id: int):
    return review_handler.review_answer_action(
        deps=build_handler_deps(),
        question_id=question_id,
        request_obj=request,
        flash_fn=flash,
        redirect_fn=redirect,
        url_for_fn=url_for,
    )


@app.route("/review/<int:question_id>/feedback", methods=["POST"])
def review_feedback(question_id: int):
    return review_handler.review_feedback_action(
        deps=build_handler_deps(),
        question_id=question_id,
        request_obj=request,
        flash_fn=flash,
        redirect_fn=redirect,
        url_for_fn=url_for,
    )


@app.route("/review/transcribe", methods=["POST"])
def review_transcribe():
    return review_handler.review_transcribe_action(
        deps=build_handler_deps(),
        request_obj=request,
        jsonify_fn=jsonify,
    )


@app.route("/questions")
def questions():
    return catalog_handler.questions_page(
        deps=build_handler_deps(),
        render_template_fn=render_template,
    )


@app.route("/topics")
def topics():
    return catalog_handler.topics_page(
        deps=build_handler_deps(),
        request_obj=request,
        render_template_fn=render_template,
    )


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
