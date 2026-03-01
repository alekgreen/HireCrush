# Development Guide

## Prerequisites

- Python 3.10+
- `pip` and `venv`
- Docker / Docker Compose (optional)

## Local development setup

Recommended:

```bash
make setup
```

Manual:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional environment config:

```bash
cp .env.example .env
```

## Run app locally

```bash
make migrate-local
make run-local
```

Helpful migration commands:

```bash
make db-status-local
make db-history-local
```

## Tests

Fast/local tests:

```bash
make test
```

Gemini integration tests:

```bash
make test-integration
```

Integration tests require `GEMINI_API_KEY`.

## Docker workflows

Build image:

```bash
make docker-build
```

Run migrations in container (named volume for DB persistence):

```bash
make docker-migrate
```

Run app container:

```bash
make docker-run
```

If `.env` exists, Make automatically passes it to Docker commands.

## Docker Compose workflows

Build:

```bash
make compose-build
```

Run migrations:

```bash
make compose-migrate
```

Start app:

```bash
make compose-up
```

Stop:

```bash
make compose-down
```

## Project structure

- `app.py`: app entrypoint.
- `interview_app/entrypoints/web.py`: Flask app factory and CLI commands.
- `interview_app/presentation/`: routes and dependency wiring.
- `interview_app/services/`: domain/application services.
- `interview_app/adapters/persistence/sqlite/`: repositories.
- `interview_app/migrations/`: migration files and migration registry.
- `tests/`: unit and integration tests.

## Adding a DB migration

1. Add a new migration file in `interview_app/migrations/versions/` with `VERSION` and `apply(db)` function.
2. Register it in `interview_app/migrations/versions/__init__.py` by importing it and appending to `MIGRATIONS`.
3. Run:

```bash
flask --app app db-upgrade
pytest -q tests/test_db_migrations.py
```
