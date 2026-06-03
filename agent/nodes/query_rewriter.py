from core.utils import extract_json_from_llm
import json
import re
from agent.state import AgentState
from agent.prompts.query_rewriter import REWRITER_PROMPT
from agent.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

def should_rewrite(query: str, history: str) -> bool:
    """
    Determines if a query needs LLM rewriting based on heuristics.
    """
    REFERENCE_PATTERNS = [
        r'\b(itu|ini|tersebut|dia|mereka|nya)\b',    # anaphoric pronouns
        r'\b(tadi|barusan|sebelumnya)\b',             # temporal deictic
        r'\b(yang sama|seperti tadi|itu juga)\b',     # comparative deictic
        r'^\s*(kenapa|mengapa|bagaimana)\s*\??\s*$',  # bare follow-up
        r'^\s*(dan|tapi|lalu|terus)\b',               # continuation opener
    ]

    has_reference = any(
        re.search(p, query, re.IGNORECASE) for p in REFERENCE_PATTERNS
    )

    if not history.strip():
        return has_reference

    if len(query.split()) > 30:
        return False

    return has_reference or len(query.split()) < 6



async def query_rewriter(state: AgentState) -> dict:
    raw_query = state["raw_query"]

    history = "\n".join(
        [msg.content if hasattr(msg, "content") else msg.get("content", "")
         for msg in state.get("messages", [])[-5:]]
    ) if state.get("messages") else ""

    if not should_rewrite(raw_query, history):
        return {"rewritten_query": None, "effective_query": raw_query}

    llm = get_llm("query_rewriter")
    prompt = REWRITER_PROMPT + (f"\nHistory:\n{history}" if history.strip() else "")

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
