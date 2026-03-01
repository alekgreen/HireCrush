from datetime import timedelta

import pytest
import requests

import app as app_module


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "test.db"
    app_module.app.config.update(
        TESTING=True,
        DATABASE=str(db_path),
        GEMINI_API_KEY="test-key",
        AUTO_GENERATE_ANSWERS=False,
    )

    with app_module.app.app_context():
        app_module.init_db()
        db = app_module.get_db()
        db.execute("DELETE FROM review_feedback")
        db.execute("DELETE FROM review_history")
        db.execute("DELETE FROM questions")
        db.commit()

    with app_module.app.test_client() as test_client:
        yield test_client


def insert_question(text="What is polymorphism in OOP?", topic="python", suggested_answer=None):
    with app_module.app.app_context():
        db = app_module.get_db()
        now = app_module.now_utc()
        db.execute(
            """
            INSERT INTO questions (
                text, text_hash, topic, created_at, next_review_at,
                suggested_answer, repetitions, interval_days, ease_factor
            ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 2.5)
            """,
            (
                text,
                app_module.question_hash(text),
                topic,
                app_module.iso(now),
                app_module.iso(now),
                suggested_answer,
            ),
        )
        db.commit()
        return db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


def test_parse_gemini_questions_json_array():
    raw = '["Question one?", "Question two?"]'
    assert app_module.parse_gemini_questions(raw) == ["Question one?", "Question two?"]


def test_add_questions_skips_duplicates_and_short(monkeypatch, client):
    responses = [
        [
            "1) What is polymorphism in OOP?",
            "What is polymorphism in OOP?",
            "tiny",
            "How do you design resilient APIs?",
        ]
    ]

    def fake_call(_topic, _count):
        return responses[0]

    monkeypatch.setattr(app_module, "call_gemini_for_questions", fake_call)

    with app_module.app.app_context():
        inserted, remaining = app_module.add_questions("backend", 2)
        total = app_module.get_db().execute(
            "SELECT COUNT(*) AS c FROM questions"
        ).fetchone()["c"]

    assert inserted == 2
    assert remaining == 0
    assert total == 2


def test_add_questions_returns_unfilled_when_not_enough_unique(monkeypatch, client):
    def fake_call(_topic, _count):
        return ["What is Python?", "What is Python?"]

    monkeypatch.setattr(app_module, "call_gemini_for_questions", fake_call)

    with app_module.app.app_context():
        inserted, remaining = app_module.add_questions("python", 3)

    assert inserted == 1
    assert remaining == 2


def test_apply_review_again_sets_quick_retry(client):
    question_id = insert_question("Explain database indexing.")

    with app_module.app.app_context():
        before = app_module.now_utc()
        app_module.apply_review(question_id, 2)
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


def test_generate_route_success_flash(monkeypatch, client):
    def fake_add_questions(_topic, _count):
        return 2, 1

    monkeypatch.setattr(app_module, "add_questions", fake_add_questions)
    response = client.post(
        "/generate",
        data={"topic": "system design", "count": "3"},
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

    monkeypatch.setattr(app_module.requests, "post", fake_post)
    app_module.app.config["GEMINI_API_KEY"] = "test-key"
    app_module.app.config["GEMINI_MODEL"] = "gemini-3-flash"

    questions = app_module.call_gemini_for_questions("backend", 1)

    assert questions == ["What is dependency injection?"]
    assert len(calls) >= 2
    first_payload = calls[0][1]
    assert first_payload["generationConfig"]["responseMimeType"] == "application/json"
    assert "responseJsonSchema" in first_payload["generationConfig"]
    assert app_module.app.config["LAST_WORKING_GEMINI_MODEL"] in (
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    )


def test_generate_route_masks_key_in_http_error(monkeypatch, client):
    response = requests.Response()
    response.status_code = 404
    response.reason = "Not Found"
    response.url = "https://example.com?key=SUPERSECRET"
    http_err = requests.HTTPError("raw error", response=response)

    def fake_add_questions(_topic, _count):
        raise http_err

    monkeypatch.setattr(app_module, "add_questions", fake_add_questions)
    res = client.post(
        "/generate",
        data={"topic": "python", "count": "2"},
        follow_redirects=True,
    )

    body = res.data.decode("utf-8")
    assert res.status_code == 200
    assert "Gemini model was not found." in body
    assert "SUPERSECRET" not in body


def test_review_answer_route_generates_model_answer(monkeypatch, client):
    question_id = insert_question("Explain eventual consistency.")

    monkeypatch.setattr(
        app_module,
        "call_gemini_for_answer",
        lambda _question, _topic=None: "Eventual consistency means replicas converge over time.",
    )
    res = client.post(f"/review/{question_id}/answer", follow_redirects=True)
    assert res.status_code == 200

    with app_module.app.app_context():
        row = app_module.get_db().execute(
            "SELECT suggested_answer FROM questions WHERE id = ?",
            (question_id,),
        ).fetchone()

    assert "replicas converge over time" in row["suggested_answer"]


def test_review_feedback_route_stores_feedback(monkeypatch, client):
    question_id = insert_question(
        "What is a database transaction?",
        suggested_answer="A transaction is an ACID unit of work.",
    )
    monkeypatch.setattr(
        app_module,
        "call_gemini_for_feedback",
        lambda **_kwargs: {
            "score": 7,
            "feedback": "Good start, add isolation and rollback details.",
            "improved_answer": "A transaction groups operations atomically with ACID guarantees.",
            "strengths": ["Mentioned ACID"],
            "gaps": ["No practical example"],
        },
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
