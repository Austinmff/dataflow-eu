# =============================================================================
# DataFlow EU — Makefile
# One-command developer interface for the entire stack.
# =============================================================================

.PHONY: help setup run stop restart test lint dbt-run dbt-test dbt-docs clean fernet

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Colours
CYAN  := \033[0;36m
RESET := \033[0m

help: ## Show this help message
	@echo ""
	@echo "  DataFlow EU — Available commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# =============================================================================
# Environment
# =============================================================================

setup: ## First-time setup: copy .env, generate Fernet key, install Python deps
	@echo "→ Setting up DataFlow EU..."
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "  ✓ .env created from .env.example"; \
	else \
		echo "  ✓ .env already exists — skipping"; \
	fi
	@FERNET=$$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"); \
	sed -i "s|your-fernet-key-here-generate-with-python|$$FERNET|g" .env; \
	echo "  ✓ Fernet key generated"
	@SECRET=$$(python3 -c "import secrets; print(secrets.token_hex(32))"); \
	sed -i "s|your-secret-key-here|$$SECRET|g" .env; \
	echo "  ✓ Webserver secret key generated"
	@pip install --quiet -r requirements-dev.txt && echo "  ✓ Python dev dependencies installed"
	@pre-commit install && echo "  ✓ pre-commit hooks installed"
	@echo ""
	@echo "  Setup complete. Run 'make run' to start the stack."
	@echo ""

fernet: ## Generate a new Fernet key (useful for manual .env updates)
	@python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# =============================================================================
# Stack lifecycle
# =============================================================================

run: ## Start the full stack (Airflow + PostgreSQL + LocalStack)
	@echo "→ Starting DataFlow EU stack..."
	@chmod +x scripts/init-localstack.sh
	docker compose up -d --build
	@echo ""
	@echo "  ✓ Stack is up"
	@echo ""
	@echo "  Airflow UI   →  http://localhost:8080  (admin / admin)"
	@echo "  PostgreSQL   →  localhost:5432"
	@echo "  LocalStack   →  http://localhost:4566"
	@echo ""

dashboard: ## Start the stack including the Streamlit dashboard
	docker compose --profile dashboard up -d --build
	@echo "  Dashboard    →  http://localhost:8501"

stop: ## Stop all containers
	docker compose --profile dashboard down
	@echo "  ✓ Stack stopped"

restart: stop run ## Full restart

clean: ## Stop containers and remove all volumes (WARNING: deletes all data)
	docker compose --profile dashboard down -v --remove-orphans
	@echo "  ✓ All containers and volumes removed"

logs: ## Tail logs for all services (Ctrl+C to exit)
	docker compose logs -f

logs-airflow: ## Tail Airflow webserver logs only
	docker compose logs -f airflow-webserver airflow-scheduler

# =============================================================================
# Testing
# =============================================================================

test: ## Run all tests: pytest + dbt test
	@echo "→ Running pytest..."
	pytest tests/ -v --tb=short --cov=extractors --cov-report=term-missing
	@echo ""
	@echo "→ Running dbt tests..."
	$(MAKE) dbt-test

test-unit: ## Run only unit tests
	pytest tests/unit/ -v --tb=short

test-integration: ## Run only integration tests (requires running stack)
	pytest tests/integration/ -v --tb=short

# =============================================================================
# dbt
# =============================================================================

dbt-run: ## Run all dbt models
	docker compose exec airflow-webserver \
		dbt run --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt

dbt-test: ## Run all dbt tests
	docker compose exec airflow-webserver \
		dbt test --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt

dbt-docs: ## Generate dbt docs and serve at http://localhost:8000
	docker compose exec airflow-webserver \
		dbt docs generate --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt
	docker compose exec airflow-webserver \
		dbt docs serve --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt --port 8000

dbt-compile: ## Compile dbt models (no execution — used in CI)
	cd dbt && dbt compile --profiles-dir .

# =============================================================================
# Linting
# =============================================================================

lint: ## Run all linters: ruff, sqlfluff, pre-commit
	@echo "→ Running ruff..."
	ruff check . --fix
	@echo "→ Running sqlfluff..."
	sqlfluff lint dbt/models/ --dialect dbt
	@echo "→ Running pre-commit..."
	pre-commit run --all-files

format: ## Auto-format Python code with ruff
	ruff format .

# =============================================================================
# Utilities
# =============================================================================

ps: ## Show status of all containers
	docker compose ps

s3-ls: ## List files in the Bronze S3 bucket (requires running LocalStack)
	aws --endpoint-url=http://localhost:4566 s3 ls s3://$$(grep S3_BUCKET_NAME .env | cut -d= -f2)/ --recursive

backfill: ## Trigger a manual Airflow backfill (set START and END env vars)
	@echo "Usage: make backfill DAG=extraction_pipeline START=2023-01-01 END=2023-12-31"
	docker compose exec airflow-scheduler \
		airflow dags backfill $(DAG) --start-date $(START) --end-date $(END)
