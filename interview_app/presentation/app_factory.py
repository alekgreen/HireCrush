import os

from dotenv import load_dotenv
from flask import Flask

from interview_app.constants import (
    DEFAULT_TOPIC_TAG_COLOR_CODE,
    GEMINI_SELECTABLE_MODELS,
    TOPIC_TAG_COLORS,
    TOPIC_TAG_STYLE_BY_CODE,
)
from interview_app.db import close_db
from interview_app.utils import format_datetime

load_dotenv()


def create_flask_app(import_name: str) -> Flask:
    app = Flask(import_name)
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
    app.config["DATABASE"] = os.getenv("DATABASE_PATH", "interview.db")
    app.config["GEMINI_API_KEY"] = os.getenv("GEMINI_API_KEY", "")
    app.config["GEMINI_MODEL"] = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    app.config["GEMINI_SELECTABLE_MODELS"] = list(GEMINI_SELECTABLE_MODELS)
    app.config["AUTO_GENERATE_ANSWERS"] = (
        os.getenv("AUTO_GENERATE_ANSWERS", "true").strip().lower() in {"1", "true", "yes", "on"}
    )
    app.teardown_appcontext(close_db)

    @app.template_filter("human_datetime")
    def human_datetime_filter(value) -> str:
        return format_datetime(value)

    @app.context_processor
    def inject_topic_tag_style():
        return {
            "topic_tag_styles": TOPIC_TAG_STYLE_BY_CODE,
            "default_topic_tag_color": DEFAULT_TOPIC_TAG_COLOR_CODE,
            "topic_tag_colors": TOPIC_TAG_COLORS,
        }

    return app
