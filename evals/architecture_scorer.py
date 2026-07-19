"""
Experiment I scorer — experiment_design.md section 2.3.1 step 6 / 2.5 / 2.6.

Reads:
  - evals/datasets/architecture_orchestration_cases.json (ground truth)
  - evals/results/architecture_orchestration_traces.jsonl (recorded runs,
    written by tests/test_e2e/test_architecture_orchestration.py)

Produces the four result tables from 2.6:
  I.1 Routing Quality      (Tool Selection Accuracy, Tool Sequence Accuracy)
  I.2 Task Completion      (Task Success Rate, Correctness)
  I.3 Answer Quality       (Faithfulness, Completeness)  [LLM-judge, optional]
  I.4 Efficiency           (Tool Calls, Latency, Tokens)

Usage:
    uv run python -m evals.architecture_scorer

Correctness/Task-Success here are computed with simple rule-based checks
against required_answer_facts / expected_tool_sequence — NOT a full LLM
judge. Faithfulness/Completeness (I.3) require an LLM judge and are only
computed if RUN_LLM_JUDGE=1 and evals/llm_judge.py exposes a compatible
`judge_faithfulness_completeness(narrative, steps_completed, rubric)`
function; otherwise those two columns are left as None and flagged in the
printed table so they aren't mistaken for real zeros.
"""
from __future__ import annotations
import json
import os
from collections import defaultdict
from pathlib import Path
from statistics import mean

from evals.datasets.schemas import ArchitectureDataset, ArchitectureCase

DATASETS_DIR = Path(__file__).parent / "datasets"
RESULTS_DIR = Path(__file__).parent / "results"
TRACE_PATH = RESULTS_DIR / "architecture_orchestration_traces.jsonl"

CONFIGS = ["A1", "A2", "A3", "A4"]
COMPLEXITIES = ["C1_single_tool", "C2_parallel_multi_tool", "C3_sequential", "C4_dependent_multi_step"]
QUERY_TYPES = [
    "data_lookup", "text_lookup", "analytical_numeric", "analytical_text",
    "analytical_hybrid", "diagnostic", "comparative", "summarization",
    "chart_interpret", "clarification_needed",
]


def _load_cases() -> dict[str, ArchitectureCase]:
    with open(DATASETS_DIR / "architecture_orchestration_cases.json", encoding="utf-8") as f:
        raw = json.load(f)
    dataset = ArchitectureDataset.model_validate(raw)
    return {c.id: c for c in dataset.cases}


