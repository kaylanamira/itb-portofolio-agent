from core.utils import extract_json_from_llm
import re
from agent.state import AgentState
from agent.prompts.query_rewriter import REWRITER_PROMPT
from agent.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage


def format_recent_history(messages: list, limit: int = 5) -> str:
    lines = []
    for msg in messages[-limit:]:
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", "")
        else:
            role = getattr(msg, "type", "user")
            content = getattr(msg, "content", "")
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def should_rewrite(query: str, history: str) -> bool:
    REFERENCE_PATTERNS = [
        r'\b(itu|tersebut|dia|mereka)\b',
        r'\b\w+nya\b',
        r'\b(tadi|barusan|sebelumnya)\b',
        r'\b(yang sama|seperti tadi|itu juga)\b',
        r'\b(that|those|previous|same)\b',
        r'^\s*(kenapa|mengapa|bagaimana|why|how)\s*\??\s*$',
        r'^\s*(dan|tapi|lalu|terus|and|but|then)\b',
    ]

    has_reference = any(
        re.search(p, query, re.IGNORECASE) for p in REFERENCE_PATTERNS
    )

    if not history.strip():
        return False

    if len(query.split()) > 30:
        return False

    if not has_reference and re.search(
        r'^\s*(siapa|berapa|apa saja|tampilkan|buat|plot|visualisasikan|what|who|show)\b',
        query,
        re.IGNORECASE,
    ):
        return False

    return has_reference or len(query.split()) < 6


async def query_rewriter(state: AgentState) -> dict:
    raw_query = state["raw_query"]

    recent_messages = state.get("messages", [])
    if recent_messages:
        last_message = recent_messages[-1]
        if isinstance(last_message, dict):
            last_content = last_message.get("content", "")
            last_role = last_message.get("role", "user")
        else:
            last_content = getattr(last_message, "content", "")
            last_role = getattr(last_message, "type", "user")
        if last_role in ("user", "human") and last_content == raw_query:
            recent_messages = recent_messages[:-1]

    history = format_recent_history(recent_messages)
    summary = state.get("conversation_summary")
    context_parts = []
    if summary:
        context_parts.append(f"Summary:\n{summary}")
    if history:
        context_parts.append(f"History:\n{history}")
    context = "\n\n".join(context_parts)

    if not should_rewrite(raw_query, context):
        return {"rewritten_query": None, "effective_query": raw_query}

    llm = get_llm("query_rewriter")
    prompt = REWRITER_PROMPT + (f"\n\nConversation context:\n{context}" if context.strip() else "")

    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=raw_query),
    ]
    response = await llm.ainvoke(messages)

    try:
        content = extract_json_from_llm(response.content)
        rewritten = content.get("rewritten_query", raw_query)
    except Exception:
        rewritten = raw_query

    return {
        "rewritten_query": rewritten if rewritten != raw_query else None,
        "effective_query": rewritten,
    }
