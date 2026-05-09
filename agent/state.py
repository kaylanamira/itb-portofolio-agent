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

class ChartArtifact(BaseModel):
    artifact_id: str                  
    artifact_type: Literal["chart"] = "chart"
    chart_type: str                    # "bar" | "line" | "heatmap" | "scatter" | "radar"
    title: str
    chart_spec: dict                    
    source_sql: Optional[str] = None   # the SQL that produced this
    columns_used: list[str]            # column names
    insight: Optional[str] = None      # 1-2 sentence agent interpretation

class TableArtifact(BaseModel):
    artifact_id: str
    artifact_type: Literal["table"] = "table"
    title: str
    columns: list[dict]                # [{name, type, display_name}]
    rows: list[dict]
    source_sql: Optional[str] = None
    row_count: int
    is_truncated: bool

class StepResult(BaseModel):
    step_number: int
    thought: str
    action: str                        # "sql" | "rag" | "hybrid"
    query: str                         # The generated SQL or Search query
    result: Any                        # Raw data returned
    observation: str                   # Agent's brief take on this specific result

class FormattedResponse(BaseModel):
    response_type: Literal["text", "mixed", "clarification", "error"]
    narrative: str
    artifacts: list[Annotated[ChartArtifact | TableArtifact, Field(discriminator="artifact_type")]] = Field(default_factory=list)
    follow_up_suggestions: list[str] = Field(default_factory=list)
    disclaimer: Optional[str] = None
    clarification_question: Optional[str] = None

class AgentState(MessagesState):
    user_scope: UserScope
    session_id: str
    
    # -- Planning & Reasoning --
    raw_query: str
    rewritten_query: Optional[str]
    effective_query: str
    domain: Optional[AgentDomain]
    query_type: Optional[QueryType]
    plan: list[dict] = Field(default_factory=list)
    current_step_index: int = 0
    steps_completed: Annotated[list[StepResult], operator.add] = Field(default_factory=list)
    reasoning_history: Annotated[list[str], operator.add] = Field(default_factory=list)
    
    # -- Memory --
    conversation_summary: Optional[str] = None
    session_entities: Optional[dict] = None
    
    # -- Input Processing --
    content_filter_result: Optional[str] = None
    extracted_keywords: Optional[list[str]] = None
    
    # -- Data Context --
    chart_context: Optional[ChartContext] # Context from frontend if user is looking at a chart
    detected_entities: Optional[DetectedEntities]
    relevant_tables: Optional[list[str]]
    schema_context: Optional[str]
    generated_sql: Optional[str] = None
    sql_with_scope: Optional[str] = None
    validation_status: Optional[ValidationStatus] = None
    validation_errors: Annotated[list[str], operator.add] = Field(default_factory=list)
    sql_result: Optional[list[dict]] = None
    sql_error: Optional[str] = None
    sql_row_count: Optional[int] = None
    
    # -- RAG Execution --
    rag_query: Optional[str] = None
    rag_chunks: Optional[list[dict]] = None
    rag_source_types: Optional[list[str]] = None
    rag_tipe_konten: Optional[list[str]] = None
    rag_scope_override: Optional[dict] = None
    rag_attempt_count: int = 0
    rag_confidence: Optional[float] = None
    rag_action: Optional[str] = None
    rag_refined_query: Optional[str] = None
    
    # -- Faithfulness --
    faithfulness_score: Optional[float] = None
    faithfulness_action: Optional[str] = None
    
    answer_is_valid: Optional[bool] = None
    next_step: Optional[str] = None 

    # -- Final Output --
    formatted_response: Optional[FormattedResponse]
    
    # -- System / Error Handling --
    attempt_count: int
    max_attempts: int
    error_history: Annotated[list[dict], operator.add]
    is_aborted: bool
    abort_reason: Optional[str]
