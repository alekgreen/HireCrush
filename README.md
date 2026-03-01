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

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Create env file:

```bash
cp .env.example .env
```

3. Set your Gemini API key in `.env`:

```bash
GEMINI_API_KEY=your_real_key
GEMINI_MODEL=gemini-2.5-flash
AUTO_GENERATE_ANSWERS=true
```

4. Run app:

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
- Change `GEMINI_MODEL` in `.env` if you want a different model.
- Optional: set `GEMINI_FALLBACK_MODELS` (comma-separated) for additional automatic model fallback.
- Set `AUTO_GENERATE_ANSWERS=false` if you prefer generating model answers on-demand in review.
