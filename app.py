import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask, flash, g, redirect, render_template, request, url_for
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
app.config["DATABASE"] = os.getenv("DATABASE_PATH", "interview.db")
app.config["GEMINI_API_KEY"] = os.getenv("GEMINI_API_KEY", "")
app.config["GEMINI_MODEL"] = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

GEMINI_MODEL_FALLBACKS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]

QUESTIONS_JSON_SCHEMA = {
    "type": "array",
    "items": {
        "type": "string",
        "description": "A single interview question. End the string with a question mark.",
    },
    "minItems": 1,
}


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            text_hash TEXT NOT NULL UNIQUE,
            topic TEXT,
            created_at TEXT NOT NULL,
            last_reviewed_at TEXT,
            next_review_at TEXT NOT NULL,
            repetitions INTEGER NOT NULL DEFAULT 0,
            interval_days INTEGER NOT NULL DEFAULT 0,
            ease_factor REAL NOT NULL DEFAULT 2.5
        );

        CREATE TABLE IF NOT EXISTS review_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL,
            old_interval_days INTEGER NOT NULL,
            new_interval_days INTEGER NOT NULL,
            old_ease_factor REAL NOT NULL,
            new_ease_factor REAL NOT NULL,
            FOREIGN KEY (question_id) REFERENCES questions(id)
        );
        """
    )
    db.commit()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str)


def normalize_text(text: str) -> str:
    compact = re.sub(r"\s+", " ", text.strip().lower())
    compact = re.sub(r"^[\d\-\.\)\s]+", "", compact)
    return compact


def question_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def clean_question_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^[\d\-\.\)\s]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def get_stats() -> dict:
    db = get_db()
    current = iso(now_utc())
    total = db.execute("SELECT COUNT(*) AS c FROM questions").fetchone()["c"]
    due = db.execute(
        "SELECT COUNT(*) AS c FROM questions WHERE next_review_at <= ?", (current,)
    ).fetchone()["c"]
    return {"total": total, "due": due}


def get_due_question():
    db = get_db()
    current = iso(now_utc())
    return db.execute(
        """
        SELECT *
        FROM questions
        WHERE next_review_at <= ?
        ORDER BY next_review_at ASC
        LIMIT 1
        """,
        (current,),
    ).fetchone()


def get_next_upcoming():
    db = get_db()
    return db.execute(
        """
        SELECT *
        FROM questions
        ORDER BY next_review_at ASC
        LIMIT 1
        """
    ).fetchone()


def parse_gemini_questions(raw_text: str) -> list[str]:
    text = raw_text.strip()
    if not text:
        return []

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        if isinstance(parsed, dict):
            items = parsed.get("questions", [])
            return [str(item).strip() for item in items if str(item).strip()]
    except json.JSONDecodeError:
        pass

    match = re.search(r"\[[\s\S]+\]", text)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass

    lines = [line.strip(" -*\t") for line in text.splitlines()]
    return [line for line in lines if line.endswith("?")]


def gemini_model_candidates() -> list[str]:
    configured = app.config.get("GEMINI_MODEL", "").strip()
    env_fallbacks = os.getenv("GEMINI_FALLBACK_MODELS", "").strip()
    extras = [m.strip() for m in env_fallbacks.split(",") if m.strip()]

    candidates = []
    for model in [configured, *extras, *GEMINI_MODEL_FALLBACKS]:
        if model and model not in candidates:
            candidates.append(model)
    return candidates


def call_gemini_for_questions(topic: str, count: int) -> list[str]:
    api_key = app.config["GEMINI_API_KEY"]
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    prompt = (
        "Generate interview questions.\n"
        f"Topic: {topic}\n"
        f"Count: {count}\n"
        "Return concise, unique interview questions only."
    )
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
                "temperature": 0.9,
                "responseMimeType": "application/json",
                "responseJsonSchema": QUESTIONS_JSON_SCHEMA,
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
        questions = parse_gemini_questions(raw)
        if questions:
            app.config["LAST_WORKING_GEMINI_MODEL"] = model
            return questions

    tried_list = ", ".join(tried_models) if tried_models else "(none)"
    raise RuntimeError(
        "No compatible Gemini model found for this API key. "
        f"Tried models: {tried_list}"
    )


def add_questions(topic: str, requested_count: int) -> tuple[int, int]:
    db = get_db()
    existing_hashes = {
        row["text_hash"] for row in db.execute("SELECT text_hash FROM questions").fetchall()
    }
    inserted = 0
    attempts = 0
    max_attempts = 5

    while inserted < requested_count and attempts < max_attempts:
        attempts += 1
        needed = min(10, (requested_count - inserted) * 2)
        generated = call_gemini_for_questions(topic, needed)
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
            db.execute(
                """
                INSERT INTO questions (
                    text, text_hash, topic, created_at, next_review_at,
                    repetitions, interval_days, ease_factor
                ) VALUES (?, ?, ?, ?, ?, 0, 0, 2.5)
                """,
                (text, h, topic, iso(now), iso(now)),
            )
            existing_hashes.add(h)
            inserted += 1

    db.commit()
    return inserted, requested_count - inserted


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


@app.route("/")
def index():
    stats = get_stats()
    db = get_db()
    recent = db.execute(
        """
        SELECT id, text, topic, created_at
        FROM questions
        ORDER BY created_at DESC
        LIMIT 10
        """
    ).fetchall()
    return render_template("index.html", stats=stats, recent=recent)


@app.route("/generate", methods=["GET", "POST"])
def generate():
    if request.method == "POST":
        topic = request.form.get("topic", "").strip()
        count_raw = request.form.get("count", "5").strip()

        if not topic:
            flash("Topic is required.", "error")
            return redirect(url_for("generate"))

        try:
            count = max(1, min(20, int(count_raw)))
        except ValueError:
            flash("Count must be an integer.", "error")
            return redirect(url_for("generate"))

        try:
            inserted, duplicates = add_questions(topic, count)
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

    return render_template("generate.html")


@app.route("/review", methods=["GET"])
def review():
    question = get_due_question()
    stats = get_stats()
    upcoming = None
    if question is None:
        upcoming = get_next_upcoming()
    return render_template(
        "review.html",
        question=question,
        stats=stats,
        upcoming=upcoming,
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
    return redirect(url_for("review"))


@app.route("/questions")
def questions():
    db = get_db()
    rows = db.execute(
        """
        SELECT id, text, topic, created_at, next_review_at, interval_days, repetitions
        FROM questions
        ORDER BY next_review_at ASC
        LIMIT 200
        """
    ).fetchall()
    return render_template("questions.html", questions=rows)


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
