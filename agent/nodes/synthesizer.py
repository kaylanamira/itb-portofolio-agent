from core.utils import extract_json_from_llm
import uuid
from agent.state import AgentState, FormattedResponse, TableArtifact, ChartArtifact
from agent.prompts.synthesizer import SYNTHESIZER_SYSTEM_PROMPT, REJECTION_SYSTEM_PROMPT, build_synthesizer_human_message
from agent.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

async def synthesizer(state: AgentState) -> dict:
    llm = get_llm("synthesis")
    query = state.get("effective_query", state.get("raw_query", ""))
    abort_reason = state.get("abort_reason")
    is_max_retries = abort_reason == "MAX_RETRIES_EXCEEDED"

    if abort_reason and not is_max_retries:
        messages = [
            SystemMessage(content=REJECTION_SYSTEM_PROMPT),
            HumanMessage(content=f"Query User: {query}\nAlasan Penolakan: {abort_reason}\n\nBuat respons penolakan:")
        ]
        try:
            response = await llm.ainvoke(messages)
            content = extract_json_from_llm(response.content)
            formatted = FormattedResponse(
                response_type="error" if state.get("is_aborted") else "text",
                narrative=content.get("narrative", abort_reason),
                artifacts=[],
                follow_up_suggestions=content.get("follow_up_suggestions", [])
            )
        except Exception:
            formatted = FormattedResponse(
                response_type="error" if state.get("is_aborted") else "text",
                narrative=abort_reason,
                artifacts=[]
            )
        return {"formatted_response": formatted}

    steps = state.get("steps_completed", [])
    sys_prompt = SYNTHESIZER_SYSTEM_PROMPT
    human_content = build_synthesizer_human_message(query, steps)
    
    messages = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=human_content),
    ]
    
    response = await llm.ainvoke(messages)
    
    try:
        content = extract_json_from_llm(response.content)
        
        artifacts = []
        for art in content.get("artifacts", []):
            art_id = str(uuid.uuid4())
            if art.get("artifact_type") == "chart":
                artifacts.append(ChartArtifact(
                    artifact_id=art_id,
                    chart_type=art.get("chart_type", "bar"),
                    title=art.get("title", "Analysis Chart"),
                    chart_spec=art.get("chart_spec", {}),
                    source_sql=art.get("source_sql"),
                    columns_used=art.get("columns_used", []),
                    insight=art.get("insight")
                ))
            else:
                artifacts.append(TableArtifact(
                    artifact_id=art_id,
                    title=art.get("title", "Data Table"),
                    columns=art.get("columns", []),
                    rows=art.get("rows", []),
                    source_sql=art.get("source_sql"),
                    row_count=art.get("row_count", len(art.get("rows", []))),
                    is_truncated=art.get("is_truncated", False)
                ))
                
        formatted = FormattedResponse(
            response_type="mixed" if artifacts else "text",
            narrative=content.get("narrative", "Berikut adalah hasil analisis kami."),
            artifacts=artifacts,
            follow_up_suggestions=content.get("follow_up_suggestions", []),
            disclaimer=content.get("disclaimer")
        )
    except Exception as e:
        formatted = FormattedResponse(
            response_type="error",
            narrative=f"Maaf, terjadi kesalahan saat menyusun jawaban: {str(e)}"
        )
        
    return {"formatted_response": formatted}
