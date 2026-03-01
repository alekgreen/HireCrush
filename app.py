import json
import os
import re
import base64
from datetime import timedelta
from urllib.parse import parse_qsl

import requests
from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from interview_app.constants import (
    ANSWER_JSON_SCHEMA,
    DEFAULT_GENERATION_LANGUAGE_CODE,
    FEEDBACK_JSON_SCHEMA,
    GEMINI_MODEL_FALLBACKS,
    GENERATION_LANGUAGES,
    GENERATION_LANGUAGE_BY_CODE,
    QUESTIONS_JSON_SCHEMA,
)
from interview_app.db import close_db, ensure_column, get_db, init_db
from interview_app.repository import (
    get_due_question,
    get_existing_topics,
    get_generation_context_questions,
    get_latest_feedback,
    get_next_upcoming,
    get_question_by_id,
    get_recent_questions,
    get_stats,
    list_questions,
    save_feedback,
)
from interview_app.utils import (
    clean_question_text,
    iso,
    normalize_text,
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

SUPPORTED_AUDIO_MIME_TYPES = {
    "audio/wav",
    "audio/mp3",
    "audio/mpeg",
    "audio/aiff",
    "audio/aac",
    "audio/ogg",
    "audio/flac",
}
MAX_INLINE_AUDIO_BYTES = 19 * 1024 * 1024


def gemini_model_candidates() -> list[str]:
    configured = app.config.get("GEMINI_MODEL", "").strip()
    env_fallbacks = os.getenv("GEMINI_FALLBACK_MODELS", "").strip()
    extras = [m.strip() for m in env_fallbacks.split(",") if m.strip()]

    candidates = []
    for model in [configured, *extras, *GEMINI_MODEL_FALLBACKS]:
        if model and model not in candidates:
            candidates.append(model)
    return candidates


def gemini_generate_json(prompt: str, response_schema: dict, temperature: float = 0.8):
    api_key = app.config["GEMINI_API_KEY"]
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    tried_models = []
    for model in gemini_model_candidates():
        tried_models.append(model)
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
                "responseJsonSchema": response_schema,
            },
        }

        response = requests.post(endpoint, json=payload, timeout=30)
        if response.status_code == 404:
            continue
        response.raise_for_status()

        data = response.json()
        options = data.get("candidates", [])
        if not options:
            continue
        parts = options[0].get("content", {}).get("parts", [])
        if not parts:
            continue

        raw = parts[0].get("text", "")
        parsed = parse_json_from_text(raw)
        if parsed is not None:
            app.config["LAST_WORKING_GEMINI_MODEL"] = model
            return parsed

    tried_list = ", ".join(tried_models) if tried_models else "(none)"
    raise RuntimeError(
        "No compatible Gemini model found for this API key. "
        f"Tried models: {tried_list}"
    )


def normalize_audio_mime_type(mime_type: str) -> str | None:
    aliases = {
        "audio/x-wav": "audio/wav",
        "audio/wave": "audio/wav",
        "audio/x-pn-wav": "audio/wav",
        "audio/x-aiff": "audio/aiff",
        "audio/mpga": "audio/mpeg",
    }
    normalized = aliases.get(mime_type.strip().lower(), mime_type.strip().lower())
    if normalized in SUPPORTED_AUDIO_MIME_TYPES:
        return normalized
    return None


