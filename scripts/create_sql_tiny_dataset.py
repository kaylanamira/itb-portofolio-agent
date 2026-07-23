import json
from pathlib import Path
import sys

# Add parent dir to path so we can import from evals
sys.path.append(str(Path(__file__).parent.parent))

from evals.datasets.schemas import SqlGroundingDataset

def main():
    root_dir = Path(__file__).parent.parent
    dataset_path = root_dir / "evals" / "datasets" / "experiments" / "sql_grounding_cases.json"
    out_path = root_dir / "evals" / "datasets" / "experiments" / "sql_grounding_tiny.json"
    
    if not dataset_path.exists():
        print(f"Error: {dataset_path} does not exist.")
        return
        
    with open(dataset_path, "r") as f:
        raw_data = json.load(f)
        
    try:
        dataset = SqlGroundingDataset.model_validate(raw_data)
        print("✅ Original dataset successfully validated against Pydantic schema!")
    except Exception as e:
        print("❌ Dataset validation failed:", e)
        return
        
    # Create tiny subset: 1 case per complexity
    tiny_cases = []
    seen_complexities = set()
    
    for case in dataset.cases:
        if case.sql_complexity not in seen_complexities:
            tiny_cases.append(case)
            seen_complexities.add(case.sql_complexity)
            
    # Update counts
    new_counts = {
        "single_table_query": 0,
        "multi_table_join": 0,
        "aggregation": 0,
        "nested_query": 0,
        "window_function": 0,
        "conditional_aggregation": 0,
        "ambiguous_or_typo_entity": 0,
        "questionnaire_metadata": 0
    }
    
    for case in tiny_cases:
        new_counts[case.sql_complexity] += 1
        
    # Copy dataset but replace cases and counts
    tiny_data = dataset.model_dump()
    tiny_data["dataset_name"] = "sql_grounding_tiny"
    tiny_data["description"] = "Tiny subset of SQL grounding cases for fast testing."
    tiny_data["total_cases"] = len(tiny_cases)
    tiny_data["distribution"]["sql_complexity_counts"] = new_counts
    tiny_data["cases"] = [c.model_dump() for c in tiny_cases]
    
    with open(out_path, "w") as f:
        json.dump(tiny_data, f, indent=2)
        
    print(f"✅ Tiny dataset created with {len(tiny_cases)} cases at {out_path}")

if __name__ == "__main__":
    main()
