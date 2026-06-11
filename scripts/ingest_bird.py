"""
Ingest Mini-BIRD Dev dataset (PostgreSQL variant) into SqlGeneratorCase format.

Usage:
    uv run python scripts/ingest_bird.py

Prerequisites:
    1. Download mini_dev_data.zip from https://github.com/bird-bench/mini_dev
    2. Extract to evals/datasets/bird/ so you have:
       - evals/datasets/bird/minidev/MINIDEV/mini_dev_postgresql.json  (question/SQL pairs)
       - evals/datasets/bird/minidev/MINIDEV/dev_databases/<db_id>/<db_id>.sqlite

Output:
    evals/datasets/bird_cases.json  — loaded by test_sql_generator.py when RUN_BIRD_EVALS=1
"""
from __future__ import annotations

import json
import os
import sys


BIRD_DIR = "evals/datasets/bird/MINIDEV"
BIRD_JSON = os.path.join(BIRD_DIR, "mini_dev_postgresql.json")
OUTPUT_PATH = "evals/datasets/bird_sql_generator_cases.json"
MAX_CASES = 100  


import sqlite3

def _read_schema_sql(db_id: str) -> str:
    """Read the DDL schema by querying the sqlite database directly."""
    db_path = os.path.join(BIRD_DIR, "dev_databases", db_id, f"{db_id}.sqlite")
    if not os.path.exists(db_path):
        return f"-- Database not found: {db_path}"

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table'")
    ddl_statements = [row[0] for row in cursor.fetchall() if row[0]]
    conn.close()
    
    return "\n".join(ddl_statements)


def _map_difficulty(difficulty: str) -> str:
    """Map BIRD difficulty labels to our complexity taxonomy."""
    return {
        "simple": "simple",
        "moderate": "medium",
        "challenging": "complex",
    }.get(difficulty.lower(), "medium")


def ingest(limit: int | None = MAX_CASES) -> None:
    if not os.path.exists(BIRD_JSON):
        print(f"ERROR: BIRD JSON not found at {BIRD_JSON}")
        print("Please download the Mini-BIRD Dev dataset and extract it to evals/datasets/bird/")
        print("See: https://github.com/bird-bench/mini_dev")
        sys.exit(1)

    with open(BIRD_JSON) as f:
        bird_data = json.load(f)

    if limit:
        bird_data = bird_data[:limit]

    cases = []
    db_id_counts: dict[str, int] = {}

    for item in bird_data:
        db_id = item["db_id"]
        db_id_counts[db_id] = db_id_counts.get(db_id, 0) + 1
        idx = db_id_counts[db_id]

        schema_ddl = _read_schema_sql(db_id)
        evidence = item.get("evidence", "").strip()

        # Combine DDL + BIRD evidence hint as schema_context
        schema_context = schema_ddl
        if evidence:
            schema_context += f"\n\n-- Evidence / Domain Hint:\n-- {evidence}"

        cases.append({
            "id": f"BIRD-EX-{db_id}-{idx:03d}",
            "description": str(item.get("question_id", "")),
            "query": item["question"],
            "query_type": "data_lookup",
            "schema_context": schema_context,
            "detected_entities": {"db_id": db_id},
            "ground_truth_sql": item["SQL"],
            "gold_sql_checks": {
                "must_be_select": True,
                "must_not_include": ["INSERT", "UPDATE", "DELETE", "DROP"]
            },
            "expected_tables": [],
            "expected_columns_used": [],
            "complexity": _map_difficulty(item.get("difficulty", "simple")),
            "tags": ["bird", db_id],
        })

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(cases, f, indent=2, ensure_ascii=False)

    print(f"Ingested {len(cases)} BIRD cases → {OUTPUT_PATH}")
    difficulty_counts = {}
    for c in cases:
        difficulty_counts[c["complexity"]] = difficulty_counts.get(c["complexity"], 0) + 1
    for k, v in sorted(difficulty_counts.items()):
        print(f"  {k}: {v} cases")


if __name__ == "__main__":
    ingest()
