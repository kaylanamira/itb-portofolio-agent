import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

def summarize():
    results_dir = Path("evals/results")
    files = sorted(results_dir.glob("sql_grounding_*.json"))
    
    if not files:
        checkpoint = results_dir / "sql_grounding_checkpoint.jsonl"
        if not checkpoint.exists():
            print("No experiment result files or checkpoints found in evals/results/")
            return
        print(f"Reading from checkpoint: {checkpoint}")
        raw_results = [json.loads(line) for line in checkpoint.read_text().splitlines() if line.strip()]
    else:
        latest_file = files[-1]
        print(f"Reading from latest result file: {latest_file}")
        data = json.loads(latest_file.read_text())
        raw_results = data["results"]

    summary = {}
    for r in raw_results:
        v = r["variant"]
        comp = r.get("sql_complexity", "unknown")
        
        if v not in summary:
            summary[v] = {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "accurate": 0,
                "total_latency": 0.0,
                "by_complexity": {}
            }
            
        summary[v]["total"] += 1
        is_success = r.get("execution_success", False)
        is_accurate = r.get("execution_accurate", is_success)  # Fallback to success for old files
        
        if is_success:
            summary[v]["passed"] += 1
        else:
            summary[v]["failed"] += 1
            
        if is_accurate:
            summary[v]["accurate"] += 1
            
        summary[v]["total_latency"] += r.get("latency_seconds", 0.0)
        
        if comp not in summary[v]["by_complexity"]:
            summary[v]["by_complexity"][comp] = {"total": 0, "passed": 0, "accurate": 0}
        summary[v]["by_complexity"][comp]["total"] += 1
        if is_success:
            summary[v]["by_complexity"][comp]["passed"] += 1
        if is_accurate:
            summary[v]["by_complexity"][comp]["accurate"] += 1

    print("\n" + "="*90)
    print(f"{'Variant':<10} | {'Total':<6} | {'Exec-Success':<12} | {'Semantic-Accurate':<18} | {'Accuracy %':<10} | {'Avg Latency':<12}")
    print("="*90)
    
    for v, stats in sorted(summary.items()):
        total = stats["total"]
        passed = stats["passed"]
        accurate = stats["accurate"]
        acc = (accurate / total * 100) if total > 0 else 0.0
        avg_lat = (stats["total_latency"] / total) if total > 0 else 0.0
        print(f"{v:<10} | {total:<6} | {passed:<12} | {accurate:<18} | {acc:>8.1f}% | {avg_lat:>10.2f}s")
    print("="*90 + "\n")

    print("Breakdown by Complexity (Accuracy / Semantic Correctness):")
    for v, stats in sorted(summary.items()):
        print(f"\n--- Variant {v} ---")
        for comp, cstats in sorted(stats["by_complexity"].items()):
            tot = cstats["total"]
            acc_count = cstats["accurate"]
            acc = (acc_count / tot * 100) if tot > 0 else 0.0
            print(f"  • {comp:<25}: {acc_count}/{tot} accurate ({acc:.1f}%)")


if __name__ == "__main__":
    summarize()
