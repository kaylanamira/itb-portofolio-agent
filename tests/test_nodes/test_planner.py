import pytest
from tests.conftest import load_cases
from agent.nodes.planner import planner
from evals.config import valid_tools
from evals.datasets.schemas import PlannerCase
from evals.scorer import NodeTestResult

CASES = load_cases("planner_cases.json", PlannerCase)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.asyncio
async def test_planner_node(case: PlannerCase, make_state, node_results):
    """Verify planner query type, tool membership, and clarification routing."""
    state = make_state(query=case.query)
    result = await planner(state)

    assert "query_type" in result, f"[{case.id}] missing query_type"
    actual_query_type = result["query_type"].value

    plan = result.get("plan", [])
    assert isinstance(plan, list), f"[{case.id}] plan must be a list"

    tools = {step.get("tool") for step in plan}
    unknown_tools = tools - valid_tools()
    assert not unknown_tools, f"[{case.id}] unknown tool(s) in plan: {unknown_tools}"

    is_query_type_correct = actual_query_type == case.expected_query_type
    is_tools_correct = tools == set(case.expected_tools)
    is_correctly_flagged_clarify = case.should_clarify and (actual_query_type == "clarification_needed")

    node_results.append(NodeTestResult(
        case_id=case.id,
        node_name="planner",
        passed=is_query_type_correct and is_tools_correct,
        expected_value=case.expected_query_type,
        actual_value=actual_query_type,
        metric_flags={
            "is_query_type_correct": is_query_type_correct,
            "is_tools_correct": is_tools_correct,
            "is_expected_clarification": case.should_clarify,
            "is_correctly_flagged_clarify": is_correctly_flagged_clarify,
        },
    ))

    assert is_query_type_correct, (
        f"[{case.id}] expected query_type '{case.expected_query_type}', got '{actual_query_type}'"
    )
    assert 1 <= len(plan) <= case.expected_max_steps, (
        f"[{case.id}] plan has {len(plan)} steps, max allowed {case.expected_max_steps}"
    )
    assert is_tools_correct, (
        f"[{case.id}] expected tools {set(case.expected_tools)}, got {tools}"
    )

    if case.should_clarify:
        assert actual_query_type == "clarification_needed", f"[{case.id}] expected clarification_needed"
        assert "clarification" in tools, f"[{case.id}] clarification tool missing"

    if case.expected_query_type in ("text_lookup", "summarization"):
        assert "rag" in tools, f"[{case.id}] RAG query must include 'rag' tool"
        assert "sql" not in tools, f"[{case.id}] RAG query must not include 'sql' tool"

    if case.expected_query_type == "analytical_hybrid":
        assert "sql" in tools, f"[{case.id}] hybrid query must include 'sql'"
        assert "rag" in tools, f"[{case.id}] hybrid query must include 'rag'"