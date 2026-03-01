import os

import pytest
import requests

from app import app as flask_app
from interview_app.db import get_db, run_migrations


def _gemini_api_key():
    key = os.getenv("GEMINI_API_KEY") or flask_app.config.get("GEMINI_API_KEY", "")
    if not key or key == "your_gemini_api_key_here":
        pytest.skip("GEMINI_API_KEY is required for integration tests.")
    return key


def _select_working_model(api_key: str) -> tuple[str, list[str]]:
    configured = flask_app.config.get("GEMINI_MODEL", "")
    preferred = os.getenv("GEMINI_TEST_MODEL", "")
    candidates = [configured, preferred, "gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"]
    models = []
    for model in candidates:
        if model and model not in models:
            models.append(model)

    last_404 = None
    runtime = flask_app.extensions["runtime"]
    for model in models:
        flask_app.config["GEMINI_API_KEY"] = api_key
        flask_app.config["GEMINI_MODEL"] = model
        try:
            questions = runtime.call_gemini_for_questions("Python backend interviews", 1)
            if questions:
                return model, questions
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                last_404 = exc
                continue
            raise

    if last_404 is not None:
        pytest.skip(
            "No compatible Gemini model found for this key. "
            "Set GEMINI_MODEL or GEMINI_TEST_MODEL to a supported model."
        )
    pytest.skip("Gemini did not return questions for tested models.")


@pytest.mark.integration
def test_call_gemini_for_questions_live_api():
    api_key = _gemini_api_key()
    model, questions = _select_working_model(api_key)

    assert isinstance(questions, list)
    assert len(questions) >= 1
    assert all(isinstance(q, str) and len(q.strip()) >= 10 for q in questions)
    assert flask_app.config["GEMINI_MODEL"] == model


@pytest.mark.integration
def test_generate_route_live_api_persists_questions(tmp_path):
    api_key = _gemini_api_key()
    model, _ = _select_working_model(api_key)
    old_database = flask_app.config["DATABASE"]
    old_key = flask_app.config["GEMINI_API_KEY"]
    old_model = flask_app.config["GEMINI_MODEL"]
    old_auto = flask_app.config.get("AUTO_GENERATE_ANSWERS", True)

    db_path = tmp_path / "integration.db"
    flask_app.config.update(
        TESTING=True,
        DATABASE=str(db_path),
        GEMINI_API_KEY=api_key,
        GEMINI_MODEL=model,
        AUTO_GENERATE_ANSWERS=False,
    )

    try:
        with flask_app.app_context():
            run_migrations()

        with flask_app.test_client() as client:
            response = client.post(
                "/generate",
                data={"topic": "Data structures", "count": "2"},
                follow_redirects=True,
            )
            assert response.status_code == 200

        with flask_app.app_context():
            total = get_db().execute(
                "SELECT COUNT(*) AS c FROM questions"
            ).fetchone()["c"]
        assert total >= 1
    finally:
        flask_app.config["DATABASE"] = old_database
        flask_app.config["GEMINI_API_KEY"] = old_key
        flask_app.config["GEMINI_MODEL"] = old_model
        flask_app.config["AUTO_GENERATE_ANSWERS"] = old_auto


@pytest.mark.integration
def test_call_gemini_for_feedback_live_api():
    api_key = _gemini_api_key()
    model, _ = _select_working_model(api_key)
    flask_app.config["GEMINI_API_KEY"] = api_key
    flask_app.config["GEMINI_MODEL"] = model
    runtime = flask_app.extensions["runtime"]

    feedback = runtime.call_gemini_for_feedback(
        question="How do you optimize SQL queries?",
        reference_answer="Start with execution plans, index strategy, and query shape improvements.",
        user_answer="I usually add indexes and avoid selecting extra columns.",
    )

    assert 1 <= feedback["score"] <= 10
    assert isinstance(feedback["feedback"], str) and feedback["feedback"].strip()
    assert isinstance(feedback["improved_answer"], str) and feedback["improved_answer"].strip()
