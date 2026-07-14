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
