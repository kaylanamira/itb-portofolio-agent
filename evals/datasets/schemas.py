from __future__ import annotations

from enum import Enum
from typing import Any, Optional, Union
from pydantic import BaseModel, Field


class BaseCase(BaseModel):
    id: str
    description: str = ""
    query: str
    tags: list[str] = Field(default_factory=list)


class InputGuardCase(BaseCase):
    expected_blocked: bool
    block_reason: str | None = None


class IntentClassifierCase(BaseCase):
    expected_domain: str


class QueryRewriterCase(BaseCase):
    history: str = ""
    history_messages: list[str] = Field(default_factory=list)
    expected_should_rewrite: bool


class PlannerCase(BaseCase):
    expected_query_type: str
    expected_tools: list[str]
    should_clarify: bool
    expected_max_steps: int = 3


class SchemaLinkerCase(BaseCase):
    scope_role: str = "kaprodi"
    scope_value: dict[str, Any] = Field(default_factory=dict)
    expected_entities: dict[str, Any]
    expected_resolved: dict[str, Any] = Field(default_factory=dict)
    expected_tables_subset: list[str]


class GoldSqlChecks(BaseModel):
    must_be_select: bool = False
    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    should_have_order_by: bool = False
    should_have_limit: bool = False
    should_have_null_guard: bool = False


class SqlGeneratorCase(BaseCase):
    query_type: str
    schema_context: str | None = None
    expected_tables: list[str] = Field(default_factory=list)
    expected_columns_used: list[str] = Field(default_factory=list)
    complexity: str | None = None
    detected_entities: dict[str, Any] = Field(default_factory=dict)
    gold_sql_checks: GoldSqlChecks = Field(default_factory=GoldSqlChecks)
    ground_truth_sql: str | None = None


class SqlValidatorCase(BaseModel):
    id: str
    description: str = ""
    sql: str
    expected_valid: bool
    expected_error_type: str | None = None
    tags: list[str] = Field(default_factory=list)


class SqlExecutorCase(BaseCase):
    sql: str
    scope_role: str = "kaprodi"
    expected_min_rows: int | None = None
    expected_max_rows: int | None = None
    expected_columns: list[str] = Field(default_factory=list)
    should_return_empty: bool = False


class AnswerValidatorCase(BaseModel):
    id: str
    description: str = ""
    question: str
    generated_sql: str
    sql_result: list[dict] | None
    sql_row_count: int
    expected_valid: bool
    tags: list[str] = Field(default_factory=list)


class StepReasonerCase(BaseCase):
    task: str
    action: str
    expected_observation: str
    expected_fully_answered: bool
    expected_next_index: int | str
    expected_facts: list[str] = Field(default_factory=list)
    current_step_index: int = 0
    generated_sql: str | None = None
    sql_result: list[dict] | None = None
    rag_chunks: list[Any] | None = None
    rag_query: str | None = None
    plan: list[dict] | None = None


class SynthesizerCase(BaseCase):
    steps_completed: list[dict] = Field(default_factory=list)
    is_aborted: bool = False
    abort_reason: str = ""
    expected_response_type: str = "text"
    has_chart: bool = False


class ClarificationHandlerCase(BaseCase):
    should_clarify: bool
    expected_query_type: str

class ErrorHandlerCase(BaseModel):
    id: str
    description: str = ""
    attempt_count: int
    max_attempts: int
    error_message: str = ""
    expected_abort: bool
    expected_route: str
    tags: list[str] = Field(default_factory=list)


class RagRetrieverCase(BaseCase):
    task: str
    scope_role: str = "kaprodi"
    complexity: str | None = None  # "simple", "compound", "temporal", "multi_entity"
    expected_hyde_triggered: bool | None = None
    expected_dosen_resolved: bool | None = None
    expected_matkul_resolved: bool | None = None
    expected_verifikator_filter: bool | None = None
    expected_min_confidence: float | None = None
    expected_faithfulness_min: float | None = None
    expected_citation_present: bool = True
    expected_empty_result_ok: bool = False  # True: legitimately no matching data, absence of chunks/citations is a PASS


class ChartInterpreterCase(BaseCase):
    chart_context: dict[str, Any]
    expected_facts: list[str] = Field(default_factory=list)


# --- Experiment I & II ---

class QueryTypeLabel(str, Enum):
    DATA_LOOKUP = "data_lookup"
    TEXT_LOOKUP = "text_lookup"
    ANALYTICAL_NUMERIC = "analytical_numeric"
    ANALYTICAL_TEXT = "analytical_text"
    ANALYTICAL_HYBRID = "analytical_hybrid"
    DIAGNOSTIC = "diagnostic"
    COMPARATIVE = "comparative"
    SUMMARIZATION = "summarization"
    CHART_INTERPRET = "chart_interpret"
    CLARIFICATION_NEEDED = "clarification_needed"


