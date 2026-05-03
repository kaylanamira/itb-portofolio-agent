import json
from agent.state import AgentState, FormattedResponse
from agent.prompts.response_formatter import RESPONSE_FORMATTER_SYSTEM, build_formatter_human_message
from agent.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

async def response_formatter(state: AgentState) -> dict:
    if state.get("formatted_response") is not None:
        return {}
        
    llm = get_llm()
    
    query_type = state.get("query_type")
    query_type_str = query_type.value if hasattr(query_type, "value") else str(query_type)
    
    human_content = build_formatter_human_message(
        query=state.get("effective_query", state.get("raw_query", "")),
        query_type=query_type_str,
        sql_result=state.get("sql_result", []),
        row_count=state.get("sql_row_count", 0),
        attempt_count=state.get("attempt_count", 0),
        abort_reason=state.get("abort_reason"),
        chart_context=state.get("chart_context"),
    )
    
    messages = [
        SystemMessage(content=RESPONSE_FORMATTER_SYSTEM),
        HumanMessage(content=human_content),
    ]
    response = await llm.ainvoke(messages)
    
    try:
        content = json.loads(response.content)
        resp = FormattedResponse(
            response_type=content.get("response_type", "text"),
            narrative=content.get("narrative", "Data telah diproses."),
            data=state.get("sql_result", []),
            chart_spec=content.get("chart_spec"),
            disclaimer=content.get("disclaimer"),
        )
    except Exception:
        # If JSON parsing fails, use raw text as narrative
        resp = FormattedResponse(
            response_type="text",
            narrative=response.content if response.content else "Maaf, ada kendala saat memformat hasil.",
        )
        
    return {"formatted_response": resp}
