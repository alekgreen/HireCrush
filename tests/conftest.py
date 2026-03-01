from dataclasses import replace

import pytest

from app import app as flask_app
from interview_app.db import get_db, run_migrations


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that call external APIs.",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-integration"):
        return

    skip_integration = pytest.mark.skip(
        reason="Integration tests are skipped by default. Use --run-integration."
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "test.db"
    flask_app.config.update(
        TESTING=True,
        DATABASE=str(db_path),
        GEMINI_API_KEY="test-key",
        AUTO_GENERATE_ANSWERS=False,
        HANDLER_DEPS_OVERRIDE=None,
    )

    with flask_app.app_context():
        run_migrations()
        db = get_db()
        db.execute("DELETE FROM review_feedback")
        db.execute("DELETE FROM review_history")
        db.execute("DELETE FROM questions")
        db.commit()

    with flask_app.test_client() as test_client:
        yield test_client
    flask_app.config["HANDLER_DEPS_OVERRIDE"] = None


@pytest.fixture()
def override_handler_deps():
    def _override(*, home=None, generation=None, review=None, catalog=None):
        base = flask_app.extensions["build_handler_deps"]()
        bundle = replace(
            base,
            home=replace(base.home, **(home or {})),
            generation=replace(base.generation, **(generation or {})),
            review=replace(base.review, **(review or {})),
            catalog=replace(base.catalog, **(catalog or {})),
        )
        flask_app.config["HANDLER_DEPS_OVERRIDE"] = bundle
        return bundle

    yield _override
    flask_app.config["HANDLER_DEPS_OVERRIDE"] = None
