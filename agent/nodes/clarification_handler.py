from agent.state import AgentState, FormattedResponse
from agent.prompts.clarification_handler import CLARIFICATION_SYSTEM_PROMPT, build_clarification_human_message
from agent.llm import get_llm
from core.utils import extract_json_from_llm
from langchain_core.messages import SystemMessage, HumanMessage

async def clarification_handler(state: AgentState) -> dict:
    """Intelligent LLM-based clarification handler to replace fragile pattern matching."""
    llm = get_llm("clarification")
    
    query = state.get("effective_query", state.get("raw_query", ""))
    messages = state.get("messages", [])
    
    sys_prompt = CLARIFICATION_SYSTEM_PROMPT
    human_content = build_clarification_human_message(query, messages)
    
    msgs = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=human_content),
    ]
    
    try:
        response = await llm.ainvoke(msgs)
        content = extract_json_from_llm(response.content)
        question = content.get("clarification_question")
        if not question:
            raise ValueError("Klarifikasi kosong dari LLM")
    except Exception:
        question = (
            "Mohon maaf, pertanyaan Anda kurang spesifik atau memiliki referensi yang belum jelas. "
            "Bisa tolong sebutkan nama mata kuliah/dosen, tahun ajaran, semester, "
            "atau batas kriteria (misal: nilai ≥ B) yang Anda maksud?"
        )
    
    return {
        "formatted_response": FormattedResponse(
            response_type="clarification",
            narrative=question, 
            clarification_question=question,
        )
    }
