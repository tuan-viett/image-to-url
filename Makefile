.PHONY: help up down logs build restart ps exec-api exec-worker exec-mysql shell-api shell-worker migrate seed e2e clean reset

help:
	@echo "ImageURL — Make targets"
	@echo "  make up        Build and start all services in background"
	@echo "  make down      Stop all services"
	@echo "  make logs      Tail logs from all services"
	@echo "  make build     Rebuild images"
	@echo "  make ps        Show running containers"
	@echo "  make shell-api Open bash in api container"
	@echo "  make exec-api  Execute a command in api container (use CMD=...)"
	@echo "  make migrate   Run alembic upgrade head"
	@echo "  make seed      Run database seeding"
	@echo "  make e2e       Run smoke E2E test script"
	@echo "  make reset     Drop all data (volumes + containers) and start fresh"

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

build:
	docker compose build

restart:
	docker compose restart

ps:
	docker compose ps

shell-api:
	docker compose exec api bash

exec-api:
	docker compose exec api $(CMD)

shell-worker:
	docker compose exec worker bash

exec-mysql:
	docker compose exec mysql mysql -uimageurl -p$$MYSQL_PASSWORD imageurl

migrate:
	docker compose exec api alembic upgrade head

seed:
	docker compose exec api python -m app.seed

e2e:
	@bash scripts/smoke_test.sh

reset:
	docker compose down -v
	docker compose up -d --build