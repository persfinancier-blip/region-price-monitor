.PHONY: build up down migrate run-once warm-ozon metrics logs

COMPOSE = docker compose -f docker-compose.prod.yml

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

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
