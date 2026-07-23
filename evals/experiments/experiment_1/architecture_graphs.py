from typing import Any, Literal
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm
from agent.state import AgentDomain, AgentState, QueryType
from agent.nodes.input_guard import input_guard
from agent.nodes.intent_classifier import intent_classifier
from agent.nodes.query_rewriter import query_rewriter
from agent.nodes.synthesizer import synthesizer
from agent.nodes.planner import planner
from agent.nodes.clarification_handler import clarification_handler

from pydantic import BaseModel, Field
from evals.experiments.experiment_1.architecture_tools import ArchitectureToolExecutor, has_terminal_response
from evals.prompts.architecture_experiment import (
    DIRECT_ROUTER_SYSTEM_PROMPT,
    REACT_CONTROLLER_SYSTEM_PROMPT,
    build_direct_router_human_message,
    build_react_controller_human_message,
)
from core.utils import extract_json_from_llm

class DirectRouteAction(BaseModel):
    action: str = Field(..., pattern="^(sql|rag|catalog_lookup|chart_interpreter|clarification|synthesis_only)$")
    reason: str = ""

class ReactAction(BaseModel):
    action: str = Field(..., pattern="^(sql|rag|catalog_lookup|chart_interpreter|clarification|finish)$")
    reason: str = ""


def _heuristic_action(state: AgentState, allow_synthesis: bool = False) -> str:
    query = str(state.get("effective_query", state.get("raw_query", ""))).lower()
    if allow_synthesis and len(query.split()) <= 3 and state.get("conversation_summary"):
        return "synthesis_only"
    if state.get("chart_context") is not None:
        chart_terms = ["chart", "grafik", "plot", "visual", "tren", "trend", "anomali", "bar", "diagram"]
        if any(term in query for term in chart_terms):
            return "chart_interpreter"
    clarification_terms = ["yang mana", "apa itu", "ini", "itu", "tersebut", "mana"]
    if len(query.split()) <= 4 and any(term in query for term in clarification_terms):
        return "clarification"
    catalog_terms = ["pertanyaan", "kuesioner", "indikator", "dimensi", "kode pertanyaan", "item survei"]
    if any(term in query for term in catalog_terms):
        return "catalog_lookup"
    text_terms = ["komentar", "saran", "keluhan", "alasan", "narasi", "teks", "feedback", "sentimen", "ringkas"]
    if any(term in query for term in text_terms):
        return "rag"
    return "sql"


