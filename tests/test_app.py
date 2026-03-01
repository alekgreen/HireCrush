from dataclasses import replace
from datetime import timedelta
import io
from urllib.parse import parse_qs, urlparse

import pytest
import requests

import app as app_module
from interview_app.services import generation_service, question_service, review_service
from interview_app.utils import parse_gemini_questions


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "test.db"
    app_module.app.config.update(
        TESTING=True,
        DATABASE=str(db_path),
        GEMINI_API_KEY="test-key",
        AUTO_GENERATE_ANSWERS=False,
        HANDLER_DEPS_OVERRIDE=None,
    )

    with app_module.app.app_context():
        app_module.run_migrations()
        db = app_module.get_db()
        db.execute("DELETE FROM review_feedback")
        db.execute("DELETE FROM review_history")
        db.execute("DELETE FROM questions")
        db.commit()

    with app_module.app.test_client() as test_client:
        yield test_client
    app_module.app.config["HANDLER_DEPS_OVERRIDE"] = None


@pytest.fixture()
def override_handler_deps():
    def _override(*, home=None, generation=None, review=None, catalog=None):
        base = app_module.build_handler_deps()
        bundle = replace(
            base,
            home=replace(base.home, **(home or {})),
            generation=replace(base.generation, **(generation or {})),
            review=replace(base.review, **(review or {})),
            catalog=replace(base.catalog, **(catalog or {})),
        )
        app_module.app.config["HANDLER_DEPS_OVERRIDE"] = bundle
        return bundle

    yield _override
    app_module.app.config["HANDLER_DEPS_OVERRIDE"] = None


def insert_question(
    text="What is polymorphism in OOP?",
    topic="python",
    suggested_answer=None,
    topic_color=None,
):
    with app_module.app.app_context():
        db = app_module.get_db()
        now = app_module.now_utc()
        db.execute(
            """
            INSERT INTO questions (
                text, text_hash, topic, topic_color, created_at, next_review_at,
                suggested_answer, repetitions, interval_days, ease_factor
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 2.5)
            """,
            (
                text,
                app_module.question_hash(text),
                topic,
                topic_color,
                app_module.iso(now),
                app_module.iso(now),
                suggested_answer,
            ),
        )
        db.commit()
        return db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


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


def test_generate_route_success_flash(client, override_handler_deps):
    def fake_add_questions(
        _topic,
        _count,
        language="English",
        additional_context=None,
        topic_color="blue",
    ):
        return 2, 1

    override_handler_deps(generation={"add_questions_fn": fake_add_questions})
    response = client.post(
        "/generate",
        data={"topic": "system design", "count": "3", "language": "en"},
        follow_redirects=True,
    )

    body = response.data.decode("utf-8")
    assert response.status_code == 200
    assert "Added 2 unique question(s)." in body
    assert "Could not add 1 question(s) after uniqueness checks." in body


