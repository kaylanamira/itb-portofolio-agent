from __future__ import annotations
from typing import Annotated, Optional, Any, Literal
from uuid import UUID
from enum import Enum
import operator
from pydantic import BaseModel, Field
from langgraph.graph import MessagesState
from core.scope import UserScope, UserRole

class QueryType(str, Enum):
    DATA_LOOKUP          = "data_lookup"
    TEXT_LOOKUP          = "text_lookup"
    ANALYTICAL_NUMERIC   = "analytical_numeric"
    ANALYTICAL_TEXT      = "analytical_text"
    ANALYTICAL_HYBRID    = "analytical_hybrid"
    DIAGNOSTIC           = "diagnostic"
    COMPARATIVE          = "comparative"
    SUMMARIZATION        = "summarization"
    CHART_GENERATE       = "chart_generate"
    CHART_INTERPRET      = "chart_interpret"
    CLARIFICATION_NEEDED = "clarification_needed"

class AgentDomain(str, Enum):
    PORTFOLIO   = "portfolio"
    WISUDAWAN   = "wisudawan"
    OUT_OF_SCOPE = "out_of_scope"

class ValidationStatus(str, Enum):
    PASS    = "pass"
    FAIL    = "fail"
    PENDING = "pending"

class ChartContext(BaseModel):
    chart_type: str
    title: str
    x_axis_label: Optional[str] = None
    y_axis_label: Optional[str] = None
    series: list[dict]
    filters_applied: dict = Field(default_factory=dict)

class DetectedEntities(BaseModel):
    kode_mk: Optional[str] = None
    nama_mk: Optional[str] = None
    no_kelas: Optional[str] = None
    nama_dosen: Optional[str] = None
    kode_prodi: Optional[str] = None
    kode_fakultas: Optional[str] = None
    semester: Optional[int] = None
    tahun_ajaran: Optional[str] = None
    resolved_kelas_id: Optional[UUID] = None
    resolved_dosen_id: Optional[UUID] = None
    resolved_prodi_id: Optional[UUID] = None
    confidence: float = 1.0

class FormattedResponse(BaseModel):
    response_type: Literal["text", "chart", "clarification", "error"]
    narrative: Optional[str] = None
    data: Optional[Any] = None
    chart_spec: Optional[dict] = None
    clarification_question: Optional[str] = None
    disclaimer: Optional[str] = None

class AgentState(MessagesState):
    user_scope: UserScope
    session_id: str
    chart_context: Optional[ChartContext]
    raw_query: str
    rewritten_query: Optional[str]
    effective_query: str
    domain: Optional[AgentDomain]
    query_type: Optional[QueryType]
    detected_entities: Optional[DetectedEntities]
    relevant_tables: Optional[list[str]]
    schema_context: Optional[str]
    generated_sql: Optional[str]
    sql_with_scope: Optional[str]
    validation_status: Optional[ValidationStatus]
    validation_errors: Annotated[list[str], operator.add]
    sql_result: Optional[list[dict]]
    sql_error: Optional[str]
    sql_row_count: Optional[int]
    rag_query: Optional[str]
    rag_chunks: Optional[list[dict]]
    answer_is_valid: Optional[bool]
    formatted_response: Optional[FormattedResponse]
    attempt_count: int
    max_attempts: int
    error_history: Annotated[list[dict], operator.add]
    is_aborted: bool
    abort_reason: Optional[str]
