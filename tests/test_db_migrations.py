from app import app as flask_app
from interview_app.db import (
    get_db,
    list_applied_migrations,
    list_known_migrations,
    list_pending_migrations,
    run_migrations,
)


def test_run_migrations_records_versions(tmp_path):
    flask_app.config.update(
        TESTING=True,
        DATABASE=str(tmp_path / "migrations.db"),
    )
    with flask_app.app_context():
        applied = run_migrations()
        expected = [
            "0001_initial_schema",
            "0002_add_suggested_answer",
            "0003_add_topic_color",
        ]
        assert applied == expected

        rows = get_db().execute(
            "SELECT version FROM schema_migrations ORDER BY version ASC"
        ).fetchall()
        assert [row["version"] for row in rows] == expected


def test_run_migrations_is_idempotent(tmp_path):
    flask_app.config.update(
        TESTING=True,
        DATABASE=str(tmp_path / "idempotent.db"),
    )
    with flask_app.app_context():
        first_run = run_migrations()
        second_run = run_migrations()

        assert first_run == [
            "0001_initial_schema",
            "0002_add_suggested_answer",
            "0003_add_topic_color",
        ]
        assert second_run == []


def test_migration_status_helpers(tmp_path):
    flask_app.config.update(
        TESTING=True,
        DATABASE=str(tmp_path / "status.db"),
    )
    with flask_app.app_context():
        assert list_known_migrations() == [
            "0001_initial_schema",
            "0002_add_suggested_answer",
            "0003_add_topic_color",
        ]
        assert list_pending_migrations() == [
            "0001_initial_schema",
            "0002_add_suggested_answer",
            "0003_add_topic_color",
        ]
        assert list_applied_migrations() == []

        run_migrations()

        applied = list_applied_migrations()
        pending = list_pending_migrations()

        assert [version for version, _applied_at in applied] == [
            "0001_initial_schema",
            "0002_add_suggested_answer",
            "0003_add_topic_color",
        ]
        assert pending == []
