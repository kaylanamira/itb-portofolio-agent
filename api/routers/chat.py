from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from api.routers.schemas import ChatRequest, ChatResponse
from api.dependencies import get_user_scope
from api.limiter import limiter
from core.scope import UserScope
from agent.orchestrator import main_graph
from api.services.chat_service import build_initial_state, save_conversation_turn, to_chat_response
from core.config import settings
import json
import logging

logger = logging.getLogger("agent.orchestrator")

router = APIRouter(prefix="/api/chat", tags=["chat"])

@router.post("", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chat"][0])
async def chat_endpoint(
    request: Request,
    payload: ChatRequest,
    user_scope: UserScope = Depends(get_user_scope)
):
    initial_state = await build_initial_state(payload, user_scope)
    logger.info("Executing chat query synchronously: %s", payload.query)
    final_state = await main_graph.ainvoke(initial_state)
    
    resp = final_state.get("formatted_response")
    if resp:
        await save_conversation_turn(payload, user_scope, final_state)
        return to_chat_response(resp)
        
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
    initial_state = await build_initial_state(payload, user_scope)
    
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
                
                final_state = {**final_state, **state_update}
                yield f"data: {json.dumps(update_payload)}\n\n"
        
        resp = final_state.get("formatted_response")
        if resp:
            await save_conversation_turn(payload, user_scope, final_state)
            final_data = {
                "response_type": resp.response_type,
                "narrative": resp.narrative,
                "artifacts": [a.model_dump() if hasattr(a, "model_dump") else a for a in resp.artifacts],
                "follow_up_suggestions": resp.follow_up_suggestions,
                "clarification_question": resp.clarification_question,
                "disclaimer": resp.disclaimer
            }
            yield f"data: {json.dumps({'event': 'final_response', 'data': final_data})}\n\n"
        else:
            yield f"data: {json.dumps({'event': 'error', 'message': 'Graph execution failed'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
