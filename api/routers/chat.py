from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from api.routers.schemas import ChatRequest, ChatResponse
from api.dependencies import get_user_scope
from api.limiter import limiter
from core.scope import UserScope
from agent.state import AgentState
from agent.orchestrator import main_graph
from core.config import settings
import json
import logging

logger = logging.getLogger("agent.orchestrator")

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chat"][0])
async def chat_endpoint(
    request: Request,
    payload: ChatRequest,
    user_scope: UserScope = Depends(get_user_scope)
):
    """
    Standard synchronous chat endpoint.
    Runs the agent pipeline to completion and returns the final response.
    """
    initial_state = AgentState(
        user_scope=user_scope,
        session_id=payload.session_id,
        messages=[{"role": "user", "content": payload.query}],
        chart_context=payload.chart_context,
        raw_query=payload.query,
        rewritten_query=None,
        effective_query=payload.query,
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
    
    logger.info("Executing chat query synchronously: %s", payload.query)
    final_state = await main_graph.ainvoke(initial_state)
    
    resp = final_state.get("formatted_response")
    if resp:
        return ChatResponse(
            response_type=resp.response_type,
            narrative=resp.narrative,
            artifacts=[a.model_dump() if hasattr(a, 'model_dump') else a for a in resp.artifacts],
            follow_up_suggestions=resp.follow_up_suggestions,
            clarification_question=resp.clarification_question,
            disclaimer=resp.disclaimer
        )
        
    return ChatResponse(
        response_type="error",
        narrative="Graph execution failed to produce a response."
    )


@router.post("/stream")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chat_stream"][0])
async def chat_stream_endpoint(
    request: Request,
    payload: ChatRequest,
    user_scope: UserScope = Depends(get_user_scope)
):
    """
    Real-time streaming chat endpoint.
    Streams server-sent events (SSE) detailing the plan, intermediate tools, and agent thoughts.
    """
    initial_state = AgentState(
        user_scope=user_scope,
        session_id=payload.session_id,
        messages=[{"role": "user", "content": payload.query}],
        chart_context=payload.chart_context,
        raw_query=payload.query,
        rewritten_query=None,
        effective_query=payload.query,
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
    
    async def event_generator():
        final_state = initial_state
        async for ns, output in main_graph.astream(initial_state, subgraphs=True):
            for node_name, state_update in output.items():
                logger.info(f"=== [NODE COMPLETED: {node_name.upper()}] ===")
                
                update_payload = {
                    "event": "node_update",
                    "node": node_name,
                    "namespace": list(ns)
                }
                
                if "plan" in state_update and state_update["plan"]:
                    plan = state_update["plan"]
                    logger.info(f"PLAN: {json.dumps(plan, indent=2)}")
                    update_payload["plan"] = plan
                if "reasoning_history" in state_update and state_update["reasoning_history"]:
                    reasoning = state_update["reasoning_history"][-1]
                    logger.info(f"REASONING: {reasoning}")
                    update_payload["reasoning"] = reasoning
                if "generated_sql" in state_update and state_update["generated_sql"]:
                    sql = state_update["generated_sql"]
                    logger.info(f"SQL: {sql}")
                    update_payload["sql"] = sql
                if "sql_error" in state_update and state_update["sql_error"]:
                    err = state_update["sql_error"]
                    logger.error(f"SQL ERROR: {err}")
                    update_payload["error"] = err
                
                # Keep track of latest state
                final_state = {**final_state, **state_update}
                
                # Yield streaming update to client
                yield f"data: {json.dumps(update_payload)}\n\n"
        
        # When graph finishes, yield final response
        resp = final_state.get("formatted_response")
        if resp:
            final_data = {
                "response_type": resp.response_type,
                "narrative": resp.narrative,
                "artifacts": [a.model_dump() if hasattr(a, 'model_dump') else a for a in resp.artifacts],
                "follow_up_suggestions": resp.follow_up_suggestions,
                "clarification_question": resp.clarification_question,
                "disclaimer": resp.disclaimer
            }
            yield f"data: {json.dumps({'event': 'final_response', 'data': final_data})}\n\n"
        else:
            yield f"data: {json.dumps({'event': 'error', 'message': 'Graph execution failed'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