def _load_traces() -> list[dict]:
    if not TRACE_PATH.exists():
        return []
    traces = []
    with open(TRACE_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                traces.append(json.loads(line))
    return traces


def _tool_selection_correct(case: ArchitectureCase, actual_tools: list[str]) -> bool:
    expected = set(t for t in case.expected_behavior.expected_tool_sequence)
    actual = set(t for t in actual_tools if t != "synthesis_only")
    return expected == actual


def _tool_sequence_correct(case: ArchitectureCase, actual_tools: list[str]) -> bool | None:
    """Only meaningful for C3/C4 (sequential/dependent) — order matters there."""
    if case.orchestration_complexity.value not in ("C3_sequential", "C4_dependent_multi_step"):
        return None
    expected = [t for t in case.expected_behavior.expected_tool_sequence]
    actual = [t for t in actual_tools if t != "synthesis_only"]
    return expected == actual


def _task_success(case: ArchitectureCase, narrative: str | None) -> bool:
    if not narrative:
        return False
    if case.query_type.value == "clarification_needed":
        # crude heuristic: a clarification response should end with a question
        return "?" in narrative
    text = narrative.lower()
    # crude heuristic: at least half the required facts' keywords appear.
    # Real scoring should replace this with the rubric checklist / LLM judge.
    hits = 0
    for fact in case.expected_behavior.required_answer_facts:
        keywords = [w.strip("?.,:;").lower() for w in fact.split() if len(w) > 4]
        if any(kw in text for kw in keywords):
            hits += 1
    total = max(len(case.expected_behavior.required_answer_facts), 1)
    return (hits / total) >= 0.5


def _try_llm_judge(narrative: str | None, steps_completed, rubric):
    if os.getenv("RUN_LLM_JUDGE") != "1":
        return None, None
    try:
        from evals.llm_judge import judge_faithfulness_completeness  # optional, may not exist yet
    except ImportError:
        return None, None
    try:
        result = judge_faithfulness_completeness(narrative, steps_completed, rubric)
        return result.get("faithfulness"), result.get("completeness")
    except Exception:
        return None, None


def score() -> dict:
    cases = _load_cases()
    traces = _load_traces()
    if not traces:
        print(f"No traces found at {TRACE_PATH}. Run tests/test_e2e/test_architecture_orchestration.py first "
              f"(with RUN_LLM_EVALS=1) to generate them.")
        return {}

    by_config_complexity = defaultdict(list)  # (config, complexity) -> list of per-case dicts
    by_config_querytype = defaultdict(list)

    for t in traces:
        case = cases.get(t["case_id"])
        if case is None:
            continue
        config = t["config"]
        tool_sel_ok = _tool_selection_correct(case, t["selected_tools"])
        tool_seq_ok = _tool_sequence_correct(case, t["selected_tools"])
        success = _task_success(case, t.get("final_narrative"))
        faithfulness, completeness = _try_llm_judge(
            t.get("final_narrative"), t.get("selected_tools"), case.scoring_rubric.model_dump()
        )

        row = {
            "case_id": case.id,
            "tool_selection_correct": tool_sel_ok,
            "tool_sequence_correct": tool_seq_ok,
            "task_success": success,
            "faithfulness": faithfulness,
            "completeness": completeness,
            "tool_call_count": t.get("tool_call_count", 0),
            "latency_seconds": t.get("latency_seconds"),
        }
        by_config_complexity[(config, case.orchestration_complexity.value)].append(row)
        by_config_querytype[(config, case.query_type.value)].append(row)

    tables = {
        "I.1_routing_quality": _table_routing_quality(by_config_complexity),
        "I.2_task_completion": _table_task_completion(by_config_complexity),
        "I.3_answer_quality": _table_answer_quality(by_config_complexity),
        "I.3b_task_success_by_query_type": _table_success_by_query_type(by_config_querytype),
        "I.4_efficiency": _table_efficiency(by_config_complexity),
    }
    return tables


def _rate(rows: list[dict], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    if not vals:
        return None
    return round(sum(1 for v in vals if v) / len(vals), 4)


def _avg(rows: list[dict], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    if not vals:
        return None
    return round(mean(vals), 4)


def _table_routing_quality(by_cc: dict) -> dict:
    out = {}
    for config in CONFIGS:
        out[config] = {}
        for cx in COMPLEXITIES:
            rows = by_cc.get((config, cx), [])
            out[config][cx] = {
                "tool_selection_accuracy": _rate(rows, "tool_selection_correct"),
                "tool_sequence_accuracy": _rate(rows, "tool_sequence_correct"),
                "n": len(rows),
            }
    return out


def _table_task_completion(by_cc: dict) -> dict:
    out = {}
    for config in CONFIGS:
        out[config] = {}
        for cx in COMPLEXITIES:
            rows = by_cc.get((config, cx), [])
            out[config][cx] = {"task_success_rate": _rate(rows, "task_success"), "n": len(rows)}
    return out


def _table_answer_quality(by_cc: dict) -> dict:
    out = {}
    for config in CONFIGS:
        out[config] = {}
        for cx in COMPLEXITIES:
            rows = by_cc.get((config, cx), [])
            out[config][cx] = {
                "faithfulness": _avg(rows, "faithfulness"),
                "completeness": _avg(rows, "completeness"),
                "n": len(rows),
                "note": None if os.getenv("RUN_LLM_JUDGE") == "1" else "RUN_LLM_JUDGE=0 — not computed",
            }
    return out


def _table_success_by_query_type(by_cqt: dict) -> dict:
    out = {}
    for config in CONFIGS:
        out[config] = {}
        for qt in QUERY_TYPES:
            rows = by_cqt.get((config, qt), [])
            out[config][qt] = {"task_success_rate": _rate(rows, "task_success"), "n": len(rows)}
    return out


def _table_efficiency(by_cc: dict) -> dict:
    out = {}
    for config in CONFIGS:
        rows = [r for cx in COMPLEXITIES for r in by_cc.get((config, cx), [])]
        out[config] = {
            "avg_tool_calls": _avg(rows, "tool_call_count"),
            "avg_latency_seconds": _avg(rows, "latency_seconds"),
            "n": len(rows),
        }
    return out


def print_tables(tables: dict):
    for name, table in tables.items():
        print(f"\n=== {name} ===")
        print(json.dumps(table, indent=2))


if __name__ == "__main__":
    results = score()
    print_tables(results)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "architecture_orchestration_scored.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved scored tables to {out_path}")
