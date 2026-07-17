from __future__ import annotations

from typing import Any, TypeVar
from pydantic import BaseModel, Field
from enum import Enum

from evals.config import metric_threshold

T = TypeVar("T", bound=BaseModel)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator > 0 else 0.0


def _compute_soft_f1(predicted_rows: list[tuple], gold_rows: list[tuple]) -> float:
    if not gold_rows:
        return 1.0 if not predicted_rows else 0.0
    if not predicted_rows:
        return 0.0
    
    def normalize_row(row: tuple) -> frozenset:
        normalized = []
        for val in row:
            if val is None:
                normalized.append(("__NULL__", None))
            elif isinstance(val, (int, float)):
                normalized.append(("num", float(val)))
            else:
                normalized.append(("str", str(val).strip().lower()))
        return frozenset(normalized)
    
    pred_set = [normalize_row(r) for r in predicted_rows]
    gold_set = [normalize_row(r) for r in gold_rows]
    
    # Count matches per row
    tp = 0  # matched cells
    fp = 0  # predicted-only cells
    fn = 0  # gold-only cells
    
    # Greedy matching: for each gold row, find best matching pred row
    used_pred = set()
    for gold_row in gold_set:
        best_match = None
        best_match_score = 0
        
        for i, pred_row in enumerate(pred_set):
            if i in used_pred:
                continue
            matched = len(gold_row & pred_row)
            if matched > best_match_score:
                best_match_score = matched
                best_match = i
        
        if best_match is not None:
            pred_row = pred_set[best_match]
            used_pred.add(best_match)
            
            matched = len(gold_row & pred_row)
            pred_only = len(pred_row - gold_row)
            gold_only = len(gold_row - pred_row)
            
            tp += matched
            fp += pred_only
            fn += gold_only
        else:
            # No match for this gold row
            fn += len(gold_row)
    
    # Add unmatched predicted rows
    for i, pred_row in enumerate(pred_set):
        if i not in used_pred:
            fp += len(pred_row)
    
    # Compute F1
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return round(f1, 4)


class MetricFlag(str, Enum):
    IS_EXPECTED_BLOCKED = "is_expected_blocked"
    IS_BLOCKED = "is_blocked"
    IS_ROUTING_CORRECT = "is_routing_correct"
    IS_EXPECTED_OOS = "is_expected_oos"
    IS_PREDICTED_OOS = "is_predicted_oos"
    IS_CORRECTLY_REJECTED = "is_correctly_rejected"
    REWRITE_TRIGGER_CORRECT = "rewrite_trigger_correct"
    SEMANTIC_PRESERVATION_PASSED = "semantic_preservation_passed"
    REWRITE_COMPLETENESS_PASSED = "rewrite_completeness_passed"
    IS_QUERY_TYPE_CORRECT = "is_query_type_correct"
    IS_TOOLS_CORRECT = "is_tools_correct"
    IS_EXPECTED_CLARIFICATION = "is_expected_clarification"
    IS_CORRECTLY_FLAGGED_CLARIFY = "is_correctly_flagged_clarify"
    IS_TABLE_CORRECT = "is_table_correct"
    ENTITY_FIELDS_MATCHED_COUNT = "entity_fields_matched_count"
    ENTITY_FIELDS_TOTAL_COUNT = "entity_fields_total_count"
    ENTITY_FIELDS_EXTRACTED_COUNT = "entity_fields_extracted_count"
    FUZZY_FIELDS_MATCHED_COUNT = "fuzzy_fields_matched_count"
    FUZZY_FIELDS_TOTAL_COUNT = "fuzzy_fields_total_count"
    IS_SYNTAX_VALID = "is_syntax_valid"
    IS_SECURITY_SAFE = "is_security_safe"
    IS_NO_PII = "is_no_pii"
    IS_CORRECT_TABLE_USED = "is_correct_table_used"
    IS_EXECUTION_ACCURATE = "is_execution_accurate"
    IS_EXPECTED_INVALID = "is_expected_invalid"
    IS_VALIDATION_CORRECT = "is_validation_correct"
    IS_PREDICTED_VALID = "is_predicted_valid"
    IS_EXPECTED_VALID = "is_expected_valid"
    IS_VALIDITY_CORRECT = "is_validity_correct"
    ABORT_TRIGGERED_CORRECTLY = "abort_triggered_correctly"
    NO_PREMATURE_ABORT = "no_premature_abort"
    STATE_RESET_CORRECT = "state_reset_correct"
    ROUTER_CORRECTNESS = "router_correctness"
    STEP_RECORDED = "step_recorded"
    SCRATCH_STATE_CLEARED = "scratch_state_cleared"
    INDEX_ADVANCED = "index_advanced"
    FORMAT_COMPLIANT = "format_compliant"
    ABORT_PATH_CORRECT = "abort_path_correct"
    CHART_ARTIFACT_VALID = "chart_artifact_valid"
    IS_CHART_CASE = "is_chart_case"
    NO_SQL_PRODUCED = "no_sql_produced"
    CORRECT_ROW_RETURN = "correct_row_return"
    IS_EMPTY_CASE = "is_empty_case"
    EMPTY_RESULT_HANDLED = "empty_result_handled"
    CLARIFICATION_RELEVANCE = "clarification_relevance"
    STEP_FAITHFULNESS = "step_faithfulness"
    STEP_ANSWER_RELEVANCE = "step_answer_relevance"
    STEP_OBSERVATION_COMPLETENESS = "step_observation_completeness"
    SOFT_F1_SCORE = "soft_f1_score"
    SYNTH_ANSWER_RELEVANCE_PASSED = "synth_answer_relevance_passed"
    SYNTH_FAITHFULNESS_PASSED = "synth_faithfulness_passed"
    SYNTH_TOXICITY_PASSED = "synth_toxicity_passed"
    ANALYSIS_EXISTS = "analysis_exists"
    RAG_RETRIEVAL_RELEVANCE_PASSED = "rag_retrieval_relevance_passed"
    RAG_FAITHFULNESS_PASSED = "rag_faithfulness_passed"
    RAG_CITATION_VALID = "rag_citation_valid"
    RAG_HYDE_TRIGGER_CORRECT = "rag_hyde_trigger_correct"
    RAG_ENTITY_RESOLUTION_CORRECT = "rag_entity_resolution_correct"
    RAG_VERIFIKATOR_FILTER_CORRECT = "rag_verifikator_filter_correct"

