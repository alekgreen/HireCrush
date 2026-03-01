from __future__ import annotations

try:
    import keyring
    from keyring.errors import KeyringError
except Exception:  # pragma: no cover - optional dependency
    keyring = None

    class KeyringError(Exception):
        pass


_SERVICE_NAME = "interview-repetition"
_GEMINI_API_KEY_ACCOUNT = "gemini_api_key"
_BACKEND_INIT_DONE = False


def _backend_priority(backend) -> float:
    try:
        return float(getattr(backend, "priority", 0))
    except Exception:
        return 0.0


def _is_keyrings_alt_backend(backend) -> bool:
    module_name = str(getattr(getattr(backend, "__class__", None), "__module__", ""))
    return module_name.startswith("keyrings.alt")


def _configure_backend_if_needed() -> None:
    global _BACKEND_INIT_DONE
    if _BACKEND_INIT_DONE or keyring is None:
        return
    _BACKEND_INIT_DONE = True

    try:
        current_backend = keyring.get_keyring()
    except Exception:
        return
    if _backend_priority(current_backend) > 0:
        return

    try:
        from keyrings.alt.file import PlaintextKeyring
    except Exception:
        return

    try:
        keyring.set_keyring(PlaintextKeyring())
    except Exception:
        return


def _active_backend():
    if keyring is None:
        return None
    _configure_backend_if_needed()
    try:
        backend = keyring.get_keyring()
    except Exception:
        return None
    if _backend_priority(backend) <= 0:
        return None
    return backend


def keyring_available() -> bool:
    return _active_backend() is not None


def backend_mode() -> str:
    backend = _active_backend()
    if backend is None:
        return "unavailable"
    if _is_keyrings_alt_backend(backend):
        return "keyrings_alt"
    return "secure"


def secure_backend_available() -> bool:
    return backend_mode() == "secure"


def using_keyrings_alt_fallback() -> bool:
    return backend_mode() == "keyrings_alt"


def get_gemini_api_key() -> str | None:
    if _active_backend() is None:
        return None
    try:
        value = keyring.get_password(_SERVICE_NAME, _GEMINI_API_KEY_ACCOUNT)
    except KeyringError:
        return None
    except Exception:
        return None

    normalized = str(value or "").strip()
    return normalized or None


def set_gemini_api_key(api_key: str) -> tuple[bool, str | None]:
    normalized = str(api_key).strip()
    if not normalized:
        return False, "Gemini API key cannot be empty."
    if _active_backend() is None:
        return (
            False,
            "Token storage backend is unavailable. Install a recommended keyring backend or `keyrings.alt`.",
        )
    try:
        keyring.set_password(_SERVICE_NAME, _GEMINI_API_KEY_ACCOUNT, normalized)
    except KeyringError as exc:
        return False, f"Could not store Gemini API key securely: {exc}"
    except Exception as exc:
        return False, f"Could not store Gemini API key securely: {exc}"
    return True, None


def clear_gemini_api_key() -> tuple[bool, str | None]:
    if _active_backend() is None:
        return (
            False,
            "Token storage backend is unavailable. Install a recommended keyring backend or `keyrings.alt`.",
        )
    try:
        keyring.delete_password(_SERVICE_NAME, _GEMINI_API_KEY_ACCOUNT)
    except KeyringError:
        return True, None
    except Exception as exc:
        return False, f"Could not clear Gemini API key from secure storage: {exc}"
    return True, None
