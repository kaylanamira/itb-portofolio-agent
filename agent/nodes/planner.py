from core.utils import extract_json_from_llm
from agent.state import AgentState, QueryType
from agent.prompts.planner import PLANNER_SYSTEM_PROMPT, build_planner_human_message
from agent.utils.plan_optimizer import optimize_plan
from agent.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage
from agent.prompts.planner import FEW_SHOT_EXAMPLES
from agent.constants.planner import (
    CHART_INTERPRETER_TASK,
    CHART_INTERPRETER_TOOL,
    CHART_INTERPRET_WITH_CONTEXT_REASONING,
    CHART_INTERPRET_WITHOUT_CONTEXT_REASONING,
    CHART_INTERPRET_WITHOUT_CONTEXT_TASK,
)

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

    if qtype == QueryType.CHART_INTERPRET:
        if chart_ctx:
            plan = [{"task": CHART_INTERPRETER_TASK, "tool": CHART_INTERPRETER_TOOL}]
            reasoning = CHART_INTERPRET_WITH_CONTEXT_REASONING
        else:
            qtype = QueryType.CLARIFICATION_NEEDED
            plan = [{"task": CHART_INTERPRET_WITHOUT_CONTEXT_TASK, "tool": "clarification"}]
            reasoning = CHART_INTERPRET_WITHOUT_CONTEXT_REASONING

    plan, optimization_note = optimize_plan(
        query=state["effective_query"],
        plan=plan,
        query_type=qtype,
    )

    reasoning_hist = [f"PLAN: {reasoning}"]
    if optimization_note:
        reasoning_hist.append(optimization_note)
        
    return {
        "query_type": qtype,
        "plan": plan,
        "current_step_index": 0,
        "reasoning_history": reasoning_hist
    }
