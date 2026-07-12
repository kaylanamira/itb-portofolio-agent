import os
import pytest
import json

from tests.conftest import load_cases
from evals.datasets.schemas import ChartInterpreterCase
from evals.scorer import NodeTestResult
from evals.config import metric_threshold
from agent.nodes.chart_interpreter import chart_interpreter
from agent.state import ChartContext, ChartFilters, QuestionReference

try:
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams
    from tests.llm_judge import custom_judge
    HAS_DEEPEVAL = True
except ImportError:
    HAS_DEEPEVAL = False

CASES = load_cases("chart_interpreter_cases.json", ChartInterpreterCase)


def _build_chart_context(raw_context: dict) -> ChartContext:
    filters = raw_context.get("filters_applied", {})
    chart_filters = ChartFilters(**filters)
    
    qr_raw = raw_context.get("question_reference", {})
    qr = None
    if qr_raw:
        qr = {k: QuestionReference(**v) for k, v in qr_raw.items()}
        
    return ChartContext(
        chart_type=raw_context.get("chart_type", "entity_comparison_bar_chart"),
        title=raw_context.get("title", ""),
        x_axis_label=raw_context.get("x_axis_label"),
        y_axis_label=raw_context.get("y_axis_label"),
        series=raw_context.get("series", []),
        filters_applied=chart_filters,
        hint=raw_context.get("hint", []),
        jumlah_kelas_aktif=raw_context.get("jumlah_kelas_aktif"),
        question_reference=qr
    )


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
@pytest.mark.asyncio
async def test_chart_interpreter_node(case: ChartInterpreterCase, make_state, scope_kaprodi, node_results):
    chart_context = _build_chart_context(case.chart_context)
    state = make_state(query=case.query, scope=scope_kaprodi, chart_context=chart_context)
    result = await chart_interpreter(state)

    completed = result.get("steps_completed", [])
    step_recorded = len(completed) == 1
    analysis_exists = False
    observation = ""
    if step_recorded:
        step_result = completed[0]
        analysis = step_result.result.get("analysis", {})
        analysis_exists = bool(analysis)
        observation = analysis.get("analysis_summary", "")

    is_faithful = True
    is_relevant = True
    is_complete = True

    if analysis_exists and HAS_DEEPEVAL and os.getenv("RUN_LLM_EVALS") == "1":
        retrieval_context = f"Chart Context: {json.dumps(case.chart_context, ensure_ascii=False)}"
        faithfulness_threshold = metric_threshold("chart_interpreter", "faithfulness")
        relevance_threshold = metric_threshold("chart_interpreter", "answer_relevance")

        test_case = LLMTestCase(
            input=case.query,
            actual_output=observation,
            expected_output=", ".join(case.expected_facts) if case.expected_facts else None,
            retrieval_context=[retrieval_context],
        )
        
        faithfulness_metric = GEval(
            name="Faithfulness",
            criteria="Interpretation must be grounded in the chart_context without hallucinating numbers (like adding percentages incorrectly).",
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.RETRIEVAL_CONTEXT],
            model=custom_judge,
            threshold=faithfulness_threshold,
        )
        
        relevance_metric = GEval(
            name="Answer Relevance",
            criteria="Interpretation must answer the original user query and adhere to hints.",
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.RETRIEVAL_CONTEXT],
            model=custom_judge,
            threshold=relevance_threshold,
        )
        
        if case.expected_facts:
            completeness_threshold = metric_threshold("chart_interpreter", "observation_completeness")
            completeness_metric = GEval(
                name="Observation Completeness",
                criteria="The actual output (observation) MUST contain the semantic meaning of EVERY key fact listed in the expected output. It is completely acceptable and expected for the actual output to contain extra context, words, or formatting. Do NOT penalize extra information. Your only goal is to verify if all the facts in the expected output are present in the actual output.",
                evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
                model=custom_judge,
                threshold=completeness_threshold,
            )
            try:
                await completeness_metric.a_measure(test_case)
                is_complete = completeness_metric.score >= completeness_threshold
            except Exception as e:
                print(f"Completeness error: {e}")
                is_complete = False

        try:
            await faithfulness_metric.a_measure(test_case)
            is_faithful = faithfulness_metric.score >= faithfulness_threshold
        except Exception as e:
            print(f"Faithfulness error: {e}")
            is_faithful = False
            
        try:
            await relevance_metric.a_measure(test_case)
            is_relevant = relevance_metric.score >= relevance_threshold
        except Exception as e:
            print(f"Relevance error: {e}")
            is_relevant = False

    passed = step_recorded and analysis_exists
    if HAS_DEEPEVAL and os.getenv("RUN_LLM_EVALS") == "1":
        passed = passed and is_faithful and is_relevant and is_complete

    node_results.append(NodeTestResult(
        case_id=case.id,
        node_name="chart_interpreter",
        passed=passed,
        metric_flags={
            "step_recorded": step_recorded,
            "analysis_exists": analysis_exists,
            "step_faithfulness": is_faithful,
            "step_answer_relevance": is_relevant,
            "step_observation_completeness": is_complete,
        },
    ))

    if step_recorded:
        print(f"\n[DEBUG] Case ID: {case.id}")
        print(f"  Task: {case.query}")
        print(f"  Agent Observation: {observation}")
        if case.expected_facts:
            print(f"  Expected Facts: {case.expected_facts}")
        if HAS_DEEPEVAL and os.getenv("RUN_LLM_EVALS") == "1":
            faithfulness_score = faithfulness_metric.score if hasattr(faithfulness_metric, 'score') else 'N/A'
            relevance_score = relevance_metric.score if hasattr(relevance_metric, 'score') else 'N/A'
            print(f"  DeepEval Faithfulness Score: {faithfulness_score} (threshold={faithfulness_threshold})")
            if not is_faithful:
                print(f"    Reason: {getattr(faithfulness_metric, 'reason', 'N/A')}")
            print(f"  DeepEval Relevance Score: {relevance_score} (threshold={relevance_threshold})")
            if not is_relevant:
                print(f"    Reason: {getattr(relevance_metric, 'reason', 'N/A')}")
            if case.expected_facts:
                completeness_score = completeness_metric.score if hasattr(completeness_metric, 'score') else 'N/A'
                print(f"  DeepEval Completeness Score: {completeness_score} (threshold={completeness_threshold})")
                if not is_complete:
                    print(f"    Reason: {getattr(completeness_metric, 'reason', 'N/A')}")

    assert step_recorded, f"[{case.id}] step not recorded correctly"
    assert analysis_exists, f"[{case.id}] analysis missing"

    if HAS_DEEPEVAL and os.getenv("RUN_LLM_EVALS") == "1":
        assert is_faithful, f"[{case.id}] Faithfulness failed: {getattr(faithfulness_metric, 'reason', 'N/A')}"
        assert is_relevant, f"[{case.id}] Answer Relevance failed: {getattr(relevance_metric, 'reason', 'N/A')}"
        if case.expected_facts:
            assert is_complete, f"[{case.id}] Observation Completeness failed: {getattr(completeness_metric, 'reason', 'N/A')}"
