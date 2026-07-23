.PHONY: build up up-postgres down migrate run-once warm-ozon metrics logs

COMPOSE = docker compose -f docker-compose.prod.yml

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d

# STORAGE_BACKEND=postgres only: also starts the `postgres` service (profile-gated, ADR-0009).
up-postgres:
	$(COMPOSE) --profile postgres up -d

down:
	$(COMPOSE) --profile postgres down

migrate:
	$(COMPOSE) run --rm app alembic upgrade head

run-once:
	$(COMPOSE) run --rm app run-once

warm-ozon:
	$(COMPOSE) run --rm app warm-ozon

metrics:
	$(COMPOSE) run --rm app metrics --last

logs:
	$(COMPOSE) logs -f app
