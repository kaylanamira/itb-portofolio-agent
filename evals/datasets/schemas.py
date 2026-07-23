from __future__ import annotations

from typing import Any
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


class ArchitectureConversationMessage(BaseModel):
    role: str
    content: str


class ArchitectureInputContext(BaseModel):
    conversation_history: list[ArchitectureConversationMessage] = Field(default_factory=list)
    chart_context: dict[str, Any] | None = None


class ArchitecturePlanStep(BaseModel):
    task: str
    tool: str
    required: bool = False


class ArchitectureExpectedBehavior(BaseModel):
    expected_query_type: str
    expected_tool_sequence: list[str]
    expected_node_sequence: list[str] = Field(default_factory=list)
    expected_plan_steps: list[ArchitecturePlanStep] = Field(default_factory=list)
    expected_response_type: str = "text"
    required_answer_facts: list[str] = Field(default_factory=list)
    acceptable_answer_patterns: list[str] = Field(default_factory=list)
    expected_clarification_slots: list[str] = Field(default_factory=list)


class ArchitectureScoringRubric(BaseModel):
    task_success_criteria: list[str] = Field(default_factory=list)
    faithfulness_reference: str = ""
    completeness_criteria: list[str] = Field(default_factory=list)


class ArchitectureOrchestrationCase(BaseModel):
    id: str
    description: str = ""
    query_type: str
    orchestration_complexity: str
    domain: str = "portfolio"
    raw_query: str
    language: str = "id"
    input_context: ArchitectureInputContext = Field(default_factory=ArchitectureInputContext)
    expected_behavior: ArchitectureExpectedBehavior
    scoring_rubric: ArchitectureScoringRubric = Field(default_factory=ArchitectureScoringRubric)
    notes_for_dataset_author: str = ""


class ArchitectureQueryTypeCounts(BaseModel):
    data_lookup: int
    text_lookup: int
    analytical_numeric: int
    analytical_text: int
    analytical_hybrid: int
    diagnostic: int
    comparative: int
    chart_generate: int
    chart_interpret: int
    clarification_needed: int


class ArchitectureComplexityCounts(BaseModel):
    C1_single_tool: int
    C2_parallel_multi_tool: int
    C3_sequential: int
    C4_dependent_multi_step: int


class ArchitectureDistribution(BaseModel):
    query_type_counts: ArchitectureQueryTypeCounts
    orchestration_complexity_counts: ArchitectureComplexityCounts


class ArchitectureOrchestrationDataset(BaseModel):
    dataset_name: str
    version: str
    description: str
    total_cases: int
    distribution: ArchitectureDistribution
    cases: list[ArchitectureOrchestrationCase]

# ==========================================
# EXPERIMENT 2: SQL GROUNDING DATASET SCHEMAS
# ==========================================

class SqlComplexityCounts(BaseModel):
    single_table_query: int
    multi_table_join: int
    aggregation: int
    nested_query: int
    window_function: int
    conditional_aggregation: int
    ambiguous_or_typo_entity: int
    questionnaire_metadata: int


class SqlGroundingDistribution(BaseModel):
    sql_complexity_counts: SqlComplexityCounts


class DatabaseSnapshot(BaseModel):
    snapshot_id: str
    description: str
    created_at: str | None = None


class UserScopeDef(BaseModel):
    role: str
    allowed_faculties: list[str] = Field(default_factory=list)
    allowed_programs: list[str] = Field(default_factory=list)
    allowed_courses: list[str] = Field(default_factory=list)


class PlanStepContext(BaseModel):
    task: str
    tool: str
    required: bool


class ExpectedGrounding(BaseModel):
    expected_tables: list[str] = Field(default_factory=list)
    expected_entities: dict[str, Any] = Field(default_factory=dict)
    expected_catalog_references: list[str] = Field(default_factory=list)


class ExpectedSqlBehavior(BaseModel):
    must_include_sql_patterns: list[str] = Field(default_factory=list)
    must_not_include_sql_patterns: list[str] = Field(default_factory=list)
    expected_result_facts: list[str] = Field(default_factory=list)
    gold_sql: str | None = None
    numeric_tolerance: float | None = None


class ScoringFlags(BaseModel):
    execution_accuracy_required: bool
    schema_selection_required: bool
    entity_resolution_required: bool
    catalog_lookup_required: bool
    retry_expected: bool


class SqlGroundingCase(BaseModel):
    id: str
    sql_complexity: str
    question: str
    language: str
    domain: str = "portfolio"
    user_scope: UserScopeDef
    plan_step_context: PlanStepContext
    prior_steps_context: str = ""
    expected_grounding: ExpectedGrounding
    expected_sql_behavior: ExpectedSqlBehavior
    scoring: ScoringFlags
    notes_for_dataset_author: str = ""


class SqlGroundingDataset(BaseModel):
    dataset_name: str
    version: str
    description: str
    total_cases: int
    database_snapshot: DatabaseSnapshot
    distribution: SqlGroundingDistribution
    cases: list[SqlGroundingCase]


# ==========================================
# UAT AND END-TO-END FINAL SYSTEM DATASET
# ==========================================

class UatRoleCounts(BaseModel):
    dosen: int
    kaprodi: int
    dekan: int
    direktorat: int


class UatAnalysisAspectCounts(BaseModel):
    academic_performance: int
    portfolio_reflection: int
    program_or_faculty_monitoring: int
    comparative_or_trend_analysis: int
    diagnostic_and_recommendation: int


class UatDataSourceMixCounts(BaseModel):
    structured: int
    textual: int
    hybrid: int


class UatDistribution(BaseModel):
    role_counts: UatRoleCounts
    analysis_aspect_counts: UatAnalysisAspectCounts
    data_source_mix_counts: UatDataSourceMixCounts


class UatUserScope(BaseModel):
    role: str
    requires_live_role_account: bool = True
    scope_notes: str = ""


class UatExpectedEvidence(BaseModel):
    expected_tools: list[str] = Field(default_factory=list)
    expected_data_sources: list[str] = Field(default_factory=list)
    expected_answer_elements: list[str] = Field(default_factory=list)
    prohibited_behavior: list[str] = Field(default_factory=list)


class UatTechnicalRubric(BaseModel):
    task_success_criteria: list[str] = Field(default_factory=list)
    correctness_reference: str = ""
    faithfulness_reference: str = ""
    completeness_criteria: list[str] = Field(default_factory=list)


class UatAcceptanceRubric(BaseModel):
    task_completion_prompt: str
    perceived_correctness_prompt: str
    usefulness_prompt: str
    clarity_prompt: str
    trust_acceptance_prompt: str


class UatValidationChecklist(BaseModel):
    pre_uat_checks: list[str] = Field(default_factory=list)
    evidence_non_empty_required: bool = True
    scope_leakage_check_required: bool = True


class UatEndToEndCase(BaseModel):
    id: str
    role: str
    analysis_aspect: str
    data_source_mix: str
    language: str = "id"
    domain: str = "portfolio"
    question: str
    user_scope: UatUserScope
    expected_evidence: UatExpectedEvidence
    technical_rubric: UatTechnicalRubric
    acceptance_rubric: UatAcceptanceRubric
    validation: UatValidationChecklist
    notes_for_evaluator: str = ""


class UatEndToEndDataset(BaseModel):
    dataset_name: str
    version: str
    description: str
    total_cases: int
    distribution: UatDistribution
    metrics: dict[str, list[str]]
    cases: list[UatEndToEndCase]
