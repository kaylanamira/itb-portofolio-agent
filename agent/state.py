from __future__ import annotations
from typing import Annotated, Optional, Any, Literal
from enum import Enum
import operator
from pydantic import BaseModel, Field
from langgraph.graph import MessagesState
from core.scope import UserScope

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
    # WISUDAWAN   = "wisudawan"
    OUT_OF_SCOPE = "out_of_scope"

class ValidationStatus(str, Enum):
    PASS    = "pass"
    FAIL    = "fail"
    PENDING = "pending"

ChartType = Literal[
    "entity_comparison_bar_chart",
    "course_ranking_top_bottom_list",
    "single_entity_percentage_value",
    "grade_distribution_stacked_bar_chart",
    "grade_distribution_single_entity_bar_chart",
    "score_trend_line_chart",
    "score_heatmap_matrix_chart",
    "grading_composition_stacked_bar_chart",
    "grading_composition_single_entity_bar_chart",
    "score_by_sks_bucket_bar_chart",
]

class QuestionReference(BaseModel):
    kode_pertanyaan_frontend: str
    pertanyaan: str

class ChartFilters(BaseModel):
    tahun_ajaran: Optional[str] = None
    semester: list[int] = Field(default_factory=list)
    jenjang: list[str] = Field(default_factory=list)
    kode_fakultas: list[str] = Field(default_factory=list)
    no_prodi: list[int] = Field(default_factory=list)

class ChartContext(BaseModel):
    chart_type: ChartType
    title: str
    x_axis_label: Optional[str] = None
    y_axis_label: Optional[str] = None
    series: list[dict]
    filters_applied: ChartFilters = Field(default_factory=ChartFilters)
    hint: list[str] = Field(default_factory=list)
    jumlah_kelas_aktif: Optional[int] = None
    question_reference: Optional[dict[str, QuestionReference]] = None

class DetectedEntities(BaseModel):
    kode_matkul: Optional[str] = None
    nama_matkul: Optional[str] = None
    no_kelas: Optional[str] = None
    nama_dosen: Optional[str] = None
    no_prodi: Optional[str | list[str]] = None
    kode_prodi: Optional[str | list[str]] = None
    nama_prodi: Optional[str | list[str]] = None
    kode_fakultas: Optional[str] = None
    nama_fakultas: Optional[str] = None
    semester: Optional[int | list[int]] = None
    tahun_ajaran: Optional[str | list[str]] = None
    tahun: Optional[int | list[int]] = None
    resolved_matkul_id: Optional[int] = None
    resolved_dosen_id: Optional[int] = None
    resolved_prodi_id: Optional[int] = None
    confidence: float = 1.0
    entity_candidates: dict = Field(default_factory=dict)

class ChartArtifact(BaseModel):
    artifact_id: str
    artifact_type: Literal["chart"] = "chart"
    chart_type: str
    title: str
    chart_spec: dict
    source_sql: Optional[str] = None
    columns_used: list[str]
    insight: Optional[str] = None

class TableArtifact(BaseModel):
    artifact_id: str
    artifact_type: Literal["table"] = "table"
    title: str
    columns: list[dict]
    rows: list[dict]
    source_sql: Optional[str] = None
    row_count: int
    is_truncated: bool

class StepResult(BaseModel):
    step_number: int
    thought: str
    action: str
    query: str
    result: Any
    observation: str

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
    needs_rewrite: Optional[bool]
    rewritten_query: Optional[str]
    effective_query: str
    domain: Optional[AgentDomain]
    query_type: Optional[QueryType]
    plan: list[dict]
    current_step_index: int
    steps_completed: Annotated[list[StepResult], operator.add]
    reasoning_history: Annotated[list[str], operator.add]

    # -- Memory --
    conversation_summary: Optional[str]
    session_entities: Optional[dict]

    # -- Input Processing --
    content_filter_result: Optional[str]
    extracted_keywords: Optional[list[str]]

    # -- Data Context --
    chart_context: Optional[ChartContext]
    detected_entities: Optional[DetectedEntities]
    relevant_tables: Optional[list[str]]
    schema_context: Optional[str]

    generated_sql: Optional[str]
    validation_status: Optional[ValidationStatus]
    validation_errors: Annotated[list[str], operator.add]
    sql_result: Optional[list[dict]]
    sql_error: Optional[str]
    sql_row_count: Optional[int]

    # -- RAG Execution --
    rag_query: Optional[str]
    rag_chunks: Optional[list[dict]]
    rag_source_types: Optional[list[str]]
    rag_tipe_konten: Optional[list[str]]
    rag_scope_override: Optional[dict]
    rag_attempt_count: int
    rag_confidence: Optional[float]
    rag_action: Optional[str]
    rag_refined_query: Optional[str]

    # -- Faithfulness --
    faithfulness_score: Optional[float]
    faithfulness_action: Optional[str]

    # -- RAG Generation --
    rag_generated_answer: Optional[str]
    rag_citations: Optional[list[dict]]

    answer_is_valid: Optional[bool]
    next_step: Optional[str]

    # -- Final Output --
    formatted_response: Optional[FormattedResponse]

    # -- System / Error Handling --
    attempt_count: int
    max_attempts: int
    error_history: Annotated[list[dict], operator.add]
    is_aborted: bool
    abort_reason: Optional[str]
    empty_result_reason: Optional[str]
