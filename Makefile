.PHONY: help up down test-backend test-worker test-frontend test-all lint-backend lint-worker lint-frontend lint-all format

VENV ?= .venv
PYTHON ?= $(VENV)/bin/python3
PYTEST ?= $(VENV)/bin/pytest
RUFF ?= $(VENV)/bin/ruff
DOCKER_NODE ?= docker run --rm -u $(shell id -u):$(shell id -g) -v "$(shell pwd)/frontend":/app -w /app node:20-alpine

help:
	@echo "Comandos disponibles:"
	@echo "  make up             - Levanta PostgreSQL con Docker Compose"
	@echo "  make down           - Detiene los contenedores de Docker Compose"
	@echo "  make test-backend   - Ejecuta pruebas unitarias de backend"
	@echo "  make test-worker    - Ejecuta pruebas unitarias de worker"
	@echo "  make test-frontend  - Ejecuta pruebas unitarias de frontend"
	@echo "  make test-all       - Ejecuta todas las pruebas (backend, worker, frontend)"
	@echo "  make lint-backend   - Ejecuta análisis estático en backend"
	@echo "  make lint-worker    - Ejecuta análisis estático en worker"
	@echo "  make lint-frontend  - Ejecuta análisis estático en frontend"
	@echo "  make lint-all       - Ejecuta todos los linters"
	@echo "  make format         - Aplica formateo automático en Python"

up:
	docker compose up -d postgres

down:
	docker compose down

test-backend:
	cd backend && PYTHONPATH=. ../$(PYTEST) -v

test-worker:
	cd worker && PYTHONPATH=. ../$(PYTEST) -v

test-frontend:
	$(DOCKER_NODE) npm test

test-all: test-backend test-worker test-frontend

lint-backend:
	cd backend && ../$(RUFF) check .

lint-worker:
	cd worker && ../$(RUFF) check .

lint-frontend:
	$(DOCKER_NODE) npm run lint

lint-all: lint-backend lint-worker lint-frontend

format:
	$(RUFF) format backend worker
	$(RUFF) check --fix backend worker
