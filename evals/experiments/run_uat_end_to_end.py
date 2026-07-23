from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agent.llm import get_llm
from agent.orchestrator import main_graph
from agent.state import AgentState
from core.config import settings
from core.database import close_db_pool, init_db_pool
from core.scope import ScopeEntry, UserRole, UserScope


import logging

logging.basicConfig(level=logging.ERROR)
logging.getLogger("agent").setLevel(logging.ERROR)
logging.getLogger("core").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = ROOT_DIR / "evals" / "datasets" / "experiments" / "uat_end_to_end_cases.json"
DEFAULT_RESULTS_DIR = ROOT_DIR / "evals" / "results"


class EndToEndCase(BaseModel):
    id: str
    role: str
    analysis_aspect: str
    data_source_mix: str
    question: str
    expected_tools: list[str] = Field(default_factory=list)
    expected_answer_elements: list[str] = Field(default_factory=list)
    task_success_criteria: list[str] = Field(default_factory=list)


class EndToEndDataset(BaseModel):
    dataset_name: str
    version: str
    cases: list[EndToEndCase]


class JudgeScores(BaseModel):
    correctness: float = Field(ge=0.0, le=1.0)
    faithfulness: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    rationale: str


class RunResult(BaseModel):
    case_id: str
    role: str
    analysis_aspect: str
    data_source_mix: str
    question: str
    task_success: bool
    correctness: float | None = None
    faithfulness: int | None = None
    completeness: int | None = None
    latency_seconds: float
    selected_tools: list[str] = Field(default_factory=list)
    final_answer: str | None = None
    response_type: str | None = None
    query_type: str | None = None
    generated_sql: str | None = None
    sql_row_count: int | None = None
    sql_error: str | None = None
    is_aborted: bool = False
    abort_reason: str | None = None
    judge_rationale: str | None = None
    error: str | None = None


def to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "value"):
        return value.value
    return str(value)