def test_review_submit_good_updates_question(client):
    question_id = insert_question("How does CAP theorem apply in distributed systems?")

    response = client.post(
        f"/review/{question_id}",
        data={"grade": "good"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app_module.app.app_context():
        row = app_module.get_db().execute(
            "SELECT repetitions, interval_days FROM questions WHERE id = ?",
            (question_id,),
        ).fetchone()

    assert row["repetitions"] == 1
    assert row["interval_days"] == 1


def test_review_route_filters_due_question_by_selected_topics(client):
    insert_question("Explain Python's GIL.", topic="python")
    insert_question("What is a SQL index?", topic="sql")

    res = client.get("/review?topics=python")
    body = res.data.decode("utf-8")

    assert res.status_code == 200
    assert "Explain Python&#39;s GIL." in body
    assert "What is a SQL index?" not in body


def test_review_route_passes_randomize_and_topics_to_selector(client, override_handler_deps):
    captured = {}

    def fake_get_due_question(topics=None, randomize=False, exclude_question_id=None):
        captured["topics"] = topics
        captured["randomize"] = randomize
        captured["exclude_question_id"] = exclude_question_id
        return None

    override_handler_deps(
        review={
            "get_due_question_fn": fake_get_due_question,
            "get_next_upcoming_fn": lambda topics=None: None,
        }
    )

    res = client.get("/review?topics=python&topics=sql&randomize=1")

    assert res.status_code == 200
    assert captured == {
        "topics": ["python", "sql"],
        "randomize": True,
        "exclude_question_id": None,
    }


def test_review_submit_redirect_preserves_filters(client):
    question_id = insert_question("How does CAP theorem apply in distributed systems?")

    response = client.post(
        f"/review/{question_id}",
        data={"grade": "good", "topics": ["python", "sql"], "randomize": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    parsed = urlparse(response.headers["Location"])
    query = parse_qs(parsed.query)
    assert parsed.path == "/review"
    assert query.get("topics") == ["python", "sql"]
    assert query.get("randomize") == ["1"]


def test_review_answer_redirect_preserves_filters(client, override_handler_deps):
    question_id = insert_question("Explain eventual consistency.")
    override_handler_deps(
        review={
            "generate_answer_for_question_fn": lambda _qid: (
                "Eventual consistency means replicas converge over time."
            )
        }
    )

    response = client.post(
        f"/review/{question_id}/answer",
        data={"topics": ["distributed systems"], "randomize": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    parsed = urlparse(response.headers["Location"])
    query = parse_qs(parsed.query)
    assert parsed.path == "/review"
    assert query.get("qid") == [str(question_id)]
    assert query.get("topics") == ["distributed systems"]
    assert query.get("randomize") == ["1"]


def test_review_skip_redirect_preserves_filters(client):
    question_id = insert_question("Explain read replicas.")

    response = client.post(
        f"/review/{question_id}/skip",
        data={"topics": ["python", "sql"], "randomize": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    parsed = urlparse(response.headers["Location"])
    query = parse_qs(parsed.query)
    assert parsed.path == "/review"
    assert query.get("skip_qid") == [str(question_id)]
    assert query.get("topics") == ["python", "sql"]
    assert query.get("randomize") == ["1"]


def test_review_route_skip_qid_loads_another_due_question(client):
    first_id = insert_question("Question one?", topic="python")
    insert_question("Question two?", topic="python")

    res = client.get(f"/review?topics=python&skip_qid={first_id}")
    body = res.data.decode("utf-8")

    assert res.status_code == 200
    assert "Question two?" in body
    assert "Question one?" not in body


def test_topics_route_lists_topic_cards(client):
    insert_question("Explain Python decorators.", topic="python", topic_color="emerald")
    insert_question("What is a SQL index?", topic="sql", topic_color="rose")

    res = client.get("/topics")
    body = res.data.decode("utf-8")

    assert res.status_code == 200
    assert "Topics" in body
    assert "python" in body
    assert "sql" in body
    assert "Open topic" in body


def test_topics_route_detail_filters_by_topic(client):
    insert_question("Explain Python decorators.", topic="python")
    insert_question("What is a SQL index?", topic="sql")

    res = client.get("/topics?topic=python")
    body = res.data.decode("utf-8")

    assert res.status_code == 200
    assert "Viewing questions for this topic." in body
    assert "Explain Python decorators." in body
    assert "What is a SQL index?" not in body


def test_call_gemini_uses_schema_and_falls_back_model(monkeypatch, client):
    class FakeResponse:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self.reason = "Not Found" if status_code == 404 else "OK"
            self._payload = payload or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(response=self)

        def json(self):
            return self._payload

    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))
        if "gemini-3-flash:" in url:
            return FakeResponse(404)
        return FakeResponse(
            200,
            {
                "candidates": [
                    {"content": {"parts": [{"text": '["What is dependency injection?"]'}]}}
                ]
            },
        )

    monkeypatch.setattr(requests, "post", fake_post)
    app_module.app.config["GEMINI_API_KEY"] = "test-key"
    app_module.app.config["GEMINI_MODEL"] = "gemini-3-flash"

    questions = app_module._runtime.call_gemini_for_questions("backend", 1)

    assert questions == ["What is dependency injection?"]
    assert len(calls) >= 2
    first_payload = calls[0][1]
    assert first_payload["generationConfig"]["responseMimeType"] == "application/json"
    assert "responseJsonSchema" in first_payload["generationConfig"]
    prompt_text = first_payload["contents"][0]["parts"][0]["text"]
    assert "Language: English" in prompt_text
    assert app_module.app.config["LAST_WORKING_GEMINI_MODEL"] in (
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    )


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


def test_generate_route_masks_key_in_http_error(client, override_handler_deps):
    response = requests.Response()
    response.status_code = 404
    response.reason = "Not Found"
    response.url = "https://example.com?key=SUPERSECRET"
    http_err = requests.HTTPError("raw error", response=response)

    def fake_add_questions(
        _topic,
        _count,
        language="English",
        additional_context=None,
        topic_color="blue",
    ):
        raise http_err

    override_handler_deps(generation={"add_questions_fn": fake_add_questions})
    res = client.post(
        "/generate",
        data={"topic": "python", "count": "2", "language": "en"},
        follow_redirects=True,
    )

    body = res.data.decode("utf-8")
    assert res.status_code == 200
    assert "Gemini model was not found." in body
    assert "SUPERSECRET" not in body


def test_generate_route_passes_selected_language(client, override_handler_deps):
    captured = {}

    def fake_add_questions(
        _topic,
        _count,
        language="English",
        additional_context=None,
        topic_color="blue",
    ):
        captured["topic"] = _topic
        captured["count"] = _count
        captured["language"] = language
        captured["additional_context"] = additional_context
        captured["topic_color"] = topic_color
        return 1, 0

    override_handler_deps(generation={"add_questions_fn": fake_add_questions})
    response = client.post(
        "/generate",
        data={"topic": "system design", "count": "2", "language": "es"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert captured == {
        "topic": "system design",
        "count": 2,
        "language": "Spanish",
        "additional_context": None,
        "topic_color": "blue",
    }


def test_generate_route_uses_selected_existing_topic(client, override_handler_deps):
    captured = {}

    def fake_add_questions(
        _topic,
        _count,
        language="English",
        additional_context=None,
        topic_color="blue",
    ):
        captured["topic"] = _topic
        captured["count"] = _count
        captured["language"] = language
        captured["topic_color"] = topic_color
        return 1, 0

    override_handler_deps(generation={"add_questions_fn": fake_add_questions})
    response = client.post(
        "/generate",
        data={"topic_select": "python", "count": "2", "language": "en"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert captured["topic"] == "python"
    assert captured["count"] == 2
    assert captured["topic_color"] == "blue"


def test_generate_route_prefers_custom_topic_over_selected(client, override_handler_deps):
    captured = {}

    def fake_add_questions(
        _topic,
        _count,
        language="English",
        additional_context=None,
        topic_color="blue",
    ):
        captured["topic"] = _topic
        captured["topic_color"] = topic_color
        return 1, 0

    override_handler_deps(generation={"add_questions_fn": fake_add_questions})
    response = client.post(
        "/generate",
        data={
            "topic_select": "python",
            "topic_new": "distributed systems",
            "count": "2",
            "language": "en",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert captured["topic"] == "distributed systems"
    assert captured["topic_color"] == "blue"


def test_generate_route_rejects_invalid_language(client):
    response = client.post(
        "/generate",
        data={"topic": "python", "count": "2", "language": "xx"},
        follow_redirects=True,
    )

    body = response.data.decode("utf-8")
    assert response.status_code == 200
    assert "Language is invalid." in body


def test_generate_route_passes_optional_context_and_selected_color(client, override_handler_deps):
    captured = {}

    def fake_add_questions(
        _topic,
        _count,
        language="English",
        additional_context=None,
        topic_color="blue",
    ):
        captured["topic"] = _topic
        captured["count"] = _count
        captured["language"] = language
        captured["additional_context"] = additional_context
        captured["topic_color"] = topic_color
        return 1, 0

    override_handler_deps(generation={"add_questions_fn": fake_add_questions})
    response = client.post(
        "/generate",
        data={
            "topic": "system design",
            "count": "2",
            "language": "en",
            "additional_context": "Staff-level architecture and tradeoffs.",
            "topic_color": "emerald",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert captured == {
        "topic": "system design",
        "count": 2,
        "language": "English",
        "additional_context": "Staff-level architecture and tradeoffs.",
        "topic_color": "emerald",
    }


def test_generate_route_rejects_invalid_topic_color(client):
    response = client.post(
        "/generate",
        data={
            "topic": "python",
            "count": "2",
            "language": "en",
            "topic_color": "not-a-color",
        },
        follow_redirects=True,
    )

    body = response.data.decode("utf-8")
    assert response.status_code == 200
    assert "Topic tag color is invalid." in body


def test_generate_route_uses_existing_topic_color_when_none_selected(client, override_handler_deps):
    insert_question("What is a queue?", topic="python", topic_color="rose")
    captured = {}

    def fake_add_questions(
        _topic,
        _count,
        language="English",
        additional_context=None,
        topic_color="blue",
    ):
        captured["topic_color"] = topic_color
        return 1, 0

    override_handler_deps(generation={"add_questions_fn": fake_add_questions})
    response = client.post(
        "/generate",
        data={"topic_select": "python", "count": "2", "language": "en"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert captured["topic_color"] == "rose"


def test_review_answer_route_generates_model_answer(client, override_handler_deps):
    question_id = insert_question("Explain eventual consistency.")

    def fake_generate_answer_for_question(question_id_value):
        return question_service.generate_answer_for_question(
            question_id=question_id_value,
            get_db_fn=app_module.get_db,
            get_question_by_id_fn=app_module.get_question_by_id,
            call_gemini_for_answer_fn=lambda _question, _topic=None: (
                "Eventual consistency means replicas converge over time."
            ),
        )

    override_handler_deps(
        review={"generate_answer_for_question_fn": fake_generate_answer_for_question}
    )
    res = client.post(f"/review/{question_id}/answer", follow_redirects=True)
    assert res.status_code == 200

    with app_module.app.app_context():
        row = app_module.get_db().execute(
            "SELECT suggested_answer FROM questions WHERE id = ?",
            (question_id,),
        ).fetchone()

    assert "replicas converge over time" in row["suggested_answer"]


def test_review_feedback_route_stores_feedback(client, override_handler_deps):
    question_id = insert_question(
        "What is a database transaction?",
        suggested_answer="A transaction is an ACID unit of work.",
    )
    override_handler_deps(
        review={
            "call_gemini_for_feedback_fn": lambda **_kwargs: {
                "score": 7,
                "feedback": "Good start, add isolation and rollback details.",
                "improved_answer": "A transaction groups operations atomically with ACID guarantees.",
                "strengths": ["Mentioned ACID"],
                "gaps": ["No practical example"],
            }
        }
    )

    res = client.post(
        f"/review/{question_id}/feedback",
        data={"user_answer": "A transaction is one logical unit of work in a DB."},
        follow_redirects=True,
    )
    assert res.status_code == 200

    with app_module.app.app_context():
        row = app_module.get_db().execute(
            "SELECT score, feedback, improved_answer FROM review_feedback WHERE question_id = ?",
            (question_id,),
        ).fetchone()

    assert row["score"] == 7
    assert "Good start" in row["feedback"]
    assert "ACID guarantees" in row["improved_answer"]


def test_review_route_hides_latest_feedback_by_default(client):
    question_id = insert_question(
        "How does transaction isolation work?",
        suggested_answer="Isolation keeps concurrent transactions from interfering.",
    )
    with app_module.app.app_context():
        app_module.save_feedback(
            question_id,
            "It prevents concurrency bugs.",
            {
                "score": 6,
                "feedback": "Decent answer, add concrete isolation levels.",
                "improved_answer": "Isolation controls visibility between concurrent transactions.",
                "strengths": ["Mentions concurrency"],
                "gaps": ["No isolation level examples"],
            },
        )

    res = client.get(f"/review?qid={question_id}")
    body = res.data.decode("utf-8")

    assert res.status_code == 200
    assert "Latest Feedback" not in body
    assert "Decent answer, add concrete isolation levels." not in body
    assert "Submit your answer to generate structured feedback and an improved response." in body


def test_review_route_shows_latest_feedback_with_flag(client):
    question_id = insert_question(
        "What is optimistic locking?",
        suggested_answer="Optimistic locking checks version conflicts at write time.",
    )
    with app_module.app.app_context():
        app_module.save_feedback(
            question_id,
            "It uses a version field to detect conflicts.",
            {
                "score": 8,
                "feedback": "Good explanation with correct conflict detection idea.",
                "improved_answer": "Optimistic locking detects write conflicts by comparing versions.",
                "strengths": ["Version check noted"],
                "gaps": [],
            },
        )

    res = client.get(f"/review?qid={question_id}&show_feedback=1")
    body = res.data.decode("utf-8")

    assert res.status_code == 200
    assert "Latest Feedback" in body
    assert "Good explanation with correct conflict detection idea." in body


def test_review_feedback_redirect_includes_show_feedback_flag(client, override_handler_deps):
    question_id = insert_question(
        "Why use indexes in databases?",
        suggested_answer="Indexes speed reads by reducing scanned rows.",
    )
    override_handler_deps(
        review={
            "call_gemini_for_feedback_fn": lambda **_kwargs: {
                "score": 7,
                "feedback": "Solid base answer.",
                "improved_answer": "Indexes accelerate lookups by narrowing search paths.",
                "strengths": [],
                "gaps": [],
            }
        }
    )

    res = client.post(
        f"/review/{question_id}/feedback",
        data={"user_answer": "Indexes can make queries faster by avoiding full scans."},
        follow_redirects=False,
    )

    assert res.status_code == 302
    assert f"/review?qid={question_id}&show_feedback=1" in res.headers["Location"]


def test_call_gemini_for_transcription_uses_audio_payload_and_falls_back_model(monkeypatch, client):
    class FakeResponse:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self.reason = "Not Found" if status_code == 404 else "OK"
            self._payload = payload or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(response=self)

        def json(self):
            return self._payload

    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))
        if "gemini-3-flash:" in url:
            return FakeResponse(404)
        return FakeResponse(
            200,
            {
                "candidates": [
                    {"content": {"parts": [{"text": "This is a transcript."}]}}
                ]
            },
        )

    monkeypatch.setattr(requests, "post", fake_post)
    app_module.app.config["GEMINI_API_KEY"] = "test-key"
    app_module.app.config["GEMINI_MODEL"] = "gemini-3-flash"

    transcript = app_module._runtime.call_gemini_for_transcription(b"fake-audio", "audio/wav")

    assert transcript == "This is a transcript."
    assert len(calls) >= 2
    first_payload = calls[0][1]
    inline_data = first_payload["contents"][0]["parts"][1]["inline_data"]
    assert inline_data["mime_type"] == "audio/wav"
    assert inline_data["data"]
    assert app_module.app.config["LAST_WORKING_GEMINI_MODEL"] in (
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    )


def test_review_transcribe_route_returns_json_transcript(client, override_handler_deps):
    override_handler_deps(
        review={
            "call_gemini_for_transcription_fn": lambda _audio_bytes, _mime_type: (
                "Transcribed answer text."
            )
        }
    )

    res = client.post(
        "/review/transcribe",
        data={"audio": (io.BytesIO(b"RIFFfake"), "answer.wav", "audio/wav")},
    )

    assert res.status_code == 200
    payload = res.get_json()
    assert payload["transcript"] == "Transcribed answer text."


def test_review_transcribe_route_requires_audio_file(client):
    res = client.post("/review/transcribe", data={})

    assert res.status_code == 400
    payload = res.get_json()
    assert "Audio file is required." in payload["error"]


def test_review_transcribe_route_rejects_unsupported_format(client):
    res = client.post(
        "/review/transcribe",
        data={"audio": (io.BytesIO(b"fake"), "answer.bin", "application/octet-stream")},
    )

    assert res.status_code == 400
    payload = res.get_json()
    assert "Unsupported audio format." in payload["error"]
