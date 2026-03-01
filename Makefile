APP_IMAGE ?= interview-app
APP_CONTAINER_PORT ?= 5000
APP_HOST_PORT ?= 5000
APP_VOLUME ?= interview_data
ENV_FILE ?= .env

DOCKER_ENV_FILE := $(if $(wildcard $(ENV_FILE)),--env-file $(ENV_FILE),)

.PHONY: help \
	setup run-local migrate-local db-status-local db-history-local test test-integration \
	docker-build docker-volume docker-run docker-migrate docker-status docker-history \
	compose-build compose-up compose-down compose-migrate compose-status compose-history

help:
	@echo "Local:"
	@echo "  make setup             # bootstrap local venv and dependencies"
	@echo "  make migrate-local     # run DB migrations locally"
	@echo "  make run-local         # run Flask app locally"
	@echo "  make db-status-local   # show local migration status"
	@echo "  make db-history-local  # show local migration history"
	@echo "  make test              # run unit test suite"
	@echo "  make test-integration  # run integration tests"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build      # build image"
	@echo "  make docker-migrate    # run migrations in container"
	@echo "  make docker-run        # run app in container"
	@echo "  make docker-status     # migration status in container"
	@echo "  make docker-history    # migration history in container"
	@echo ""
	@echo "Docker Compose:"
	@echo "  make compose-build     # build compose image"
	@echo "  make compose-migrate   # run migrations with compose"
	@echo "  make compose-up        # start compose app"
	@echo "  make compose-down      # stop compose app"
	@echo "  make compose-status    # migration status with compose"
	@echo "  make compose-history   # migration history with compose"

setup:
	./setup.sh

run-local:
	.venv/bin/python app.py

migrate-local:
	.venv/bin/flask --app app db-upgrade

db-status-local:
	.venv/bin/flask --app app db-status

db-history-local:
	.venv/bin/flask --app app db-history

test:
	.venv/bin/pytest -q

test-integration:
	.venv/bin/pytest -q --run-integration

docker-build:
	docker build -t $(APP_IMAGE) .

docker-volume:
	docker volume create $(APP_VOLUME)

docker-run: docker-build docker-volume
	docker run --rm $(DOCKER_ENV_FILE) -p $(APP_HOST_PORT):$(APP_CONTAINER_PORT) -v $(APP_VOLUME):/app/data $(APP_IMAGE)

docker-migrate: docker-build docker-volume
	docker run --rm $(DOCKER_ENV_FILE) -v $(APP_VOLUME):/app/data $(APP_IMAGE) flask --app app db-upgrade

docker-status: docker-build docker-volume
	docker run --rm $(DOCKER_ENV_FILE) -v $(APP_VOLUME):/app/data $(APP_IMAGE) flask --app app db-status

docker-history: docker-build docker-volume
	docker run --rm $(DOCKER_ENV_FILE) -v $(APP_VOLUME):/app/data $(APP_IMAGE) flask --app app db-history

compose-build:
	docker compose build

compose-up:
	docker compose up

compose-down:
	docker compose down

compose-migrate:
	docker compose run --rm app flask --app app db-upgrade

compose-status:
	docker compose run --rm app flask --app app db-status

compose-history:
	docker compose run --rm app flask --app app db-history
