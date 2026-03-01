import app as app_module
from interview_app.db import run_migrations


def test_run_migrations_records_versions(tmp_path):
    app_module.app.config.update(
        TESTING=True,
        DATABASE=str(tmp_path / "migrations.db"),
    )
    with app_module.app.app_context():
        applied = run_migrations()
        assert applied == [
            "0001_initial_schema",
            "0002_add_suggested_answer",
            "0003_add_topic_color",
        ]

        rows = app_module.get_db().execute(
            "SELECT version FROM schema_migrations ORDER BY version ASC"
        ).fetchall()
        assert [row["version"] for row in rows] == applied


def test_run_migrations_is_idempotent(tmp_path):
    app_module.app.config.update(
        TESTING=True,
        DATABASE=str(tmp_path / "idempotent.db"),
    )
    with app_module.app.app_context():
        first_run = run_migrations()
        second_run = run_migrations()

        assert first_run == [
            "0001_initial_schema",
            "0002_add_suggested_answer",
            "0003_add_topic_color",
        ]
        assert second_run == []

