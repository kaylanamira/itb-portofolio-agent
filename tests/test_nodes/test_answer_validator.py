import pytest
from unittest.mock import AsyncMock, MagicMock

from tests.conftest import load_cases
from agent.tools.sql.tool import SQLTool
from agent.tools.security import check_sql_security
from evals.datasets.schemas import AnswerValidatorCase
from evals.scorer import NodeTestResult

CASES = load_cases("answer_validator_cases.json", AnswerValidatorCase)

_SHARED_TOOL = SQLTool(
    schema_linker_prompt="mock",
    entity_resolver=AsyncMock(return_value=None),
    few_shot_examples=lambda _: "",
    schema_context="mock schema",
    default_table="mv_kelas",
    executor=MagicMock(),
    max_attempts=3,
)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
@pytest.mark.asyncio
async def test_answer_validator_validity(case: AnswerValidatorCase, node_results):
    """Verify answer_validator correctly judges validity for each labeled case."""
    result = await _SHARED_TOOL.validate_answer(
        question=case.question,
        generated_sql=case.generated_sql,
        sql_result=case.sql_result,
        sql_row_count=case.sql_row_count,
        plan_step_context={"task": case.question},
    )

    actual_valid = result.get("answer_is_valid")
    is_expected_valid = case.expected_valid
    is_predicted_valid = actual_valid is True
    is_validity_correct = actual_valid == case.expected_valid

    node_results.append(NodeTestResult(
        case_id=case.id,
        node_name="answer_validator",
        passed=is_validity_correct,
        expected_value=case.expected_valid,
        actual_value=actual_valid,
        metric_flags={
            "is_expected_valid": is_expected_valid,
            "is_predicted_valid": is_predicted_valid,
            "is_validity_correct": is_validity_correct,
        },
    ))

    assert actual_valid == case.expected_valid, (
        f"[{case.id}] expected answer_is_valid={case.expected_valid}, "
        f"got {actual_valid}, reason: {result.get('reason')}"
    )


@pytest.mark.asyncio
async def test_answer_validator_returns_reason():
    result = await _SHARED_TOOL.validate_answer(
        question="Berapa nilai A di IF1220?",
        generated_sql="SELECT dist_jumlah_a FROM analitik.mv_kelas WHERE kode_mk = 'IF1220'",
        sql_result=[{"dist_jumlah_a": 26}],
        sql_row_count=1,
    )
    assert "reason" in result
    assert isinstance(result["reason"], str) and len(result["reason"]) > 0


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_answer_validator_case_sql_passes_security(case: AnswerValidatorCase):
    ok, err = check_sql_security(case.generated_sql)
    assert ok, f"[{case.id}] test case SQL fails security check: {err}"
