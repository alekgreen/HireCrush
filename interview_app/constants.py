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

TOPIC_TAG_COLORS = [
    ("blue", "Blue"),
    ("emerald", "Emerald"),
    ("amber", "Amber"),
    ("rose", "Rose"),
    ("violet", "Violet"),
    ("slate", "Slate"),
]
DEFAULT_TOPIC_TAG_COLOR_CODE = "blue"
TOPIC_TAG_COLOR_BY_CODE = {code: label for code, label in TOPIC_TAG_COLORS}
TOPIC_TAG_STYLE_BY_CODE = {
    "blue": {
        "border": "#bfdbfe",
        "bg": "#eff6ff",
        "text": "#1d4ed8",
        "border_dark": "#1d4ed8",
        "bg_dark": "#172554",
        "text_dark": "#bfdbfe",
    },
    "emerald": {
        "border": "#a7f3d0",
        "bg": "#ecfdf5",
        "text": "#047857",
        "border_dark": "#10b981",
        "bg_dark": "#022c22",
        "text_dark": "#a7f3d0",
    },
    "amber": {
        "border": "#fcd34d",
        "bg": "#fffbeb",
        "text": "#b45309",
        "border_dark": "#f59e0b",
        "bg_dark": "#451a03",
        "text_dark": "#fde68a",
    },
    "rose": {
        "border": "#fecdd3",
        "bg": "#fff1f2",
        "text": "#be123c",
        "border_dark": "#e11d48",
        "bg_dark": "#4c0519",
        "text_dark": "#fecdd3",
    },
    "violet": {
        "border": "#ddd6fe",
        "bg": "#f5f3ff",
        "text": "#6d28d9",
        "border_dark": "#8b5cf6",
        "bg_dark": "#2e1065",
        "text_dark": "#ddd6fe",
    },
    "slate": {
        "border": "#cbd5e1",
        "bg": "#f8fafc",
        "text": "#334155",
        "border_dark": "#64748b",
        "bg_dark": "#0f172a",
        "text_dark": "#cbd5e1",
    },
}

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
