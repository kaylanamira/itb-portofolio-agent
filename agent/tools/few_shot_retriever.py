"""Few-shot SQL example retriever.

Examples are loaded from YAML files under data/few_shots/ by default.
The loader interface supports future migration to pgvector-based retrieval
without changing any node code.
"""

import os
import logging
from pathlib import Path
from typing import Callable, Optional

import yaml

from agent.state import QueryType

logger = logging.getLogger(__name__)

FEW_SHOTS_DIR = Path(os.getenv("FEW_SHOTS_DIR", "data/few_shots"))


def _load_yaml_examples(query_type: QueryType, n: int) -> list[tuple[str, str]]:
    """Loads examples from a YAML file matching the query type name.

    Args:
        query_type: The classified query type.
        n: Max number of examples to return.

    Returns:
        List of (nl, sql) tuples.
    """
    file_path = FEW_SHOTS_DIR / f"{query_type.value}.yaml"
    if not file_path.exists():
        fallback = FEW_SHOTS_DIR / "data_lookup.yaml"
        if fallback.exists():
            file_path = fallback
        else:
            return []

    try:
        with open(file_path, "r") as f:
            data = yaml.safe_load(f)
        examples = data.get("examples", [])
        return [(ex["nl"], ex["sql"]) for ex in examples[:n] if "nl" in ex and "sql" in ex]
    except Exception as e:
        logger.warning("Failed to load few-shots from %s: %s", file_path, e)
        return []


def retrieve_few_shots(
    query_type: QueryType,
    n: int = 3,
    loader: Optional[Callable[[QueryType, int], list[tuple[str, str]]]] = None,
) -> str:
    """Returns formatted few-shot SQL examples for the given query type.

    Args:
        query_type: The classified query type.
        n: Max number of examples to return.
        loader: Optional custom loader callable (QueryType, int) -> list[tuple[str, str]].
                When provided, bypasses the default YAML loader.
                Enables pgvector or DB-backed examples without changing node code.

    Returns:
        Formatted string for the {few_shot_examples} slot in the SQL generator prompt.
    """
    if loader is not None:
        examples = loader(query_type, n)
    else:
        examples = _load_yaml_examples(query_type, n)

    if not examples:
        return "(no examples available)"

    lines = []
    for i, (nl, sql) in enumerate(examples, 1):
        lines.append(f"Example {i}:\n  NL: {nl}\n  SQL: {sql}")

    return "\n\n".join(lines)
