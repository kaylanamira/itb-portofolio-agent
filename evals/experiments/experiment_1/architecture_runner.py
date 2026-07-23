from __future__ import annotations

from agent.orchestrator import main_graph
from agent.state import AgentDomain, AgentState, ChartContext
from evals.experiments.experiment_1.architecture_experiment import ArchitectureConfig, ArchitectureRunResult, normalize_sequence, timed_result
from evals.datasets.schemas import ArchitectureOrchestrationCase
from evals.experiments.experiment_1.architecture_tools import ArchitectureToolExecutor, response_payload
from evals.experiments.experiment_1.architecture_graphs import ArchitectureGraphFactory

class ArchitectureRunner:
    def __init__(self, make_state):
        self.make_state = make_state
        self.executor = ArchitectureToolExecutor()
        self.factory = ArchitectureGraphFactory(self.executor)
        self.direct_graph = self.factory.build_direct_graph()
        self.react_graph = self.factory.build_react_graph()
        self.plan_execute_graph = self.factory.build_plan_execute_graph()

    @timed_result
    async def run(self, config: ArchitectureConfig, case: ArchitectureOrchestrationCase) -> ArchitectureRunResult:
        try:
            state = self._initial_state(case)
            
            run_config = {
                "run_name": f"{config.name}_{case.query_type if case.query_type else 'unknown'}",
                "tags": ["experiment_1", config.name],
                "metadata": {
                    "case_id": case.id,
                    "complexity": case.orchestration_complexity
                }
            }
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if config == ArchitectureConfig.A1_DIRECT_TOOL:
                        result = await self.direct_graph.ainvoke(state, config=run_config)
                    elif config == ArchitectureConfig.A2_REACT_STYLE:
                        result = await self.react_graph.ainvoke(state, config=run_config)
                    elif config == ArchitectureConfig.A3_PLAN_EXECUTE:
                        result = await self.plan_execute_graph.ainvoke(state, config=run_config)
                    else:
                        result = await main_graph.ainvoke(state, config=run_config)
                    break
                except Exception as exc:
                    err_str = str(exc).lower()
                    if ("429" in err_str or "rate limit" in err_str) and attempt < max_retries - 1:
                        import asyncio
                        wait_time = 30 * (attempt + 1)
                        print(f"\n⚠️ Rate limit encountered. Sleeping {wait_time}s before retry {attempt + 1}/{max_retries}...", flush=True)
                        await asyncio.sleep(wait_time)
                    else:
                        raise exc

            return self._build_result(case, config, result, self._infer_nodes(result))
        except Exception as exc:
            return ArchitectureRunResult(
                case_id=case.id,
                config=config,
                query_type=case.query_type,
                orchestration_complexity=case.orchestration_complexity,
                error=str(exc),
            )

    def _initial_state(self, case: ArchitectureOrchestrationCase) -> AgentState:
        chart_context = case.input_context.chart_context
        valid_domains = {item.value for item in AgentDomain}
        return self.make_state(
            query=case.raw_query,
            messages=[message.model_dump() for message in case.input_context.conversation_history],
            chart_context=ChartContext.model_validate(chart_context) if chart_context else None,
            domain=AgentDomain(case.domain) if case.domain in valid_domains else None,
        )

    def _build_result(
        self,
        case: ArchitectureOrchestrationCase,
        config: ArchitectureConfig,
        state: AgentState,
        nodes: list[str],
    ) -> ArchitectureRunResult:
        response_type, narrative = response_payload(state)
        tools = self._tools_from_state(state, response_type)
        return ArchitectureRunResult(
            case_id=case.id,
            config=config,
            query_type=case.query_type,
            orchestration_complexity=case.orchestration_complexity,
            selected_tool_sequence=tools,
            selected_node_sequence=nodes,
            final_response_type=response_type,
            final_narrative=narrative,
            tool_call_count=len([tool for tool in tools if tool != "synthesis_only"]),
            faithfulness_score=self._faithfulness_score(state, narrative),
            completeness_score=self._completeness_score(case, narrative),
        )

    def _tools_from_state(self, state: AgentState, response_type: str | None) -> list[str]:
        if response_type == "clarification":
            return ["clarification"]
        steps = state.get("steps_completed", [])
        if not steps:
            return ["synthesis_only"] if response_type else []
        return normalize_sequence([step.action for step in steps])

    def _infer_nodes(self, state: AgentState) -> list[str]:
        nodes = ["input_guard", "intent_classifier", "query_rewriter", "planner"]
        for tool in self._tools_from_state(state, None):
            if tool == "sql":
                nodes.extend(["sql_pipeline", "step_reasoner"])
            elif tool == "rag":
                nodes.extend(["rag_retriever", "step_reasoner"])
            elif tool == "catalog_lookup":
                nodes.extend(["catalog_lookup", "step_reasoner"])
            elif tool == "chart_interpreter":
                nodes.append("chart_interpreter")
            elif tool == "clarification":
                nodes.append("clarification_handler")
        if state.get("formatted_response") and "clarification" not in self._tools_from_state(state, None):
            nodes.append("synthesizer")
        return nodes

    def _faithfulness_score(self, state: AgentState, narrative: str) -> float:
        if not narrative:
            return 0.0
        return 1.0 if state.get("steps_completed") else 0.0

    def _completeness_score(self, case: ArchitectureOrchestrationCase, narrative: str) -> float:
        criteria = case.scoring_rubric.completeness_criteria or case.expected_behavior.required_answer_facts
        if not criteria:
            return 1.0 if narrative else 0.0
        narrative_lower = narrative.lower()
        matched = sum(1 for item in criteria if item.lower() in narrative_lower)
        return round(matched / len(criteria), 4)
