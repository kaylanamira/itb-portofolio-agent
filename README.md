# ITB Academic Portfolio Analytics

A hybrid agentic system built to answer natural language questions about ITB's Academic Portfolio data. It translates complex queries into precise, scoped PostgreSQL operations (Text-to-SQL) and unstructured data into LLM insights (RAG).

**Key Features:**
- **Text-to-SQL Pipeline:** Accurate and secure SQL generation powered by LLMs, with fuzzy search for entity resolution.
- **Row Level Security (RLS):** Built into the PostgreSQL queries directly to ensure users only see data they are permitted to view based on their role (e.g. `dosen`, `dekan`).
- **Dynamic Multi-Provider Support:** Instantly swap between Google Gemini, OpenAI, Anthropic, or Groq.
- **Chart Generation:** Outputs Vega-Lite specifications directly for the frontend to render graphs interactively.

---

## Developer Setup Guide

This project requires **Python (via `uv`)**, **Docker**, and **Docker Compose**.

### 1. Install Dependencies
We use `uv` as our Python package manager. If you don't have it, install it via: `curl -LsSf https://astral.sh/uv/install.sh | sh`

Sync the environment:
```bash
uv sync
```

### 2. Configure Environment
A `.env` file is required to connect to the DB and use the LLMs.
```bash
make env
```
This copies `.env.example` to `.env`. **You must open `.env` and configure your API keys** (e.g. `OPENAI_API_KEY`, `GOOGLE_API_KEY`). The default LLM is Groq, but you can change `LLM_PROVIDER` to `openai`, `google`, or `anthropic`.

### 3. Setup Database & Run Ingestion
We've streamlined the entire local database setup. The following command will start the Docker containers (PostgreSQL + Adminer), wait for initialization, and run the Python ingestion scripts to seed the database with mock ITB data.

```bash
make setup
```

*(Note: The database schema is automatically built when the postgres container starts via `db/schema.sql`. The Python ingestion scripts populate the master data and materialized views.)*

### 4. Run the API Server
Start the FastAPI server with hot-reloading:

```bash
make run
```

The API will be available at: http://localhost:8000
Adminer (for easy database viewing) is running at: http://localhost:8080 (credentials are in `.env`).

---

## Useful Makefile Commands

- `make setup` - Runs initial environment setup, starts DB, and seeds data.
- `make run` - Starts the FastAPI uvicorn server.
- `make db-up` - Starts the PostgreSQL & Adminer containers in the background.
- `make ingest` - Re-runs the `ingestion/ingest_master.py` and `ingestion/ingest_kelas_pengajar.py` scripts.
- `make graph` - Regenerates the Mermaid diagrams in the `docs/` folder to reflect the latest LangGraph architecture.
- `make clean` - Stops and deletes the Docker containers and database volumes (wipes data).
