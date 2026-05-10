from fastapi import APIRouter, Depends, Request
from api.routers.schemas import ChatRequest, ChatResponse
from api.dependencies import get_user_scope
from core.scope import UserScope
from agent.memory.session_manager import get_session_manager
from agent.state import AgentState
from agent.orchestrator import main_graph
from core.config import settings

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    user_scope: UserScope = Depends(get_user_scope)
):
    session_manager = get_session_manager(request.session_id)
    history = await session_manager.get_recent_messages()
    await session_manager.append_message("user", request.query)

    initial_state = AgentState(
        user_scope=user_scope,
        session_id=request.session_id,
        messages=history + [{"role": "user", "content": request.query}],
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
        conversation_summary=await session_manager.get_summary(),
        session_entities=await session_manager.get_entities(),
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
        await session_manager.append_message("assistant", resp.narrative)
        next_turn_index = await session_manager.next_turn_index()
        if next_turn_index is not None:
            query_type_value = final_state.get("query_type")
            query_type = getattr(query_type_value, "value", str(query_type_value or ""))
            entities = final_state.get("detected_entities")
            await session_manager.save_turn(
                user_id=user_scope.user_id,
                turn_index=next_turn_index,
                role="user",
                content=request.query,
                query_type=query_type,
                entities=entities.model_dump(mode="json") if entities else None,
                summary=final_state.get("conversation_summary"),
            )
            await session_manager.save_turn(
                user_id=user_scope.user_id,
                turn_index=next_turn_index + 1,
                role="assistant",
                content=resp.narrative,
                query_type=query_type,
                entities=entities.model_dump(mode="json") if entities else None,
                summary=final_state.get("conversation_summary"),
            )
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
