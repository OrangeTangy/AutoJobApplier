# AutoJobApplier Makefile
# Usage: make setup   (first time)
#        make up      (subsequent runs)

.PHONY: setup up down restart logs shell-backend shell-db migrate reset help

## First-time setup: generate secrets + build + start
setup:
	@bash setup.sh

## Start all services (after first setup)
up:
	docker compose up -d

## Stop all services
down:
	docker compose down

## Restart all services
restart:
	docker compose down && docker compose up -d

## Stream logs from all services
logs:
	docker compose logs -f

## Stream backend logs only
logs-backend:
	docker compose logs -f backend

## Run Alembic migrations manually
migrate:
	docker compose exec backend alembic upgrade head

## Open a shell in the backend container
shell-backend:
	docker compose exec backend bash

## Open a psql shell in the database
shell-db:
	docker compose exec db psql -U postgres autojobapplier

## Rebuild images (run after code changes)
build:
	docker compose build --parallel

## DANGER: stop and delete all data volumes
reset:
	@echo "WARNING: This will delete all data. Press Ctrl+C to cancel, Enter to continue."
	@read _confirm
	docker compose down -v

## Run backend tests
test:
	docker compose exec backend pytest tests/ -v --tb=short

## Show help
help:
	@echo "AutoJobApplier commands:"
	@echo "  make setup          First-time setup (generates secrets, builds, starts)"
	@echo "  make up             Start services"
	@echo "  make down           Stop services"
	@echo "  make restart        Restart services"
	@echo "  make logs           Stream all logs"
	@echo "  make migrate        Run database migrations"
	@echo "  make shell-backend  Shell into backend container"
	@echo "  make shell-db       psql shell into database"
	@echo "  make build          Rebuild Docker images"
	@echo "  make test           Run test suite"
	@echo "  make reset          DANGER: wipe all data"
