"""
Experiment II scorer — experiment_design.md section 3.3.1 step 5 / 3.5 / 3.6.

Reads:
  - evals/datasets/sql_grounding_cases.json (ground truth)
  - evals/results/sql_grounding_traces.jsonl (recorded runs, written by
    tests/test_e2e/test_sql_grounding_experiment.py)

Produces the metrics from 3.5, broken down by sql_complexity category and
overall total, matching the 3.6 output table template:
  Execution Accuracy, Execution Success Rate, Valid SQL Rate,
  Retry Success Rate, Number of Repair Iterations,
  Schema Selection Accuracy, Average Generation Time.

Usage:
    uv run python -m evals.sql_grounding_scorer
"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

from evals.datasets.schemas import SqlGroundingDataset, SqlGroundingCase

DATASETS_DIR = Path(__file__).parent / "datasets"
RESULTS_DIR = Path(__file__).parent / "results"
TRACE_PATH = RESULTS_DIR / "sql_grounding_traces.jsonl"

CONFIGS = ["S1", "S2", "S3"]
COMPLEXITIES = [
    "single_table_query", "multi_table_join", "aggregation", "nested_query",
    "window_function", "conditional_aggregation", "ambiguous_or_typo_entity",
    "questionnaire_metadata",
]


def _load_cases() -> dict[str, SqlGroundingCase]:
    with open(DATASETS_DIR / "sql_grounding_cases.json", encoding="utf-8") as f:
        raw = json.load(f)
    dataset = SqlGroundingDataset.model_validate(raw)
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


def _sql_is_valid(trace: dict) -> bool:
    """Valid SQL Rate: generated SQL exists and there was no sql_error
    classified as a syntax/security validation failure (i.e. it at least
    reached execution). This is a proxy — swap in check_sql_security /
    sqlglot parse validity here if stricter grading is needed."""
    return bool(trace.get("generated_sql")) and not trace.get("is_aborted", False)


def _executed_without_error(trace: dict) -> bool:
    return trace.get("generated_sql") is not None and not trace.get("sql_error")


def _must_include_ok(case: SqlGroundingCase, sql: str | None) -> bool:
    if not sql:
        return False
    sql_upper = sql.upper()
    return all(
        pattern.upper() in sql_upper or pattern in sql
        for pattern in case.expected_sql_behavior.must_include_sql_patterns
    )


def _must_not_include_ok(case: SqlGroundingCase, sql: str | None) -> bool:
    if not sql:
        return True
    sql_upper = sql.upper()
    return not any(pattern.upper() in sql_upper for pattern in case.expected_sql_behavior.must_not_include_sql_patterns)


def _execution_accuracy_proxy(case: SqlGroundingCase, trace: dict) -> bool | None:
    """Proxy execution accuracy: real accuracy needs comparing sql_result
    against gold_sql's actual executed result (row-level diff). Without a
    live DB connection to also run gold_sql at scoring time, this proxy
    instead checks the generated SQL executed successfully AND satisfied
    must_include/must_not_include pattern checks. Replace this function
    with a real gold-vs-actual row comparison once gold_sql is verified
    against the real DB snapshot (see notes_for_dataset_author on each
    case) — the hook point is here."""
    if not case.scoring.execution_accuracy_required:
        return None
    sql = trace.get("generated_sql")
    if not _executed_without_error(trace):
        return False
    return _must_include_ok(case, sql) and _must_not_include_ok(case, sql)


def _schema_selection_correct(case: SqlGroundingCase, trace: dict) -> bool | None:
    if not case.scoring.schema_selection_required:
        return None
    actual_tables = set(trace.get("relevant_tables") or [])
    expected_tables = set(case.expected_grounding.expected_tables)
    if not expected_tables:
        return None
    return expected_tables.issubset(actual_tables)


def score() -> dict:
    cases = _load_cases()
    traces = _load_traces()
    if not traces:
        print(f"No traces found at {TRACE_PATH}. Run tests/test_e2e/test_sql_grounding_experiment.py first "
              f"(with RUN_LLM_EVALS=1) to generate them.")
        return {}

    by_config_complexity = defaultdict(list)

    for t in traces:
        case = cases.get(t["case_id"])
        if case is None:
            continue
        config = t["config"]
        row = {
            "case_id": case.id,
            "valid_sql": _sql_is_valid(t),
            "executed_ok": _executed_without_error(t),
            "execution_accuracy": _execution_accuracy_proxy(case, t),
            "schema_selection_correct": _schema_selection_correct(case, t),
            "attempt_count": t.get("attempt_count", 0),
            "retry_expected": case.scoring.retry_expected,
            "retried": (t.get("attempt_count", 0) or 0) > 1,
            "latency_seconds": t.get("latency_seconds"),
        }
        by_config_complexity[(config, case.sql_complexity.value)].append(row)

    table = _build_output_table(by_config_complexity)
    return table


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


def _build_output_table(by_cc: dict) -> dict:
    out = {}
    for config in CONFIGS:
        out[config] = {}
        all_rows = []
        for cx in COMPLEXITIES:
            rows = by_cc.get((config, cx), [])
            all_rows.extend(rows)
            retried_rows = [r for r in rows if r["retried"]]
            out[config][cx] = {
                "execution_accuracy": _rate(rows, "execution_accuracy"),
                "execution_success_rate": _rate(rows, "executed_ok"),
                "valid_sql_rate": _rate(rows, "valid_sql"),
                "retry_success_rate": _rate(retried_rows, "execution_accuracy"),
                "avg_repair_iterations": _avg(rows, "attempt_count"),
                "schema_selection_accuracy": _rate(rows, "schema_selection_correct"),
                "avg_generation_time_seconds": _avg(rows, "latency_seconds"),
                "n": len(rows),
            }
        retried_all = [r for r in all_rows if r["retried"]]
        out[config]["TOTAL"] = {
            "execution_accuracy": _rate(all_rows, "execution_accuracy"),
            "execution_success_rate": _rate(all_rows, "executed_ok"),
            "valid_sql_rate": _rate(all_rows, "valid_sql"),
            "retry_success_rate": _rate(retried_all, "execution_accuracy"),
            "avg_repair_iterations": _avg(all_rows, "attempt_count"),
            "schema_selection_accuracy": _rate(all_rows, "schema_selection_correct"),
            "avg_generation_time_seconds": _avg(all_rows, "latency_seconds"),
            "n": len(all_rows),
        }
    return out


def print_table(table: dict):
    print("\n=== Tabel 4.Y Hasil Eksperimen II — Perbandingan Konfigurasi SQL Pipeline ===")
    print(json.dumps(table, indent=2))


if __name__ == "__main__":
    results = score()
    print_table(results)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "sql_grounding_scored.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved scored table to {out_path}")
