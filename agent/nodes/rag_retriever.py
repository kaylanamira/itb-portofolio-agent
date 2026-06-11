from typing import Any

from agent.state import AgentState


async def rag_retriever(state: AgentState) -> dict[str, Any]:
    task = ""
    plan = state.get("plan", [])
    idx = state.get("current_step_index", 0)
    if idx < len(plan) and plan[idx].get("tool") == "rag":
        task = plan[idx].get("task", "")
    else:
        for step in plan:
            if step.get("tool") == "rag":
                task = step.get("task", "")
                break

    chunks: list[dict[str, Any]] = []
    if "IF1220" in task:
        chunks.append({
            "content": "IF1220 Matematika Diskrit. Deskripsi singkat: Mata kuliah ini mempelajari dasar-dasar matematika untuk ilmu komputer.",
            "source_type": "phase_2_placeholder",
        })
    elif "attendance" in task.lower() or "kehadiran" in task.lower():
        chunks.append({
            "content": "Kehadiran minimal mahasiswa untuk dapat mengikuti ujian dan lulus mata kuliah adalah 80% dari total pertemuan.",
            "source_type": "phase_2_placeholder",
        })

    return {
        "rag_query": task or state.get("effective_query"),
        "rag_chunks": chunks,
        "rag_confidence": 0.0,
        "rag_action": "phase_2_placeholder",
    }
