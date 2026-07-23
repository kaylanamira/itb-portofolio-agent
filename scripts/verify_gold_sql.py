import os
import json
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from core.scope import UserScope, ScopeEntry, UserRole
from core.sql_executor import PsycopgExecutor
from core.database import init_db_pool, close_db_pool
from evals.datasets.schemas import SqlGroundingDataset

def _build_mock_user_scope(scope_def_obj) -> UserScope:
    scope_def = scope_def_obj if isinstance(scope_def_obj, dict) else scope_def_obj.model_dump()
    role_str = scope_def.get("role", "dosen").lower()
    
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


def truncate_rows(rows, max_rows=5, max_str_len=100):
    if not rows:
        return rows
    
    truncated = []
    for idx, row in enumerate(rows):
        if idx >= max_rows:
            break
        
        trunc_row = {}
        for k, v in row.items():
            if isinstance(v, str) and len(v) > max_str_len:
                trunc_row[k] = v[:max_str_len] + "... (truncated)"
            else:
                trunc_row[k] = v
        truncated.append(trunc_row)
        
    return truncated


async def main():
    dataset_path = Path("evals/datasets/experiments/sql_grounding_cases.json")
    out_path = Path("evals/results/gold_sql_results.json")
    
    if not dataset_path.exists():
        print(f"Error: {dataset_path} does not exist.")
        return
        
    raw = json.loads(dataset_path.read_text())
    dataset = SqlGroundingDataset.model_validate(raw)
    
    await init_db_pool()
    executor = PsycopgExecutor()
    
    results = []
    
    for idx, case in enumerate(dataset.cases):
        print(f"[{idx+1}/{len(dataset.cases)}] Case: {case.id}")
        
        gold_sql = case.expected_sql_behavior.gold_sql
        if not gold_sql:
            print("  Skipping: No gold SQL")
            continue
            
        scope = _build_mock_user_scope(case.user_scope)
        
        try:
            res = await executor.execute(sql=gold_sql, user_scope=scope)
            error = res.error
            rows = res.rows
            row_count = res.row_count
        except Exception as e:
            error = str(e)
            rows = []
            row_count = 0
            
        if error:
            print(f"  ❌ Error: {error}")
        else:
            print(f"  ✅ Success: {row_count} rows returned")
            
        case_result = {
            "case_id": case.id,
            "question": case.question,
            "gold_sql": gold_sql,
            "error": error,
            "row_count": row_count,
            "rows": truncate_rows(rows)
        }
        results.append(case_result)
        
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
        
    print(f"\nDone. Results saved to {out_path}")
    await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
