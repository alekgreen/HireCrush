import os

import requests
from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from interview_app import gemini_service, generation_service, question_service, review_service
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


@app.route("/")
def index():
    stats = get_stats()
    recent = get_recent_questions(limit=10)
    available_topics = get_existing_topics()
    return render_template(
        "index.html",
        stats=stats,
        recent=recent,
        available_topics=available_topics,
    )


@app.route("/generate", methods=["GET", "POST"])
def generate():
    available_topics = get_existing_topics()
    if request.method == "POST":
        selected_topic = request.form.get("topic_select", "").strip()
        custom_topic = request.form.get("topic_new", "").strip()
        topic_legacy = request.form.get("topic", "").strip()
        topic = custom_topic or selected_topic or topic_legacy
        additional_context = request.form.get("additional_context", "").strip()
        topic_color_raw = request.form.get("topic_color", "").strip().lower()
        count_raw = request.form.get("count", "5").strip()
        language_code = request.form.get(
            "language", DEFAULT_GENERATION_LANGUAGE_CODE
        ).strip().lower()
        language = GENERATION_LANGUAGE_BY_CODE.get(language_code)

        if not topic:
            flash("Topic is required.", "error")
            return redirect(url_for("generate"))
        if language is None:
            flash("Language is invalid.", "error")
            return redirect(url_for("generate"))
        if topic_color_raw and topic_color_raw not in TOPIC_TAG_COLOR_BY_CODE:
            flash("Topic tag color is invalid.", "error")
            return redirect(url_for("generate"))

        resolved_topic_color = (
            topic_color_raw
            or get_recent_topic_color(topic)
            or DEFAULT_TOPIC_TAG_COLOR_CODE
        )

        try:
            count = max(1, min(20, int(count_raw)))
        except ValueError:
            flash("Count must be an integer.", "error")
            return redirect(url_for("generate"))

        try:
            inserted, duplicates = add_questions(
                topic,
                count,
                language=language,
                additional_context=additional_context or None,
                topic_color=resolved_topic_color,
            )
        except requests.HTTPError as exc:
            flash(format_http_error(exc), "error")
            return redirect(url_for("generate"))
        except Exception as exc:
            flash(f"Generation failed: {exc}", "error")
            return redirect(url_for("generate"))

        if inserted:
            flash(f"Added {inserted} unique question(s).", "success")
        if duplicates:
            flash(
                f"Could not add {duplicates} question(s) after uniqueness checks.",
                "info",
            )
        return redirect(url_for("index"))

    return render_template(
        "generate.html",
        generation_languages=GENERATION_LANGUAGES,
        selected_language=DEFAULT_GENERATION_LANGUAGE_CODE,
        available_topics=available_topics,
        topic_tag_colors=TOPIC_TAG_COLORS,
    )


@app.route("/review", methods=["GET"])
def review():
    selected_topics = normalize_topic_filters(request.args.getlist("topics"))
    randomize = is_randomized_review(request.args.get("randomize", ""))
    skipped_qid = request.args.get("skip_qid", type=int)
    requested_qid = request.args.get("qid", type=int)
    show_feedback = str(request.args.get("show_feedback", "")).strip().lower() in {
        "1",
        "true",
        "yes",
    }
    question = get_question_by_id(requested_qid) if requested_qid else None
    if question is None:
        question = get_due_question(
            topics=selected_topics,
            randomize=randomize,
            exclude_question_id=skipped_qid,
        )
        if question is None and skipped_qid is not None:
            question = get_due_question(topics=selected_topics, randomize=randomize)

    stats = get_stats()
    upcoming = None
    latest_feedback = None
    if question is None:
        upcoming = get_next_upcoming(topics=selected_topics)
    elif show_feedback:
        latest_feedback = get_latest_feedback(question["id"])

    return render_template(
        "review.html",
        question=question,
        stats=stats,
        upcoming=upcoming,
        latest_feedback=latest_feedback,
        selected_topics=selected_topics,
        randomize=randomize,
    )


@app.route("/review/<int:question_id>", methods=["POST"])
def review_submit(question_id: int):
    rating_map = {"again": 2, "hard": 3, "good": 4, "easy": 5}
    grade = request.form.get("grade", "").strip().lower()
    rating = rating_map.get(grade)
    if rating is None:
        flash("Invalid review grade.", "error")
        return redirect(url_for("review"))

    apply_review(question_id, rating)
    selected_topics = normalize_topic_filters(request.form.getlist("topics"))
    randomize = is_randomized_review(request.form.get("randomize", ""))
    if not selected_topics and not randomize:
        selected_topics, randomize = extract_review_filters_from_referrer()
    return review_redirect(topics=selected_topics, randomize=randomize)


