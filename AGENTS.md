# ITB Academic Portfolio Analytics — AI Agent Guidelines

This project is a production-grade LangGraph agentic system that translates natural language queries into SQL and RAG queries to analyze academic portfolio data. 

## Tech Stack
- **Backend**: FastAPI, Python 3.10+
- **Agent Orchestration**: LangGraph
- **Data Validation**: Pydantic
- **Database**: PostgreSQL with `psycopg3` (async) and `pgvector`
- **SQL Parsing**: `sqlglot`
- **Fuzzy Matching**: `pg_trgm`, `fuzzystrmatch`

## Architecture Overview
The system follows a Two-Phase approach:
- **Phase 1**: Text-to-SQL agent with orchestrator, planner, SQL pipeline, and synthesizer.
- **Phase 2**: RAG extension. `agent/tools/rag/pipeline.py` is the modular, standalone-callable
  RAG engine (hybrid dense+sparse retrieval with metadata filtering, CRAG-style corrective retrieval,
  Multi-HyDE query expansion, Gemini-based generation with citations, RAGAS-style faithfulness self-check
  with a Self-RAG-style regenerate loop). `agent/nodes/rag_retriever.py` is a thin LangGraph adapter over it.

See `docs/ARCHITECTURE.md` and `docs/AGENT_NODES.md` for deep dives into node responsibilities.

## Core Development Guidelines

### 1. State Management
- `AgentState` (`docs/STATE_CONTRACT.md`) is the **single source of truth**.
- Nodes read from and write partial updates to this state.
- **Routers (conditional edges) must be pure functions.** They must never mutate state; they only return the next node name.
- The `error_handler` increments retries; routers and the SQL generator should not.

### 2. Security & Scope Enforcement (CRITICAL)
- **Read-Only**: The agent must NEVER generate `INSERT`, `UPDATE`, `DELETE`, or `DROP` statements.
- **Scope Injection**: Every agent invocation has a `UserScope`. The SQL Generator MUST leave a `{SCOPE_FILTER}` placeholder. The SQL Executor dynamically replaces it before execution.
- **Validation**: All generated SQL must pass through `sqlglot` validation before execution.

### 3. Query Classification
The planner (`agent/nodes/planner.py`) owns query classification and plan creation.
- SQL-only: `data_lookup`, `comparative`, `chart_generate`
- RAG-only: `text_lookup`, `summarization`
- Hybrid (SQL+RAG): `diagnostic`, `analytical_hybrid`
- Analytical (SQL+LLM): `analytical_numeric`
Ensure hybrid plan steps support both `sql` and `rag` routing.

### 4. Code Style
- Use `async`/`await` for all DB interactions and LLM calls.
- Use explicit type hints for all function signatures.
- Prefer explicit Pydantic validation over loose dictionaries.

## Common Commands
- **Run API server**: `uv run uvicorn api.main:app --reload`
- **Run tests**: `uv run pytest`
