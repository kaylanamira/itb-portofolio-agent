"""
Eval-only orchestration adapters for Experiment I (architecture comparison).

These implement A1, A2, and A3 from experiment_design.md section 2.3.
They deliberately do NOT touch production orchestration code
(agent/orchestrator.py, agent/graph.py) — A4 is run by calling that
production graph directly, unmodified, elsewhere (Step 4 of the plan).

Each adapter here is a thin wrapper that calls the SAME production tool
functions (sql_pipeline, rag_retriever, catalog_lookup, chart_interpreter,
clarification_handler, synthesizer) but strings them together with a
simpler/different control flow, so that only the orchestration strategy
differs between configurations — per the isolation constraint in 2.3.

IMPORTANT — before running for real:
Import paths below (agent.nodes.sql_pipeline, etc.) are assumed based on
the production graph wiring seen in agent/graph.py. Confirm these match
your actual package layout before running; adjust the `from ... import`
lines if your project structure differs.
"""
from __future__ import annotations
import time
from typing import Any

from agent.state import AgentState, QueryType
from agent.nodes.sql_pipeline import sql_pipeline
from agent.nodes.rag_retriever import rag_retriever
from agent.nodes.catalog_lookup import catalog_lookup
from agent.nodes.chart_interpreter import chart_interpreter
from agent.nodes.clarification_handler import clarification_handler
from agent.nodes.synthesizer import synthesizer


class VariantRunResult:
    """Uniform trace record for any A1/A2/A3 run, so the test runner (Step 4)
    can score A1/A2/A3 with the same code path used for A4."""

    def __init__(self, config_label: str):
        self.config_label = config_label
        self.selected_tools: list[str] = []
        self.node_sequence: list[str] = []
        self.tool_call_count = 0
        self.steps_completed: list[dict] = []
        self.final_state: dict[str, Any] = {}
        self.start_time = time.monotonic()
        self.latency_seconds: float | None = None

    def record_tool(self, tool_name: str, node_name: str):
        self.selected_tools.append(tool_name)
        self.node_sequence.append(node_name)
        self.tool_call_count += 1

    def finish(self, final_state: dict):
        self.final_state = final_state
        self.latency_seconds = time.monotonic() - self.start_time
        self.steps_completed = final_state.get("steps_completed", [])
        return self


# ---------------------------------------------------------------------------
# A1 — Direct Tool Calling
# ---------------------------------------------------------------------------
# Single eval adapter that routes to exactly one tool based on the case's
# predicted primary tool (taken from the dataset's expected_tool_sequence[0]
# for eval purposes — a real A1 baseline would use a lightweight classifier;
# for this thesis's isolation constraint we use the dataset's own query_type
# to decide the primary tool, which is a reasonable stand-in for "a simple
# router with no planning").

def _predict_primary_tool(query_type: str) -> str:
    mapping = {
        "data_lookup": "sql", "analytical_numeric": "sql", "comparative": "sql",
        "text_lookup": "rag", "analytical_text": "rag", "summarization": "rag",
        "analytical_hybrid": "sql",  # forced to primary tool only — this IS the baseline limitation A1 is meant to expose
        "diagnostic": "sql",
        "chart_interpret": "chart_interpreter",
        "clarification_needed": "clarification",
    }
    return mapping.get(query_type, "sql")


async def direct_tool_workflow_eval(state: AgentState, query_type: str) -> VariantRunResult:
    """A1: one tool call only, no dependent second step, no observation loop."""
    result = VariantRunResult("A1_direct_tool_calling")
    tool = _predict_primary_tool(query_type)

    if tool == "clarification":
        update = await clarification_handler(state)
        result.record_tool("clarification", "clarification_handler")
        state = {**state, **update}
        return result.finish(state)

    if tool == "sql":
        update = await sql_pipeline(state)
        result.record_tool("sql", "sql_pipeline")
    elif tool == "rag":
        update = await rag_retriever(state)
        result.record_tool("rag", "rag_retriever")
    elif tool == "chart_interpreter":
        update = await chart_interpreter(state)
        result.record_tool("chart_interpreter", "chart_interpreter")
    else:
        update = {}

    state = {**state, **update}
    # Synthesizer receives exactly one observation, per 2.3 table.
    final_update = await synthesizer(state)
    result.record_tool("synthesis_only", "synthesizer")
    state = {**state, **final_update}
    return result.finish(state)


# ---------------------------------------------------------------------------
# A2 — ReAct-style Agent + iterative reasoning
# ---------------------------------------------------------------------------
# Eval-only controller that chooses the next action from tool descriptions
# at each iteration using thought/action/observation format. No production
# planner or step_reasoner is used; no initial plan is stored.

