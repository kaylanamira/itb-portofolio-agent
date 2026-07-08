from api.routers.schemas import ChatRequest, ChatResponse
from core.scope import UserScope
from agent.state import AgentState
from agent.memory import get_session_history_store
from core.config import settings

async def build_initial_state(payload: ChatRequest, user_scope: UserScope) -> AgentState:
    history_store = get_session_history_store()
    history = await history_store.load_history(payload.session_id)
    messages = [message.model_dump(exclude_none=True) for message in history.messages]
    messages.append({"role": "user", "content": payload.query})

    return AgentState(
        user_scope=user_scope,
        session_id=payload.session_id,
        messages=messages,
        conversation_summary=history.summary,
        session_entities=None,
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
        content_filter_result=None,
        extracted_keywords=None,
        detected_entities=None,
        relevant_tables=None,
        schema_context=None,
        generated_sql=None,
        validation_status=None,
        validation_errors=[],
        sql_result=None,
        sql_error=None,
        sql_row_count=None,
        rag_query=None,
        rag_chunks=None,
        rag_source_types=None,
        rag_tipe_konten=None,
        rag_scope_override=None,
        rag_attempt_count=0,
        rag_confidence=None,
        rag_action=None,
        rag_refined_query=None,
        faithfulness_score=None,
        faithfulness_action=None,
        answer_is_valid=None,
        next_step=None,
        formatted_response=None,
        attempt_count=0,
        max_attempts=settings.MAX_SQL_ATTEMPTS,
        error_history=[],
        is_aborted=False,
        abort_reason=None,
        empty_result_reason=None,
    )

async def save_conversation_turn(
    payload: ChatRequest,
    user_scope: UserScope,
    final_state: dict,
) -> None:
    resp = final_state.get("formatted_response")
    if not resp:
        return

    history_store = get_session_history_store()
    await history_store.save_turn(
        session_id=payload.session_id,
        user_message=payload.query,
        assistant_message=resp.narrative,
    )
    await history_store.summarize_history(payload.session_id)
    history = await history_store.load_history(payload.session_id)
    query_type = final_state.get("query_type")
    
    metadata = {}
    if resp.artifacts:
        metadata["artifacts"] = [a.model_dump() if hasattr(a, "model_dump") else a for a in resp.artifacts]
    if final_state.get("generated_sql"):
        metadata["sql"] = final_state.get("generated_sql")
    if not metadata:
        metadata = None

    await history_store.save_turn_to_archive(
        session_id=payload.session_id,
        user_scope=user_scope,
        user_message=payload.query,
        assistant_message=resp.narrative,
        query_type=query_type.value if hasattr(query_type, "value") else query_type,
        summary=history.summary,
        metadata=metadata,
    )

def to_chat_response(resp) -> ChatResponse:
    return ChatResponse(
        response_type=resp.response_type,
        narrative=resp.narrative,
        artifacts=[a.model_dump() if hasattr(a, "model_dump") else a for a in resp.artifacts],
        follow_up_suggestions=resp.follow_up_suggestions,
        clarification_question=resp.clarification_question,
        disclaimer=resp.disclaimer,
    )
