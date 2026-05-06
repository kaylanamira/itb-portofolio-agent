from fastapi import APIRouter, Depends, Request
from api.routers.schemas import ChatRequest, ChatResponse
from api.dependencies import get_user_scope
from core.scope import UserScope
from agent.state import AgentState
from agent.orchestrator import main_graph
from core.config import settings

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    user_scope: UserScope = Depends(get_user_scope)
):
    initial_state = AgentState(
        user_scope=user_scope,
        session_id=request.session_id,
        messages=[{"role": "user", "content": request.query}],
        chart_context=request.chart_context,
        raw_query=request.query,
        rewritten_query=None,
        effective_query=request.query,
        domain=None,
        query_type=None,
        plan=[],
        current_step_index=0,
        steps_completed=[],
        reasoning_history=[],
        detected_entities=None,
        relevant_tables=None,
        schema_context=None,
        formatted_response=None,
        attempt_count=0,
        max_attempts=settings.MAX_SQL_ATTEMPTS,
        error_history=[],
        is_aborted=False,
        abort_reason=None
    )
    
    final_state = initial_state
    async for output in main_graph.astream(initial_state):
        for node_name, state_update in output.items():
            print(f"\n[NODE FINISHED]: {node_name}")
            if "plan" in state_update:
                print(f"  > Plan: {state_update['plan']}")
            if "reasoning_history" in state_update:
                print(f"  > Reasoning: {state_update['reasoning_history'][-1]}")
            if "generated_sql" in state_update:
                print(f"  > SQL: {state_update['generated_sql']}")
            
            # Keep track of latest state
            final_state = {**final_state, **state_update}
    
    resp = final_state.get("formatted_response")
    if resp:
        return ChatResponse(
            response_type=resp.response_type,
            narrative=resp.narrative,
            artifacts=[a.model_dump() for a in resp.artifacts],
            follow_up_suggestions=resp.follow_up_suggestions,
            clarification_question=resp.clarification_question,
            disclaimer=resp.disclaimer
        )
        
    return ChatResponse(
        response_type="error",
        narrative="Graph execution failed to produce a response."
    )
