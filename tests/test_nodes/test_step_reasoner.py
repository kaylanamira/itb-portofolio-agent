import os
import pytest

from tests.conftest import load_cases
from agent.state import ValidationStatus
from evals.datasets.schemas import StepReasonerCase
from evals.scorer import NodeTestResult
from evals.config import metric_threshold
from agent.nodes.step_reasoner import step_reasoner

try:
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams
    from tests.llm_judge import custom_judge
    HAS_DEEPEVAL = True
except ImportError:
    HAS_DEEPEVAL = False

CASES = load_cases("step_reasoner_cases.json", StepReasonerCase)


def _build_state_kwargs(case: StepReasonerCase) -> dict:
    plan = case.plan or [{"task": case.task, "tool": case.action}]
    kwargs = {
        "plan": plan,
        "current_step_index": case.current_step_index,
    }
    if case.generated_sql is not None:
        kwargs["generated_sql"] = case.generated_sql
    if case.sql_result is not None:
        kwargs["sql_result"] = case.sql_result
    if case.rag_chunks is not None:
        kwargs["rag_chunks"] = case.rag_chunks
    if case.rag_query is not None:
        kwargs["rag_query"] = case.rag_query
    return kwargs


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
@pytest.mark.asyncio
async def test_step_reasoner_node(case: StepReasonerCase, make_state, scope_kaprodi, node_results):
    """Verify structural correctness: step is recorded, scratch state cleared, index advanced."""
    state = make_state(query=case.query, scope=scope_kaprodi, **_build_state_kwargs(case))
    result = await step_reasoner(state)

    completed = result.get("steps_completed", [])
    step_recorded = len(completed) == 1 and completed[0].step_number == case.current_step_index + 1
    scratch_state_cleared = (
        result.get("generated_sql") is None
        and result.get("sql_result") is None
        and result.get("validation_status") == ValidationStatus.PENDING
    )
    plan = state["plan"]
    expected_valid_indices = {case.current_step_index + 1, len(plan)}
    index_advanced = result.get("current_step_index") in expected_valid_indices

    is_faithful = True
    is_relevant = True
    is_complete = True

    if completed and HAS_DEEPEVAL and os.getenv("RUN_LLM_EVALS") == "1" and case.action != "unknown":
        observation = completed[0].observation
        retrieval_context = f"Task Context: {case.task}\nExecution Result: {case.sql_result or case.rag_chunks}"
        faithfulness_threshold = metric_threshold("step_reasoner", "faithfulness")
        relevance_threshold = metric_threshold("step_reasoner", "answer_relevance")

        test_case = LLMTestCase(
            input=case.task,
            actual_output=observation,
            expected_output=", ".join(case.expected_facts) if case.expected_facts else None,
            retrieval_context=[retrieval_context],
        )
        
        faithfulness_metric = GEval(
            name="Faithfulness",
            criteria="Observation is grounded from the raw SQL/RAG step results without inventing new numbers, themes, or entities; no hallucination.",
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.RETRIEVAL_CONTEXT],
            model=custom_judge,
            threshold=faithfulness_threshold,
        )
        
        relevance_metric = GEval(
            name="Answer Relevance",
            criteria="Observation addresses the step task, not an unrelated topic.",
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            model=custom_judge,
            threshold=relevance_threshold,
        )
        
        if case.expected_facts:
            completeness_threshold = metric_threshold("step_reasoner", "observation_completeness")
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

    passed = step_recorded and scratch_state_cleared and index_advanced
    if HAS_DEEPEVAL and os.getenv("RUN_LLM_EVALS") == "1" and case.action != "unknown":
        passed = passed and is_faithful and is_relevant and is_complete

    node_results.append(NodeTestResult(
        case_id=case.id,
        node_name="step_reasoner",
        passed=passed,
        metric_flags={
            "step_recorded": step_recorded,
            "scratch_state_cleared": scratch_state_cleared,
            "index_advanced": index_advanced,
            "step_faithfulness": is_faithful,
            "step_answer_relevance": is_relevant,
            "step_observation_completeness": is_complete,
        },
    ))

    if completed:
        observation = completed[0].observation
        print(f"\n[DEBUG] Case ID: {case.id}")
        print(f"  Task: {case.task}")
        print(f"  Execution Result: {case.sql_result or case.rag_chunks}")
        print(f"  Agent Observation: {observation}")
        if case.expected_facts:
            print(f"  Expected Facts: {case.expected_facts}")
        if HAS_DEEPEVAL and os.getenv("RUN_LLM_EVALS") == "1" and case.action != "unknown":
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
    assert scratch_state_cleared, f"[{case.id}] scratch state not cleared"
    assert index_advanced, f"[{case.id}] current_step_index={result.get('current_step_index')} not a valid advancement"

    if completed:
        assert completed[0].action == case.action, f"[{case.id}] action mismatch"
        if case.action == "sql":
            assert completed[0].result == case.sql_result
            assert completed[0].query == (case.generated_sql or "N/A")
        elif case.action == "rag":
            assert completed[0].result == case.rag_chunks
            assert completed[0].query == (case.rag_query or "N/A")
            
    if completed and HAS_DEEPEVAL and os.getenv("RUN_LLM_EVALS") == "1" and case.action != "unknown":
        assert is_faithful, f"[{case.id}] Faithfulness failed: {getattr(faithfulness_metric, 'reason', 'N/A')}"
        assert is_relevant, f"[{case.id}] Answer Relevance failed: {getattr(relevance_metric, 'reason', 'N/A')}"
        assert is_complete, f"[{case.id}] Observation Completeness failed"