def compact_text(value: Any, limit: int = 9000) -> str:
    text = json.dumps(to_jsonable(value), ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[[TRUNCATED]]"


def load_dataset(path: Path) -> EndToEndDataset:
    return EndToEndDataset.model_validate_json(path.read_text())


def filter_cases(cases: list[EndToEndCase], args: argparse.Namespace) -> list[EndToEndCase]:
    selected = cases
    if args.role != "all":
        selected = [case for case in selected if case.role == args.role]
    if args.case_id:
        selected = [case for case in selected if case.id == args.case_id]
    if args.aspect:
        selected = [case for case in selected if case.analysis_aspect == args.aspect]
    if args.limit is not None:
        selected = selected[: args.limit]
    return selected


def scope_for_role(role: str) -> UserScope:
    if role == "dosen":
        entry = ScopeEntry(
            user_role_id=1,
            role=UserRole.DOSEN,
            dosen_id=int(os.getenv("UAT_DOSEN_ID", "556")),
            is_prime=True,
        )
        return UserScope(user_id=int(os.getenv("UAT_DOSEN_USER_ID", "1001")), active_role=entry, available_roles=[entry])
    if role == "kaprodi":
        entry = ScopeEntry(user_role_id=1, role=UserRole.KAPRODI, no_ps=int(os.getenv("UAT_NO_PS", "135")), is_prime=True)
        return UserScope(user_id=int(os.getenv("UAT_KAPRODI_USER_ID", "1002")), active_role=entry, available_roles=[entry])
    if role == "dekan":
        entry = ScopeEntry(user_role_id=1, role=UserRole.DEKAN, kd_fak=os.getenv("UAT_KD_FAK", "STEI"), is_prime=True)
        return UserScope(user_id=int(os.getenv("UAT_DEKAN_USER_ID", "1003")), active_role=entry, available_roles=[entry])
    if role == "direktorat":
        entry = ScopeEntry(user_role_id=1, role=UserRole.DIREKTORAT, is_prime=True)
        return UserScope(user_id=int(os.getenv("UAT_DIREKTORAT_USER_ID", "1004")), active_role=entry, available_roles=[entry])
    raise ValueError(f"Unsupported role: {role}")


def build_state(case: EndToEndCase) -> AgentState:
    return AgentState(
        user_scope=scope_for_role(case.role),
        session_id=f"uat-e2e-{case.id.lower()}",
        messages=[{"role": "user", "content": case.question}],
        conversation_summary=None,
        session_entities=None,
        chart_context=None,
        raw_query=case.question,
        needs_rewrite=None,
        rewritten_query=None,
        effective_query=case.question,
        domain=None,
        query_type=None,
        plan=[],
        current_step_index=0,
        steps_completed=[],
        reasoning_history=[],
        content_filter_result=None,
        extracted_keywords=None,
        detected_entities=None,
        relevant_tables=None,
        schema_context=None,
        generated_sql=None,
        validation_status=None,
        validation_errors=[],
        sql_result=None,
        sql_error=None,
        sql_row_count=None,
        rag_query=None,
        rag_chunks=None,
        rag_source_types=None,
        rag_tipe_konten=None,
        rag_scope_override=None,
        rag_attempt_count=0,
        rag_confidence=None,
        rag_action=None,
        rag_refined_query=None,
        faithfulness_score=None,
        faithfulness_action=None,
        rag_generated_answer=None,
        rag_citations=None,
        answer_is_valid=None,
        next_step=None,
        formatted_response=None,
        attempt_count=0,
        max_attempts=settings.MAX_SQL_ATTEMPTS,
        error_history=[],
        is_aborted=False,
        abort_reason=None,
        empty_result_reason=None,
    )


def response_from_state(state: dict[str, Any]) -> tuple[str | None, str | None]:
    response = state.get("formatted_response")
    if response is None:
        return None, None
    if hasattr(response, "narrative"):
        return response.narrative, response.response_type
    if isinstance(response, dict):
        return response.get("narrative"), response.get("response_type")
    return str(response), None


def selected_tools_from_state(state: dict[str, Any]) -> list[str]:
    tools: list[str] = []
    for step in state.get("steps_completed") or []:
        action = getattr(step, "action", None)
        if action is None and isinstance(step, dict):
            action = step.get("action")
        if action:
            tools.append(str(action))
    if state.get("generated_sql") and "sql" not in tools:
        tools.append("sql")
    if state.get("rag_chunks") and "rag" not in tools:
        tools.append("rag")
    return list(dict.fromkeys(tools))


def deterministic_success(state: dict[str, Any], final_answer: str | None) -> bool:
    if state.get("is_aborted"):
        return False
    if state.get("sql_error"):
        return False
    if not final_answer or not final_answer.strip():
        return False
    response_type = response_from_state(state)[1]
    return response_type not in {"error", "clarification"}


async def judge_case(case: EndToEndCase, state: dict[str, Any], final_answer: str | None) -> JudgeScores:
    llm = get_llm("llm_evaluation", force_json=False).with_structured_output(JudgeScores)
    prompt = f"""
Evaluate a final answer from an academic portfolio analytics agent.

Question:
{case.question}

Expected answer elements:
{json.dumps(case.expected_answer_elements, ensure_ascii=False)}

Task success criteria:
{json.dumps(case.task_success_criteria, ensure_ascii=False)}

Final answer:
{final_answer or ""}

Tool evidence and execution state:
{compact_text({
    "selected_tools": selected_tools_from_state(state),
    "query_type": to_jsonable(state.get("query_type")),
    "generated_sql": state.get("generated_sql"),
    "sql_row_count": state.get("sql_row_count"),
    "sql_error": state.get("sql_error"),
    "sql_result": state.get("sql_result"),
    "rag_chunks": state.get("rag_chunks"),
    "steps_completed": state.get("steps_completed"),
})}

Score correctness from 0.0 to 1.0. Score faithfulness and completeness from 1 to 5.
Correctness measures factual alignment with evidence.
Faithfulness measures whether claims are supported by tool evidence.
Completeness measures whether the answer covers the requested task.
"""
    return await llm.ainvoke(prompt)


async def run_case(case: EndToEndCase, llm_judge: bool) -> RunResult:
    start = time.perf_counter()
    try:
        state = await main_graph.ainvoke(build_state(case))
        latency = time.perf_counter() - start
        final_answer, response_type = response_from_state(state)
        result = RunResult(
            case_id=case.id,
            role=case.role,
            analysis_aspect=case.analysis_aspect,
            data_source_mix=case.data_source_mix,
            question=case.question,
            task_success=deterministic_success(state, final_answer),
            latency_seconds=round(latency, 4),
            selected_tools=selected_tools_from_state(state),
            final_answer=final_answer,
            response_type=response_type,
            query_type=to_jsonable(state.get("query_type")),
            generated_sql=state.get("generated_sql"),
            sql_row_count=state.get("sql_row_count"),
            sql_error=state.get("sql_error"),
            is_aborted=bool(state.get("is_aborted")),
            abort_reason=state.get("abort_reason"),
        )
        if llm_judge:
            scores = await judge_case(case, state, final_answer)
            result.correctness = scores.correctness
            result.faithfulness = scores.faithfulness
            result.completeness = scores.completeness
            result.judge_rationale = scores.rationale
            result.task_success = result.task_success and scores.correctness >= 0.7 and scores.faithfulness >= 3 and scores.completeness >= 3
        return result
    except Exception as exc:
        latency = time.perf_counter() - start
        return RunResult(
            case_id=case.id,
            role=case.role,
            analysis_aspect=case.analysis_aspect,
            data_source_mix=case.data_source_mix,
            question=case.question,
            task_success=False,
            latency_seconds=round(latency, 4),
            error=str(exc),
        )


def average(values: list[float | int | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    return round(sum(present) / len(present), 4)


def aggregate(results: list[RunResult], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[RunResult]] = {}
    for result in results:
        groups.setdefault(getattr(result, key), []).append(result)
    rows = []
    for name, items in sorted(groups.items()):
        rows.append({
            key: name,
            "n": len(items),
            "task_success_rate": round(sum(1 for item in items if item.task_success) / len(items), 4),
            "correctness": average([item.correctness for item in items]),
            "faithfulness": average([item.faithfulness for item in items]),
            "completeness": average([item.completeness for item in items]),
            "avg_latency_seconds": average([item.latency_seconds for item in items]),
        })
    return rows


def write_checkpoint(path: Path, result: RunResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as file:
        file.write(json.dumps(result.model_dump(mode="json"), ensure_ascii=False) + "\n")


def print_result(result: RunResult) -> None:
    status_symbol = "✅ PASS" if result.task_success else "⚠️ NEEDS REVIEW"
    print("\n" + "=" * 80)
    print(f"[{result.case_id}] Role: {result.role.upper()} | Status: {status_symbol}")
    print(f"Question : {result.question}")
    print(f"Tools    : {', '.join(result.selected_tools) if result.selected_tools else '-'}")
    print(f"Latency  : {result.latency_seconds:.2f}s")
    if result.correctness is not None:
        print(f"Metrics  : Correctness={result.correctness:.2f} | Faithfulness={result.faithfulness}/5 | Completeness={result.completeness}/5")
    
    if result.final_answer:
        print(f"\n--- Agent Answer ---\n{result.final_answer}")
    if result.judge_rationale:
        print(f"\n--- Judge Rationale ---\n{result.judge_rationale}")
    if result.error:
        print(f"\n❌ Error: {result.error}")
    print("=" * 80)


def read_checkpoint_completed(path: Path) -> dict[str, RunResult]:
    completed = {}
    if not path.exists():
        return completed
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                data = json.loads(line_str)
                res = RunResult(**data)
                if not res.error:
                    completed[res.case_id] = res
            except Exception:
                pass
    return completed


async def run(args: argparse.Namespace) -> int:
    dataset = load_dataset(args.dataset)
    cases = filter_cases(dataset.cases, args)
    if not cases:
        print("No cases selected.")
        return 1

    args.results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = args.results_dir / f"uat_end_to_end_{args.role}_{timestamp}.json"
    checkpoint_path = args.results_dir / f"uat_end_to_end_checkpoint_{args.role}.jsonl"

    completed_map = read_checkpoint_completed(checkpoint_path) if args.resume else {}

    print(f"Dataset   : {dataset.dataset_name} v{dataset.version}")
    print(f"Cases     : {len(cases)}")
    print(f"Role      : {args.role}")
    print(f"LLM judge : {args.llm_judge}")
    print(f"Resume    : {args.resume} ({len(completed_map)} cases already completed)")
    print(f"Checkpoint: {checkpoint_path}")

    await init_db_pool()
    results: list[RunResult] = []
    try:
        for case in cases:
            if case.id in completed_map:
                res = completed_map[case.id]
                results.append(res)
                print(f"⏩ [SKIP] {case.id} (Loaded from checkpoint)")
                continue
            result = await run_case(case, args.llm_judge)
            results.append(result)
            write_checkpoint(checkpoint_path, result)
            print_result(result)
    finally:
        await close_db_pool()

    report = {
        "dataset_name": dataset.dataset_name,
        "dataset_version": dataset.version,
        "run_timestamp": timestamp,
        "role_filter": args.role,
        "llm_judge": args.llm_judge,
        "case_count": len(results),
        "by_role": aggregate(results, "role"),
        "by_analysis_aspect": aggregate(results, "analysis_aspect"),
        "cases": [result.model_dump(mode="json") for result in results],
    }
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nReport: {output_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--role", choices=["all", "dosen", "kaprodi", "dekan", "direktorat"], default="all")
    parser.add_argument("--case-id")
    parser.add_argument("--aspect")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--llm-judge", action="store_true")
    parser.add_argument("--print-answers", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    raise SystemExit(asyncio.run(run(parse_args())))


if __name__ == "__main__":
    main()