class NodeTestResult(BaseModel):
    case_id: str
    node_name: str
    passed: bool
    expected_value: Any | None = None
    actual_value: Any | None = None
    metric_flags: dict[MetricFlag, Any] = Field(default_factory=dict)
    complexity: str = "simple"
    query_type: str = "unknown"


class MetricSummary(BaseModel):
    metric_name: str
    score: float
    threshold: float
    passed: bool


def _summarize(node: str, metric: str, score: float, lower_is_better: bool = False) -> MetricSummary:
    threshold = metric_threshold(node, metric)
    passed = score <= threshold if lower_is_better else score >= threshold
    return MetricSummary(metric_name=metric, score=score, threshold=threshold, passed=passed)


def score_input_guard(results: list[NodeTestResult]) -> list[MetricSummary]:
    total_injection = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_EXPECTED_BLOCKED))
    total_clean = sum(1 for r in results if not r.metric_flags.get(MetricFlag.IS_EXPECTED_BLOCKED))
    correctly_blocked = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_EXPECTED_BLOCKED) and r.metric_flags.get(MetricFlag.IS_BLOCKED))
    incorrectly_blocked = sum(1 for r in results if not r.metric_flags.get(MetricFlag.IS_EXPECTED_BLOCKED) and r.metric_flags.get(MetricFlag.IS_BLOCKED))

    return [
        _summarize("input_guard", "true_positive_rate", _ratio(correctly_blocked, total_injection)),
        _summarize("input_guard", "false_positive_rate", _ratio(incorrectly_blocked, total_clean), lower_is_better=True),
    ]


def score_intent_classifier(results: list[NodeTestResult]) -> list[MetricSummary]:
    total = len(results)
    routing_correct = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_ROUTING_CORRECT))
    expected_oos = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_EXPECTED_OOS))
    predicted_oos = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_PREDICTED_OOS))
    correctly_rejected = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_CORRECTLY_REJECTED))

    return [
        _summarize("intent_classifier", "routing_accuracy", _ratio(routing_correct, total)),
        _summarize("intent_classifier", "oos_recall", _ratio(correctly_rejected, expected_oos)),
        _summarize("intent_classifier", "oos_precision", _ratio(correctly_rejected, predicted_oos)),
    ]


