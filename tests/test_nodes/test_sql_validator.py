import pytest
from agent.state import AgentState, ValidationStatus
from agent.nodes.sql_validator import sql_validator

@pytest.mark.asyncio
async def test_sql_validator_blocks_destructive():
    state = AgentState(generated_sql="DROP TABLE mv_kelas;", attempt_count=0)
    result = await sql_validator(state)
    assert result["validation_status"] == ValidationStatus.FAIL
    assert "security_violation" in result["error_history"][0]["type"]

@pytest.mark.asyncio
async def test_sql_validator_allows_select():
    state = AgentState(generated_sql="SELECT * FROM mv_kelas LIMIT 10;")
    result = await sql_validator(state)
    assert result["validation_status"] == ValidationStatus.PASS
