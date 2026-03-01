# Interview Question Repetition Web App

Python Flask web app that:
- generates interview questions using Gemini API,
- stores only unique questions,
- schedules repetition using an Anki-style spaced repetition flow,
- lets you generate more questions in the interface.

## Features

- Gemini-powered generation from a topic/role prompt.
- Structured output JSON schema (`responseJsonSchema`) for predictable parsing.
- Duplicate prevention using normalized content hash + DB unique constraint.
- Model answer support for each interview question.
- "Write your answer" workflow with Gemini scoring + actionable feedback.
- Review queue for due cards with `Again / Hard / Good / Easy`.
- SM-2-like scheduling fields (`repetitions`, `interval_days`, `ease_factor`, `next_review_at`).
- SQLite persistence.

## Setup

1. Run bootstrap script (recommended):

```bash
./setup.sh
```

2. Manual setup (if you prefer):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Optional: create `.env` only if you want to override defaults:

```bash
cp .env.example .env
```

4. Optional `.env` values:

```bash
FLASK_SECRET_KEY=change-this-secret
DATABASE_PATH=interview.db
```

Gemini model/API key can be configured from **Settings** in the app UI (or via env vars if you prefer).

5. Run migrations:

```bash
flask --app app db-upgrade
```

Optional migration inspection commands:

```bash
flask --app app db-status
flask --app app db-history
```

6. Run app:

```bash
python app.py
```

Then open `http://localhost:5000`.

## Run tests

```bash
pytest -q
```

Run live Gemini integration tests explicitly:

```bash
pytest -q --run-integration
```

Integration tests require a valid `GEMINI_API_KEY`.

## Notes

- New cards are due immediately.
- `Again` schedules a quick retry (10 minutes).
- Other grades schedule by interval in days.
- Preferred Gemini models can be selected in `Settings`:
  `gemini-3.1-pro-preview`, `gemini-3-pro-preview`, `gemini-3-flash-preview`,
  `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`,
  `gemini-2.0-flash`, `gemini-2.0-flash-lite`.
- Gemini API key can be stored securely in local OS credential storage via `keyring` from `Settings`.
- If no OS keyring backend is available, the app falls back to `keyrings.alt` local storage (not OS-secure keychain storage).
- Run `./setup.sh` and check the backend summary at the end to confirm which mode is active.
- Optional: set `GEMINI_FALLBACK_MODELS` (comma-separated) for additional automatic model fallback.
- Set `AUTO_GENERATE_ANSWERS=false` if you prefer generating model answers on-demand in review.
