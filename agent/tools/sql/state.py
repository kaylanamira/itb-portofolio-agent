from __future__ import annotations

from agent.state import ValidationStatus
from agent.state import DetectedEntities
from typing import Annotated, Optional
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
import operator
from core.scope import UserScope

class SQLState(TypedDict, total=False):
    question: str
    user_scope: UserScope
    plan_step_context: dict
    query_type: Optional[str]
    schema_context: Optional[str]
    default_table: Optional[str]

    detected_entities: Optional[DetectedEntities]
    relevant_tables: Optional[list[str]]

    generated_sql: Optional[str] = None
    sql_with_scope: Optional[str] = None

    validation_status: Optional[ValidationStatus] = None
    validation_errors: Annotated[list[str], operator.add] = Field(default_factory=list)

    sql_result: Optional[list[dict]] = None
    sql_error: Optional[str] = None
    sql_row_count: Optional[int] = None

    answer_is_valid: Optional[bool] = None

    attempt_count: int
    max_attempts: int
    error_history: Annotated[list[dict], operator.add]
    is_aborted: bool
    abort_reason: Optional[str]
