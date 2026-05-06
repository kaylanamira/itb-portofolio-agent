from agent.state import AgentState

async def step_executor(state: AgentState) -> dict:
    plan = state.get("plan", [])
    idx = state.get("current_step_index", 0)
    
    if idx >= len(plan):
        return {"next_step": "finalize"}
        
    current_task = plan[idx]
    tool = current_task.get("tool", "sql")
    return {"next_step": tool}

def route_from_step_executor(state: AgentState) -> str:
    tool = state.get("next_step", "sql")
    if tool == "rag":
        return "rag_retriever"
    if tool == "finalize":
        return "synthesizer"
    return "sql_pipeline"