def score_query_rewriter(results: list[NodeTestResult]) -> list[MetricSummary]:
    trigger_total = sum(1 for r in results if MetricFlag.REWRITE_TRIGGER_CORRECT in r.metric_flags)
    trigger_correct = sum(1 for r in results if r.metric_flags.get(MetricFlag.REWRITE_TRIGGER_CORRECT))
    
    sem_pres_total = sum(1 for r in results if MetricFlag.SEMANTIC_PRESERVATION_PASSED in r.metric_flags)
    sem_pres_correct = sum(1 for r in results if r.metric_flags.get(MetricFlag.SEMANTIC_PRESERVATION_PASSED))
    
    rew_comp_total = sum(1 for r in results if MetricFlag.REWRITE_COMPLETENESS_PASSED in r.metric_flags)
    rew_comp_correct = sum(1 for r in results if r.metric_flags.get(MetricFlag.REWRITE_COMPLETENESS_PASSED))

    summaries = [
        _summarize("query_rewriter", "rewrite_trigger_accuracy", _ratio(trigger_correct, max(trigger_total, 1))),
    ]
    if sem_pres_total > 0:
        summaries.append(_summarize("query_rewriter", "semantic_preservation", _ratio(sem_pres_correct, sem_pres_total)))
    if rew_comp_total > 0:
        summaries.append(_summarize("query_rewriter", "rewrite_completeness", _ratio(rew_comp_correct, rew_comp_total)))
        
    return summaries


def score_planner(results: list[NodeTestResult]) -> list[MetricSummary]:
    total = len(results)
    qtype_correct = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_QUERY_TYPE_CORRECT))
    tools_correct = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_TOOLS_CORRECT))
    expected_clarify = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_EXPECTED_CLARIFICATION))
    predicted_clarify = sum(1 for r in results if r.actual_value == "clarification_needed")
    correctly_flagged = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_CORRECTLY_FLAGGED_CLARIFY))

    return [
        _summarize("planner", "query_type_accuracy", _ratio(qtype_correct, total)),
        _summarize("planner", "tool_membership_correctness", _ratio(tools_correct, total)),
        _summarize("planner", "clarification_precision", _ratio(correctly_flagged, predicted_clarify)),
    ]


def score_schema_linker(results: list[NodeTestResult]) -> list[MetricSummary]:
    total = len(results)
    table_correct = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_TABLE_CORRECT))
    entity_fields_matched = sum(r.metric_flags.get(MetricFlag.ENTITY_FIELDS_MATCHED_COUNT, 0) for r in results)
    entity_fields_total = sum(r.metric_flags.get(MetricFlag.ENTITY_FIELDS_TOTAL_COUNT, 0) for r in results)
    entity_fields_extracted = sum(r.metric_flags.get(MetricFlag.ENTITY_FIELDS_EXTRACTED_COUNT, 0) for r in results)
    
    fuzzy_fields_matched = sum(r.metric_flags.get(MetricFlag.FUZZY_FIELDS_MATCHED_COUNT, 0) for r in results)
    fuzzy_fields_total = sum(r.metric_flags.get(MetricFlag.FUZZY_FIELDS_TOTAL_COUNT, 0) for r in results)

    summaries = [
        _summarize("schema_linker", "entity_precision", _ratio(entity_fields_matched, entity_fields_extracted)),
        _summarize("schema_linker", "entity_recall", _ratio(entity_fields_matched, entity_fields_total)),
        _summarize("schema_linker", "table_selection_accuracy", _ratio(table_correct, total)),
    ]
    if fuzzy_fields_total > 0:
        summaries.append(_summarize("schema_linker", "fuzzy_resolution_rate", _ratio(fuzzy_fields_matched, fuzzy_fields_total)))
    return summaries


