import pytest
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from tests.conftest import load_cases
from agent.nodes.clarification_handler import clarification_handler
from evals.datasets.schemas import ClarificationHandlerCase
from evals.scorer import NodeTestResult
from evals.config import deepeval_include_reason, metric_threshold

try:
    from tests.llm_judge import custom_judge
    HAS_DEEPEVAL = True
except ImportError:
    HAS_DEEPEVAL = False

CASES = load_cases("clarification_handler_cases.json", ClarificationHandlerCase)


@pytest.mark.parametrize("case", CASES)
@pytest.mark.asyncio
async def test_clarification_handler_node(case: ClarificationHandlerCase, make_state, node_results):
    """Verify clarification response structure and confirm no SQL is produced."""
    state = make_state(query=case.query)
    result = await clarification_handler(state)

    response = result.get("formatted_response")
    format_compliant = (
        response is not None
        and response.response_type == "clarification"
        and isinstance(response.clarification_question, str)
        and len(response.clarification_question.strip()) > 0
    )
    no_sql_produced = result.get("generated_sql") is None

    is_relevant = True
    if HAS_DEEPEVAL and format_compliant:
        relevance_threshold = metric_threshold("clarification_handler", "clarification_relevance")
        test_case = LLMTestCase(
            input=case.query,
            actual_output=response.clarification_question,
        )
        metric = GEval(
            name="Clarification Relevance",
            criteria="Determine whether the actual output is a helpful and relevant clarification question asking for missing context from the input.",
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            threshold=relevance_threshold,
            model=custom_judge
        )
        try:
            assert_test(test_case, metrics=[metric])
        except AssertionError:
            is_relevant = False
    elif not HAS_DEEPEVAL:
        is_relevant = False

    node_results.append(NodeTestResult(
        case_id=case.id,
        node_name="clarification_handler",
        passed=format_compliant and no_sql_produced and (not HAS_DEEPEVAL or is_relevant),
        metric_flags={
            "format_compliant": format_compliant,
            "no_sql_produced": no_sql_produced,
            "clarification_relevance": is_relevant,
        },
    ))

    assert format_compliant, (
        f"[{case.id}] expected response_type='clarification' with a non-empty clarification_question, "
        f"got type={getattr(response, 'response_type', None)}"
    )
    assert no_sql_produced, f"[{case.id}] clarification_handler must not produce generated_sql"
    if HAS_DEEPEVAL:
        assert is_relevant, f"[{case.id}] Clarification relevancy failed."