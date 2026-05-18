from __future__ import annotations

from typing import Annotated, Any, Optional
from typing_extensions import TypedDict
import operator
from core.scope import UserScope


class SQLState(TypedDict, total=False):
    question: str
    user_scope: UserScope
    plan_step_context: Optional[dict]
    query_type: Optional[str]
    # default_table: Optional[str]

    # ── Schema linking outputs ──────────────────────────────────────────────────
    plan_context: Optional[str]           
    detected_entities: Optional[Any]
    relevant_tables: Optional[list[str]]
    schema_context: Optional[str]

    # ── Generation / execution outputs ─────────────────────────────────────────
    generated_sql: Optional[str]
    sql_with_scope: Optional[str]
    validation_status: Optional[str]          # "pass" | "fail" | "pending"
    validation_errors: Annotated[list[str], operator.add]

    sql_result: Optional[list[dict]]
    sql_error: Optional[str]
    sql_row_count: Optional[int]
    answer_is_valid: Optional[bool]

    # ── Retry / abort tracking ──────────────────────────────────────────────────
    attempt_count: int
    max_attempts: int
    error_history: Annotated[list[dict], operator.add]
    is_aborted: bool
    abort_reason: Optional[str]
