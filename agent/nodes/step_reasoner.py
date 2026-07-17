from agent.state import AgentState, StepResult, ValidationStatus
from langchain_core.messages import SystemMessage, HumanMessage
from agent.llm import get_llm
from agent.prompts.step_reasoner import STEP_REASONER_SYSTEM_PROMPT, build_step_reasoner_human_message
from core.utils import extract_json_from_llm

async def step_reasoner(state: AgentState) -> dict:
    """
    Captures the result of the current SQL/RAG step into StepResult,
    clears all per-step scratch-pad fields, and advances the step index.
    Supports early-exit (fully_answered) to eliminate redundant planning steps.
    """
    plan = state.get("plan", [])
    idx = state.get("current_step_index", 0)

    sql_res = state.get("sql_result")
    rag_res = state.get("rag_chunks")
    generated_sql = state.get("generated_sql")
    rag_query = state.get("rag_query")

    result_data = {}
    action_parts = []
    query_parts = []

    if sql_res is not None:
        action_parts.append("sql")
        result_data["sql"] = sql_res
        query_parts.append(f"SQL: {generated_sql}")

    if rag_res is not None:
        action_parts.append("rag")
        generated_answer = state.get("rag_generated_answer")
        if generated_answer:
            result_data["rag"] = {
                "answer": generated_answer,
                "citations": state.get("rag_citations", []),
            }
        else:
            # FALLBACK/empty-chunk case: no generated answer, fall back to raw chunks.
            result_data["rag"] = [
                {"source": chunk.get("source_type"), "content": chunk.get("chunk_text")}
                for chunk in rag_res
            ]
        query_parts.append(f"RAG: {rag_query}")

    if not action_parts:
        action_parts.append("unknown")
        result_data["unknown"] = []
        query_parts.append("N/A")

    action = " + ".join(action_parts)
    query_used = " | ".join(query_parts)

    llm = get_llm("step_reasoning")
    step_desc = plan[idx].get("task", "") if idx < len(plan) else "Final step"

    fully_answered = False
    try:
        human_content = build_step_reasoner_human_message(
            step_desc=step_desc,
            result_data=result_data,
            effective_query=state.get("effective_query", ""),
        )
        response = await llm.ainvoke([
            SystemMessage(content=STEP_REASONER_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ])
        analysis = extract_json_from_llm(response.content)
        observation = analysis.get("observation", "Data retrieved successfully.")
        fully_answered = analysis.get("fully_answered", False)
    except Exception:
        observation = "Data retrieved successfully."

    new_step_result = StepResult(
        step_number=idx + 1,
        thought=step_desc,
        action=action,
        query=query_used,
        result=result_data,
        observation=observation
    )

    if fully_answered:
        new_idx = len(plan)
    else:
        new_idx = idx + 1

    return {
        "steps_completed": [new_step_result],
        "current_step_index": new_idx,
        "reasoning_history": [f"[Step {new_idx}] {observation}"],
        "generated_sql": None,
        "validation_status": ValidationStatus.PENDING,
        "sql_result": None,
        "sql_error": None,
        "sql_row_count": None,
        "rag_query": None,
        "rag_chunks": None,
        "rag_generated_answer": None,
        "rag_citations": None,
        "answer_is_valid": None,
        "next_step": None,
        "attempt_count": 0,
    }
