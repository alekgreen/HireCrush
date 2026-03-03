from app import app as flask_app
from interview_app.db import get_db

ALL_MODELS = [
    "gemini-3.1-pro-preview",
    "gemini-3-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]


def _set_store_hooks(
    monkeypatch,
    *,
    resolve_api_key=lambda: None,
    persist_api_key=lambda _value: (True, None),
    clear_api_key=lambda: (True, None),
    store_available=lambda: True,
    store_mode=lambda: "secure",
    uses_alt_fallback=lambda: False,
):
    monkeypatch.setitem(flask_app.extensions, "resolve_gemini_api_key_fn", resolve_api_key)
    monkeypatch.setitem(flask_app.extensions, "persist_gemini_api_key_fn", persist_api_key)
    monkeypatch.setitem(flask_app.extensions, "clear_gemini_api_key_fn", clear_api_key)
    monkeypatch.setitem(
        flask_app.extensions,
        "gemini_api_key_store_available_fn",
        store_available,
    )
    monkeypatch.setitem(
        flask_app.extensions,
        "gemini_api_key_store_mode_fn",
        store_mode,
    )
    monkeypatch.setitem(
        flask_app.extensions,
        "gemini_api_key_store_uses_alt_fallback_fn",
        uses_alt_fallback,
    )


def test_settings_route_renders_model_options(client, monkeypatch):
    _set_store_hooks(monkeypatch, resolve_api_key=lambda: None)

    response = client.get("/settings")
    body = response.data.decode("utf-8")

    assert response.status_code == 200
    assert "Settings" in body
    for model in ALL_MODELS:
        assert model in body


def test_settings_route_saves_selected_model(client, monkeypatch):
    _set_store_hooks(monkeypatch, resolve_api_key=lambda: None)

    response = client.post(
        "/settings",
        data={"gemini_model": "gemini-2.5-pro"},
        follow_redirects=True,
    )
    body = response.data.decode("utf-8")

    assert response.status_code == 200
    assert "Saved Gemini model: gemini-2.5-pro" in body
    assert flask_app.config["GEMINI_MODEL"] == "gemini-2.5-pro"

    with flask_app.app_context():
        row = get_db().execute(
            "SELECT value FROM app_settings WHERE key = ?",
            ("gemini_model",),
        ).fetchone()
    assert row["value"] == "gemini-2.5-pro"


def test_settings_route_rejects_invalid_model(client, monkeypatch):
    _set_store_hooks(monkeypatch, resolve_api_key=lambda: None)

    response = client.post(
        "/settings",
        data={"gemini_model": "gemini-not-real"},
        follow_redirects=True,
    )
    body = response.data.decode("utf-8")

    assert response.status_code == 200
    assert "Selected Gemini model is invalid." in body


def test_settings_route_saves_api_key_in_secure_store(client, monkeypatch):
    captured = {}

    def fake_set_gemini_api_key(value):
        captured["token"] = value
        return True, None

    _set_store_hooks(
        monkeypatch,
        resolve_api_key=lambda: "stored-token",
        persist_api_key=fake_set_gemini_api_key,
        uses_alt_fallback=lambda: False,
        store_mode=lambda: "secure",
    )

    response = client.post(
        "/settings",
        data={
            "gemini_model": "gemini-2.5-flash",
            "gemini_api_key": "secret-value",
        },
        follow_redirects=True,
    )
    body = response.data.decode("utf-8")

    assert response.status_code == 200
    assert captured["token"] == "secret-value"
    assert "Gemini API key saved in secure local storage." in body
    assert flask_app.config["GEMINI_API_KEY"] == "secret-value"


def test_settings_route_keeps_api_key_in_runtime_when_secure_store_fails(client, monkeypatch):
    _set_store_hooks(
        monkeypatch,
        resolve_api_key=lambda: None,
        persist_api_key=lambda _value: (False, "Secure token storage is unavailable."),
        uses_alt_fallback=lambda: False,
        store_available=lambda: False,
    )

    response = client.post(
        "/settings",
        data={
            "gemini_model": "gemini-2.5-flash",
            "gemini_api_key": "runtime-only-token",
        },
        follow_redirects=True,
    )
    body = response.data.decode("utf-8")

    assert response.status_code == 200
    assert "active for this running app only" in body
    assert flask_app.config["GEMINI_API_KEY"] == "runtime-only-token"


def test_settings_route_saves_api_key_in_keyrings_alt_fallback(client, monkeypatch):
    _set_store_hooks(
        monkeypatch,
        resolve_api_key=lambda: "stored-token",
        persist_api_key=lambda _value: (True, None),
        uses_alt_fallback=lambda: True,
        store_mode=lambda: "keyrings_alt",
    )

    response = client.post(
        "/settings",
        data={
            "gemini_model": "gemini-2.5-flash",
            "gemini_api_key": "fallback-token",
        },
        follow_redirects=True,
    )
    body = response.data.decode("utf-8")

    assert response.status_code == 200
    assert "keyrings.alt local fallback storage" in body
    assert flask_app.config["GEMINI_API_KEY"] == "fallback-token"


def test_settings_route_database_mode_does_not_set_process_global_api_key(client, monkeypatch):
    original_key = flask_app.config["GEMINI_API_KEY"]

    _set_store_hooks(
        monkeypatch,
        resolve_api_key=lambda: None,
        persist_api_key=lambda _value: (False, "Encrypted storage unavailable."),
        store_mode=lambda: "database_encrypted",
        store_available=lambda: False,
    )

    response = client.post(
        "/settings",
        data={
            "gemini_model": "gemini-2.5-flash",
            "gemini_api_key": "tenant-secret-key",
        },
        follow_redirects=True,
    )
    body = response.data.decode("utf-8")

    assert response.status_code == 200
    assert "Encrypted storage unavailable." in body
    assert flask_app.config["GEMINI_API_KEY"] == original_key