def score_sql_generator(results: list[NodeTestResult]) -> list[MetricSummary]:
    total = len(results)
    syntax_valid = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_SYNTAX_VALID))
    security_safe = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_SECURITY_SAFE))
    no_pii = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_NO_PII))
    correct_table = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_CORRECT_TABLE_USED))
    execution_accurate = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_EXECUTION_ACCURATE))

    summaries = [
        _summarize("sql_generator", "sql_syntax_validity", _ratio(syntax_valid, total)),
        _summarize("sql_generator", "security_pass_rate", _ratio(security_safe, total)),
        _summarize("sql_generator", "no_pii_column_rate", _ratio(no_pii, total)),
        _summarize("sql_generator", "correct_table_usage", _ratio(correct_table, total)),
        _summarize("sql_generator", "execution_accuracy", _ratio(execution_accurate, total)),
    ]

    for c in ["simple", "medium", "complex"]:
        c_cases = [r for r in results if r.complexity == c]
        if c_cases:
            c_acc = sum(1 for r in c_cases if r.metric_flags.get(MetricFlag.IS_EXECUTION_ACCURATE))
            summaries.append(_summarize("sql_generator", f"execution_accuracy_{c}", _ratio(c_acc, len(c_cases))))

    f1_cases = [r for r in results if MetricFlag.SOFT_F1_SCORE in r.metric_flags]
    if f1_cases:
        mean_f1 = round(sum(r.metric_flags[MetricFlag.SOFT_F1_SCORE] for r in f1_cases) / len(f1_cases), 4)
        summaries.append(_summarize("sql_generator", "soft_f1_score", mean_f1))

        for c in ["simple", "medium", "complex"]:
            c_f1_cases = [r for r in f1_cases if r.complexity == c]
            if c_f1_cases:
                c_mean_f1 = round(sum(r.metric_flags[MetricFlag.SOFT_F1_SCORE] for r in c_f1_cases) / len(c_f1_cases), 4)
                summaries.append(_summarize("sql_generator", f"soft_f1_{c}", c_mean_f1))

    return summaries


def score_sql_validator(results: list[NodeTestResult]) -> list[MetricSummary]:
    injection_cases = [r for r in results if r.metric_flags.get(MetricFlag.IS_EXPECTED_INVALID)]
    valid_cases = [r for r in results if not r.metric_flags.get(MetricFlag.IS_EXPECTED_INVALID)]
    true_blocked = sum(1 for r in injection_cases if r.metric_flags.get(MetricFlag.IS_VALIDATION_CORRECT))
    false_blocked = sum(1 for r in valid_cases if not r.metric_flags.get(MetricFlag.IS_VALIDATION_CORRECT))

    return [
        _summarize("sql_validator", "true_block_rate", _ratio(true_blocked, len(injection_cases))),
        _summarize("sql_validator", "false_block_rate", _ratio(false_blocked, len(valid_cases))),
    ]


def score_answer_validator(results: list[NodeTestResult]) -> list[MetricSummary]:
    predicted_valid = [r for r in results if r.metric_flags.get(MetricFlag.IS_PREDICTED_VALID)]
    actually_valid = [r for r in results if r.metric_flags.get(MetricFlag.IS_EXPECTED_VALID)]
    true_valid = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_EXPECTED_VALID) and r.metric_flags.get(MetricFlag.IS_PREDICTED_VALID))
    false_invalid = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_EXPECTED_VALID) and not r.metric_flags.get(MetricFlag.IS_PREDICTED_VALID))

    return [
        _summarize("answer_validator", "validity_precision", _ratio(true_valid, len(predicted_valid))),
        _summarize("answer_validator", "validity_recall", _ratio(true_valid, len(actually_valid))),
        _summarize("answer_validator", "false_invalid_rate", _ratio(false_invalid, len(actually_valid)), lower_is_better=True),
    ]


def score_error_handler(results: list[NodeTestResult]) -> list[MetricSummary]:
    total = len(results)
    abort_correct = sum(1 for r in results if r.metric_flags.get(MetricFlag.ABORT_TRIGGERED_CORRECTLY))
    no_premature = sum(1 for r in results if r.metric_flags.get(MetricFlag.NO_PREMATURE_ABORT))
    state_reset = sum(1 for r in results if r.metric_flags.get(MetricFlag.STATE_RESET_CORRECT))
    router_correct = sum(1 for r in results if r.metric_flags.get(MetricFlag.ROUTER_CORRECTNESS))

    return [
        _summarize("error_handler", "abort_trigger", _ratio(abort_correct, total)),
        _summarize("error_handler", "no_premature_abort", _ratio(no_premature, total)),
        _summarize("error_handler", "state_reset", _ratio(state_reset, total)),
        _summarize("error_handler", "router_correctness", _ratio(router_correct, total)),
    ]


