GEMINI_MODEL_FALLBACKS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]

GEMINI_SELECTABLE_MODELS = [
    "gemini-3.1-pro-preview",
    "gemini-3-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
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
    ("indigo", "Indigo"),
    ("cyan", "Cyan"),
    ("lime", "Lime"),
    ("orange", "Orange"),
    ("red", "Red"),
    ("fuchsia", "Fuchsia"),
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
    "indigo": {
        "border": "#c7d2fe",
        "bg": "#eef2ff",
        "text": "#4338ca",
        "border_dark": "#6366f1",
        "bg_dark": "#1e1b4b",
        "text_dark": "#c7d2fe",
    },
    "cyan": {
        "border": "#a5f3fc",
        "bg": "#ecfeff",
        "text": "#0e7490",
        "border_dark": "#22d3ee",
        "bg_dark": "#083344",
        "text_dark": "#a5f3fc",
    },
    "lime": {
        "border": "#bef264",
        "bg": "#f7fee7",
        "text": "#4d7c0f",
        "border_dark": "#84cc16",
        "bg_dark": "#1a2e05",
        "text_dark": "#d9f99d",
    },
    "orange": {
        "border": "#fdba74",
        "bg": "#fff7ed",
        "text": "#c2410c",
        "border_dark": "#f97316",
        "bg_dark": "#431407",
        "text_dark": "#fdba74",
    },
    "red": {
        "border": "#fca5a5",
        "bg": "#fef2f2",
        "text": "#b91c1c",
        "border_dark": "#ef4444",
        "bg_dark": "#450a0a",
        "text_dark": "#fca5a5",
    },
    "fuchsia": {
        "border": "#f5d0fe",
        "bg": "#fdf4ff",
        "text": "#a21caf",
        "border_dark": "#d946ef",
        "bg_dark": "#4a044e",
        "text_dark": "#f5d0fe",
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

QUESTION_TYPE_THEORY = "theory"
QUESTION_TYPE_CODE_REVIEW = "code_review"
QUESTION_TYPES = [
    (QUESTION_TYPE_THEORY, "Theory Q&A"),
    (QUESTION_TYPE_CODE_REVIEW, "Code Review"),
]

CODE_REVIEW_QUESTION_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "question_text": {
                "type": "string",
                "description": "Description of what the candidate should find and fix in the code.",
            },
            "code_snippet": {
                "type": "string",
                "description": "The code containing intentional bugs, anti-patterns, or issues to be fixed.",
            },
            "language": {
                "type": "string",
                "description": "Programming language of the code snippet (e.g. python, javascript, java).",
            },
        },
        "required": ["question_text", "code_snippet", "language"],
    },
    "minItems": 1,
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
