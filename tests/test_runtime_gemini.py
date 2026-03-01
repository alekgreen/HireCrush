import requests

from app import app as flask_app


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