def score_step_reasoner(results: list[NodeTestResult]) -> list[MetricSummary]:
    total = len(results)
    
    eval_total = sum(1 for r in results if MetricFlag.STEP_FAITHFULNESS in r.metric_flags)
    eval_total = eval_total if eval_total > 0 else total

    faithfulness = sum(1 for r in results if r.metric_flags.get(MetricFlag.STEP_FAITHFULNESS))
    relevance = sum(1 for r in results if r.metric_flags.get(MetricFlag.STEP_ANSWER_RELEVANCE))
    completeness = sum(1 for r in results if r.metric_flags.get(MetricFlag.STEP_OBSERVATION_COMPLETENESS))

    return [
        _summarize("step_reasoner", "observation_completeness", _ratio(completeness, eval_total)),
        _summarize("step_reasoner", "faithfulness", _ratio(faithfulness, eval_total)),
        _summarize("step_reasoner", "answer_relevance", _ratio(relevance, eval_total)),
    ]


def score_synthesizer(results: list[NodeTestResult]) -> list[MetricSummary]:
    total = len(results)
    format_ok = sum(1 for r in results if r.metric_flags.get(MetricFlag.FORMAT_COMPLIANT))
    abort_ok = sum(1 for r in results if r.metric_flags.get(MetricFlag.ABORT_PATH_CORRECT))
    chart_ok = sum(1 for r in results if r.metric_flags.get(MetricFlag.CHART_ARTIFACT_VALID))
    chart_total = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_CHART_CASE))

    summaries = [
        _summarize("synthesizer", "format_compliance", _ratio(format_ok, total)),
        _summarize("synthesizer", "abort_path_format", _ratio(abort_ok, total)),
    ]
    if chart_total > 0:
        summaries.append(_summarize("synthesizer", "chart_artifact_validity", _ratio(chart_ok, chart_total)))

    eval_total = sum(1 for r in results if MetricFlag.SYNTH_ANSWER_RELEVANCE_PASSED in r.metric_flags)
    if eval_total > 0:
        relevance = sum(1 for r in results if r.metric_flags.get(MetricFlag.SYNTH_ANSWER_RELEVANCE_PASSED))
        toxicity = sum(1 for r in results if r.metric_flags.get(MetricFlag.SYNTH_TOXICITY_PASSED))
        summaries += [
            _summarize("synthesizer", "answer_relevance", _ratio(relevance, eval_total)),
            _summarize("synthesizer", "toxicity_bias", _ratio(toxicity, eval_total)),
        ]

        faith_total = sum(1 for r in results if MetricFlag.SYNTH_FAITHFULNESS_PASSED in r.metric_flags)
        if faith_total > 0:
            faithfulness = sum(1 for r in results if r.metric_flags.get(MetricFlag.SYNTH_FAITHFULNESS_PASSED))
            summaries.append(_summarize("synthesizer", "faithfulness", _ratio(faithfulness, faith_total)))

    return summaries


def score_clarification_handler(results: list[NodeTestResult]) -> list[MetricSummary]:
    total = len(results)
    format_ok = sum(1 for r in results if r.metric_flags.get(MetricFlag.FORMAT_COMPLIANT))
    relevant_count = sum(1 for r in results if r.metric_flags.get(MetricFlag.CLARIFICATION_RELEVANCE))

    return [
        _summarize("clarification_handler", "response_format_rate", _ratio(format_ok, total)),
        _summarize("clarification_handler", "clarification_relevance", _ratio(relevant_count, total)),
    ]


def score_chart_interpreter(results: list[NodeTestResult]) -> list[MetricSummary]:
    total = len(results)
    
    eval_total = sum(1 for r in results if MetricFlag.STEP_FAITHFULNESS in r.metric_flags)
    eval_total = eval_total if eval_total > 0 else total

    faithfulness = sum(1 for r in results if r.metric_flags.get(MetricFlag.STEP_FAITHFULNESS))
    relevance = sum(1 for r in results if r.metric_flags.get(MetricFlag.STEP_ANSWER_RELEVANCE))
    completeness = sum(1 for r in results if r.metric_flags.get(MetricFlag.STEP_OBSERVATION_COMPLETENESS))

    return [
        _summarize("chart_interpreter", "observation_completeness", _ratio(completeness, eval_total)),
        _summarize("chart_interpreter", "faithfulness", _ratio(faithfulness, eval_total)),
        _summarize("chart_interpreter", "answer_relevance", _ratio(relevance, eval_total)),
    ]


