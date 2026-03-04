import requests

from app import app as flask_app
from interview_app.db import get_db

from tests.support import insert_question


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
    flask_app.config["GEMINI_API_KEY"] = "test-key"
    flask_app.config["GEMINI_MODEL"] = "gemini-3-flash"
    runtime = flask_app.extensions["runtime"]

    questions = runtime.call_gemini_for_questions("backend", 1)

    assert questions == ["What is dependency injection?"]
    assert len(calls) >= 2
    first_payload = calls[0][1]
    assert first_payload["generationConfig"]["responseMimeType"] == "application/json"
    assert "responseJsonSchema" in first_payload["generationConfig"]
    prompt_text = first_payload["contents"][0]["parts"][0]["text"]
    assert "Language: English" in prompt_text
    assert flask_app.config["LAST_WORKING_GEMINI_MODEL"] in (
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    )


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
    flask_app.config["GEMINI_API_KEY"] = "test-key"
    flask_app.config["GEMINI_MODEL"] = "gemini-3-flash"
    runtime = flask_app.extensions["runtime"]

    transcript = runtime.call_gemini_for_transcription(b"fake-audio", "audio/wav")

    assert transcript == "This is a transcript."
    assert len(calls) >= 2
    first_payload = calls[0][1]
    inline_data = first_payload["contents"][0]["parts"][1]["inline_data"]
    assert inline_data["mime_type"] == "audio/wav"
    assert inline_data["data"]
    assert flask_app.config["LAST_WORKING_GEMINI_MODEL"] in (
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    )


def test_stream_answer_for_question_streams_and_persists_answer(monkeypatch, client):
    class FakeResponse:
        def __init__(self, status_code, lines):
            self.status_code = status_code
            self.reason = "Not Found" if status_code == 404 else "OK"
            self._lines = lines
            self.closed = False

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(response=self)

        def iter_lines(self, decode_unicode=True):
            for line in self._lines:
                yield line

        def close(self):
            self.closed = True

    calls = []

    def fake_post(url, json, timeout, stream=False):
        calls.append((url, json, timeout, stream))
        return FakeResponse(
            200,
            [
                'data: {"candidates":[{"content":{"parts":[{"text":"Eventual consistency means "}]}}]}',
                'data: {"candidates":[{"content":{"parts":[{"text":"replicas converge over time."}]}}]}',
            ],
        )

    monkeypatch.setattr(requests, "post", fake_post)
    flask_app.config["GEMINI_API_KEY"] = "test-key"
    flask_app.config["GEMINI_MODEL"] = "gemini-2.5-flash"
    runtime = flask_app.extensions["runtime"]
    question_id = insert_question("Explain eventual consistency.")

    with flask_app.app_context():
        chunks = list(runtime.stream_answer_for_question(question_id))
        stored = get_db().execute(
            "SELECT suggested_answer FROM questions WHERE id = ?",
            (question_id,),
        ).fetchone()

    assert "".join(chunks) == "Eventual consistency means replicas converge over time."
    assert stored["suggested_answer"] == "Eventual consistency means replicas converge over time."
    assert calls
    assert calls[0][3] is True
    assert ":streamGenerateContent?alt=sse&key=test-key" in calls[0][0]
    assert flask_app.config["LAST_WORKING_GEMINI_MODEL"] == "gemini-2.5-flash"


def test_stream_answer_for_question_uses_existing_answer_without_api_call(monkeypatch, client):
    def fail_post(*_args, **_kwargs):
        raise AssertionError("API call should not be made when answer already exists.")

    monkeypatch.setattr(requests, "post", fail_post)
    runtime = flask_app.extensions["runtime"]
    question_id = insert_question(
        "Explain read replicas.",
        suggested_answer="Read replicas scale read traffic.",
    )

    with flask_app.app_context():
        chunks = list(runtime.stream_answer_for_question(question_id))

    assert chunks == ["Read replicas scale read traffic."]
