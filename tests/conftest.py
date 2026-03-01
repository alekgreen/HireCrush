from dataclasses import replace

import pytest

import app as app_module


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
    app_module.app.config.update(
        TESTING=True,
        DATABASE=str(db_path),
        GEMINI_API_KEY="test-key",
        AUTO_GENERATE_ANSWERS=False,
        HANDLER_DEPS_OVERRIDE=None,
    )

    with app_module.app.app_context():
        app_module.run_migrations()
        db = app_module.get_db()
        db.execute("DELETE FROM review_feedback")
        db.execute("DELETE FROM review_history")
        db.execute("DELETE FROM questions")
        db.commit()

    with app_module.app.test_client() as test_client:
        yield test_client
    app_module.app.config["HANDLER_DEPS_OVERRIDE"] = None


@pytest.fixture()
def override_handler_deps():
    def _override(*, home=None, generation=None, review=None, catalog=None):
        base = app_module.build_handler_deps()
        bundle = replace(
            base,
            home=replace(base.home, **(home or {})),
            generation=replace(base.generation, **(generation or {})),
            review=replace(base.review, **(review or {})),
            catalog=replace(base.catalog, **(catalog or {})),
        )
        app_module.app.config["HANDLER_DEPS_OVERRIDE"] = bundle
        return bundle

    yield _override
    app_module.app.config["HANDLER_DEPS_OVERRIDE"] = None
