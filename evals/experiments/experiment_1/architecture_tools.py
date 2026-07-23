from __future__ import annotations

from typing import Any

from agent.nodes.catalog_lookup import catalog_lookup
from agent.nodes.chart_interpreter import chart_interpreter
from agent.nodes.clarification_handler import clarification_handler
from agent.nodes.rag_retriever import rag_retriever
from agent.nodes.sql_pipeline import sql_pipeline
from agent.state import AgentState, FormattedResponse, StepResult
from evals.experiments.experiment_1.architecture_experiment import normalize_tool


def merge_state(state: AgentState, update: dict[str, Any]) -> AgentState:
    merged = dict(state)
    additive = {"steps_completed", "reasoning_history", "validation_errors", "error_history"}
    for key, value in update.items():
        if key in additive and value:
            merged[key] = list(merged.get(key, [])) + list(value)
        else:
            merged[key] = value
    return merged


def has_terminal_response(state: AgentState) -> bool:
    return state.get("formatted_response") is not None


class ArchitectureToolExecutor:
    async def execute(self, state: AgentState, tool: str) -> tuple[AgentState, list[str]]:
        normalized = normalize_tool(tool)
        if normalized == "sql":
            return await self._execute_sql(state)
        if normalized == "rag":
            return await self._execute_rag(state)
        if normalized == "catalog_lookup":
            return await self._execute_catalog_lookup(state)
        if normalized == "chart_interpreter":
            return await self._execute_chart_interpreter(state)
        if normalized == "clarification":
            return await self._execute_clarification(state)
        return state, []

    async def _execute_sql(self, state: AgentState) -> tuple[AgentState, list[str]]:
        state = merge_state(state, await sql_pipeline(state))
        state = self._append_observation(state, "sql")
        return state, ["sql_pipeline"]

    async def _execute_rag(self, state: AgentState) -> tuple[AgentState, list[str]]:
        state = merge_state(state, await rag_retriever(state))
        state = self._append_observation(state, "rag")
        return state, ["rag_retriever"]

    async def _execute_catalog_lookup(self, state: AgentState) -> tuple[AgentState, list[str]]:
        state = merge_state(state, await catalog_lookup(state))
        state = self._append_observation(state, "catalog_lookup")
        return state, ["catalog_lookup"]

    async def _execute_chart_interpreter(self, state: AgentState) -> tuple[AgentState, list[str]]:
        state = merge_state(state, await chart_interpreter(state))
        return state, ["chart_interpreter"]

    async def _execute_clarification(self, state: AgentState) -> tuple[AgentState, list[str]]:
        state = merge_state(state, await clarification_handler(state))
        return state, ["clarification_handler"]

    def _append_observation(self, state: AgentState, action: str) -> AgentState:
        steps = list(state.get("steps_completed", []))
        steps.append(StepResult(
            step_number=len(steps) + 1,
            thought=self._current_task(state),
            action=action,
            query=self._query_for_action(state, action),
            result=self._result_for_action(state, action),
            observation=self._observation_for_action(state, action),
        ))
        state["steps_completed"] = steps
        state["generated_sql"] = None
        state["sql_result"] = None
        state["sql_error"] = None
        state["sql_row_count"] = None
        state["rag_query"] = None
        state["rag_chunks"] = None
        state["rag_generated_answer"] = None
        state["rag_citations"] = None
        return state

    def _current_task(self, state: AgentState) -> str:
        plan = state.get("plan", [])
        idx = state.get("current_step_index", 0)
        if idx < len(plan):
            return plan[idx].get("task", state.get("effective_query", ""))
        return state.get("effective_query", "")

    def _query_for_action(self, state: AgentState, action: str) -> str:
        if action in {"sql", "catalog_lookup"}:
            return state.get("generated_sql") or state.get("effective_query", "")
        if action == "rag":
            return state.get("rag_query") or state.get("effective_query", "")
        return state.get("effective_query", "")

    def _result_for_action(self, state: AgentState, action: str) -> dict[str, Any]:
        if action in {"sql", "catalog_lookup"}:
            return {
                "sql": state.get("generated_sql"),
                "rows": state.get("sql_result"),
                "row_count": state.get("sql_row_count"),
                "error": state.get("sql_error"),
            }
        if action == "rag":
            return {
                "query": state.get("rag_query"),
                "chunks": state.get("rag_chunks"),
                "answer": state.get("rag_generated_answer"),
                "citations": state.get("rag_citations"),
            }
        return {}

    def _observation_for_action(self, state: AgentState, action: str) -> str:
        if action in {"sql", "catalog_lookup"}:
            if state.get("sql_error"):
                return f"SQL failed: {state.get('sql_error')}"
            return f"SQL returned {state.get('sql_row_count', 0)} rows."
        if action == "rag":
            chunks = state.get("rag_chunks") or []
            answer = state.get("rag_generated_answer")
            suffix = " with generated answer." if answer else "."
            return f"RAG returned {len(chunks)} chunks{suffix}"
        return "Tool executed."


def response_payload(state: AgentState) -> tuple[str | None, str]:
    response = state.get("formatted_response")
    if isinstance(response, FormattedResponse):
        return response.response_type, response.narrative
    if response:
        return getattr(response, "response_type", None), getattr(response, "narrative", "")
    return None, ""
