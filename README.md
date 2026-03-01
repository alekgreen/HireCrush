# HireCrush

Interview prep app

## Quick start

Optional config (for all launch modes):

```bash
cp .env.example .env
```

Open the app at `http://localhost:5000`.

### Easiest: use Make

```bash
make setup
make migrate-local
make run-local
```

Docker with Make:

```bash
make docker-migrate
make docker-run
```

Docker Compose with Make:

```bash
make compose-migrate
make compose-up
```

### Option 1: Local Python venv

```bash
./setup.sh
source .venv/bin/activate
flask --app app db-upgrade
python app.py
```

### Option 2: Docker

```bash
docker build -t interview-app .
docker volume create interview_data
docker run --rm -v interview_data:/app/data interview-app flask --app app db-upgrade
docker run --rm -p 5000:5000 -v interview_data:/app/data interview-app
```

If you created `.env`, pass it with `--env-file .env` on both `docker run` commands.

### Option 3: Docker Compose

```bash
docker compose up --build -d
docker compose run --rm app flask --app app db-upgrade
```

Stop compose mode:

```bash
docker compose down
```

## Migration commands

Local:

```bash
make db-status-local
make db-history-local

flask --app app db-status
flask --app app db-history
```

Docker:

```bash
make docker-status
make docker-history

docker run --rm -v interview_data:/app/data interview-app flask --app app db-status
docker run --rm -v interview_data:/app/data interview-app flask --app app db-history
```

Docker Compose:

```bash
make compose-status
make compose-history

docker compose run --rm app flask --app app db-status
docker compose run --rm app flask --app app db-history
```

## Tests

```bash
make test
make test-integration

pytest -q
pytest -q --run-integration
```

`--run-integration` requires a valid `GEMINI_API_KEY`.

## Developer docs

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).
