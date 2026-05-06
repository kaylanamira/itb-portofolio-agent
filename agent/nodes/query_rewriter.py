from core.utils import extract_json_from_llm
import json
from agent.state import AgentState
from agent.prompts.query_rewriter import REWRITER_PROMPT
from agent.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

async def query_rewriter(state: AgentState) -> dict:
    if len(state["raw_query"].split()) > 50:
        return {"rewritten_query": None, "effective_query": state["raw_query"]}
        
    llm = get_llm("query_rewriter")
    history = "\n".join(
        [msg.content if hasattr(msg, "content") else msg.get("content", "") 
         for msg in state.get("messages", [])[-5:]]
    ) if state.get("messages") else ""
    prompt = REWRITER_PROMPT + f"\nHistory: {history}"
    
    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=state["raw_query"])
    ]
    response = await llm.ainvoke(messages)
    
    try:
        content = extract_json_from_llm(response.content)
        rewritten = content.get("rewritten_query", state["raw_query"])
    except Exception:
        rewritten = state["raw_query"]
        
    return {
        "rewritten_query": rewritten if rewritten != state["raw_query"] else None,
        "effective_query": rewritten
    }
