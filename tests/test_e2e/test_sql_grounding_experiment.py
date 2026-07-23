import asyncio
import os
import json
import pytest
from pathlib import Path
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from core.scope import UserScope, ScopeEntry, UserRole
from core.sql_executor import PsycopgExecutor
from agent.tools.sql.state import SQLState
from evals.datasets.schemas import SqlGroundingDataset, SqlGroundingCase
from evals.experiments.experiment_2.sql_pipeline_variants import (
    build_s1_pipeline,
    build_s2_pipeline,
    build_s3_pipeline,
)

ROOT_DIR = Path(__file__).parent.parent.parent
DATASETS_DIR = ROOT_DIR / "evals" / "datasets"
RESULTS_DIR = ROOT_DIR / "evals" / "results"

USE_TINY = os.getenv("USE_TINY_DATASET") == "1"
DATASET_FILE = "sql_grounding_tiny.json" if USE_TINY else "sql_grounding_cases.json"
DATASET_PATH = DATASETS_DIR / "experiments" / DATASET_FILE
CHECKPOINT_FILE = RESULTS_DIR / "sql_grounding_checkpoint_2.jsonl"

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("RUN_SQL_EXPERIMENT") != "1", reason="Set RUN_SQL_EXPERIMENT=1 to run"),
]


class SqlGroundingRunResult(BaseModel):
    case_id: str
    variant: str
    sql_complexity: str
    
    # State tracking
    generated_sql: str | None = None
    relevant_tables: list[str] = Field(default_factory=list)
    schema_context: str | None = None
    sql_error: str | None = None
    attempt_count: int = 0
    is_aborted: bool = False
    
    # Metrics
    execution_success: bool = False
    execution_accurate: bool = False
    latency_seconds: float = 0.0


def _compare_sql_results(gen_rows: list[dict] | None, gold_rows: list[dict] | None) -> bool:
    if gen_rows is None or gold_rows is None:
        return False
    if not gen_rows and not gold_rows:
        return True
        
    def to_row_set(rows: list[dict]) -> set[tuple]:
        tuples = []
        for r in rows:
            tuples.append(tuple(sorted(str(v).strip().lower() if v is not None else "__null__" for v in r.values())))
        return set(tuples)
        
    try:
        gen_set = to_row_set(gen_rows)
        gold_set = to_row_set(gold_rows)
        return gen_set == gold_set
    except Exception:
        return False


def _build_mock_user_scope(scope_def_obj) -> UserScope:
    scope_def = scope_def_obj.model_dump()
    role_str = scope_def.get("role", "dosen").lower()
    
    # Try mapping to enum
    try:
        role_enum = UserRole(role_str)
    except ValueError:
        role_enum = UserRole.DOSEN
        
    prodi_list = scope_def.get("allowed_programs", [])
    fak_list = scope_def.get("allowed_faculties", [])
    
    scope_entry = ScopeEntry(
        user_role_id=1,
        role=role_enum,
        no_ps=int(prodi_list[0]) if prodi_list else None,
        kd_fak=fak_list[0] if fak_list else None,
        is_prime=True
    )
    return UserScope(user_id=1, active_role=scope_entry, available_roles=[scope_entry])


def _load_sql_cases() -> list[SqlGroundingCase]:
    if not DATASET_PATH.exists():
        pytest.skip(f"{DATASET_PATH} is required")
    raw = json.loads(DATASET_PATH.read_text())
    dataset = SqlGroundingDataset.model_validate(raw)
    return dataset.cases


