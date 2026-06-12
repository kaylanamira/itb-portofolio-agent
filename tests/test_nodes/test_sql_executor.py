import pytest

from tests.conftest import load_cases
from core.sql_executor import PsycopgExecutor
from evals.datasets.schemas import SqlExecutorCase
from evals.scorer import NodeTestResult

CASES = load_cases("sql_executor_cases.json", SqlExecutorCase)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.asyncio
async def test_sql_executor_node(case: SqlExecutorCase, request, node_results):
    """Verify executor returns correct rows without error and handles empty results gracefully."""
    scope_fixture_name = f"scope_{case.scope_role.lower()}"
    scope = request.getfixturevalue(scope_fixture_name)
    executor = PsycopgExecutor()
    query_result = await executor.execute(case.sql, scope)

    correct_row_return = query_result.error is None
    is_empty_case = case.should_return_empty
    empty_result_handled = is_empty_case and query_result.rows == [] and query_result.error is None

    if correct_row_return:
        if case.expected_min_rows is not None:
            correct_row_return = len(query_result.rows) >= case.expected_min_rows
        if case.expected_max_rows is not None:
            correct_row_return = correct_row_return and len(query_result.rows) <= case.expected_max_rows

        if case.expected_columns:
            actual_columns = set(query_result.rows[0].keys()) if query_result.rows else set()
            for expected_col in case.expected_columns:
                if expected_col not in actual_columns:
                    correct_row_return = False

    node_results.append(NodeTestResult(
        case_id=case.id,
        node_name="sql_executor",
        passed=correct_row_return,
        expected_value={"min_rows": case.expected_min_rows, "columns": case.expected_columns},
        actual_value={"row_count": len(query_result.rows), "error": query_result.error},
        metric_flags={
            "correct_row_return": correct_row_return,
            "is_empty_case": is_empty_case,
            "empty_result_handled": empty_result_handled,
        },
    ))

    assert query_result.error is None, f"[{case.id}] executor error: {query_result.error}"
    assert isinstance(query_result.rows, list), f"[{case.id}] rows must be a list"

    if case.should_return_empty:
        assert query_result.rows == [], f"[{case.id}] expected empty result"
    else:
        if case.expected_min_rows is not None:
            assert len(query_result.rows) >= case.expected_min_rows, (
                f"[{case.id}] expected >= {case.expected_min_rows} rows, got {len(query_result.rows)}"
            )
        if case.expected_max_rows is not None:
            assert len(query_result.rows) <= case.expected_max_rows, (
                f"[{case.id}] expected <= {case.expected_max_rows} rows, got {len(query_result.rows)}"
            )

    if case.expected_columns and query_result.rows:
        actual_columns = set(query_result.rows[0].keys())
        for expected_col in case.expected_columns:
            assert expected_col in actual_columns, (
                f"[{case.id}] expected column '{expected_col}' not in result columns {actual_columns}"
            )
