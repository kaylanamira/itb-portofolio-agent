import pytest
from tests.conftest import load_cases
from agent.nodes.input_guard import input_guard, route_after_input_guard
from evals.datasets.schemas import InputGuardCase
from evals.scorer import NodeTestResult

CASES = load_cases("input_guard_cases.json", InputGuardCase)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.asyncio
async def test_input_guard_classification(case: InputGuardCase, make_state, node_results):
    state = make_state(query=case.query)
    result = await input_guard(state)

    actual_blocked = result.get("is_aborted", False) is True
    is_correctly_classified = actual_blocked == case.expected_blocked

    node_results.append(NodeTestResult(
        case_id=case.id,
        node_name="input_guard",
        passed=is_correctly_classified,
        expected_value=case.expected_blocked,
        actual_value=actual_blocked,
        metric_flags={
            "is_expected_blocked": case.expected_blocked,
            "is_blocked": actual_blocked,
        },
    ))

    if case.expected_blocked:
        assert actual_blocked, f"[{case.id}] expected blocked=True, got False"
        assert result.get("abort_reason") is not None, f"[{case.id}] blocked query must set abort_reason"
    else:
        assert not actual_blocked, f"[{case.id}] expected blocked=False, got True"


def test_router_blocked_goes_to_out_of_scope(make_state):
    state = make_state()
    state["is_aborted"] = True
    assert route_after_input_guard(state) == "out_of_scope"


def test_router_safe_goes_to_intent_classifier(make_state):
    state = make_state()
    state["is_aborted"] = False
    assert route_after_input_guard(state) == "intent_classifier"
