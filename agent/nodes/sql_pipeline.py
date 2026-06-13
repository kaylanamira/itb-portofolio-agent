"""SQL pipeline node — bridges AgentState to the domain-agnostic SQLTool."""

from typing import Optional
import logging
from agent.state import AgentState, DetectedEntities, QueryType
from agent.tools.sql import build_sql_pipeline
from agent.tools.fuzzy_search import fuzzy_resolve_entities, FuzzyResolutionError
from agent.tools.few_shot_retriever import retrieve_few_shots
from agent.tools.schema_retriever import describe_tables
from agent.tools.academic_calendar import get_current_academic_period
from agent.prompts.schema_linker import SCHEMA_LINKER_SYSTEM_PROMPT, build_schema_linker_human_message, PORTFOLIO_SQL_DOMAIN_RULES
from core.config import settings
from core.scope import UserScope
from core.sql_executor import PsycopgExecutor

logger = logging.getLogger(__name__)


async def _portfolio_entity_resolver(entities_dict: dict):
    """Resolves raw LLM-extracted entity dict to DetectedEntities."""
    valid_fields = DetectedEntities.model_fields.keys()
    filtered: dict = {}

    for k, v in entities_dict.items():
        if k not in valid_fields or v is None or str(v).strip().lower() in ("null", "none", ""):
            continue
        if k in ["no_kelas", "no_prodi"] and isinstance(v, int):
            filtered[k] = str(v)
        else:
            filtered[k] = v

    raw_entities = DetectedEntities(**filtered)
    try:
        return await fuzzy_resolve_entities(raw_entities)
    except FuzzyResolutionError as exc:
        logger.warning("Fuzzy entity resolution failed (DB error): %s", exc)
        return raw_entities


def portfolio_few_shot_examples(query_type: str | None) -> str:
    """Returns few-shot SQL examples for the given query type."""
    if not query_type:
        return "(no examples)"
    try:
        return retrieve_few_shots(QueryType(query_type))
    except ValueError:
        return "(no examples)"


def _build_prior_steps_context(state: AgentState) -> str | None:
    """Summarize previous completed steps for plan-aware schema linking."""
    steps = state.get("steps_completed", [])
    if not steps:
        return None
    summaries = [
        f"Step {step.step_number} ({step.action}): {step.observation}"
        for step in steps
    ]
    return "; ".join(summaries)


def _portfolio_human_message_builder(
    task: str,
    user_scope: UserScope,
    prior_steps_context: Optional[str],
) -> str:
    """Builds the schema linker human message with academic calendar context."""
    current_semester, current_tahun_ajaran = get_current_academic_period()
    return build_schema_linker_human_message(
        query=task,
        current_semester=current_semester,
        current_tahun_ajaran=current_tahun_ajaran,
        user_role=user_scope.role.value,
        plan_context=prior_steps_context,
    )


_portfolio_sql_pipeline = build_sql_pipeline(
    schema_linker_prompt=SCHEMA_LINKER_SYSTEM_PROMPT,
    entity_resolver=_portfolio_entity_resolver,
    few_shot_examples=portfolio_few_shot_examples,
    human_message_builder=_portfolio_human_message_builder,
    schema_context=describe_tables,
    default_table="analitik.v_akademik_kelas",
    executor=PsycopgExecutor(),
    max_attempts=settings.MAX_SQL_ATTEMPTS,
    domain_rules=PORTFOLIO_SQL_DOMAIN_RULES,
)


async def sql_pipeline(state: AgentState) -> dict:
    plan = state.get("plan", [])
    idx = state.get("current_step_index", 0)
    plan_step = plan[idx] if idx < len(plan) else {"task": state["effective_query"]}
    query_type = state.get("query_type")

    sql_state = {
        "question": state["effective_query"],
        "user_scope": state["user_scope"],
        "plan_step_context": plan_step,
        "prior_steps_context": _build_prior_steps_context(state),
        "query_type": query_type.value if query_type else None,
        "error_history": [],
        "attempt_count": 0,
        "is_aborted": False,
    }

    result = await _portfolio_sql_pipeline.ainvoke(sql_state)

    return {
        "detected_entities": result.get("detected_entities"),
        "relevant_tables": result.get("relevant_tables"),
        "schema_context": result.get("schema_context"),
        "generated_sql": result.get("generated_sql"),
        "sql_result": result.get("sql_result"),
        "sql_error": result.get("sql_error"),
        "sql_row_count": result.get("sql_row_count"),
        "answer_is_valid": result.get("answer_is_valid"),
        "attempt_count": result.get("attempt_count", 0),
        "error_history": result.get("error_history", []),
        "is_aborted": result.get("is_aborted", False),
        "abort_reason": result.get("abort_reason"),
    }


def route_after_sql_pipeline(state: AgentState) -> str:
    """Routes after SQL execution: to synthesizer on abort, step_reasoner otherwise."""
    if state.get("is_aborted", False):
        return "synthesizer"
    return "step_reasoner"
