from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse
from api.routers.schemas import ChatRequest, ChatResponse, SessionSummary, ChatMessageOut
from api.dependencies import get_user_scope
from api.limiter import limiter
from core.scope import UserScope
from core.database import get_db_connection
from agent.orchestrator import main_graph
from api.services.chat_service import build_initial_state, save_conversation_turn, to_chat_response, verify_session_ownership
from core.config import settings
from core.redis_client import get_redis
import json
import logging
import uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(user_scope: UserScope = Depends(get_user_scope)):
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT session_id, title, summary, updated_at
                FROM analitik.chat_sessions
                WHERE user_id = %s AND active_role = %s::jsonb
                ORDER BY updated_at DESC
                LIMIT 50
                """,
                (user_scope.user_id, json.dumps(user_scope.role.value)),
            )
            rows = await cur.fetchall()
 
    return [
        SessionSummary(session_id=r[0], title=r[1], summary=r[2], updated_at=r[3])
        for r in rows
    ]

@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
async def get_session_messages(session_id: str, user_scope: UserScope = Depends(get_user_scope)):
    if not await verify_session_ownership(session_id, user_scope):
        raise HTTPException(status_code=403, detail="Not your session")

    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT role, content, created_at
                FROM analitik.chat_messages
                WHERE session_id = %s
                ORDER BY turn_index, message_id
                """,
                (session_id,),
            )
            rows = await cur.fetchall()

    return [ChatMessageOut(role=r[0], content=r[1], created_at=r[2]) for r in rows]


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user_scope: UserScope = Depends(get_user_scope)):
    if not await verify_session_ownership(session_id, user_scope):
        raise HTTPException(status_code=403, detail="Not your session")

    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM analitik.chat_sessions WHERE session_id = %s",
                (session_id,),
            )
        await conn.commit()

    redis = get_redis()
    await redis.delete(f"chat:{session_id}:messages", f"chat:{session_id}:summary")

    return {"status": "deleted"}

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
        try:
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
        except Exception:
            # Exception apapun di node manapun (mis. UnicodeDecodeError saat baca
            # file schema, error koneksi DB, dst) TIDAK BOLEH membuat generator
            # ini mati diam-diam -- kalau itu terjadi, koneksi SSE cuma tertutup
            # tanpa event apa pun, dan frontend tidak akan pernah tahu (macet
            # permanen di progress indicator terakhir, seperti yang dilaporkan).
            # Log lengkap untuk debugging, lalu kirim event error yang jelas ke
            # client supaya UI bisa menampilkan pesan dan berhenti "berpikir".
            logger.exception("Unhandled error while streaming chat graph")
            yield f"data: {json.dumps({'event': 'error', 'message': 'Terjadi kesalahan saat memproses pertanyaan Anda. Silakan coba lagi.'})}\n\n"
            return

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