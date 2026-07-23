from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from langchain_core.caches import InMemoryCache
from langchain_core.globals import set_llm_cache

import pytest

from agent.orchestrator import main_graph
from core.scope import ScopeEntry, UserRole, UserScope
from evals.datasets.schemas import UatEndToEndCase, UatEndToEndDataset
from evals.experiments.uat_end_to_end import (
    UatEndToEndRunResult,
    build_validation_flags,
    deterministic_task_success,
    judge_answer,
    response_payload,
    score_report,
    tools_from_state,
)
from tests.conftest import DATASETS_DIR, RESULTS_DIR


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("RUN_UAT_E2E") != "1", reason="Set RUN_UAT_E2E=1 to run UAT end-to-end evaluation"),
]


DATASET_PATH = DATASETS_DIR / "experiments" / "uat_end_to_end_cases.json"
CHECKPOINT_FILE = RESULTS_DIR / "uat_end_to_end_checkpoint.jsonl"


def _load_cases() -> list[UatEndToEndCase]:
    if not DATASET_PATH.exists():
        pytest.skip(f"{DATASET_PATH} is required")
    dataset = UatEndToEndDataset.model_validate_json(DATASET_PATH.read_text())
    assert dataset.total_cases == len(dataset.cases)
    return dataset.cases


def _scope_for_role(role: str) -> UserScope:
    role_enum = UserRole(role)
    if role_enum == UserRole.DOSEN:
        entry = ScopeEntry(
            user_role_id=1,
            role=role_enum,
            dosen_id=int(os.getenv("UAT_DOSEN_ID", "556")),
            is_prime=True,
        )
        return UserScope(user_id=int(os.getenv("UAT_DOSEN_USER_ID", "1001")), active_role=entry, available_roles=[entry])
    if role_enum == UserRole.KAPRODI:
        entry = ScopeEntry(
            user_role_id=1,
            role=role_enum,
            no_ps=int(os.getenv("UAT_NO_PS", "135")),
            is_prime=True,
        )
        return UserScope(user_id=int(os.getenv("UAT_KAPRODI_USER_ID", "1002")), active_role=entry, available_roles=[entry])
    if role_enum == UserRole.DEKAN:
        entry = ScopeEntry(
            user_role_id=1,
            role=role_enum,
            kd_fak=os.getenv("UAT_KD_FAK", "STEI"),
            is_prime=True,
        )
        return UserScope(user_id=int(os.getenv("UAT_DEKAN_USER_ID", "1003")), active_role=entry, available_roles=[entry])
    if role_enum == UserRole.DIREKTORAT:
        entry = ScopeEntry(user_role_id=1, role=role_enum, is_prime=True)
        return UserScope(user_id=int(os.getenv("UAT_DIREKTORAT_USER_ID", "1004")), active_role=entry, available_roles=[entry])
    raise ValueError(f"Unsupported UAT role: {role}")


def _filter_cases(cases: list[UatEndToEndCase]) -> list[UatEndToEndCase]:
    target_role = os.getenv("TARGET_ROLE") or os.getenv("UAT_ROLE")
    if target_role:
        cases = [case for case in cases if case.role == target_role]

    target_case_id = os.getenv("TARGET_CASE_ID")
    if target_case_id:
        cases = [case for case in cases if case.id == target_case_id]

    target_aspect = os.getenv("TARGET_ASPECT")
    if target_aspect:
        cases = [case for case in cases if case.analysis_aspect == target_aspect]

    target_mix = os.getenv("TARGET_DATA_SOURCE_MIX")
    if target_mix:
        cases = [case for case in cases if case.data_source_mix == target_mix]

    return cases


def _load_checkpoint(valid_case_ids: set[str]) -> tuple[list[UatEndToEndRunResult], set[str]]:
    results_map: dict[str, UatEndToEndRunResult] = {}
    completed: set[str] = set()
    if not CHECKPOINT_FILE.exists():
        return [], completed

    with CHECKPOINT_FILE.open() as f:
        for line in f:
            if not line.strip():
                continue
            result = UatEndToEndRunResult.model_validate_json(line)
            if result.case_id not in valid_case_ids:
                continue
            results_map[result.case_id] = result
            if not result.error:
                completed.add(result.case_id)
            else:
                completed.discard(result.case_id)
    return list(results_map.values()), completed


