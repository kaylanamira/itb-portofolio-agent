from agent.state import AgentState, StepResult, ValidationStatus
from langchain_core.messages import SystemMessage, HumanMessage
from agent.llm import get_llm
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

    if sql_res is not None:
        action = "sql"
        result_data = sql_res
        query_used = generated_sql or "N/A"
    elif rag_res is not None:
        action = "rag"
        result_data = rag_res
        query_used = rag_query or "N/A"
    else:
        action = "unknown"
        result_data = []
        query_used = "N/A"

    llm = get_llm("step_reasoning")
    step_desc = plan[idx].get("task", "") if idx < len(plan) else "Final step"
    
    # Generate the system prompt dynamically inside function scope to safely include effective_query
    system_prompt = f"""Kamu adalah analis data ITB Academic Portfolio.
Berikan observasi 1-2 kalimat tentang apa yang ditemukan dari data langkah ini.
Tentukan juga apakah data yang dikumpulkan saat ini sudah SEPENUHNYA menjawab pertanyaan asli pengguna secara tuntas sehingga kita bisa langsung menyusun kesimpulan tanpa langkah/tindakan lanjutan.

Pertanyaan Asli Pengguna: "{state.get('effective_query', '')}"

Balas HANYA dengan JSON format berikut:
{{
  "observation": "Observasi singkat tentang data langkah ini...",
  "fully_answered": true | false
}}
Jangan tulis teks lainnya selain JSON.
"""

    fully_answered = False
    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Step Task: {step_desc}\nStep Data: {str(result_data)[:800]}")
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
        "sql_with_scope": None,
        "validation_status": ValidationStatus.PENDING,
        "sql_result": None,
        "sql_error": None,
        "sql_row_count": None,
        "rag_query": None,
        "rag_chunks": None,
        "answer_is_valid": None,
        "next_step": None,
        "attempt_count": 0, 
    }

def route_after_reasoning(state: AgentState) -> str:
    """Route back to step_executor if more steps remain, else go to synthesizer."""
    plan = state.get("plan", [])
    idx = state.get("current_step_index", 0)
    return "synthesizer" if idx >= len(plan) else "step_executor"