def score_rag_retriever(results: list[NodeTestResult]) -> list[MetricSummary]:
    relevance_total = sum(1 for r in results if MetricFlag.RAG_RETRIEVAL_RELEVANCE_PASSED in r.metric_flags)
    relevance_passed = sum(1 for r in results if r.metric_flags.get(MetricFlag.RAG_RETRIEVAL_RELEVANCE_PASSED))

    faith_total = sum(1 for r in results if MetricFlag.RAG_FAITHFULNESS_PASSED in r.metric_flags)
    faith_passed = sum(1 for r in results if r.metric_flags.get(MetricFlag.RAG_FAITHFULNESS_PASSED))

    citation_total = sum(1 for r in results if MetricFlag.RAG_CITATION_VALID in r.metric_flags)
    citation_passed = sum(1 for r in results if r.metric_flags.get(MetricFlag.RAG_CITATION_VALID))

    hyde_total = sum(1 for r in results if MetricFlag.RAG_HYDE_TRIGGER_CORRECT in r.metric_flags)
    hyde_correct = sum(1 for r in results if r.metric_flags.get(MetricFlag.RAG_HYDE_TRIGGER_CORRECT))

    entity_total = sum(1 for r in results if MetricFlag.RAG_ENTITY_RESOLUTION_CORRECT in r.metric_flags)
    entity_correct = sum(1 for r in results if r.metric_flags.get(MetricFlag.RAG_ENTITY_RESOLUTION_CORRECT))

    verifikator_total = sum(1 for r in results if MetricFlag.RAG_VERIFIKATOR_FILTER_CORRECT in r.metric_flags)
    verifikator_correct = sum(1 for r in results if r.metric_flags.get(MetricFlag.RAG_VERIFIKATOR_FILTER_CORRECT))

    summaries = []
    if relevance_total > 0:
        summaries.append(_summarize("rag_retriever", "context_precision", _ratio(relevance_passed, relevance_total)))
    if faith_total > 0:
        summaries.append(_summarize("rag_retriever", "faithfulness", _ratio(faith_passed, faith_total)))
    if citation_total > 0:
        summaries.append(_summarize("rag_retriever", "citation_validity", _ratio(citation_passed, citation_total)))
    if hyde_total > 0:
        summaries.append(_summarize("rag_retriever", "hyde_trigger_accuracy", _ratio(hyde_correct, hyde_total)))
    if entity_total > 0:
        summaries.append(_summarize("rag_retriever", "entity_resolution_accuracy", _ratio(entity_correct, entity_total)))
    if verifikator_total > 0:
        summaries.append(_summarize("rag_retriever", "verifikator_filter_accuracy", _ratio(verifikator_correct, verifikator_total)))

    return summaries


def score_sql_executor(results: list[NodeTestResult]) -> list[MetricSummary]:
    total = len(results)
    correct_rows = sum(1 for r in results if r.metric_flags.get(MetricFlag.CORRECT_ROW_RETURN))
    empty_handled = sum(1 for r in [r for r in results if r.metric_flags.get(MetricFlag.IS_EMPTY_CASE)] if r.metric_flags.get(MetricFlag.EMPTY_RESULT_HANDLED))
    empty_total = sum(1 for r in results if r.metric_flags.get(MetricFlag.IS_EMPTY_CASE))

    summaries = [
        _summarize("sql_executor", "correct_row_return", _ratio(correct_rows, total)),
    ]
    if empty_total > 0:
        summaries.append(_summarize("sql_executor", "empty_result_handling", _ratio(empty_handled, empty_total)))
    return summaries


_SCORERS: dict[str, Any] = {
    "input_guard": score_input_guard,
    "intent_classifier": score_intent_classifier,
    "query_rewriter": score_query_rewriter,
    "planner": score_planner,
    "schema_linker": score_schema_linker,
    "sql_generator": score_sql_generator,
    "sql_validator": score_sql_validator,
    "answer_validator": score_answer_validator,
    "error_handler": score_error_handler,
    "step_reasoner": score_step_reasoner,
    "synthesizer": score_synthesizer,
    "clarification_handler": score_clarification_handler,
    "chart_interpreter": score_chart_interpreter,
    "sql_executor": score_sql_executor,
    "rag_retriever": score_rag_retriever,
}


def aggregate(results: list[NodeTestResult], node_name: str) -> list[MetricSummary]:
    """Aggregate NodeTestResults into MetricSummary list for the given node."""
    scorer = _SCORERS.get(node_name)
    if scorer is None:
        return []
    return scorer(results)