@app.route("/review/<int:question_id>/skip", methods=["POST"])
def review_skip(question_id: int):
    selected_topics = normalize_topic_filters(request.form.getlist("topics"))
    randomize = is_randomized_review(request.form.get("randomize", ""))
    if not selected_topics and not randomize:
        selected_topics, randomize = extract_review_filters_from_referrer()
    return review_redirect(
        topics=selected_topics,
        randomize=randomize,
        skip_qid=question_id,
    )


@app.route("/review/<int:question_id>/answer", methods=["POST"])
def review_answer(question_id: int):
    question = get_question_by_id(question_id)
    if question is None:
        flash("Question not found.", "error")
        return redirect(url_for("review"))

    try:
        generate_answer_for_question(question_id)
        flash("Model answer is ready.", "success")
    except requests.HTTPError as exc:
        flash(format_http_error(exc), "error")
    except Exception as exc:
        flash(f"Could not generate answer: {exc}", "error")

    selected_topics = normalize_topic_filters(request.form.getlist("topics"))
    randomize = is_randomized_review(request.form.get("randomize", ""))
    if not selected_topics and not randomize:
        selected_topics, randomize = extract_review_filters_from_referrer()
    return review_redirect(topics=selected_topics, randomize=randomize, qid=question_id)


@app.route("/review/<int:question_id>/feedback", methods=["POST"])
def review_feedback(question_id: int):
    question = get_question_by_id(question_id)
    if question is None:
        flash("Question not found.", "error")
        return redirect(url_for("review"))

    user_answer = request.form.get("user_answer", "").strip()
    selected_topics = normalize_topic_filters(request.form.getlist("topics"))
    randomize = is_randomized_review(request.form.get("randomize", ""))
    if not selected_topics and not randomize:
        selected_topics, randomize = extract_review_filters_from_referrer()
    if len(user_answer) < 20:
        flash("Please enter a longer answer to get meaningful feedback.", "error")
        return review_redirect(topics=selected_topics, randomize=randomize, qid=question_id)

    show_feedback = False
    try:
        reference_answer = generate_answer_for_question(question_id)
        result = call_gemini_for_feedback(
            question=question["text"],
            reference_answer=reference_answer,
            user_answer=user_answer,
        )
        save_feedback(question_id, user_answer, result)
        show_feedback = True
        flash("Feedback generated.", "success")
    except requests.HTTPError as exc:
        flash(format_http_error(exc), "error")
    except Exception as exc:
        flash(f"Could not evaluate answer: {exc}", "error")

    if show_feedback:
        return review_redirect(
            topics=selected_topics,
            randomize=randomize,
            qid=question_id,
            show_feedback=True,
        )
    return review_redirect(topics=selected_topics, randomize=randomize, qid=question_id)


@app.route("/review/transcribe", methods=["POST"])
def review_transcribe():
    audio_file = request.files.get("audio")
    if audio_file is None:
        return jsonify({"error": "Audio file is required."}), 400

    mime_type = normalize_audio_mime_type(audio_file.mimetype or "")
    if mime_type is None:
        return (
            jsonify({"error": "Unsupported audio format. Use WAV, MP3, AIFF, AAC, OGG, or FLAC."}),
            400,
        )

    audio_bytes = audio_file.read()
    if not audio_bytes:
        return jsonify({"error": "Audio file is empty."}), 400
    if len(audio_bytes) > MAX_INLINE_AUDIO_BYTES:
        return jsonify({"error": "Audio file is too large. Keep uploads under 19 MB."}), 400

    try:
        transcript = call_gemini_for_transcription(audio_bytes, mime_type)
        return jsonify({"transcript": transcript}), 200
    except requests.HTTPError as exc:
        status = getattr(getattr(exc, "response", None), "status_code", 502)
        if status == 429:
            return jsonify({"error": format_http_error(exc)}), 429
        if status in {400, 413, 415}:
            return jsonify({"error": "Gemini could not process this audio file."}), 400
        if status == 404:
            return jsonify({"error": format_http_error(exc)}), 500
        return jsonify({"error": format_http_error(exc)}), 502
    except Exception as exc:
        return jsonify({"error": f"Transcription failed: {exc}"}), 500


@app.route("/questions")
def questions():
    rows = list_questions(limit=200)
    return render_template("questions.html", questions=rows)


@app.route("/topics")
def topics():
    selected_topic = request.args.get("topic", "").strip()
    if selected_topic:
        rows = list_questions_by_topic(selected_topic, limit=400)
        return render_template(
            "topics.html",
            selected_topic=selected_topic,
            topic_questions=rows,
        )

    rows = list_topics_with_stats(limit=200)
    return render_template(
        "topics.html",
        topics=rows,
        selected_topic="",
        topic_questions=[],
    )


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
