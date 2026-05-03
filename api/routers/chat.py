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
        detected_entities=None,
        relevant_tables=None,
        schema_context=None,
        generated_sql=None,
        sql_with_scope=None,
        validation_status=None,
        validation_errors=[],
        sql_result=None,
        sql_error=None,
        sql_row_count=None,
        rag_query=None,
        rag_chunks=None,
        answer_is_valid=None,
        formatted_response=None,
        attempt_count=0,
        max_attempts=settings.MAX_SQL_ATTEMPTS,
        error_history=[],
        is_aborted=False,
        abort_reason=None
    )
    
    final_state = await main_graph.ainvoke(initial_state)
    
    resp = final_state.get("formatted_response")
    if resp:
        return ChatResponse(
            response_type=resp.response_type,
            narrative=resp.narrative,
            data=resp.data,
            chart_spec=resp.chart_spec,
            clarification_question=resp.clarification_question,
            disclaimer=resp.disclaimer
        )
        
    return ChatResponse(
        response_type="error",
        narrative="Graph execution failed to produce a response."
    )
