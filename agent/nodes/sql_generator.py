import json
import re
from typing import Any
from agent.state import AgentState
from agent.prompts.sql_generator import SQL_GENERATOR_SYSTEM, SQL_GENERATOR_RETRY
from agent.tools.few_shot_retriever import retrieve_few_shots
from agent.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage


def _build_scope_context(state: AgentState) -> tuple[str, str]:
    """Extract scope description and hint from state."""
    user_scope = state.get("user_scope")
    if not user_scope:
        return "Unknown", "TRUE"

    relevant_tables = state.get("relevant_tables") or ["mv_kelas"]
    target_table = relevant_tables[0]
    
    scope_where, _ = user_scope.scope_where(target_table)
    return f"Role: {user_scope.role.value}", f"For {target_table}: {scope_where}"


def _format_entities(entities: Any) -> str:
    """Format detected entities into a string."""
    if not entities:
        return "None detected"
    if hasattr(entities, "model_dump"):
        return str(entities.model_dump())
    if hasattr(entities, "dict"):
        return str(entities.dict())
    return str(entities)


def _extract_sql(raw_response: str) -> str:
    """Extract SQL query from LLM response (JSON or raw text with markdown)."""
    raw = raw_response.strip()
    
    # Try parsing as JSON first
    try:
        content = json.loads(raw)
        if isinstance(content, dict) and "sql" in content:
            return content["sql"]
    except (json.JSONDecodeError, AttributeError):
        pass

    # Fallback to markdown fence stripping
    cleaned = re.sub(r"^```(?:sql)?\s*", "", raw, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    sql = cleaned.strip()

    # Fallback safety
    if not sql or not sql.upper().startswith("SELECT"):
        return "SELECT 1"
        
    return sql


async def sql_generator(state: AgentState) -> dict:
    """LangGraph node: Generates SQL from natural language."""
    llm = get_llm(force_json=False)
    
    scope_desc, scope_hint = _build_scope_context(state)
    entities_str = _format_entities(state.get("detected_entities"))
    query_type = state.get("query_type")
    few_shots = retrieve_few_shots(query_type) if query_type else "(no examples)"
    
    sys_prompt = SQL_GENERATOR_SYSTEM.format(
        schema_context=state.get("schema_context", ""),
        detected_entities=entities_str,
        scope_description=scope_desc,
        scope_hint=scope_hint,
        few_shot_examples=few_shots,
    )
    
    # Append retry context if this is a subsequent attempt
    attempt_count = state.get("attempt_count", 0)
    error_history = state.get("error_history", [])
    
    if attempt_count > 0 and error_history:
        last_error = error_history[-1]
        sys_prompt += "\n" + SQL_GENERATOR_RETRY.format(
            attempt_count=attempt_count,
            max_attempts=state.get("max_attempts", 3),
            previous_sql=last_error.get("sql", ""),
            last_error=last_error.get("error", ""),
            error_history=json.dumps(error_history, indent=2, default=str),
        )
    
    messages = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=state["effective_query"]),
    ]
    
    response = await llm.ainvoke(messages)
    sql = _extract_sql(response.content)
    
    return {"generated_sql": sql}
