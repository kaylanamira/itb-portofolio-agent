from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm
from agent.prompts.query_rewriter import (
    MULTI_QUERY_SYSTEM_PROMPT,
    REFINE_QUERY_SYSTEM_PROMPT,
    build_multi_query_human_message,
    build_refine_query_human_message,
)
from core.utils import extract_json_from_llm

logger = logging.getLogger(__name__)


async def generate_multi_queries(query: str, task: str) -> list[str]:
    llm = get_llm("query_rewriter")
    try:
        response = await llm.ainvoke([
            SystemMessage(content=MULTI_QUERY_SYSTEM_PROMPT),
            HumanMessage(content=build_multi_query_human_message(query=query, task=task)),
        ])
        data = extract_json_from_llm(response.content)
        queries = [item for item in data.get("queries", []) if isinstance(item, str) and item.strip()]
        return queries[:3] or [query]
    except Exception as exc:
        logger.warning("Multi-query generation failed: %s", exc)
        return [query]


async def refine_query(query: str, task: str, suggestion: str | None) -> str:
    llm = get_llm("query_rewriter")
    try:
        response = await llm.ainvoke([
            SystemMessage(content=REFINE_QUERY_SYSTEM_PROMPT),
            HumanMessage(content=build_refine_query_human_message(
                query=query,
                task=task,
                suggestion=suggestion or "",
            )),
        ])
        data = extract_json_from_llm(response.content)
        refined = data.get("query")
        return refined if isinstance(refined, str) and refined.strip() else query
    except Exception as exc:
        logger.warning("RAG query refinement failed: %s", exc)
        return query
