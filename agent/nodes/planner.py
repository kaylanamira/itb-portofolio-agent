from core.utils import extract_json_from_llm
from agent.state import AgentState, QueryType
from agent.prompts.planner import PLANNER_SYSTEM_PROMPT, build_planner_human_message
from agent.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage
from agent.state import QueryType
from agent.prompts.planner import FEW_SHOT_EXAMPLES

async def planner(state: AgentState) -> dict:
    """
    Analyzes the query and creates a step-by-step execution plan.
    """
    llm = get_llm("planning")
    
    chart_ctx = state.get("chart_context")
    chart_status = "present" if chart_ctx else "absent"
    
    sys_prompt = PLANNER_SYSTEM_PROMPT.format(
        chart_context_status=chart_status,
        FEW_SHOT_EXAMPLES=FEW_SHOT_EXAMPLES
    )
    
    human_content = build_planner_human_message(
        query=state["effective_query"],
        recent_messages=state.get("messages", [])
    )
    
    messages = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=human_content),
    ]
    
    response = await llm.ainvoke(messages)
    
    try:
        content = extract_json_from_llm(response.content)
        qtype_str = content.get("query_type", "clarification_needed")
        try:
            qtype = QueryType(qtype_str)
        except ValueError:
            qtype = QueryType.CLARIFICATION_NEEDED
            
        plan = content.get("plan", [])
        reasoning = content.get("reasoning", "Planning execution steps...")
        
    except Exception:
        qtype = QueryType.CLARIFICATION_NEEDED
        plan = [{"task": "Minta klarifikasi dari pengguna.", "tool": "clarification"}]
        reasoning = "Gagal memproses query, butuh klarifikasi."
        
    return {
        "query_type": qtype,
        "plan": plan,
        "current_step_index": 0,
        "reasoning_history": [f"PLAN: {reasoning}"]
    }
