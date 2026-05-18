# =============================================================================
# LEGACY — plan_optimizer.py
# =============================================================================

from __future__ import annotations

import re
from typing import Any

from agent.state import QueryType


_DERIVED_RATIO_TERMS = (
    "total",
    "persen",
    "persentase",
    "percent",
    "percentage",
    "rasio",
    "ratio",
    "proporsi",
    "proportion",
    "share",
)

_COMPLEXITY_TERMS = (
    "kenapa",
    "mengapa",
    "penyebab",
    "sebab",
    "faktor",
    "diagnos",
    "tren",
    "trend",
    "dari semester ke semester",
    "tahun ke tahun",
    "komentar",
    "refleksi",
    "usulan",
    "tema",
    "sentimen",
)

_COUNT_TOTAL_PATTERNS = (
    r"\b(total|semua|seluruh)\b",
    r"\bdenominator\b",
    r"\bpenyebut\b",
)

_COUNT_SUBSET_PATTERNS = (
    r"\b(yang|subset|bagian|terkait|dibawah|di bawah|under)\b",
    r"\bnumerator\b",
    r"\bpembilang\b",
)

_COUNT_STEP_PATTERNS = (
    r"\b(hitung|jumlah|count|berapa banyak|ada berapa)\b",
)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _is_sql_only(plan: list[dict[str, Any]]) -> bool:
    return bool(plan) and all(step.get("tool", "sql") == "sql" for step in plan)


def _is_safe_query_type(query_type: QueryType | None) -> bool:
    return query_type in {
        QueryType.DATA_LOOKUP,
        QueryType.ANALYTICAL_NUMERIC,
        QueryType.COMPARATIVE,
        None,
    }


def should_compact_ratio_plan(
    query: str,
    plan: list[dict[str, Any]],
    query_type: QueryType | None,
) -> bool:
    """
    Return True only for simple all-SQL plans that decompose one ratio metric.
    """
    if len(plan) < 2 or not _is_sql_only(plan) or not _is_safe_query_type(query_type):
        return False

    query_text = _normalize_text(query)
    task_texts = [_normalize_text(str(step.get("task", ""))) for step in plan]
    combined_tasks = " ".join(task_texts)
    combined_text = f"{query_text} {combined_tasks}"

    if not _contains_any(combined_text, _DERIVED_RATIO_TERMS):
        return False

    if _contains_any(query_text, _COMPLEXITY_TERMS):
        return False

    has_total_step = any(_matches_any(task, _COUNT_TOTAL_PATTERNS) for task in task_texts)
    has_subset_step = any(_matches_any(task, _COUNT_SUBSET_PATTERNS) for task in task_texts)
    has_count_step = any(_matches_any(task, _COUNT_STEP_PATTERNS) for task in task_texts)
    has_ratio_step = any(_contains_any(task, _DERIVED_RATIO_TERMS) for task in task_texts)

    return has_ratio_step and (has_total_step or has_subset_step or has_count_step)


def optimize_plan(
    query: str,
    plan: list[dict[str, Any]],
    query_type: QueryType | None,
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Compact simple ratio decompositions into one SQL step.

    The generated task keeps the original query text so downstream schema
    linking still sees the entities and filters the user mentioned.
    """
    if not should_compact_ratio_plan(query, plan, query_type):
        return plan, None

    optimized_step = {
        "task": (
            "Jawab query pengguna dalam satu SQL: hitung pembilang, penyebut, "
            "dan persentase/rasio menggunakan CTE atau conditional aggregation. "
            f"Query pengguna: {query}"
        ),
        "tool": "sql",
    }
    return [optimized_step], "Plan optimized: compacted derived ratio into one SQL step."
