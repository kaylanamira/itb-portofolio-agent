from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from agent.state import QueryType
from agent.tools.security import ALLOWED_SCHEMAS, FORBIDDEN_TABLES, SENSITIVE_COLUMN_PATTERNS
from core.scope import UserRole

CONFIG_PATH = Path(__file__).with_name("config.json")
DATASETS_DIR = Path(__file__).with_name("datasets")
RESULTS_DIR = Path(__file__).with_name("results")
QUERY_TYPES = {item.value for item in QueryType}
USER_ROLES = {item.value for item in UserRole}
SECURITY_ALLOWED_SCHEMAS = ALLOWED_SCHEMAS
SECURITY_FORBIDDEN_TABLES = FORBIDDEN_TABLES
SECURITY_SENSITIVE_COLUMNS = SENSITIVE_COLUMN_PATTERNS


@lru_cache(maxsize=1)
def load_eval_config() -> dict[str, Any]:
    with CONFIG_PATH.open() as f:
        return json.load(f)


def metric_threshold(node: str, metric: str) -> float:
    return float(load_eval_config()["metrics"][node][metric])


def valid_tools() -> set[str]:
    return set(load_eval_config()["valid_tools"])


def deepeval_include_reason() -> bool:
    return bool(load_eval_config().get("deepeval", {}).get("include_reason", True))
