from __future__ import annotations

from collections import defaultdict
from statistics import mean
from time import perf_counter
from typing import Any

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from agent.llm import get_llm
from agent.state import AgentState, FormattedResponse
from evals.datasets.schemas import UatEndToEndCase


class UatJudgeScores(BaseModel):
    correctness: float = Field(ge=0.0, le=1.0)
    faithfulness: float = Field(ge=1.0, le=5.0)
    completeness: float = Field(ge=1.0, le=5.0)
    rationale: str = ""


class UatEndToEndRunResult(BaseModel):
    case_id: str
    role: str
    analysis_aspect: str
    data_source_mix: str
    question: str
    selected_tool_sequence: list[str] = Field(default_factory=list)
    final_response_type: str | None = None
    final_narrative: str = ""
    tool_call_count: int = 0
    latency_seconds: float = 0.0
    task_success: bool = False
    correctness: float | None = None
    faithfulness: float | None = None
    completeness: float | None = None
    judge_rationale: str = ""
    validation_flags: dict[str, bool] = Field(default_factory=dict)
    error: str | None = None


class UatEndToEndMetricRow(BaseModel):
    group: str
    n: int
    task_success_rate: float
    correctness: float | None = None
    faithfulness: float | None = None
    completeness: float | None = None
    average_latency_seconds: float
    average_tool_calls: float


class UatEndToEndReport(BaseModel):
    dataset_size: int
    by_role: list[UatEndToEndMetricRow]
    by_analysis_aspect: list[UatEndToEndMetricRow]
    by_data_source_mix: list[UatEndToEndMetricRow]
    total: UatEndToEndMetricRow
    cases: list[UatEndToEndRunResult]


def timed_run(fn):
    async def wrapped(*args, **kwargs):
        start = perf_counter()
        result = await fn(*args, **kwargs)
        result.latency_seconds = round(perf_counter() - start, 4)
        return result
    return wrapped


def response_payload(state: AgentState) -> tuple[str | None, str]:
    response = state.get("formatted_response")
    if isinstance(response, FormattedResponse):
        return response.response_type, response.narrative
    if response:
        return getattr(response, "response_type", None), getattr(response, "narrative", "")
    return None, ""


def tools_from_state(state: AgentState, response_type: str | None) -> list[str]:
    if response_type == "clarification":
        return ["clarification"]
    steps = state.get("steps_completed", []) or []
    tools: list[str] = []
    for step in steps:
        action = getattr(step, "action", None)
        if action is None and isinstance(step, dict):
            action = step.get("action")
        if action and action not in tools:
            tools.append(str(action))
    return tools


def serialize_steps(state: AgentState) -> list[dict[str, Any]]:
    serialized = []
    for step in state.get("steps_completed", []) or []:
        if hasattr(step, "model_dump"):
            serialized.append(step.model_dump(mode="json"))
        elif isinstance(step, dict):
            serialized.append(step)
        else:
            serialized.append({"value": str(step)})
    return serialized


def build_validation_flags(case: UatEndToEndCase, state: AgentState, response_type: str | None, error: str | None) -> dict[str, bool]:
    steps = state.get("steps_completed", []) or []
    narrative = response_payload(state)[1]
    evidence_non_empty = bool(steps) or bool(state.get("sql_result")) or bool(state.get("rag_chunks")) or bool(state.get("rag_generated_answer"))
    return {
        "full_graph_completed": error is None and response_type is not None,
        "evidence_non_empty": evidence_non_empty if case.validation.evidence_non_empty_required else True,
        "not_error_response": response_type != "error",
        "answer_non_empty": bool(narrative.strip()),
    }


def deterministic_task_success(case: UatEndToEndCase, result: UatEndToEndRunResult) -> bool:
    if result.error or result.final_response_type == "error":
        return False
    if not result.final_narrative.strip():
        return False
    if not all(result.validation_flags.values()):
        return False
    expected_tools = set(case.expected_evidence.expected_tools)
    actual_tools = set(result.selected_tool_sequence)
    if expected_tools and actual_tools and actual_tools.isdisjoint(expected_tools):
        return False
    return True


async def judge_answer(case: UatEndToEndCase, state: AgentState, narrative: str) -> UatJudgeScores:
    evidence = {
        "steps_completed": serialize_steps(state),
        "sql_row_count": state.get("sql_row_count"),
        "sql_result_sample": (state.get("sql_result") or [])[:5],
        "rag_chunk_count": len(state.get("rag_chunks") or []),
        "rag_generated_answer": state.get("rag_generated_answer"),
    }
    prompt = f"""
You are evaluating an academic portfolio analytics agent answer.

Return scores using this scale:
- correctness: 0.0 to 1.0, based on whether factual claims match available evidence and the case rubric.
- faithfulness: 1 to 5, based on whether the final answer is supported by tool evidence.
- completeness: 1 to 5, based on whether the answer covers the requested task.

Question:
{case.question}

Expected answer elements:
{case.expected_evidence.expected_answer_elements}

Task success criteria:
{case.technical_rubric.task_success_criteria}

Completeness criteria:
{case.technical_rubric.completeness_criteria}

Evidence:
{evidence}

Final answer:
{narrative}
"""
    model = get_llm("llm_evaluation").with_structured_output(UatJudgeScores)
    return await model.ainvoke([HumanMessage(content=prompt)])


def score_report(cases: list[UatEndToEndCase], results: list[UatEndToEndRunResult]) -> UatEndToEndReport:
    return UatEndToEndReport(
        dataset_size=len(cases),
        by_role=_score_group(results, "role"),
        by_analysis_aspect=_score_group(results, "analysis_aspect"),
        by_data_source_mix=_score_group(results, "data_source_mix"),
        total=_score_results("total", results),
        cases=results,
    )


def _score_group(results: list[UatEndToEndRunResult], attr: str) -> list[UatEndToEndMetricRow]:
    grouped: dict[str, list[UatEndToEndRunResult]] = defaultdict(list)
    for result in results:
        grouped[getattr(result, attr)].append(result)
    return [_score_results(group, grouped[group]) for group in sorted(grouped)]


def _score_results(group: str, results: list[UatEndToEndRunResult]) -> UatEndToEndMetricRow:
    n = len(results)
    return UatEndToEndMetricRow(
        group=group,
        n=n,
        task_success_rate=_ratio(sum(1 for result in results if result.task_success), n),
        correctness=_average_optional([result.correctness for result in results]),
        faithfulness=_average_optional([result.faithfulness for result in results]),
        completeness=_average_optional([result.completeness for result in results]),
        average_latency_seconds=round(mean([result.latency_seconds for result in results]), 4) if results else 0.0,
        average_tool_calls=round(mean([result.tool_call_count for result in results]), 4) if results else 0.0,
    )


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _average_optional(values: list[float | None]) -> float | None:
    concrete = [value for value in values if value is not None]
    return round(mean(concrete), 4) if concrete else None
