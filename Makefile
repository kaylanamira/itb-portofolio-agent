.PHONY: help setup env db-up ingest run clean graph

help:
	@echo "Available commands:"
	@echo "  make setup   - Full initial setup (create .env, start DB, run ingestion)"
	@echo "  make env     - Create .env file from .env.example if it doesn't exist"
	@echo "  make db-up   - Start PostgreSQL container in background"
	@echo "  make ingest  - Run all python ingestion scripts to seed database"
	@echo "  make run     - Run the FastAPI application with auto-reload"
	@echo "  make graph   - Regenerate the LangGraph mermaid diagrams"
	@echo "  make clean   - Stop docker containers and remove database volumes"

setup: env db-up
	@echo "Waiting 5 seconds for PostgreSQL to accept connections..."
	@sleep 5
	$(MAKE) ingest
	@echo "Setup complete! You can now run the app with 'make run'"

env:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example. Please remember to update your LLM API keys!"; \
	else \
		echo ".env file already exists."; \
	fi

db-up:
	docker-compose up -d postgres adminer
	@echo "Database is running on localhost:5432"
	@echo "Adminer is running on http://localhost:8080"

ingest:
	@echo "Running data ingestion scripts..."
	uv run python ingestion/ingest_master.py
	uv run python ingestion/ingest_kelas_pengajar.py
	@echo "Data ingestion complete!"

run:
	uv run uvicorn api.main:app --reload

graph:
	uv run python generate_graphs.py

clean:
	docker-compose down -v
	@echo "Database volumes and containers removed."
