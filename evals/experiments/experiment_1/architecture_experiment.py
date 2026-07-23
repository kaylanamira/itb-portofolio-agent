from __future__ import annotations

from collections import defaultdict
from enum import Enum
from statistics import mean
from time import perf_counter
from typing import Any

from pydantic import BaseModel, Field

from evals.datasets.schemas import ArchitectureOrchestrationCase


class ArchitectureConfig(str, Enum):
    A1_DIRECT_TOOL = "A1"
    A2_REACT_STYLE = "A2"
    A3_PLAN_EXECUTE = "A3"
    A4_PROPOSED = "A4"


class ArchitectureRunResult(BaseModel):
    case_id: str
    config: ArchitectureConfig
    query_type: str
    orchestration_complexity: str
    selected_tool_sequence: list[str] = Field(default_factory=list)
    selected_node_sequence: list[str] = Field(default_factory=list)
    final_response_type: str | None = None
    final_narrative: str = ""
    tool_call_count: int = 0
    latency_seconds: float = 0.0
    token_count: int | None = None
    faithfulness_score: float | None = None
    completeness_score: float | None = None
    error: str | None = None


class ArchitectureMetricRow(BaseModel):
    config: ArchitectureConfig
    group: str
    n: int
    tool_selection_accuracy: float
    tool_sequence_accuracy: float
    task_success_rate: float
    correctness: float
    faithfulness: float
    completeness: float
    average_tool_calls: float
    average_latency_seconds: float
    average_token_count: float | None = None


class ArchitectureExperimentReport(BaseModel):
    dataset_size: int
    configs: list[ArchitectureConfig]
    by_complexity: list[ArchitectureMetricRow]
    by_query_type: list[ArchitectureMetricRow]
    totals: list[ArchitectureMetricRow]
    cases: list[ArchitectureRunResult]


def timed_result(fn):
    async def wrapped(*args, **kwargs):
        start = perf_counter()
        result = await fn(*args, **kwargs)
        result.latency_seconds = round(perf_counter() - start, 4)
        return result
    return wrapped


def normalize_tool(tool: str) -> str:
    mapping = {
        "chart_interpret": "chart_interpreter",
        "chart": "chart_interpreter",
        "sql_pipeline": "sql",
        "rag_retriever": "rag",
        "out_of_scope": "clarification",
        "synthesis_only": "synthesis_only",
    }
    return mapping.get(tool, tool)


def normalize_sequence(sequence: list[str]) -> list[str]:
    normalized: list[str] = []
    for item in sequence:
        parts = [part.strip() for part in str(item).replace("+", ",").split(",")]
        for part in parts:
            if not part:
                continue
            tool = normalize_tool(part)
            if tool not in normalized:
                normalized.append(tool)
    return normalized


def score_report(
    cases: list[ArchitectureOrchestrationCase],
    results: list[ArchitectureRunResult],
) -> ArchitectureExperimentReport:
    case_by_id = {case.id: case for case in cases}
    configs = sorted({result.config for result in results}, key=lambda item: item.value)
    return ArchitectureExperimentReport(
        dataset_size=len(cases),
        configs=configs,
        by_complexity=_score_group(results, case_by_id, "orchestration_complexity"),
        by_query_type=_score_group(results, case_by_id, "query_type"),
        totals=_score_total(results, case_by_id),
        cases=results,
    )


def _score_group(
    results: list[ArchitectureRunResult],
    case_by_id: dict[str, ArchitectureOrchestrationCase],
    attr: str,
) -> list[ArchitectureMetricRow]:
    grouped: dict[tuple[ArchitectureConfig, str], list[ArchitectureRunResult]] = defaultdict(list)
    for result in results:
        grouped[(result.config, getattr(result, attr))].append(result)
    rows = []
    for (config, group), group_results in sorted(grouped.items(), key=lambda item: (item[0][0].value, item[0][1])):
        rows.append(_score_results(config, group, group_results, case_by_id))
    return rows


def _score_total(
    results: list[ArchitectureRunResult],
    case_by_id: dict[str, ArchitectureOrchestrationCase],
) -> list[ArchitectureMetricRow]:
    grouped: dict[ArchitectureConfig, list[ArchitectureRunResult]] = defaultdict(list)
    for result in results:
        grouped[result.config].append(result)
    return [
        _score_results(config, "total", grouped[config], case_by_id)
        for config in sorted(grouped, key=lambda item: item.value)
    ]


def _score_results(
    config: ArchitectureConfig,
    group: str,
    results: list[ArchitectureRunResult],
    case_by_id: dict[str, ArchitectureOrchestrationCase],
) -> ArchitectureMetricRow:
    n = len(results)
    return ArchitectureMetricRow(
        config=config,
        group=group,
        n=n,
        tool_selection_accuracy=_ratio(sum(_tool_set_correct(result, case_by_id[result.case_id]) for result in results), n),
        tool_sequence_accuracy=_ratio(sum(_tool_sequence_correct(result, case_by_id[result.case_id]) for result in results), n),
        task_success_rate=_ratio(sum(_task_success(result, case_by_id[result.case_id]) for result in results), n),
        correctness=_ratio(sum(_answer_correct(result, case_by_id[result.case_id]) for result in results), n),
        faithfulness=_average_score(results, "faithfulness_score"),
        completeness=_average_score(results, "completeness_score"),
        average_tool_calls=round(mean([result.tool_call_count for result in results]), 4) if results else 0.0,
        average_latency_seconds=round(mean([result.latency_seconds for result in results]), 4) if results else 0.0,
        average_token_count=_average_score(results, "token_count"),
    )


def _tool_set_correct(result: ArchitectureRunResult, case: ArchitectureOrchestrationCase) -> bool:
    expected = set(normalize_sequence(case.expected_behavior.expected_tool_sequence))
    actual = set(normalize_sequence(result.selected_tool_sequence))
    if expected == actual:
        return True
    if actual.issubset(expected) and len(actual) > 0 and not result.error and result.final_response_type != "error":
        return True
    return False


def _is_subsequence(actual: list[str], expected: list[str]) -> bool:
    it = iter(expected)
    return all(x in it for x in actual)


def _tool_sequence_correct(result: ArchitectureRunResult, case: ArchitectureOrchestrationCase) -> bool:
    expected = normalize_sequence(case.expected_behavior.expected_tool_sequence)
    actual = normalize_sequence(result.selected_tool_sequence)
    if expected == actual:
        return True
    if _is_subsequence(actual, expected) and len(actual) > 0 and not result.error and result.final_response_type != "error":
        return True
    return False


def _task_success(result: ArchitectureRunResult, case: ArchitectureOrchestrationCase) -> bool:
    if result.error:
        return False
    if result.final_response_type != case.expected_behavior.expected_response_type:
        return False
    if not _tool_set_correct(result, case):
        return False
    return _answer_correct(result, case)


def _answer_correct(result: ArchitectureRunResult, case: ArchitectureOrchestrationCase) -> bool:
    facts = case.expected_behavior.required_answer_facts
    if not facts:
        return result.error is None
    narrative = result.final_narrative.lower()
    return all(fact.lower() in narrative for fact in facts)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _average_score(results: list[ArchitectureRunResult], attr: str) -> float | None:
    values = [getattr(result, attr) for result in results if getattr(result, attr) is not None]
    return round(mean(values), 4) if values else 0.0


def result_to_json(report: ArchitectureExperimentReport) -> dict[str, Any]:
    return report.model_dump(mode="json")
