GEMINI_MODEL_FALLBACKS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]

GENERATION_LANGUAGES = [
    ("en", "English"),
    ("ru", "Russian"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("de", "German"),
    ("pt", "Portuguese"),
    ("it", "Italian"),
    ("nl", "Dutch"),
    ("pl", "Polish"),
    ("tr", "Turkish"),
    ("uk", "Ukrainian"),
    ("ar", "Arabic"),
    ("he", "Hebrew"),
    ("hi", "Hindi"),
    ("bn", "Bengali"),
    ("ur", "Urdu"),
    ("fa", "Persian"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("zh", "Chinese (Simplified)"),
    ("zh-tw", "Chinese (Traditional)"),
    ("vi", "Vietnamese"),
    ("th", "Thai"),
    ("id", "Indonesian"),
    ("ms", "Malay"),
    ("sw", "Swahili"),
    ("cs", "Czech"),
    ("ro", "Romanian"),
    ("hu", "Hungarian"),
    ("el", "Greek"),
    ("sv", "Swedish"),
    ("no", "Norwegian"),
    ("da", "Danish"),
    ("fi", "Finnish"),
]

DEFAULT_GENERATION_LANGUAGE_CODE = "en"
GENERATION_LANGUAGE_BY_CODE = {code: label for code, label in GENERATION_LANGUAGES}

QUESTIONS_JSON_SCHEMA = {
    "type": "array",
    "items": {
        "type": "string",
        "description": "A single interview question. End the string with a question mark.",
    },
    "minItems": 1,
}

ANSWER_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {
            "type": "string",
            "description": "A strong interview answer in clear and concise language.",
        }
    },
    "required": ["answer"],
}

FEEDBACK_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "How good the user answer is for an interview setting.",
        },
        "feedback": {"type": "string", "description": "Direct, actionable feedback."},
        "improved_answer": {
            "type": "string",
            "description": "A stronger example answer the user can study.",
        },
        "strengths": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["score", "feedback", "improved_answer"],
}
