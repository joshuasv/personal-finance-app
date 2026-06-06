.PHONY: help sync hooks fmt lint typecheck test test-cov run-api run-bot run-web run-all build-web clean

PY := uv run

help:
	@echo "Targets:"
	@echo "  sync       Install/refresh deps via uv"
	@echo "  hooks      Install pre-commit hooks (run once after a fresh clone)"
	@echo "  fmt        Format with ruff"
	@echo "  lint       Lint with ruff"
	@echo "  typecheck  Type-check with mypy"
	@echo "  test       Run pytest"
	@echo "  test-cov   Run pytest with coverage"
	@echo "  run-api    Start FastAPI (REST + MCP) via finance serve"
	@echo "  run-bot    Start the Telegram bot"
	@echo "  run-web    Start the Vite dev server"
	@echo "  run-all    Start API + web (dev) + bot in one terminal"
	@echo "  build-web  Build the web UI for production"

sync:
	uv sync --all-groups

hooks:
	$(PY) pre-commit install --install-hooks

fmt:
	$(PY) ruff format src tests
	$(PY) ruff check --fix src tests

lint:
	$(PY) ruff check src tests
	$(PY) ruff format --check src tests

typecheck:
	$(PY) mypy src

test:
	$(PY) pytest

test-cov:
	$(PY) pytest --cov=finance --cov-report=term-missing

run-api:
	$(PY) finance serve

run-bot:
	$(PY) finance bot

run-web:
	npm --prefix src/finance/web run dev

run-all:
	./scripts/dev.sh

build-web:
	npm --prefix src/finance/web run build

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov build dist
	find . -type d -name __pycache__ -exec rm -rf {} +
