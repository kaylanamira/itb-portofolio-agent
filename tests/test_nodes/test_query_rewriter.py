import re
import pytest
from langchain_core.messages import HumanMessage, AIMessage

from tests.conftest import load_cases
from agent.nodes.query_rewriter import should_rewrite, query_rewriter
from evals.datasets.schemas import QueryRewriterCase
from evals.scorer import NodeTestResult
import os
from evals.config import metric_threshold

try:
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams
    from tests.llm_judge import custom_judge
    HAS_DEEPEVAL = True
except ImportError:
    HAS_DEEPEVAL = False

ANAPHORIC_PATTERN = re.compile(
    r'\b(itu|ini|tersebut|dia|mereka|nya|tadi|barusan|sebelumnya)\b', re.IGNORECASE
)

CASES = load_cases("query_rewriter_cases.json", QueryRewriterCase)


@pytest.mark.parametrize("case", CASES)
def test_should_rewrite_heuristic(case: QueryRewriterCase):
    """Verify the deterministic heuristic without LLM calls."""
    actual = should_rewrite(case.query, case.history)
    assert actual == case.expected_should_rewrite, (
        f"[{case.id}] expected should_rewrite={case.expected_should_rewrite}, got {actual}"
    )


@pytest.mark.parametrize("case", CASES)
@pytest.mark.asyncio
async def test_query_rewriter_node(case: QueryRewriterCase, make_state, node_results):
    """Verify rewriter output self-containment and trigger accuracy."""
    messages = []
    for i, content in enumerate(case.history_messages):
        messages.append(HumanMessage(content=content) if i % 2 == 0 else AIMessage(content=content))

    state = make_state(query=case.query, messages=messages)
    result = await query_rewriter(state)

    rewritten = result.get("effective_query", "")
    trigger_correct = (result.get("rewritten_query") is not None) == case.expected_should_rewrite

    node_results.append(NodeTestResult(
        case_id=case.id,
        node_name="query_rewriter",
        passed=trigger_correct,
        expected_value=case.expected_should_rewrite,
        actual_value=result.get("rewritten_query") is not None,
        metric_flags={"rewrite_trigger_correct": trigger_correct},
    ))

    if case.expected_should_rewrite:
        assert result.get("rewritten_query") is not None, f"[{case.id}] expected rewritten_query to be set"
        assert not ANAPHORIC_PATTERN.search(rewritten), (
            f"[{case.id}] rewritten query still contains anaphoric pronoun: '{rewritten}'"
        )
    else:
        assert result.get("effective_query") == case.query, f"[{case.id}] query should be unchanged"
        assert result.get("rewritten_query") is None, f"[{case.id}] rewritten_query must be None"


@pytest.mark.parametrize("case", [c for c in CASES if c.expected_should_rewrite])
@pytest.mark.asyncio
async def test_query_rewriter_deepeval_metrics(case: QueryRewriterCase, make_state, node_results):
    """Verify semantic preservation and completeness of the rewritten query."""
    if not HAS_DEEPEVAL or os.getenv("RUN_LLM_EVALS") != "1":
        pytest.skip("Set RUN_LLM_EVALS=1 to run LLM judge metrics")

    messages = []
    for i, content in enumerate(case.history_messages):
        messages.append(HumanMessage(content=content) if i % 2 == 0 else AIMessage(content=content))

    state = make_state(query=case.query, messages=messages)
    result = await query_rewriter(state)
    rewritten = result.get("effective_query", "")

    if not rewritten or rewritten == case.query:
        pytest.fail(f"[{case.id}] Failed to rewrite query when it was expected to rewrite.")

    preservation_threshold = metric_threshold("query_rewriter", "semantic_preservation")
    completeness_threshold = metric_threshold("query_rewriter", "rewrite_completeness")

    # Metric 1: Semantic Preservation
    context = case.history_messages
    if context:
        test_case_preservation = LLMTestCase(
            input=case.query,
            actual_output=rewritten,
            retrieval_context=context
        )
        eval_params = [LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.RETRIEVAL_CONTEXT]
    else:
        test_case_preservation = LLMTestCase(
            input=case.query,
            actual_output=rewritten
        )
        eval_params = [LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT]

    preservation_metric = GEval(
        name="Rewrite Semantic Preservation",
        evaluation_steps=[
            "Check if the rewritten query preserves the core meaning and intent of the original query.",
            "Ensure no critical constraints, filters, or subjects are lost.",
            "If the rewritten query adds specific subjects or identifiers not present in the input, verify they are correctly resolved from the retrieval context.",
            "Do NOT penalize the rewritten query for omitting implicit references (such as user ask for same reasoning pattern) if the core intent is still clear.",
            "Ensure the rewritten query asks for the same fundamental data as the original query."
        ],
        evaluation_params=eval_params,
        model=custom_judge,
        threshold=preservation_threshold
    )
    preservation_metric.measure(test_case_preservation)
    preservation_passed = preservation_metric.score >= preservation_threshold

    # Metric 2: Rewrite Completeness
    if context:
        test_case_completeness = LLMTestCase(
            input=case.query,
            actual_output=rewritten,
            retrieval_context=context
        )
        completeness_metric = GEval(
            name="Rewrite Completeness",
            evaluation_steps=[
                "Check if the rewritten query is fully self-contained and requires no external context to be understood.",
                "Ensure any pronouns or temporal references from the original query have been resolved using the context.",
                "Ensure no ambiguous references remain in the rewritten query."
            ],
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.RETRIEVAL_CONTEXT],
            model=custom_judge,
            threshold=completeness_threshold
        )
        completeness_metric.measure(test_case_completeness)
        completeness_passed = completeness_metric.score >= completeness_threshold
    else:
        completeness_passed = True

    node_results.append(NodeTestResult(
        case_id=case.id,
        node_name="query_rewriter",
        passed=preservation_passed and completeness_passed,
        metric_flags={
            "semantic_preservation_passed": preservation_passed,
            "rewrite_completeness_passed": completeness_passed,
        }
    ))

    assert preservation_passed, f"[{case.id}] SemanticPreservation={preservation_metric.score}: {preservation_metric.reason}"
    if context:
        assert completeness_passed, f"[{case.id}] RewriteCompleteness={completeness_metric.score}: {completeness_metric.reason}"

