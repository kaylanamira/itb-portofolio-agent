import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.globals import set_llm_cache
from langchain_core.caches import InMemoryCache

from core.database import pool
from core.scope import UserScope, ScopeEntry, UserRole
from agent.state import AgentState
from evals.experiments.experiment_1.architecture_experiment import ArchitectureConfig, ArchitectureRunResult, score_report, result_to_json
from evals.datasets.schemas import ArchitectureOrchestrationDataset, ArchitectureOrchestrationCase
from evals.experiments.experiment_1.architecture_runner import ArchitectureRunner


def make_state(query: str, query_type: str = None, **kwargs) -> AgentState:
    entry = ScopeEntry(user_role_id=1, role=UserRole.ADMIN, is_prime=True)
    scope = UserScope(
        user_id=1004,
        active_role=entry,
        available_roles=[entry]
    )
    return {
        "raw_query": query,
        "effective_query": query,
        "rewritten_query": None,
        "user_scope": scope,
        "session_id": "interactive-run",
        "domain": None,
        "query_type": query_type,
        "plan": [],
        "current_step_index": 0,
        "steps_completed": [],
        "reasoning_history": [],
        "sql_results": [],
        "rag_results": [],
        "chart_context": None,
        "final_response_type": None,
        "final_narrative": None,
        "error_context": None,
        "metrics": {"total_tokens": 0, "latency_seconds": 0.0, "tool_calls": 0},
    }


async def main():
    parser = argparse.ArgumentParser(description="Interactive Architecture Orchestration Runner")
    parser.add_argument(
        "--dataset",
        choices=["subset", "full", "subset-v2", "full-v2"],
        default="subset-v2",
        help="Which dataset to run: subset | full (v1) | subset-v2 | full-v2 (default: subset-v2)",
    )
    parser.add_argument("--config", type=str, default="all", help="Specific config to run (A1, A2, A3, A4) or 'all'")
    parser.add_argument("--verbose", action="store_true", help="Print detailed trace for each case")
    parser.add_argument("--clear-checkpoint", action="store_true", help="Clear the checkpoint file before running")
    args = parser.parse_args()

    set_llm_cache(InMemoryCache())

    _DATASET_FILES = {
        "subset":    "architecture_orchestration_subset.json",
        "full":      "architecture_orchestration_cases.json",
        "subset-v2": "architecture_orchestration_subset_v2.json",
        "full-v2":   "architecture_orchestration_cases_v2.json",
    }
    dataset_file = _DATASET_FILES[args.dataset]
    dataset_path = Path("evals/datasets/experiments") / dataset_file
    
    if not dataset_path.exists():
        print(f"Error: Dataset {dataset_path} not found.")
        sys.exit(1)
        
    with open(dataset_path, "r") as f:
        dataset_raw = json.load(f)
    dataset = ArchitectureOrchestrationDataset.model_validate(dataset_raw)
    cases = dataset.cases
    print(f"Loaded {len(cases)} cases from {dataset_file}.")

    configs_to_run = list(ArchitectureConfig)
    if args.config.lower() != "all":
        configs_to_run = [c for c in configs_to_run if args.config.lower() in c.name.lower()]
        if not configs_to_run:
            print(f"Error: No configuration matches '{args.config}'. Available: {[c.name for c in ArchitectureConfig]}")
            sys.exit(1)

    results_dir = Path("results")
    results_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_file = results_dir / "architecture_checkpoint.jsonl"
    
    if args.clear_checkpoint and checkpoint_file.exists():
        checkpoint_file.unlink()
        print("Cleared existing checkpoint file.")

    completed = set()
    results = []
    if checkpoint_file.exists():
        with open(checkpoint_file, "r") as f:
            for line in f:
                if not line.strip(): continue
                data = json.loads(line)
                res = ArchitectureRunResult.model_validate(data)
                completed.add((res.config, res.case_id))
                results.append(res)
        print(f"Loaded {len(completed)} completed cases from checkpoint.")

    runner = ArchitectureRunner(make_state)

    await pool.open()
    try:
        for config in configs_to_run:
            print(f"\n========== RUNNING CONFIG: {config.name} ==========")
            for i, case in enumerate(cases):
                if (config.value, case.id) in completed:
                    print(f"[{i+1}/{len(cases)}] Skipping {case.id} (already completed)")
                    continue
                
                print(f"[{i+1}/{len(cases)}] Running {case.id} (Complexity: {case.orchestration_complexity}) ... ", end="", flush=True)
                
                try:
                    result = await runner.run(config, case)
                    results.append(result)
                    
                    # Immediately persist
                    with open(checkpoint_file, "a") as f:
                        f.write(result.model_dump_json() + "\n")
                        
                    print("DONE")
                    if args.verbose:
                        print(f"  | Tool Sequence:  {result.selected_tool_sequence}")
                        print(f"  | Node Sequence:  {result.selected_node_sequence}")
                        if result.error:
                            print(f"  | Error: {result.error}")
                        else:
                            narrative_snippet = result.final_narrative[:100].replace('\n', ' ') + "..." if result.final_narrative else "None"
                            print(f"  | Narrative: {narrative_snippet}")
                        print("  " + "-"*50)
                except Exception as e:
                    print(f"FAILED with error: {e}")
                    import traceback
                    traceback.print_exc()

        print("\nAll runs complete! Generating report...")
        report = score_report(cases, results)
        
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = results_dir / f"architecture_report_{run_id}.json"
        with open(output_path, "w") as f:
            json.dump(result_to_json(report), f, indent=2)
        print(f"Final report saved to: {output_path}")

    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