def _initial_state(make_state, case: UatEndToEndCase):
    return make_state(
        query=case.question,
        scope=_scope_for_role(case.role),
        session_id=f"uat-e2e-{case.role}-{case.id}",
        messages=[],
    )


async def _run_case(make_state, case: UatEndToEndCase) -> UatEndToEndRunResult:
    state = _initial_state(make_state, case)
    run_config = {
        "run_name": f"uat_e2e_{case.role}_{case.id}",
        "tags": ["uat_e2e", case.role, case.analysis_aspect],
        "metadata": {
            "case_id": case.id,
            "role": case.role,
            "analysis_aspect": case.analysis_aspect,
            "data_source_mix": case.data_source_mix,
        },
    }

    try:
        final_state = await main_graph.ainvoke(state, config=run_config)
        response_type, narrative = response_payload(final_state)
        tools = tools_from_state(final_state, response_type)
        result = UatEndToEndRunResult(
            case_id=case.id,
            role=case.role,
            analysis_aspect=case.analysis_aspect,
            data_source_mix=case.data_source_mix,
            question=case.question,
            selected_tool_sequence=tools,
            final_response_type=response_type,
            final_narrative=narrative,
            tool_call_count=len([tool for tool in tools if tool != "clarification"]),
            validation_flags=build_validation_flags(case, final_state, response_type, None),
        )
        result.task_success = deterministic_task_success(case, result)

        if os.getenv("RUN_UAT_LLM_JUDGE") == "1":
            scores = await judge_answer(case, final_state, narrative)
            result.correctness = scores.correctness
            result.faithfulness = scores.faithfulness
            result.completeness = scores.completeness
            result.judge_rationale = scores.rationale

        return result
    except Exception as exc:
        return UatEndToEndRunResult(
            case_id=case.id,
            role=case.role,
            analysis_aspect=case.analysis_aspect,
            data_source_mix=case.data_source_mix,
            question=case.question,
            error=str(exc),
        )


async def test_uat_end_to_end_report(make_state):
    set_llm_cache(InMemoryCache())
    cases = _filter_cases(_load_cases())
    if not cases:
        pytest.skip("No UAT end-to-end cases selected by current filters")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    valid_case_ids = {case.id for case in cases}
    results, completed = _load_checkpoint(valid_case_ids)

    print("\nStarting UAT end-to-end evaluation:")
    print(f"   • Dataset Cases : {len(cases)}")
    print(f"   • Target Role   : {os.getenv('TARGET_ROLE') or os.getenv('UAT_ROLE') or 'all'}")
    print(f"   • LLM Judge     : {os.getenv('RUN_UAT_LLM_JUDGE') == '1'}")
    print(f"   • Cached Runs   : {len(completed)}\n", flush=True)

    current_idx = len(completed)
    for case in cases:
        if case.id in completed:
            continue

        current_idx += 1
        print(f"[{current_idx}/{len(cases)}] Role: {case.role:<10} | Case: {case.id} ... ", end="", flush=True)
        start = datetime.now(timezone.utc)
        result = await _run_case(make_state, case)
        result.latency_seconds = (datetime.now(timezone.utc) - start).total_seconds()
        results.append(result)

        if result.error:
            print(f"FAILED ({result.error}) [{result.latency_seconds:.2f}s]", flush=True)
        elif result.task_success:
            print(f"PASSED [{result.latency_seconds:.2f}s]", flush=True)
        else:
            print(f"NEEDS REVIEW [{result.latency_seconds:.2f}s]", flush=True)

        with CHECKPOINT_FILE.open("a") as f:
            f.write(result.model_dump_json() + "\n")
            f.flush()

    report = score_report(cases, results)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    role_suffix = os.getenv("TARGET_ROLE") or os.getenv("UAT_ROLE") or "all"
    output_path = RESULTS_DIR / f"uat_end_to_end_{role_suffix}_{run_id}.json"
    output_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2))
    assert output_path.exists()
