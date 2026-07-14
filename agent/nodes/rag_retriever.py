import logging
from typing import Any

from agent.state import AgentState
from agent.tools.rag.pipeline import run_rag

logger = logging.getLogger(__name__)


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

    query = task or state.get("effective_query", "")

    result = await run_rag(
        query=query,
        user_scope=state["user_scope"],
        source_types=state.get("rag_source_types"),
    )

    return {
        "rag_query": result.rag_query,
        "rag_chunks": result.chunks_used,
        "rag_confidence": result.retrieval_confidence,
        "rag_action": result.retrieval_action,
        "rag_refined_query": result.rag_query if result.rag_query != query else None,
        "faithfulness_score": result.faithfulness_score,
        "faithfulness_action": result.faithfulness_action,
        "rag_generated_answer": result.answer,
        "rag_citations": [c.model_dump() for c in result.citations],
    }
