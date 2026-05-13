"""SQL pipeline node — bridges AgentState to the domain-agnostic SQLTool."""

from agent.state import AgentState, DetectedEntities, QueryType
from agent.tools.sql import SQLTool
from agent.tools.schema_loader import load_schema_context
from agent.tools.fuzzy_search import fuzzy_resolve_entities
from agent.tools.few_shot_retriever import retrieve_few_shots
from agent.prompts.schema_linker import SCHEMA_LINKER_SYSTEM_PROMPT
from core.config import settings

# --- Option A (LangGraph subgraph) — uncomment to use instead of Option B ---
from agent.tools.sql import build_sql_pipeline

async def sql_pipeline(state: AgentState) -> dict:
    plan = state.get("plan", [])
    idx = state.get("current_step_index", 0)
    plan_step = plan[idx] if idx < len(plan) else {"task": state["effective_query"]}
    query_type = state.get("query_type")

    sql_state = {
        "question": state["effective_query"],
        "user_scope": state["user_scope"],
        "plan_step_context": plan_step,
        "query_type": query_type.value if query_type else None,
        "error_history": [],
        "attempt_count": 0,
        "max_attempts": settings.MAX_SQL_ATTEMPTS,
        "is_aborted": False,
    }

    sql_pipeline_graph = build_sql_pipeline(
        schema_linker_prompt=SCHEMA_LINKER_SYSTEM_PROMPT,
        entity_resolver=_portfolio_entity_resolver,
        few_shot_examples=_portfolio_few_shot_examples,
        schema_context=load_schema_context(),
        default_table="mv_kelas",
        max_attempts=settings.MAX_SQL_ATTEMPTS,
    )

    result = await sql_pipeline_graph.ainvoke(sql_state)

    return {
        "detected_entities": result.get("detected_entities"),
        "relevant_tables": result.get("relevant_tables"),
        "schema_context": result.get("schema_context"),
        "generated_sql": result.get("generated_sql"),
        "sql_with_scope": result.get("sql_with_scope"),
        "sql_result": result.get("sql_result"),
        "sql_error": result.get("sql_error"),
        "sql_row_count": result.get("sql_row_count"),
        "answer_is_valid": result.get("answer_is_valid"),
        "attempt_count": result.get("attempt_count", 0),
        "error_history": result.get("error_history", []),
        "is_aborted": result.get("is_aborted", False),
        "abort_reason": result.get("abort_reason"),
    }

async def _portfolio_entity_resolver(entities_dict: dict):
    """Resolves raw entity dict to DetectedEntities via pg_trgm fuzzy search."""
    valid_fields = DetectedEntities.model_fields.keys()
    filtered = {k: v for k, v in entities_dict.items() if k in valid_fields and v is not None}
    return await fuzzy_resolve_entities(DetectedEntities(**filtered))


def _portfolio_few_shot_examples(query_type: str | None) -> str:
    """Returns few-shot SQL examples for the given query type."""
    if not query_type:
        return "(no examples)"
    try:
        return retrieve_few_shots(QueryType(query_type))
    except ValueError:
        return "(no examples)"


# async def sql_pipeline(state: AgentState) -> dict:
#     """
#     LangGraph node that executes the full SQL pipeline via SQLTool.

#     Input: AgentState with effective_query, user_scope, plan, current_step_index.
#     Output: partial AgentState update with SQL results or abort.
#     """
#     plan = state.get("plan", [])
#     idx = state.get("current_step_index", 0)
#     plan_step = plan[idx] if idx < len(plan) else {"task": state["effective_query"]}

#     query_type = state.get("query_type")
#     query_type_str = query_type.value if query_type else None

#     sql_state = {
#         "question": state["effective_query"],
#         "user_scope": state["user_scope"],
#         "plan_step_context": plan_step,
#         "query_type": query_type_str,
#         "error_history": [],
#     }

#     sql_tool = SQLTool(
#         schema_linker_prompt=SCHEMA_LINKER_SYSTEM_PROMPT,
#         entity_resolver=_portfolio_entity_resolver,
#         few_shot_examples=_portfolio_few_shot_examples,
#         schema_context=load_schema_context(),
#         default_table="mv_kelas",
#         max_attempts=settings.MAX_SQL_ATTEMPTS,
#     )

#     result = await sql_tool.run(sql_state)

#     return {
#         "detected_entities": result.get("detected_entities"),
#         "relevant_tables": result.get("relevant_tables"),
#         "schema_context": result.get("schema_context"),
#         "generated_sql": result.get("generated_sql"),
#         "sql_with_scope": result.get("sql_with_scope"),
#         "sql_result": result.get("sql_result"),
#         "sql_error": result.get("sql_error"),
#         "sql_row_count": result.get("sql_row_count"),
#         "answer_is_valid": result.get("answer_is_valid"),
#         "attempt_count": result.get("attempt_count", 0),
#         "error_history": result.get("error_history", []),
#         "is_aborted": result.get("is_aborted", False),
#         "abort_reason": result.get("abort_reason"),
#     }


def route_after_sql_pipeline(state: AgentState) -> str:
    """Routes after SQL execution: to synthesizer on abort, step_reasoner otherwise."""
    if state.get("is_aborted", False):
        return "synthesizer"
    return "step_reasoner"

