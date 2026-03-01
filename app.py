from interview_app.constants import QUESTIONS_JSON_SCHEMA
from interview_app.db import get_db, run_migrations
from interview_app.entrypoints.web import create_app
from interview_app.repository import (
    get_generation_context_questions,
    get_question_by_id,
    save_feedback,
)
from interview_app.utils import (
    clean_question_text,
    iso,
    now_utc,
    parse_iso,
    question_hash,
)

app = create_app()
_runtime = app.extensions["runtime"]
build_handler_deps = app.extensions["build_handler_deps"]


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
