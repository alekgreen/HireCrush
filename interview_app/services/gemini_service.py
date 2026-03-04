import base64
import json

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


def build_model_candidates(
    configured_model: str,
    env_fallback_models: str,
    default_models: list[str],
) -> list[str]:
    configured = configured_model.strip()
    extras = [m.strip() for m in env_fallback_models.split(",") if m.strip()]

    candidates = []
    for model in [configured, *extras, *default_models]:
        if model and model not in candidates:
            candidates.append(model)
    return candidates


def generate_json(
    prompt: str,
    response_schema: dict,
    temperature: float,
    api_key: str,
    model_candidates: list[str],
    parse_json_from_text_fn,
    http_client,
):
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    tried_models = []
    for model in model_candidates:
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

        response = http_client.post(endpoint, json=payload, timeout=30)
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
        parsed = parse_json_from_text_fn(raw)
        if parsed is not None:
            return parsed, model

    tried_list = ", ".join(tried_models) if tried_models else "(none)"
    raise RuntimeError(
        "No compatible Gemini model found for this API key. "
        f"Tried models: {tried_list}"
    )


def _iter_stream_text_pieces(response):
    emitted_text = ""
    for raw_line in response.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue
        line = str(raw_line).strip()
        if not line or not line.startswith("data:"):
            continue
        payload_text = line[5:].strip()
        if not payload_text or payload_text == "[DONE]":
            continue
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            continue

        for candidate in payload.get("candidates", []):
            parts = candidate.get("content", {}).get("parts", [])
            for part in parts:
                text = str(part.get("text", ""))
                if not text:
                    continue

                if text.startswith(emitted_text):
                    delta = text[len(emitted_text):]
                    emitted_text = text
                elif emitted_text.endswith(text):
                    delta = ""
                else:
                    max_overlap = 0
                    overlap_limit = min(len(emitted_text), len(text))
                    for idx in range(1, overlap_limit + 1):
                        if emitted_text.endswith(text[:idx]):
                            max_overlap = idx
                    delta = text[max_overlap:]
                    emitted_text += delta

                if delta:
                    yield delta


def stream_text(
    prompt: str,
    temperature: float,
    api_key: str,
    model_candidates: list[str],
    http_client,
):
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    tried_models = []
    for model in model_candidates:
        tried_models.append(model)
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:streamGenerateContent?alt=sse&key={api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        }

        response = http_client.post(endpoint, json=payload, timeout=90, stream=True)
        if response.status_code == 404:
            continue
        response.raise_for_status()

        pieces = _iter_stream_text_pieces(response)
        try:
            first_piece = next(pieces)
        except StopIteration:
            close_fn = getattr(response, "close", None)
            if callable(close_fn):
                close_fn()
            continue

        def stream():
            try:
                yield first_piece
                for piece in pieces:
                    if piece:
                        yield piece
            finally:
                close_fn = getattr(response, "close", None)
                if callable(close_fn):
                    close_fn()

        return stream(), model

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


def transcribe_audio(
    audio_bytes: bytes,
    mime_type: str,
    api_key: str,
    model_candidates: list[str],
    http_client,
    normalize_audio_mime_type_fn=normalize_audio_mime_type,
    max_inline_audio_bytes: int = MAX_INLINE_AUDIO_BYTES,
):
    if not audio_bytes:
        raise RuntimeError("Audio file is empty.")
    if len(audio_bytes) > max_inline_audio_bytes:
        raise RuntimeError("Audio file is too large. Keep uploads under 19 MB.")

    normalized_mime_type = normalize_audio_mime_type_fn(mime_type)
    if normalized_mime_type is None:
        raise RuntimeError("Unsupported audio format.")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    encoded_audio = base64.b64encode(audio_bytes).decode("ascii")
    prompt = (
        "Transcribe this audio clip. Return only the transcript text, "
        "with punctuation and no additional commentary."
    )

    tried_models = []
    for model in model_candidates:
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

        response = http_client.post(endpoint, json=payload, timeout=60)
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
            return "\n".join(transcript_parts), model

    tried_list = ", ".join(tried_models) if tried_models else "(none)"
    raise RuntimeError(
        "No compatible Gemini model found for this API key. "
        f"Tried models: {tried_list}"
    )
