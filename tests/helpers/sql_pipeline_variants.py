"""
Eval-only SQL pipeline variants for Experiment II (SQL grounding comparison).

experiment_design.md 3.3 defines:
  S1 Static Schema            — fixed schema context, no schema_linker, no
                                 fuzzy resolver, no catalog_lookup, no
                                 few-shot retrieval, no answer_validator, no retry.
  S2 Dynamic Schema Grounding  — schema_linker + dynamic describe_tables,
                                 exact entity matching only (no fuzzy resolver),
                                 no catalog_lookup, no answer_validator, no retry.
  S3 Full Grounded SQL Pipeline — production, run unmodified elsewhere
                                 (agent/nodes/sql_pipeline.py). Not built here.

`agent/tools/sql.py`'s build_sql_pipeline() is a factory that already takes
every one of these components as a parameter, so S1/S2 are built by calling
that SAME factory with different components swapped for no-op stand-ins —
no production code is forked or edited, satisfying the isolation constraint
in 3.3 ("Only the SQL pipeline block changes").

Model, temperature, database snapshot, user role, and SQL executor are
reused unmodified from the production configuration (agent/llm.py,
core/sql_executor.py, core/scope.py) per 3.3.1 step 3.
"""
from __future__ import annotations
from typing import Optional

from agent.state import DetectedEntities, QueryType
from agent.tools.sql import build_sql_pipeline
from agent.tools.few_shot_retriever import retrieve_few_shots
from agent.tools.schema_retriever import describe_tables
from agent.tools.academic_calendar import get_current_academic_period
from agent.prompts.schema_linker import (
    SCHEMA_LINKER_SYSTEM_PROMPT,
    build_schema_linker_human_message,
    PORTFOLIO_SQL_DOMAIN_RULES,
)
from core.config import settings
from core.scope import UserScope
from core.sql_executor import PsycopgExecutor

# The fixed schema context S1 gets instead of dynamic describe_tables().
# NOTE: fill this in with the real, full column-level schema text for the
# 8 views listed in experiment_design.md 3.4 before running for real — this
# placeholder only lists view names, which is not enough context for the
# generator to produce correct joins/columns.
STATIC_SCHEMA_CONTEXT = """
Available views (static, fixed schema context — no dynamic lookup):
- analitik.v_akademik_statistik_dosen
- analitik.v_akademik_statistik_prodi
- analitik.v_akademik_portofolio
- analitik.v_info_umum_kelas_matkul
- analitik.v_info_umum_dosen
- analitik.v_akademik_komponen_evaluasi_kelas
- analitik.v_akademik_komentar_mahasiswa
- analitik.v_info_umum_institusi
TODO: replace with real column-level schema text before running.
""".strip()


def _no_few_shot_examples(query_type: str | None) -> str:
    """S1: no query-type few-shot examples supplied."""
    return "(no examples)"


def _production_few_shot_examples(query_type: str | None) -> str:
    """S2/S3 behavior — reused as-is from production sql_pipeline.py."""
    if not query_type:
        return "(no examples)"
    try:
        return retrieve_few_shots(QueryType(query_type))
    except ValueError:
        return "(no examples)"


async def _exact_match_entity_resolver(entities_dict: dict):
    """S2: exact entity matching only — skips the fuzzy resolver entirely.
    Raw LLM-extracted entities are used as-is with no typo/alias correction."""
    valid_fields = DetectedEntities.model_fields.keys()
    filtered: dict = {}
    for k, v in entities_dict.items():
        if k not in valid_fields or v is None or str(v).strip().lower() in ("null", "none", ""):
            continue
        if k in ["no_kelas", "no_prodi"] and isinstance(v, int):
            filtered[k] = str(v)
        else:
            filtered[k] = v
    return DetectedEntities(**filtered)


def _static_schema_context(*_args, **_kwargs) -> str:
    """S1: ignores query/table args entirely, always returns the same fixed text."""
    return STATIC_SCHEMA_CONTEXT


def _s1_human_message_builder(task: str, user_scope: UserScope, prior_steps_context: Optional[str]) -> str:
    """S1: same prompt builder, but prior_steps_context is dropped (no
    plan-aware schema linking — schema_linker itself is disabled for S1)."""
    current_semester, current_tahun_ajaran = get_current_academic_period()
    return build_schema_linker_human_message(
        query=task,
        current_semester=current_semester,
        current_tahun_ajaran=current_tahun_ajaran,
        user_role=user_scope.role.value,
        plan_context=None,
    )


def _s2_human_message_builder(task: str, user_scope: UserScope, prior_steps_context: Optional[str]) -> str:
    """S2: same as production — plan-aware schema linking is active."""
    current_semester, current_tahun_ajaran = get_current_academic_period()
    return build_schema_linker_human_message(
        query=task,
        current_semester=current_semester,
        current_tahun_ajaran=current_tahun_ajaran,
        user_role=user_scope.role.value,
        plan_context=prior_steps_context,
    )


# ---------------------------------------------------------------------------
# S1 — Static Schema
# ---------------------------------------------------------------------------
# active: sql_generator, sql_validator, sql_executor, fixed schema context
# disabled: schema_linker, fuzzy resolver, catalog_lookup, few-shot retrieval,
#           answer_validator, error_handler retry loop (max_attempts=1)
s1_static_schema_pipeline = build_sql_pipeline(
    schema_linker_prompt=SCHEMA_LINKER_SYSTEM_PROMPT,
    entity_resolver=_exact_match_entity_resolver,  # no fuzzy correction, exact match only
    few_shot_examples=_no_few_shot_examples,
    human_message_builder=_s1_human_message_builder,
    schema_context=_static_schema_context,  # fixed, not dynamic describe_tables
    default_table="analitik.v_akademik_portofolio",
    executor=PsycopgExecutor(),  # same executor as production
    max_attempts=1,  # no retry loop
    domain_rules=PORTFOLIO_SQL_DOMAIN_RULES,
)


# ---------------------------------------------------------------------------
# S2 — Dynamic Schema Grounding
# ---------------------------------------------------------------------------
# active: schema_linker, dynamic describe_tables, sql_generator, sql_validator,
#         sql_executor, exact entity matching
# disabled: fuzzy resolver, catalog_lookup, few-shot retrieval, answer_validator,
#           error_handler retry loop (max_attempts=1)
s2_dynamic_schema_pipeline = build_sql_pipeline(
    schema_linker_prompt=SCHEMA_LINKER_SYSTEM_PROMPT,
    entity_resolver=_exact_match_entity_resolver,  # exact match only, no fuzzy
    few_shot_examples=_no_few_shot_examples,
    human_message_builder=_s2_human_message_builder,
    schema_context=describe_tables,  # dynamic, same as production
    default_table="analitik.v_akademik_portofolio",
    executor=PsycopgExecutor(),
    max_attempts=1,  # no retry loop
    domain_rules=PORTFOLIO_SQL_DOMAIN_RULES,
)


async def run_variant(pipeline, question: str, user_scope: UserScope, plan_step_context: dict,
                       prior_steps_context: str | None, query_type: str | None) -> dict:
    """Uniform entrypoint so the test runner (Step 4) can call S1/S2/S3
    identically. S3 is the unmodified production sql_pipeline() node instead
    of a pipeline built here — call it directly for that configuration."""
    sql_state = {
        "question": question,
        "user_scope": user_scope,
        "plan_step_context": plan_step_context,
        "prior_steps_context": prior_steps_context,
        "query_type": query_type,
        "error_history": [],
        "attempt_count": 0,
        "is_aborted": False,
    }
    return await pipeline.ainvoke(sql_state)
