"""
Experiment II end-to-end runner — experiment_design.md section 3.3.1 step 4.

Runs all 80 cases in evals/datasets/sql_grounding_cases.json through:
  S1 — tests/helpers/sql_pipeline_variants.py :: s1_static_schema_pipeline
  S2 — tests/helpers/sql_pipeline_variants.py :: s2_dynamic_schema_pipeline
  S3 — agent/nodes/sql_pipeline.py :: sql_pipeline (production, unmodified)

For each (config, case) pair, executes the generated SQL through the same
validation/execution harness (S1/S2 pipelines already run validation +
execution internally via SQLTool, matching S3), and records:
  generated SQL, selected tables, execution success, row count/result,
  attempt count, and whether it matched expected_result_facts (left for
  the scorer to judge — this file just records raw outcomes).

Traces go to evals/results/sql_grounding_traces.jsonl.

Requires: RUN_LLM_EVALS=1 and a working DATABASE_URL against the SAME
database snapshot for all three configs (per 3.3.1 step 3).
"""
from __future__ import annotations
import json
import time

import pytest

from tests.conftest import load_cases, RESULTS_DIR
from evals.datasets.schemas import SqlGroundingCase
from core.scope import UserScope, ScopeEntry, UserRole

from tests.helpers.sql_pipeline_variants import (
    s1_static_schema_pipeline,
    s2_dynamic_schema_pipeline,
    run_variant,
)

CASES: list[SqlGroundingCase] = load_cases("sql_grounding_cases.json", SqlGroundingCase)
TRACE_PATH = RESULTS_DIR / "sql_grounding_traces.jsonl"

CONFIGS = ["S1", "S2", "S3"]


def _scope_for_role(role: str) -> UserScope:
    role_map = {
        "dosen": UserRole.DOSEN, "kaprodi": UserRole.KAPRODI,
        "dekan": UserRole.DEKAN, "admin": UserRole.ADMIN,
    }
    ur = role_map.get(role, UserRole.DOSEN)
    entry = ScopeEntry(user_role_id=1, role=ur, is_prime=True)
    return UserScope(user_id=9002, active_role=entry, available_roles=[entry])


def _append_trace(record: dict):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(TRACE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


async def _run_s3_production(case: SqlGroundingCase, scope: UserScope) -> tuple[dict, float]:
    """S3: run the real, unmodified production sql_pipeline node."""
    from agent.nodes.sql_pipeline import sql_pipeline

    state = {
        "effective_query": case.question,
        "user_scope": scope,
        "plan": [case.plan_step_context.model_dump()],
        "current_step_index": 0,
        "steps_completed": [],
        "query_type": None,
    }
    start = time.monotonic()
    result = await sql_pipeline(state)
    latency = time.monotonic() - start
    return result, latency


@pytest.mark.llm_eval
@pytest.mark.asyncio
@pytest.mark.parametrize("config", CONFIGS)
@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
async def test_sql_grounding_case(config, case: SqlGroundingCase):
    """Runs one (configuration, case) pair and records the trace. Pass/fail
    judgment against expected_sql_behavior / expected_grounding happens in
    evals/sql_grounding_scorer.py, which reads these recorded traces."""
    scope = _scope_for_role(case.user_scope.role)

    if config == "S3":
        result, latency = await _run_s3_production(case, scope)
    else:
        pipeline = {"S1": s1_static_schema_pipeline, "S2": s2_dynamic_schema_pipeline}[config]
        start = time.monotonic()
        result = await run_variant(
            pipeline,
            question=case.question,
            user_scope=scope,
            plan_step_context=case.plan_step_context.model_dump(),
            prior_steps_context=case.prior_steps_context or None,
            query_type=None,
        )
        latency = time.monotonic() - start

    record = {
        "case_id": case.id,
        "config": config,
        "sql_complexity": case.sql_complexity.value,
        "generated_sql": result.get("generated_sql"),
        "relevant_tables": result.get("relevant_tables"),
        "detected_entities": (
            result.get("detected_entities").model_dump()
            if hasattr(result.get("detected_entities"), "model_dump")
            else result.get("detected_entities")
        ),
        "sql_result": result.get("sql_result"),
        "sql_row_count": result.get("sql_row_count"),
        "sql_error": result.get("sql_error"),
        "attempt_count": result.get("attempt_count", 0),
        "is_aborted": result.get("is_aborted", False),
        "latency_seconds": latency,
    }
    _append_trace(record)

    assert record["case_id"] == case.id  # smoke assertion: the run completed
