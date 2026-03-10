import requests

from app import app as flask_app
from interview_app.db import get_db
from interview_app.services import gemini_service

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

    transcript = runtime.call_gemini_for_transcription(b"fake-audio", "audio/webm")

    assert transcript == "This is a transcript."
    assert len(calls) >= 2
    first_payload = calls[0][1]
    inline_data = first_payload["contents"][0]["parts"][1]["inline_data"]
    assert inline_data["mime_type"] == "audio/webm"
    assert inline_data["data"]
    assert flask_app.config["LAST_WORKING_GEMINI_MODEL"] in (
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    )


def test_normalize_audio_mime_type_accepts_compressed_recorder_formats():
    assert gemini_service.normalize_audio_mime_type("audio/webm") == "audio/webm"
    assert gemini_service.normalize_audio_mime_type("audio/webm;codecs=opus") == "audio/webm"
    assert gemini_service.normalize_audio_mime_type("audio/mp4") == "audio/mp4"
    assert gemini_service.normalize_audio_mime_type("audio/x-m4a") == "audio/m4a"
    assert gemini_service.normalize_audio_mime_type("audio/ogg;codecs=opus") == "audio/ogg"


def test_call_gemini_retries_transient_503_then_falls_back_model(monkeypatch, client):
    class FakeResponse:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self.reason = "Service Unavailable" if status_code == 503 else "OK"
            self._payload = payload or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(response=self)

        def json(self):
            return self._payload

    calls_by_model = {"gemini-3-flash": 0, "gemini-2.5-flash": 0}

    def fake_post(url, json, timeout):
        if "gemini-3-flash:" in url:
            calls_by_model["gemini-3-flash"] += 1
            return FakeResponse(503)
        if "gemini-2.5-flash:" in url:
            calls_by_model["gemini-2.5-flash"] += 1
            return FakeResponse(
                200,
                {
                    "candidates": [
                        {"content": {"parts": [{"text": '["Fallback model worked?"]'}]}}
                    ]
                },
            )
        return FakeResponse(404)

    monkeypatch.setattr(requests, "post", fake_post)
    flask_app.config["GEMINI_API_KEY"] = "test-key"
    flask_app.config["GEMINI_MODEL"] = "gemini-3-flash"
    runtime = flask_app.extensions["runtime"]

    questions = runtime.call_gemini_for_questions("backend", 1)

    assert questions == ["Fallback model worked?"]
    assert calls_by_model["gemini-3-flash"] == 3
    assert calls_by_model["gemini-2.5-flash"] == 1
    assert flask_app.config["LAST_WORKING_GEMINI_MODEL"] == "gemini-2.5-flash"


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


def test_stream_answer_for_question_retries_transient_503_then_falls_back_model(monkeypatch, client):
    class FakeResponse:
        def __init__(self, status_code, lines=None):
            self.status_code = status_code
            self.reason = "Service Unavailable" if status_code == 503 else "OK"
            self._lines = lines or []

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(response=self)

        def iter_lines(self, decode_unicode=True):
            for line in self._lines:
                yield line

        def close(self):
            return None

    calls_by_model = {"gemini-3-flash": 0, "gemini-2.5-flash": 0}

    def fake_post(url, json, timeout, stream=False):
        assert stream is True
        if "gemini-3-flash:" in url:
            calls_by_model["gemini-3-flash"] += 1
            return FakeResponse(503)
        if "gemini-2.5-flash:" in url:
            calls_by_model["gemini-2.5-flash"] += 1
            return FakeResponse(
                200,
                [
                    'data: {"candidates":[{"content":{"parts":[{"text":"Fallback streaming answer."}]}}]}',
                ],
            )
        return FakeResponse(404)

    monkeypatch.setattr(requests, "post", fake_post)
    flask_app.config["GEMINI_API_KEY"] = "test-key"
    flask_app.config["GEMINI_MODEL"] = "gemini-3-flash"
    runtime = flask_app.extensions["runtime"]
    question_id = insert_question("Explain replication lag.")

    with flask_app.app_context():
        chunks = list(runtime.stream_answer_for_question(question_id))

    assert "".join(chunks) == "Fallback streaming answer."
    assert calls_by_model["gemini-3-flash"] == 3
    assert calls_by_model["gemini-2.5-flash"] == 1
    assert flask_app.config["LAST_WORKING_GEMINI_MODEL"] == "gemini-2.5-flash"