class OrchestrationComplexity(str, Enum):
    C1_SINGLE_TOOL = "C1_single_tool"
    C2_PARALLEL_MULTI_TOOL = "C2_parallel_multi_tool"
    C3_SEQUENTIAL = "C3_sequential"
    C4_DEPENDENT_MULTI_STEP = "C4_dependent_multi_step"


class ArchDomain(str, Enum):
    PORTFOLIO = "portfolio"
    OUT_OF_SCOPE = "out_of_scope"


class UserScopeCase(BaseModel):
    role: str
    allowed_faculties: list[str] = Field(default_factory=list)
    allowed_programs: list[str] = Field(default_factory=list)
    allowed_courses: list[str] = Field(default_factory=list)


class ConversationMessage(BaseModel):
    role: str
    content: str


class ArchInputContext(BaseModel):
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    chart_context: Optional[dict] = None


class ExpectedPlanStep(BaseModel):
    task: str
    tool: str
    required: bool


class ArchExpectedBehavior(BaseModel):
    expected_query_type: QueryTypeLabel
    expected_tool_sequence: list[str]
    expected_node_sequence: list[str]
    expected_plan_steps: list[ExpectedPlanStep]
    expected_response_type: str
    required_answer_facts: list[str]
    acceptable_answer_patterns: list[str]
    expected_clarification_slots: Optional[list[str]] = None


class ArchScoringRubric(BaseModel):
    task_success_criteria: list[str]
    faithfulness_reference: str
    completeness_criteria: list[str]


class ArchitectureCase(BaseModel):
    id: str
    query_type: QueryTypeLabel
    orchestration_complexity: OrchestrationComplexity
    domain: ArchDomain
    raw_query: str
    language: str
    user_scope: UserScopeCase
    input_context: ArchInputContext
    expected_behavior: ArchExpectedBehavior
    scoring_rubric: ArchScoringRubric
    notes_for_dataset_author: str


class ArchitectureDistribution(BaseModel):
    query_type_counts: dict[str, int]
    orchestration_complexity_counts: dict[str, int]


class ArchitectureDataset(BaseModel):
    dataset_name: str
    version: str
    description: str
    total_cases: int
    distribution: ArchitectureDistribution
    cases: list[ArchitectureCase]


class SqlComplexity(str, Enum):
    SINGLE_TABLE_QUERY = "single_table_query"
    MULTI_TABLE_JOIN = "multi_table_join"
    AGGREGATION = "aggregation"
    NESTED_QUERY = "nested_query"
    WINDOW_FUNCTION = "window_function"
    CONDITIONAL_AGGREGATION = "conditional_aggregation"
    AMBIGUOUS_OR_TYPO_ENTITY = "ambiguous_or_typo_entity"
    QUESTIONNAIRE_METADATA = "questionnaire_metadata"


class PlanStepContext(BaseModel):
    task: str
    tool: str
    required: bool


class ExpectedGrounding(BaseModel):
    expected_tables: list[str]
    expected_entities: dict[str, Union[str, int, float, list, dict, None]]
    expected_catalog_references: list[str] = Field(default_factory=list)


class ExpectedSqlBehavior(BaseModel):
    must_include_sql_patterns: list[str]
    must_not_include_sql_patterns: list[str]
    expected_result_facts: list[str]
    gold_sql: Optional[str] = None
    numeric_tolerance: Optional[float] = None


class SqlScoringFlags(BaseModel):
    execution_accuracy_required: bool
    schema_selection_required: bool
    entity_resolution_required: bool
    catalog_lookup_required: bool
    retry_expected: bool


class SqlGroundingCase(BaseModel):
    id: str
    sql_complexity: SqlComplexity
    question: str
    language: str
    domain: str
    user_scope: UserScopeCase
    plan_step_context: PlanStepContext
    prior_steps_context: str = ""
    expected_grounding: ExpectedGrounding
    expected_sql_behavior: ExpectedSqlBehavior
    scoring: SqlScoringFlags
    notes_for_dataset_author: str


class DatabaseSnapshot(BaseModel):
    snapshot_id: str
    description: str
    created_at: Optional[str] = None


class SqlGroundingDistribution(BaseModel):
    sql_complexity_counts: dict[str, int]


class SqlGroundingDataset(BaseModel):
    dataset_name: str
    version: str
    description: str
    total_cases: int
    database_snapshot: DatabaseSnapshot
    distribution: SqlGroundingDistribution
    cases: list[SqlGroundingCase]