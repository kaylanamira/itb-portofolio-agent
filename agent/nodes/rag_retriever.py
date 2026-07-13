import logging
from typing import Any

from agent.state import AgentState
from agent.tools.rag.retrieval.hybrid_retriever import HybridRetriever
from agent.tools.rag.evaluation.chunk_grader import ChunkGrader
from agent.tools.rag.evaluation.query_transformer import QueryTransformer
from core.sql_executor import PsycopgExecutor
from core.config import settings

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

    original_query = task or state.get("effective_query", "")
    current_query = original_query
    
    executor = PsycopgExecutor()
    retriever = HybridRetriever(executor=executor)
    grader = ChunkGrader()
    transformer = QueryTransformer()
    
    final_chunks = []
    confidence = 0.0
    action = "FALLBACK"
    
    max_attempts = settings.RAG_MAX_ATTEMPTS
    
    for attempt in range(max_attempts):
        chunks = await retriever.retrieve(current_query, user_scope=state["user_scope"])
        
        if not chunks:
            break
            
        combined_text = "\\n---\\n".join([c.get("chunk_text", "") for c in chunks])
        evaluation = await grader.evaluate(original_query, combined_text)
        
        score = evaluation.score
        
        if score >= settings.CRAG_CONFIDENCE_ACCEPT:
            final_chunks = chunks
            confidence = score
            action = "ACCEPT"
            break
        elif score >= settings.CRAG_CONFIDENCE_REFINE and attempt < max_attempts - 1:
            current_query = await transformer.transform(original_query, evaluation.reasoning)
        else:
            final_chunks = chunks if score >= 0.20 else []
            confidence = score
            action = "FALLBACK"
            break

    return {
        "rag_query": current_query,
        "rag_chunks": final_chunks,
        "rag_confidence": confidence,
        "rag_action": action,
    }
