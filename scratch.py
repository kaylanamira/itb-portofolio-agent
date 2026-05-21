import asyncio
from agent.orchestrator import main_graph
from agent.state import AgentState
from core.scope import UserScope, UserRole
import uuid

async def test():
    state = AgentState(
        user_scope=UserScope(user_id=uuid.uuid4(), role=UserRole.KAPRODI),
        session_id="test",
        messages=[{"role": "user", "content": "ada berapa fakultas"}],
        raw_query="ada berapa fakultas",
        effective_query="ada berapa fakultas",
        attempt_count=0,
        max_attempts=3,
        error_history=[],
        is_aborted=False
    )
    print("Testing astream(subgraphs=True)")
    try:
        async for item in main_graph.astream(state, subgraphs=True):
            print(item)
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test())