def call_gemini_for_transcription(audio_bytes: bytes, mime_type: str) -> str:
    if not audio_bytes:
        raise RuntimeError("Audio file is empty.")
    if len(audio_bytes) > MAX_INLINE_AUDIO_BYTES:
        raise RuntimeError("Audio file is too large. Keep uploads under 19 MB.")

    normalized_mime_type = normalize_audio_mime_type(mime_type)
    if normalized_mime_type is None:
        raise RuntimeError("Unsupported audio format.")

    api_key = app.config["GEMINI_API_KEY"]
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    encoded_audio = base64.b64encode(audio_bytes).decode("ascii")
    prompt = (
        "Transcribe this audio clip. Return only the transcript text, "
        "with punctuation and no additional commentary."
    )

    tried_models = []
    for model in gemini_model_candidates():
        tried_models.append(model)
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": normalized_mime_type,
                                "data": encoded_audio,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.0},
        }

        response = requests.post(endpoint, json=payload, timeout=60)
        if response.status_code == 404:
            continue
        response.raise_for_status()

        data = response.json()
        options = data.get("candidates", [])
        if not options:
            continue
        parts = options[0].get("content", {}).get("parts", [])
        transcript_parts = []
        for part in parts:
            text = str(part.get("text", "")).strip()
            if text:
                transcript_parts.append(text)
        if transcript_parts:
            app.config["LAST_WORKING_GEMINI_MODEL"] = model
            return "\n".join(transcript_parts)

    tried_list = ", ".join(tried_models) if tried_models else "(none)"
    raise RuntimeError(
        "No compatible Gemini model found for this API key. "
        f"Tried models: {tried_list}"
    )


def call_gemini_for_questions(
    topic: str,
    count: int,
    language: str = "English",
    existing_questions: list[str] | None = None,
) -> list[str]:
    context_block = ""
    if existing_questions:
        capped_lines = []
        total_chars = 0
        max_chars = 12000
        for idx, question in enumerate(existing_questions[:120], start=1):
            compact = re.sub(r"\s+", " ", str(question).strip())
            if not compact:
                continue
            if len(compact) > 220:
                compact = compact[:217] + "..."
            line = f"{idx}. {compact}"
            total_chars += len(line) + 1
            if total_chars > max_chars:
                break
            capped_lines.append(line)
        if capped_lines:
            context_block = (
                "Existing questions already stored in the system:\n"
                + "\n".join(capped_lines)
                + "\n"
            )

    prompt = (
        "Generate interview questions.\n"
        f"Topic: {topic}\n"
        f"Count: {count}\n"
        f"Language: {language}\n"
        f"Write every question in {language}.\n"
        "Do not repeat or paraphrase any existing question with the same intent.\n"
        "A reworded version of an existing question still counts as duplicate.\n"
        f"{context_block}"
        "Return concise, unique interview questions only."
    )
    parsed = gemini_generate_json(prompt, QUESTIONS_JSON_SCHEMA, temperature=0.9)
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    if isinstance(parsed, dict):
        values = parsed.get("questions", [])
        if isinstance(values, list):
            return [str(item).strip() for item in values if str(item).strip()]
    return parse_gemini_questions(json.dumps(parsed))


def call_gemini_for_answer(question: str, topic: str | None = None) -> str:
    prompt = (
        "You are helping a candidate prepare for interviews.\n"
        f"Topic: {topic or 'General'}\n"
        f"Question: {question}\n"
        "Provide one high-quality sample answer (around 120-220 words), practical and specific."
    )
    parsed = gemini_generate_json(prompt, ANSWER_JSON_SCHEMA, temperature=0.6)
    if isinstance(parsed, dict):
        answer = str(parsed.get("answer", "")).strip()
        if answer:
            return answer
    raise RuntimeError("Gemini did not return a valid answer.")


def call_gemini_for_feedback(question: str, reference_answer: str, user_answer: str) -> dict:
    prompt = (
        "Evaluate the user's interview answer.\n"
        f"Question: {question}\n"
        f"Reference answer: {reference_answer}\n"
        f"User answer: {user_answer}\n"
        "Score the user answer from 1 to 10 and provide direct coaching."
    )
    parsed = gemini_generate_json(prompt, FEEDBACK_JSON_SCHEMA, temperature=0.4)
    if not isinstance(parsed, dict):
        raise RuntimeError("Gemini did not return a valid feedback payload.")

    def to_list(value) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    return {
        "score": max(1, min(10, int(parsed.get("score", 1)))),
        "feedback": str(parsed.get("feedback", "")).strip() or "No feedback provided.",
        "improved_answer": str(parsed.get("improved_answer", "")).strip()
        or "No improved answer provided.",
        "strengths": to_list(parsed.get("strengths")),
        "gaps": to_list(parsed.get("gaps")),
    }


