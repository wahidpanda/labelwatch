.PHONY: install dev db test test-backend test-frontend lint lint-backend lint-frontend format migrate

UV ?= uv

install:
	cd backend && $(UV) sync
	cd frontend && npm ci

db:
	docker compose up -d db

dev: db
	cd backend && $(UV) run uvicorn app.main:create_app --factory --reload --port 8000 & \
	cd frontend && npm run dev

test: test-backend test-frontend

test-backend:
	cd backend && $(UV) run pytest

test-frontend:
	cd frontend && npx vitest run --coverage

lint: lint-backend lint-frontend

lint-backend:
	cd backend && $(UV) run ruff check . && $(UV) run ruff format --check . && $(UV) run mypy

lint-frontend:
	cd frontend && npm run lint && npm run typecheck

format:
	cd backend && $(UV) run ruff check --fix . && $(UV) run ruff format .

migrate:
	cd backend && $(UV) run python -m app.db.migrate
