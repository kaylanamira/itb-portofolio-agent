from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from langchain_core.globals import set_llm_cache
from langchain_core.caches import InMemoryCache

import pytest

from evals.experiments.experiment_1.architecture_experiment import ArchitectureConfig, ArchitectureRunResult, result_to_json, score_report
from evals.datasets.schemas import ArchitectureOrchestrationCase, ArchitectureOrchestrationDataset
from tests.conftest import DATASETS_DIR, RESULTS_DIR
from evals.experiments.experiment_1.architecture_runner import ArchitectureRunner


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv("RUN_ARCH_EXPERIMENT") != "1", reason="Set RUN_ARCH_EXPERIMENT=1 to run architecture experiment"),
]


USE_FULL = os.getenv("USE_FULL_DATASET") == "1"
USE_TINY = os.getenv("USE_TINY_DATASET") == "1"

if USE_TINY:
    DATASET_FILE = "architecture_orchestration_tiny.json"
elif USE_FULL:
    DATASET_FILE = "architecture_orchestration_cases_v2.json"
else:
    DATASET_FILE = "architecture_orchestration_subset_v2.json"

DATASET_PATH = DATASETS_DIR / "experiments" / DATASET_FILE

CHECKPOINT_FILE = RESULTS_DIR / "architecture_checkpoint.jsonl"


def _load_architecture_cases() -> list[ArchitectureOrchestrationCase]:
    if not DATASET_PATH.exists():
        pytest.skip(f"{DATASET_PATH} is required for Experiment I")
    raw = json.loads(DATASET_PATH.read_text())
    if isinstance(raw, list):
        return [ArchitectureOrchestrationCase.model_validate(item) for item in raw]
    dataset = ArchitectureOrchestrationDataset.model_validate(raw)
    assert dataset.total_cases == len(dataset.cases)
    return dataset.cases


async def test_architecture_orchestration_report(make_state):
    set_llm_cache(InMemoryCache())
    cases = _load_architecture_cases()
    
    target_case_id = os.getenv("TARGET_CASE_ID")
    if target_case_id:
        cases = [c for c in cases if c.id == target_case_id]
        
    target_complexity = os.getenv("TARGET_COMPLEXITY")
    if target_complexity:
        cases = [c for c in cases if c.orchestration_complexity == target_complexity]
        
    runner = ArchitectureRunner(make_state)
    
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    
    completed = set()
    results_map = {}
    valid_case_ids = {c.id for c in cases}
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, "r") as f:
            for line in f:
                if not line.strip(): continue
                data = json.loads(line)
                res = ArchitectureRunResult.model_validate(data)
                
                if res.case_id not in valid_case_ids:
                    continue
                
                config_val = res.config.value if hasattr(res.config, "value") else str(res.config)
                
                results_map[(config_val, res.case_id)] = res
                
                if not res.error:
                    completed.add((config_val, res.case_id))
                else:
                    completed.discard((config_val, res.case_id))

    results = list(results_map.values())
                
    total_cases = len(cases)
    total_configs = len(ArchitectureConfig)
    total_runs = total_cases * total_configs

    print(f"\n Starting Architecture Experiment 1 evaluation:")
    print(f"   • Dataset Cases : {total_cases}")
    print(f"   • Configs       : {total_configs}")
    print(f"   • Total Runs    : {total_runs}")
    print(f"   • Cached Runs   : {len(completed)}\n", flush=True)

    current_idx = len(completed)

    for config in ArchitectureConfig:
        for case in cases:
            if (config.value, case.id) in completed:
                continue

            current_idx += 1
            print(f"[{current_idx}/{total_runs}] Config: {config.value:<18} | Case: {case.id} ... ", end="", flush=True)

            result = await runner.run(config, case)
            results.append(result)

            if result.error:
                print(f"❌ FAILED ({result.error}) [{result.latency_seconds:.2f}s]", flush=True)
            else:
                print(f"✅ PASSED [{result.latency_seconds:.2f}s]", flush=True)

            with open(CHECKPOINT_FILE, "a") as f:
                f.write(result.model_dump_json() + "\n")
                f.flush()
                
    report = score_report(cases, results)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = RESULTS_DIR / f"architecture_orchestration_{run_id}.json"
    output_path.write_text(json.dumps(result_to_json(report), indent=2))
    assert output_path.exists()
