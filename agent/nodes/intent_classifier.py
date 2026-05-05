from core.utils import extract_json_from_llm
import json
from agent.state import AgentState, AgentDomain
from agent.prompts.intent_classifier import INTENT_SYSTEM_PROMPT, build_intent_human_message
from agent.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

async def intent_classifier(state: AgentState) -> dict:
    llm = get_llm()
    
    human_content = build_intent_human_message(
        query=state["raw_query"],
        recent_messages=state.get("messages", []),
        chart_context=state.get("chart_context"),
    )
    
    messages = [
        SystemMessage(content=INTENT_SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ]
    response = await llm.ainvoke(messages)
    
    try:
        content = extract_json_from_llm(response.content)
        domain = AgentDomain(content.get("domain", "out_of_scope"))
        reason = content.get("reason", "Topik ini di luar pengetahuan saya.")
    except Exception:
        domain = AgentDomain.OUT_OF_SCOPE
        reason = "Maaf, terjadi kesalahan saat memahami pertanyaan Anda."
        
    updates = {
        "domain": domain,
        "effective_query": state["raw_query"],
    }
    
    if domain == AgentDomain.OUT_OF_SCOPE:
        updates["abort_reason"] = reason
        
    return updates