async def test_sql_grounding_experiment():
    cases = _load_sql_cases()
    
    target_case_id = os.getenv("TARGET_CASE_ID")
    if target_case_id:
        cases = [c for c in cases if c.id == target_case_id]
        
    target_complexity = os.getenv("TARGET_COMPLEXITY")
    if target_complexity:
        cases = [c for c in cases if c.sql_complexity == target_complexity]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    
    completed = set()
    results_map = {}
    valid_case_ids = {c.id for c in cases}
    
    if os.getenv("RESET_CHECKPOINT") == "1" and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()

    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, "r") as f:
            for line in f:
                if not line.strip(): continue
                res = SqlGroundingRunResult.model_validate_json(line)
                if res.case_id not in valid_case_ids:
                    continue
                results_map[(res.variant, res.case_id)] = res
                if res.execution_success:
                    completed.add((res.variant, res.case_id))

    results = list(results_map.values())
    
    variants = ["S1", "S3", "S2"]
    total_runs = len(cases) * len(variants)
    current_idx = len(completed)

    print(f"\n Starting Experiment 2: SQL Pipeline Architecture:")
    print(f"   • Dataset Cases : {len(cases)}")
    print(f"   • Total Runs    : {total_runs}")
    print(f"   • Cached Runs   : {len(completed)}\n", flush=True)

    executor = PsycopgExecutor()
    s1_pipeline = build_s1_pipeline(executor)
    s2_pipeline = build_s2_pipeline(executor)
    s3_pipeline = build_s3_pipeline(executor)

    pipelines = {
        "S1": s1_pipeline,
        "S2": s2_pipeline,
        "S3": s3_pipeline
    }

    for variant_name in variants:
        pipeline = pipelines[variant_name]
        for case in cases:
            if (variant_name, case.id) in completed:
                continue

            current_idx += 1
            print(f"[{current_idx}/{total_runs}] Variant: {variant_name:<2} | Case: {case.id} ... ", end="", flush=True)

            start_time = datetime.now(timezone.utc)
            
            initial_state: SQLState = {
                "question": case.question,
                "user_scope": _build_mock_user_scope(case.user_scope),
                "query_type": case.sql_complexity,
                "plan_step_context": case.plan_step_context.model_dump(),
                "prior_steps_context": case.prior_steps_context,
                "attempt_count": 0,
            }

            try:
                # Sleep to prevent Gemini/Groq rate limiting (429)
                await asyncio.sleep(3)
                final_state = await pipeline.ainvoke(initial_state)
            except Exception as e:
                final_state = {"sql_error": str(e), "is_aborted": True, "generated_sql": None}

            exec_success = not bool(final_state.get("sql_error")) and final_state.get("generated_sql") is not None
            is_accurate = False
            
            if exec_success:
                try:
                    mock_scope = _build_mock_user_scope(case.user_scope)
                    gold_res = await executor.execute(case.expected_sql_behavior.gold_sql, mock_scope)
                    if not gold_res.error:
                        is_accurate = _compare_sql_results(final_state.get("sql_result"), gold_res.rows)
                except Exception as ex:
                    print(f"\nAccuracy check error: {ex}", flush=True)

            latency = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            run_result = SqlGroundingRunResult(
                case_id=case.id,
                variant=variant_name,
                sql_complexity=case.sql_complexity,
                generated_sql=final_state.get("generated_sql"),
                relevant_tables=final_state.get("relevant_tables", []),
                schema_context=final_state.get("schema_context"),
                sql_error=final_state.get("sql_error"),
                attempt_count=final_state.get("attempt_count", 1),
                is_aborted=final_state.get("is_aborted", False),
                execution_success=exec_success,
                execution_accurate=is_accurate,
                latency_seconds=latency
            )
            
            results.append(run_result)

            if run_result.execution_success:
                status = "ACCURATE" if run_result.execution_accurate else "INACCURATE"
                symbol = "✅" if run_result.execution_accurate else "⚠️"
                print(f"{symbol} {status} [{latency:.2f}s]", flush=True)
            else:
                err_msg = str(run_result.sql_error)[:50] + "..." if run_result.sql_error else "Aborted"
                print(f"❌ FAILED ({err_msg}) [{latency:.2f}s]", flush=True)

            with open(CHECKPOINT_FILE, "a") as f:
                f.write(run_result.model_dump_json() + "\n")
                f.flush()

    # Generate final report
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = RESULTS_DIR / f"sql_grounding_{run_id}_2.json"
    
    report = {
        "total_cases": len(cases),
        "variants": variants,
        "results": [r.model_dump() for r in results]
    }
    
    output_path.write_text(json.dumps(report, indent=2))
    assert output_path.exists()