class ArchitectureGraphFactory:
    """Factory to build stateless LangGraph architectures around a specific executor."""

    def __init__(self, executor: ArchitectureToolExecutor, react_max_steps: int = 3):
        self.executor = executor
        self.react_max_steps = react_max_steps

    def _create_tool_nodes(self):
        async def tool_sql(state: AgentState): 
            new_state, _ = await self.executor.execute(state, "sql")
            return new_state

        async def tool_rag(state: AgentState): 
            new_state, _ = await self.executor.execute(state, "rag")
            return new_state

        async def tool_catalog_lookup(state: AgentState): 
            new_state, _ = await self.executor.execute(state, "catalog_lookup")
            return new_state

        async def tool_chart_interpreter(state: AgentState): 
            new_state, _ = await self.executor.execute(state, "chart_interpreter")
            return new_state

        async def tool_clarification(state: AgentState): 
            new_state, _ = await self.executor.execute(state, "clarification")
            return new_state
            
        return {
            "sql": tool_sql,
            "rag": tool_rag,
            "catalog_lookup": tool_catalog_lookup,
            "chart_interpreter": tool_chart_interpreter,
            "clarification_handler": tool_clarification,
        }

    def build_direct_graph(self) -> CompiledStateGraph:
        tools = self._create_tool_nodes()

        async def direct_router(state: AgentState):
            llm = get_llm("planning")
            messages = [
                SystemMessage(content=DIRECT_ROUTER_SYSTEM_PROMPT),
                HumanMessage(content=build_direct_router_human_message(
                    query=state.get("effective_query", state.get("raw_query", "")),
                    has_chart_context=state.get("chart_context") is not None,
                    conversation_summary=state.get("conversation_summary"),
                )),
            ]
            response = await llm.ainvoke(messages)
            try:
                action = DirectRouteAction(**extract_json_from_llm(str(response.content))).action
            except Exception:
                action = _heuristic_action(state, allow_synthesis=True)
            return {"next_step": action}

        def route_direct(state: AgentState) -> str:
            action = state.get("next_step", "synthesis_only")
            if action == "synthesis_only":
                return "synthesizer"
            if action == "clarification":
                return "clarification_handler"
            return action

        builder_direct = StateGraph(AgentState)
        builder_direct.add_node("input_guard", input_guard)
        builder_direct.add_node("intent_classifier", intent_classifier)
        builder_direct.add_node("query_rewriter", query_rewriter)
        builder_direct.add_node("direct_router", direct_router)
        builder_direct.add_node("sql", tools["sql"])
        builder_direct.add_node("rag", tools["rag"])
        builder_direct.add_node("catalog_lookup", tools["catalog_lookup"])
        builder_direct.add_node("chart_interpreter", tools["chart_interpreter"])
        builder_direct.add_node("clarification_handler", tools["clarification_handler"])
        builder_direct.add_node("synthesizer", synthesizer)

        builder_direct.set_entry_point("input_guard")
        builder_direct.add_edge("input_guard", "intent_classifier")
        builder_direct.add_conditional_edges(
            "intent_classifier",
            lambda state: "synthesizer" if state.get("abort_reason") or state.get("domain") == AgentDomain.OUT_OF_SCOPE else "query_rewriter"
        )
        builder_direct.add_edge("query_rewriter", "direct_router")
        builder_direct.add_conditional_edges("direct_router", route_direct)
        for tool in ["sql", "rag", "catalog_lookup", "chart_interpreter"]:
            builder_direct.add_edge(tool, "synthesizer")
        builder_direct.add_edge("clarification_handler", END)
        builder_direct.add_edge("synthesizer", END)
        return builder_direct.compile()

    def build_react_graph(self) -> CompiledStateGraph:
        tools = self._create_tool_nodes()
        react_max_steps = self.react_max_steps

        async def react_agent(state: AgentState):
            steps = state.get("steps_completed", [])
            step_number = len(steps) + 1
            if step_number > react_max_steps:
                return {"next_step": "finish"}
                
            llm = get_llm("planning")
            observations = [
                f"{step.step_number}. {step.action}: {step.observation}"
                for step in steps
            ]
            messages = [
                SystemMessage(content=REACT_CONTROLLER_SYSTEM_PROMPT),
                HumanMessage(content=build_react_controller_human_message(
                    query=state.get("effective_query", state.get("raw_query", "")),
                    has_chart_context=state.get("chart_context") is not None,
                    observations=observations,
                    step_number=step_number,
                    max_steps=react_max_steps,
                    conversation_summary=state.get("conversation_summary"),
                )),
            ]
            response = await llm.ainvoke(messages)
            try:
                action = ReactAction(**extract_json_from_llm(str(response.content))).action
            except Exception:
                action = "finish" if observations else _heuristic_action(state)
                
            if action == "finish" and not steps:
                action = _heuristic_action(state)
                
            return {"next_step": action}

        def route_react(state: AgentState) -> str:
            if has_terminal_response(state):
                return "synthesizer"
            action = state.get("next_step", "finish")
            if action == "finish":
                return "synthesizer"
            if action == "clarification":
                return "clarification_handler"
            return action

        builder_react = StateGraph(AgentState)
        builder_react.add_node("input_guard", input_guard)
        builder_react.add_node("intent_classifier", intent_classifier)
        builder_react.add_node("query_rewriter", query_rewriter)
        builder_react.add_node("react_agent", react_agent)
        builder_react.add_node("sql", tools["sql"])
        builder_react.add_node("rag", tools["rag"])
        builder_react.add_node("catalog_lookup", tools["catalog_lookup"])
        builder_react.add_node("chart_interpreter", tools["chart_interpreter"])
        builder_react.add_node("clarification_handler", tools["clarification_handler"])
        builder_react.add_node("synthesizer", synthesizer)

        builder_react.set_entry_point("input_guard")
        builder_react.add_edge("input_guard", "intent_classifier")
        builder_react.add_conditional_edges(
            "intent_classifier",
            lambda state: "synthesizer" if state.get("abort_reason") or state.get("domain") == AgentDomain.OUT_OF_SCOPE else "query_rewriter"
        )
        builder_react.add_edge("query_rewriter", "react_agent")
        builder_react.add_conditional_edges("react_agent", route_react)
        for tool in ["sql", "rag", "catalog_lookup", "chart_interpreter"]:
            builder_react.add_edge(tool, "react_agent")
        builder_react.add_edge("clarification_handler", END)
        builder_react.add_edge("synthesizer", END)
        return builder_react.compile()

    def build_plan_execute_graph(self) -> CompiledStateGraph:
        tools = self._create_tool_nodes()

        def plan_advancer(state: AgentState):
            current = state.get("current_step_index", 0)
            return {"current_step_index": current + 1}

        def route_plan_step(state: AgentState) -> str:
            if state.get("query_type") == QueryType.CLARIFICATION_NEEDED:
                return "clarification_handler"
            if has_terminal_response(state):
                return "synthesizer"
            plan = state.get("plan", [])
            idx = state.get("current_step_index", 0)
            if idx >= len(plan):
                return "synthesizer"
            step = plan[idx]
            tool = "catalog_lookup" if step.get("required") else step.get("tool", "sql")
            if tool == "clarification":
                return "clarification_handler"
            return tool

        builder_plan = StateGraph(AgentState)
        builder_plan.add_node("input_guard", input_guard)
        builder_plan.add_node("intent_classifier", intent_classifier)
        builder_plan.add_node("query_rewriter", query_rewriter)
        builder_plan.add_node("planner", planner)
        builder_plan.add_node("plan_advancer", plan_advancer)
        builder_plan.add_node("sql", tools["sql"])
        builder_plan.add_node("rag", tools["rag"])
        builder_plan.add_node("catalog_lookup", tools["catalog_lookup"])
        builder_plan.add_node("chart_interpreter", tools["chart_interpreter"])
        builder_plan.add_node("clarification_handler", tools["clarification_handler"])
        builder_plan.add_node("synthesizer", synthesizer)

        builder_plan.set_entry_point("input_guard")
        builder_plan.add_edge("input_guard", "intent_classifier")
        builder_plan.add_conditional_edges(
            "intent_classifier",
            lambda state: "synthesizer" if state.get("abort_reason") or state.get("domain") == AgentDomain.OUT_OF_SCOPE else "query_rewriter"
        )
        builder_plan.add_edge("query_rewriter", "planner")
        builder_plan.add_conditional_edges("planner", route_plan_step)
        for tool in ["sql", "rag", "catalog_lookup", "chart_interpreter"]:
            builder_plan.add_edge(tool, "plan_advancer")
        builder_plan.add_conditional_edges("plan_advancer", route_plan_step)
        builder_plan.add_edge("clarification_handler", END)
        builder_plan.add_edge("synthesizer", END)
        return builder_plan.compile()
