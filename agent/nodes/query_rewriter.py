from core.utils import extract_json_from_llm
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


async def query_rewriter(state: AgentState) -> dict:
    raw_query = state["raw_query"]

    if not state.get("needs_rewrite", False):
        return {"rewritten_query": None, "effective_query": raw_query}

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
