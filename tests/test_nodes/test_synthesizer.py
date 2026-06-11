import os
import pytest

from tests.conftest import load_cases
from agent.nodes.synthesizer import synthesizer
from agent.state import StepResult, FormattedResponse
from evals.config import deepeval_include_reason, metric_threshold
from evals.datasets.schemas import SynthesizerCase
from evals.scorer import NodeTestResult, MetricFlag

try:
    from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric, ToxicityMetric
    from deepeval.test_case import LLMTestCase
    from tests.llm_judge import custom_judge
    HAS_DEEPEVAL = True
except ImportError:
    HAS_DEEPEVAL = False

CASES = load_cases("synthesizer_cases.json", SynthesizerCase)
VALID_RESPONSE_TYPES = {"text", "mixed", "error", "clarification"}


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
@pytest.mark.asyncio
async def test_synthesizer_node(case: SynthesizerCase, make_state, scope_kaprodi, node_results):
    """Verify response structure, type routing, and quality metrics."""
    steps = [StepResult(**s) for s in case.steps_completed]
    state = make_state(query=case.query, scope=scope_kaprodi, steps_completed=steps)

    if case.is_aborted:
        state["is_aborted"] = True
        state["abort_reason"] = case.abort_reason or "Aborted"

    result = await synthesizer(state)
    response: FormattedResponse = result["formatted_response"]
    narrative = response.narrative

    format_compliant = (
        response.response_type in VALID_RESPONSE_TYPES
        and isinstance(narrative, str)
        and len(narrative) > 0
        and "{" not in narrative
    )
    abort_path_correct = (not case.is_aborted) or (response.response_type == "error")
    is_chart_case = case.has_chart
    chart_artifact_valid = True
    if is_chart_case:
        chart_artifact_valid = (
            hasattr(response, "artifact_type")
            and hasattr(response, "chart_type")
            and hasattr(response, "chart_spec")
        )

    metric_flags = {
        MetricFlag.FORMAT_COMPLIANT: format_compliant,
        MetricFlag.ABORT_PATH_CORRECT: abort_path_correct,
        MetricFlag.IS_CHART_CASE: is_chart_case,
        MetricFlag.CHART_ARTIFACT_VALID: chart_artifact_valid,
    }

    assert format_compliant, f"[{case.id}] format not compliant: type={response.response_type}, narrative={narrative!r}"
    assert abort_path_correct, f"[{case.id}] abort path: expected response_type='error', got '{response.response_type}'"

    if not case.is_aborted and HAS_DEEPEVAL and os.getenv("RUN_LLM_EVALS") == "1":
        relevance_threshold = metric_threshold("synthesizer", "answer_relevance")
        faithfulness_threshold = metric_threshold("synthesizer", "faithfulness")
        toxicity_threshold = metric_threshold("synthesizer", "toxicity_bias")

        test_case = LLMTestCase(input=case.query, actual_output=narrative)

        relevance = AnswerRelevancyMetric(threshold=relevance_threshold, model=custom_judge, include_reason=deepeval_include_reason())
        relevance.measure(test_case)
        metric_flags[MetricFlag.SYNTH_ANSWER_RELEVANCE_PASSED] = relevance.score >= relevance_threshold
        assert relevance.score >= relevance_threshold, f"[{case.id}] AnswerRelevance={relevance.score}: {relevance.reason}"

        if steps:
            context = [step.observation for step in steps if step.observation]
            if context:
                faith_case = LLMTestCase(input=case.query, actual_output=narrative, retrieval_context=context)
                faithfulness = FaithfulnessMetric(threshold=faithfulness_threshold, model=custom_judge, include_reason=deepeval_include_reason())
                faithfulness.measure(faith_case)
                metric_flags[MetricFlag.SYNTH_FAITHFULNESS_PASSED] = faithfulness.score >= faithfulness_threshold
                assert faithfulness.score >= faithfulness_threshold, f"[{case.id}] Faithfulness={faithfulness.score}: {faithfulness.reason}"

        toxicity = ToxicityMetric(threshold=toxicity_threshold, model=custom_judge, include_reason=deepeval_include_reason())
        toxicity.measure(LLMTestCase(input=case.query, actual_output=narrative))
        metric_flags[MetricFlag.SYNTH_TOXICITY_PASSED] = toxicity.score <= toxicity_threshold
        assert toxicity.score <= toxicity_threshold, f"[{case.id}] ToxicityScore={toxicity.score}: {toxicity.reason}"

    node_results.append(NodeTestResult(
        case_id=case.id,
        node_name="synthesizer",
        passed=format_compliant and abort_path_correct,
        expected_value=case.expected_response_type,
        actual_value=response.response_type,
        metric_flags=metric_flags,
    ))