REACT_TOOL_DESCRIPTIONS = {
    "sql": "Query the academic portfolio database for structured numeric/factual data.",
    "rag": "Retrieve textual evidence (comments, reflections) via semantic search.",
    "chart_interpreter": "Interpret the currently displayed dashboard chart.",
    "clarification": "Ask the user a clarifying question when the request is ambiguous.",
    "finish": "Stop iterating and produce the final answer from gathered observations.",
}

MAX_REACT_ITERATIONS = 3


async def _react_choose_next_action(state: AgentState, observations: list[dict], llm_choose_fn=None) -> str:
    """Chooses the next tool using an LLM in thought/action/observation format.

    `llm_choose_fn` is injectable for testing; in production eval runs, pass
    a callable that prompts the shared LLM (agent/llm.py) with
    REACT_TOOL_DESCRIPTIONS + observations so far and returns one of the
    keys in REACT_TOOL_DESCRIPTIONS. This keeps the *routing decision*
    eval-only while the *LLM call itself* reuses the production model/config.
    """
    if llm_choose_fn is not None:
        return await llm_choose_fn(state, observations, REACT_TOOL_DESCRIPTIONS)
    # Minimal deterministic fallback used only if no LLM chooser is wired up
    # (keeps this module importable/testable without live credentials).
    if not observations:
        return "sql"
    return "finish"


async def react_controller_eval(state: AgentState, llm_choose_fn=None) -> VariantRunResult:
    """A2: iterative up to three tool calls; each next tool chosen after
    observing the previous result. No initial plan is stored."""
    result = VariantRunResult("A2_react_style")
    observations: list[dict] = []
    working_state = dict(state)

    for _ in range(MAX_REACT_ITERATIONS):
        action = await _react_choose_next_action(working_state, observations, llm_choose_fn)
        if action == "finish":
            break
        if action == "clarification":
            update = await clarification_handler(working_state)
            result.record_tool("clarification", "clarification_handler")
            working_state = {**working_state, **update}
            return result.finish(working_state)
        if action == "sql":
            update = await sql_pipeline(working_state)
            result.record_tool("sql", "sql_pipeline")
        elif action == "rag":
            update = await rag_retriever(working_state)
            result.record_tool("rag", "rag_retriever")
        elif action == "chart_interpreter":
            update = await chart_interpreter(working_state)
            result.record_tool("chart_interpreter", "chart_interpreter")
        else:
            break
        working_state = {**working_state, **update}
        observations.append(update)

    # Accumulated ReAct observations are converted into steps_completed
    # before reaching the shared production synthesizer.
    final_update = await synthesizer(working_state)
    result.record_tool("synthesis_only", "synthesizer")
    working_state = {**working_state, **final_update}
    return result.finish(working_state)


# ---------------------------------------------------------------------------
# A3 — Plan-Execute Agent
# ---------------------------------------------------------------------------
# Uses the PRODUCTION planner (per 2.3: "Include production planner"), but
# executes the plan with an eval-only sequential executor that follows the
# initial plan exactly — no early stop, no replanning (unlike production
# step_reasoner).

async def sequential_executor_eval(state: AgentState) -> VariantRunResult:
    """A3: planner creates all steps once; executor runs step 1..n in order.
    Results from previous steps are passed as context, but the plan cannot
    be shortened or adjusted."""
    from agent.nodes.planner import planner  # production planner, per constraint

    result = VariantRunResult("A3_plan_execute")
    plan_update = await planner(state)
    result.node_sequence.append("planner")
    working_state = {**state, **plan_update}
    plan = working_state.get("plan", [])

    for step in plan:
        tool = step.get("tool", "sql")
        if step.get("required"):
            update = await catalog_lookup(working_state)
            result.record_tool("catalog_lookup", "catalog_lookup")
            working_state = {**working_state, **update}
        if tool == "sql":
            update = await sql_pipeline(working_state)
            result.record_tool("sql", "sql_pipeline")
        elif tool == "rag":
            update = await rag_retriever(working_state)
            result.record_tool("rag", "rag_retriever")
        elif tool == "chart_interpreter":
            update = await chart_interpreter(working_state)
            result.record_tool("chart_interpreter", "chart_interpreter")
        elif tool == "clarification":
            update = await clarification_handler(working_state)
            result.record_tool("clarification", "clarification_handler")
            working_state = {**working_state, **update}
            return result.finish(working_state)  # clarification always terminates
        else:
            continue
        working_state = {**working_state, **update}

    final_update = await synthesizer(working_state)
    result.record_tool("synthesis_only", "synthesizer")
    working_state = {**working_state, **final_update}
    return result.finish(working_state)
