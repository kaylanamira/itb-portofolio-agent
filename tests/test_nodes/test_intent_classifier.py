import pytest
from langchain_core.messages import HumanMessage, AIMessage

from tests.conftest import load_cases
from agent.nodes.intent_classifier import intent_classifier, route_after_intent
from agent.state import AgentDomain
from evals.datasets.schemas import IntentClassifierCase
from evals.scorer import NodeTestResult

ALL_CASES = load_cases("intent_classifier_cases.json", IntentClassifierCase)
OOS_CASES = [c for c in ALL_CASES if c.expected_domain == "out_of_scope"]
NON_OOS_CASES = [c for c in ALL_CASES if c.expected_domain != "out_of_scope"]


def test_intent_classifier_domain_routing(make_state):
    """Test pure routing logic without LLM calls."""
    state_portfolio = make_state()
    state_portfolio["domain"] = AgentDomain.PORTFOLIO
    assert route_after_intent(state_portfolio) == "portfolio_agent"

    state_wisudawan = make_state()
    state_wisudawan["domain"] = AgentDomain.WISUDAWAN
    assert route_after_intent(state_wisudawan) == "wisudawan_agent"

    state_oos = make_state()
    state_oos["domain"] = AgentDomain.OUT_OF_SCOPE
    assert route_after_intent(state_oos) == "out_of_scope"


@pytest.mark.parametrize("case", OOS_CASES)
@pytest.mark.asyncio
async def test_oos_queries_are_rejected(case: IntentClassifierCase, make_state, node_results):
    """Verify out-of-scope queries are classified as OUT_OF_SCOPE and set abort_reason."""
    state = make_state(query=case.query)
    result = await intent_classifier(state)

    actual_domain = result.get("domain")
    is_predicted_oos = actual_domain == AgentDomain.OUT_OF_SCOPE
    is_routing_correct = is_predicted_oos

    node_results.append(NodeTestResult(
        case_id=case.id,
        node_name="intent_classifier",
        passed=is_routing_correct,
        expected_value=case.expected_domain,
        actual_value=str(actual_domain),
        metric_flags={
            "is_routing_correct": is_routing_correct,
            "is_expected_oos": True,
            "is_predicted_oos": is_predicted_oos,
            "is_correctly_rejected": is_predicted_oos,
        },
    ))

    assert is_predicted_oos, f"[{case.id}] expected out_of_scope, got {actual_domain}"
    assert "abort_reason" in result, f"[{case.id}] OOS query must set abort_reason"
    assert isinstance(result["abort_reason"], str) and len(result["abort_reason"]) > 0


@pytest.mark.parametrize("case", NON_OOS_CASES)
@pytest.mark.asyncio
async def test_non_oos_queries_not_rejected(case: IntentClassifierCase, make_state, node_results):
    """Verify in-scope queries are routed to their domain without setting abort_reason."""
    if "clarification_needed" in case.tags:
        messages = [
            HumanMessage(content="Tampilkan nilai rata-rata IF1220 semester lalu."),
            AIMessage(content="Rata-rata nilainya adalah B."),
        ]
        state = make_state(query=case.query, messages=messages)
    else:
        state = make_state(query=case.query)

    result = await intent_classifier(state)

    actual_domain = result.get("domain")
    is_predicted_oos = actual_domain == AgentDomain.OUT_OF_SCOPE
    is_routing_correct = actual_domain is not None and actual_domain.value == case.expected_domain

    node_results.append(NodeTestResult(
        case_id=case.id,
        node_name="intent_classifier",
        passed=is_routing_correct,
        expected_value=case.expected_domain,
        actual_value=str(actual_domain),
        metric_flags={
            "is_routing_correct": is_routing_correct,
            "is_expected_oos": False,
            "is_predicted_oos": is_predicted_oos,
            "is_correctly_rejected": False,
        },
    ))

    assert is_routing_correct, f"[{case.id}] expected '{case.expected_domain}', got '{actual_domain}'"
    assert "abort_reason" not in result, f"[{case.id}] in-scope query must not set abort_reason"
