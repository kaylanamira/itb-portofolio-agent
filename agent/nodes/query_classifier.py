import json
from agent.state import AgentState, QueryType
from agent.prompts.query_classifier import (
    CLASSIFIER_SYSTEM_PROMPT, FEW_SHOT_EXAMPLES, build_classifier_human_message
)
from agent.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

async def query_classifier(state: AgentState) -> dict:
    llm = get_llm()
    
    # Determine chart context status for the prompt
    chart_ctx = state.get("chart_context")
    chart_status = "present (user is viewing a chart)" if chart_ctx else "absent (no chart on screen)"
    
    sys_prompt = CLASSIFIER_SYSTEM_PROMPT.format(
        chart_context_status=chart_status,
        few_shot_examples=FEW_SHOT_EXAMPLES,
    )
    
    human_content = build_classifier_human_message(
        query=state["effective_query"],
        recent_messages=state.get("messages", []),
    )
    
    messages = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=human_content),
    ]
    response = await llm.ainvoke(messages)
    
    try:
        content = json.loads(response.content)
        qtype = QueryType(content.get("query_type", "clarification_needed"))
    except Exception:
        qtype = QueryType.CLARIFICATION_NEEDED
        
    return {"query_type": qtype}

def route_after_classification(state: AgentState) -> str:
    match state.get("query_type"):
        case QueryType.CLARIFICATION_NEEDED:
            return "clarification_handler"
        case QueryType.CHART_INTERPRET:
            return "response_formatter" 
        case QueryType.TEXT_LOOKUP | QueryType.ANALYTICAL_TEXT | QueryType.SUMMARIZATION:
            return "rag_retriever"     
        case QueryType.DATA_LOOKUP | QueryType.ANALYTICAL_NUMERIC | \
             QueryType.COMPARATIVE | QueryType.DIAGNOSTIC | \
             QueryType.CHART_GENERATE | QueryType.ANALYTICAL_HYBRID:
            return "schema_linker"
        case _:
            return "clarification_handler"