def add_questions(
    topic: str, requested_count: int, language: str = "English"
) -> tuple[int, int]:
    db = get_db()
    existing_hashes = {
        row["text_hash"] for row in db.execute("SELECT text_hash FROM questions").fetchall()
    }
    inserted = 0
    attempts = 0
    max_attempts = 5
    generation_context = get_generation_context_questions(topic, limit=120)

    while inserted < requested_count and attempts < max_attempts:
        attempts += 1
        needed = min(10, (requested_count - inserted) * 2)
        generated = call_gemini_for_questions(
            topic,
            needed,
            language=language,
            existing_questions=generation_context,
        )
        if not generated:
            continue

        for item in generated:
            if inserted >= requested_count:
                break
            text = clean_question_text(item)
            if not text or len(text) < 10:
                continue
            h = question_hash(text)
            if h in existing_hashes:
                continue

            now = now_utc()
            suggested_answer = None
            if app.config.get("AUTO_GENERATE_ANSWERS", True):
                try:
                    suggested_answer = call_gemini_for_answer(text, topic)
                except Exception:
                    suggested_answer = None
            db.execute(
                """
                INSERT INTO questions (
                    text, text_hash, topic, created_at, next_review_at,
                    suggested_answer, repetitions, interval_days, ease_factor
                ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 2.5)
                """,
                (text, h, topic, iso(now), iso(now), suggested_answer),
            )
            existing_hashes.add(h)
            generation_context.append(text)
            inserted += 1

    db.commit()
    return inserted, requested_count - inserted


def generate_answer_for_question(question_id: int) -> str:
    db = get_db()
    question = get_question_by_id(question_id)
    if question is None:
        raise RuntimeError("Question not found.")

    existing = (question["suggested_answer"] or "").strip()
    if existing:
        return existing

    answer = call_gemini_for_answer(question["text"], question["topic"])
    db.execute(
        "UPDATE questions SET suggested_answer = ? WHERE id = ?",
        (answer, question_id),
    )
    db.commit()
    return answer


def format_http_error(exc: requests.HTTPError) -> str:
    response = getattr(exc, "response", None)
    if response is None:
        return "Gemini API request failed."
    status = response.status_code
    reason = response.reason or "Error"
    if status == 404:
        return (
            "Gemini model was not found. Set GEMINI_MODEL to a supported model "
            "(for example: gemini-2.5-flash or gemini-3-flash-preview)."
        )
    if status == 429:
        return "Gemini API rate limit exceeded. Please retry in a moment."
    return f"Gemini API request failed ({status} {reason})."


def apply_review(question_id: int, rating: int) -> None:
    db = get_db()
    question = db.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    if question is None:
        return

    now = now_utc()
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
        (reps, interval, ef, iso(now), iso(next_due), question_id),
    )
    db.execute(
        """
        INSERT INTO review_history (
            question_id, rating, reviewed_at, old_interval_days,
            new_interval_days, old_ease_factor, new_ease_factor
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (question_id, rating, iso(now), old_interval, interval, old_ef, ef),
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


def review_redirect(
    topics: list[str] | None = None,
    randomize: bool = False,
    qid: int | None = None,
    show_feedback: bool = False,
):
    params: dict[str, object] = {}
    if qid is not None:
        params["qid"] = qid
    if show_feedback:
        params["show_feedback"] = 1
    if randomize:
        params["randomize"] = 1
    if topics:
        params["topics"] = topics
    return redirect(url_for("review", **params))


def extract_review_filters_from_referrer() -> tuple[list[str], bool]:
    referrer = request.referrer or ""
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

        try:
            count = max(1, min(20, int(count_raw)))
        except ValueError:
            flash("Count must be an integer.", "error")
            return redirect(url_for("generate"))

        try:
            inserted, duplicates = add_questions(topic, count, language=language)
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
    )


@app.route("/review", methods=["GET"])
def review():
    selected_topics = normalize_topic_filters(request.args.getlist("topics"))
    randomize = is_randomized_review(request.args.get("randomize", ""))
    requested_qid = request.args.get("qid", type=int)
    show_feedback = str(request.args.get("show_feedback", "")).strip().lower() in {
        "1",
        "true",
        "yes",
    }
    question = get_question_by_id(requested_qid) if requested_qid else None
    if question is None:
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


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
