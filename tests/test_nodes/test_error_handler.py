import pytest
from tests.conftest import load_cases
from agent.tools.sql.state import SQLState
from evals.datasets.schemas import ErrorHandlerCase
from evals.scorer import NodeTestResult, MetricFlag
from agent.tools.sql.pipeline import build_sql_pipeline

CASES = load_cases("error_handler_cases.json", ErrorHandlerCase)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.asyncio
async def test_error_handler_node(case: ErrorHandlerCase, node_results):
    state = SQLState(
        question="test query",
        user_scope=None,
        plan_step_context={"task": "test", "tool": "sql"},
        attempt_count=case.attempt_count,
        error_history=[{"type": case.error_message, "message": case.error_message}],
        generated_sql="SELECT 1",
        sql_result=[{"test": 1}],
        sql_error=case.error_message if "execution" in case.error_message else None,
    )

    from unittest.mock import MagicMock, AsyncMock
    test_pipeline = build_sql_pipeline(
        schema_linker_prompt="mock",
        entity_resolver=AsyncMock(return_value=None),
        few_shot_examples=lambda _: "",
        schema_context="mock schema",
        default_table="mv_kelas",
        executor=MagicMock(),
        max_attempts=case.max_attempts,
    )
    result = await test_pipeline.nodes["error_handler"].ainvoke(state)

    new_attempt_count = result.get("attempt_count")
    is_aborted = result.get("is_aborted", False)
    abort_reason = result.get("abort_reason")
    
    abort_triggered_correctly = (
        (case.expected_abort and is_aborted and abort_reason == "MAX_RETRIES_EXCEEDED") or
        (not case.expected_abort and not is_aborted)
    )
    
    no_premature_abort = not is_aborted if new_attempt_count < case.max_attempts else True
    
    state_reset_correct = (
        result.get("generated_sql") is None and
        result.get("sql_result") is None and
        result.get("sql_error") is None
    ) if not is_aborted else True
    
    state_with_result = {**state, **result}
    
    from langgraph.graph import END
    def route_after_error_handler(state: SQLState) -> str:
        if state.get("is_aborted", False) or state.get("attempt_count", 0) >= case.max_attempts:
            return END
        return "sql_generator"

    expected_route = route_after_error_handler(state_with_result)
    expected_route_normalized = "END" if expected_route == END else expected_route
    router_correctness = expected_route_normalized == case.expected_route

    node_results.append(NodeTestResult(
        case_id=case.id,
        node_name="error_handler",
        passed=abort_triggered_correctly and no_premature_abort and state_reset_correct and router_correctness,
        expected_value=case.expected_abort,
        actual_value=is_aborted,
        metric_flags={
            MetricFlag.ABORT_TRIGGERED_CORRECTLY: abort_triggered_correctly,
            MetricFlag.NO_PREMATURE_ABORT: no_premature_abort,
            MetricFlag.STATE_RESET_CORRECT: state_reset_correct,
            MetricFlag.ROUTER_CORRECTNESS: router_correctness,
        },
    ))

    assert new_attempt_count == case.attempt_count + 1, (
        f"[{case.id}] attempt_count should increment by 1"
    )

    if case.expected_abort:
        assert is_aborted is True, f"[{case.id}] should abort when attempt_count >= max_attempts"
        assert abort_reason == "MAX_RETRIES_EXCEEDED", f"[{case.id}] abort_reason should be MAX_RETRIES_EXCEEDED"
    else:
        assert is_aborted is False, f"[{case.id}] should not abort prematurely"
        assert result.get("generated_sql") is None, f"[{case.id}] generated_sql should be cleared"
        assert result.get("sql_result") is None, f"[{case.id}] sql_result should be cleared"
        assert result.get("sql_error") is None, f"[{case.id}] sql_error should be cleared"

    assert router_correctness, (
        f"[{case.id}] router returned '{expected_route_normalized}', expected '{case.expected_route}'"
    )
