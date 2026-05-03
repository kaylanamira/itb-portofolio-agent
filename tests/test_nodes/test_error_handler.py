import pytest
from agent.state import AgentState, FormattedResponse
from agent.nodes.error_handler import error_handler
from core.config import settings

@pytest.mark.asyncio
async def test_error_handler_increments():
    state = AgentState(attempt_count=0, max_attempts=3)
    result = await error_handler(state)
    assert result["attempt_count"] == 1
    assert result.get("is_aborted") is None

@pytest.mark.asyncio
async def test_error_handler_aborts_on_max():
    state = AgentState(attempt_count=3, max_attempts=3)
    result = await error_handler(state)
    assert result["attempt_count"] == 4
    assert result["is_aborted"] is True
    assert result["formatted_response"].response_type == "error"
