import hashlib
import json
import re
from datetime import datetime, timezone


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str)


def normalize_text(text: str) -> str:
    compact = re.sub(r"\\s+", " ", text.strip().lower())
    compact = re.sub(r"^[\\d\\-\\.\\)\\s]+", "", compact)
    return compact


def question_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def clean_question_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^[\\d\\-\\.\\)\\s]+", "", cleaned)
    cleaned = re.sub(r"\\s+", " ", cleaned)
    return cleaned


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

    match = re.search(r"\\[[\\s\\S]+\\]", text)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass

    lines = [line.strip(" -*\\t") for line in text.splitlines()]
    return [line for line in lines if line.endswith("?")]


def parse_json_from_text(raw_text: str):
    text = (raw_text or "").strip()
    if not text:
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    for pattern in (r"\\[[\\s\\S]+\\]", r"\\{[\\s\\S]+\\}"):
        match = re.search(pattern, text)
        if not match:
            continue
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
    return None
