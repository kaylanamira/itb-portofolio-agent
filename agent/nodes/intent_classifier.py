from pydantic import BaseModel, Field
from core.utils import extract_json_from_llm
import logging
from agent.state import AgentState, AgentDomain
from agent.prompts.intent_classifier import INTENT_SYSTEM_PROMPT, build_intent_human_message
from agent.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

class DomainRoute(BaseModel):
    domain: AgentDomain = Field(..., description="The domain of the query.")
    reason: str = Field(..., description="Reason for the domain choice.")
    
async def intent_classifier(state: AgentState) -> dict:
    llm = get_llm("intent_classification")
    
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
        route = DomainRoute(**content)
        domain = route.domain
        reason = route.reason
    except Exception as e:
        logger.error(f"Failed to parse DomainRoute: {e}")
        domain = AgentDomain.OUT_OF_SCOPE
        reason = "Maaf, terjadi kesalahan saat memahami pertanyaan Anda."
        
    updates = {
        "domain": domain,
        "effective_query": state["raw_query"],
    }
    
    if domain == AgentDomain.OUT_OF_SCOPE:
        updates["abort_reason"] = reason
        
    return updates

def route_after_intent(state: AgentState) -> str:
    domain = state.get("domain", "out_of_scope")
    logger.info(f"Routing logic determined domain is: {domain}")
    if domain == "portfolio":
        return "portfolio_agent"
    # elif domain == "wisudawan":
    #     return "wisudawan_agent"
    return "out_of_scope"
