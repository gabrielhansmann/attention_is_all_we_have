# Common tasks. Run `make help`. Needs Python 3.11+, Node 20+ and pnpm.
PY ?= .venv/bin/python
BACKEND_PORT ?= 8000

.PHONY: help install install-backend install-frontend dev backend frontend test test-backend build check-db lint

help:
	@echo "make install    create .venv, install backend and frontend dependencies"
	@echo "make dev        run backend and frontend together (BACKEND_PORT=$(BACKEND_PORT), frontend on 5173)"
	@echo "make backend    run only the FastAPI backend"
	@echo "make frontend   run only the Vite dev server"
	@echo "make test       backend tests (no database or OpenAI key needed)"
	@echo "make build      type-check and build the frontend"
	@echo "make lint       lint the frontend"
	@echo "make check-db   verify the database connection and OpenAI key"

install: install-backend install-frontend

install-backend:
	python3 -m venv .venv
	.venv/bin/pip install -e "backend[dev]"

install-frontend:
	cd frontend && pnpm install

dev:
	$(MAKE) -j2 backend frontend

backend:
	$(PY) -m uvicorn app.main:app --app-dir backend --reload --port $(BACKEND_PORT)

frontend:
	cd frontend && VITE_API_PROXY=http://localhost:$(BACKEND_PORT) pnpm dev

test: test-backend

test-backend:
	cd backend && $(abspath $(PY)) -m pytest -q

build:
	cd frontend && pnpm build

lint:
	cd frontend && pnpm lint

check-db:
	$(PY) skills/database-setup/scripts/check_db.py --openai
