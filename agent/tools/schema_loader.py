import os

SCHEMA_PATH = os.getenv("AGENT_SCHEMA_PATH", "db/schema_for_agent.md")

def load_schema_context() -> str:
    """Loads the schema markdown file into a string for the LLM context."""
    try:
        with open(SCHEMA_PATH, "r") as f:
            return f.read()
    except FileNotFoundError:
        return f"Warning: Schema context file not found at {SCHEMA_PATH}"
