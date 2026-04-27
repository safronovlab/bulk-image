.PHONY: help build run stop clean test lint shell logs

APP_NAME := bulk-color-tool
CONTAINER_NAME := bulk-color-api
DOCKER_COMPOSE := docker compose
PORT := 8000

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

build: ## Build Docker image
	docker build -t $(APP_NAME) .

run: ## Run container with docker-compose
	$(DOCKER_COMPOSE) up -d

stop: ## Stop container
	$(DOCKER_COMPOSE) down

restart: stop run ## Restart container

clean: stop ## Stop and remove container + volumes
	$(DOCKER_COMPOSE) down -v

logs: ## Show container logs
	$(DOCKER_COMPOSE) logs -f

shell: ## Open shell in running container
	docker exec -it $(CONTAINER_NAME) /bin/bash

health: ## Check API health
	curl -sf http://localhost:$(PORT)/api/health && echo " OK" || echo " FAIL"

test: ## Run tests inside container
	$(DOCKER_COMPOSE) run --rm api python -m pytest app/ -v

lint: ## Run basic syntax check
	$(DOCKER_COMPOSE) run --rm api python -m py_compile app/main.py

ps: ## Show running containers
	$(DOCKER_COMPOSE) ps

prune: ## Remove all unused Docker data (CAUTION)
	docker system prune -f

status: health ps ## Show health and container status
