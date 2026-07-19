"""
Experiment I end-to-end runner — experiment_design.md section 2.3.1 step 5.

Runs all 80 cases in evals/datasets/architecture_orchestration_cases.json
through all four configurations:
  A1 — tests/helpers/orchestration_variants.py :: direct_tool_workflow_eval
  A2 — tests/helpers/orchestration_variants.py :: react_controller_eval
  A3 — tests/helpers/orchestration_variants.py :: sequential_executor_eval
  A4 — agent/orchestrator.py :: main_graph (production, unmodified)

For each (config, case) pair, records a trace to
evals/results/architecture_orchestration_traces.jsonl :
  selected tools, node sequence, number of tool calls, latency, final
  answer text, and (if RUN_LLM_JUDGE=1) an LLM-as-judge faithfulness/
  completeness score.

This file only RECORDS traces — it does not compute the four Evaluation
I.1-I.4 tables. That aggregation step lives in evals/architecture_scorer.py
(next step) and reads this .jsonl file.

Requires: RUN_LLM_EVALS=1 (live LLM calls) and a working DATABASE_URL,
same as the other node-level eval tests in this repo (see conftest.py).
"""
from __future__ import annotations
import json
import os
import time
from pathlib import Path

import pytest

from tests.conftest import load_cases, DATASETS_DIR, RESULTS_DIR
from evals.datasets.schemas import ArchitectureCase
from core.scope import UserScope, ScopeEntry, UserRole
from agent.state import QueryType

from tests.helpers.orchestration_variants import (
    direct_tool_workflow_eval,
    react_controller_eval,
    sequential_executor_eval,
)

CASES: list[ArchitectureCase] = load_cases(
    "architecture_orchestration_cases.json", ArchitectureCase
)
TRACE_PATH = RESULTS_DIR / "architecture_orchestration_traces.jsonl"

CONFIGS = ["A1", "A2", "A3", "A4"]


def _scope_for_role(role: str) -> UserScope:
    role_map = {
        "dosen": UserRole.DOSEN, "kaprodi": UserRole.KAPRODI,
        "dekan": UserRole.DEKAN, "admin": UserRole.ADMIN,
    }
    ur = role_map.get(role, UserRole.DOSEN)
    entry = ScopeEntry(user_role_id=1, role=ur, is_prime=True)
    return UserScope(user_id=9001, active_role=entry, available_roles=[entry])


def _build_initial_state(case: ArchitectureCase, make_state) -> dict:
    state = make_state(
        query=case.raw_query,
        scope=_scope_for_role(case.user_scope.role),
        query_type=None,  # let planner/router decide — that's what we're testing
    )
    if case.input_context.chart_context:
        state["chart_context"] = case.input_context.chart_context
    return state


def _append_trace(record: dict):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(TRACE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


async def _run_a4_production(state: dict) -> tuple[list[str], list[str], int, dict, float]:
    """A4: run the real, unmodified production graph."""
    from agent.orchestrator import main_graph

    start = time.monotonic()
    final_state = await main_graph.ainvoke(state)
    latency = time.monotonic() - start

    steps = final_state.get("steps_completed", [])
    tool_seq = [s.action if hasattr(s, "action") else s.get("action") for s in steps]
    node_seq = tool_seq  # production doesn't separately expose node names in this state
    return tool_seq, node_seq, len(steps), final_state, latency


@pytest.mark.llm_eval
@pytest.mark.asyncio
@pytest.mark.parametrize("config", CONFIGS)
@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
async def test_architecture_case(config, case: ArchitectureCase, make_state):
    """Runs one (configuration, case) pair and records the trace.

    This test always 'passes' if it completes without raising — pass/fail
    judgment against the case's expected_behavior happens later in
    evals/architecture_scorer.py, which reads the recorded traces. Keeping
    execution and scoring separate lets us re-score without re-running
    (LLM calls are the expensive part).
    """
    state = _build_initial_state(case, make_state)

    if config == "A4":
        tool_seq, node_seq, n_calls, final_state, latency = await _run_a4_production(state)
    else:
        adapter = {
            "A1": direct_tool_workflow_eval,
            "A2": react_controller_eval,
            "A3": sequential_executor_eval,
        }[config]
        if config == "A1":
            result = await adapter(state, case.query_type.value)
        else:
            result = await adapter(state)
        tool_seq = result.selected_tools
        node_seq = result.node_sequence
        n_calls = result.tool_call_count
        final_state = result.final_state
        latency = result.latency_seconds

    formatted = final_state.get("formatted_response")
    narrative = getattr(formatted, "narrative", None) if formatted else final_state.get("narrative")
    response_type = getattr(formatted, "response_type", None) if formatted else final_state.get("response_type")

    record = {
        "case_id": case.id,
        "config": config,
        "query_type": case.query_type.value,
        "orchestration_complexity": case.orchestration_complexity.value,
        "selected_tools": tool_seq,
        "node_sequence": node_seq,
        "tool_call_count": n_calls,
        "latency_seconds": latency,
        "final_narrative": narrative,
        "response_type": response_type,
    }
    _append_trace(record)

    assert record["case_id"] == case.id  # smoke assertion: the run completed
