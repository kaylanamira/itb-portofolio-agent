import logging
from typing import Optional

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from agent.llm import get_llm
from core.utils import extract_json_from_llm
from agent.prompts.rag_prompts import (
    RAG_GENERATION_SYSTEM_PROMPT,
    build_rag_generation_human_message,
    RAG_REGENERATE_SYSTEM_PROMPT,
    build_rag_regenerate_human_message,
)

logger = logging.getLogger(__name__)


class Citation(BaseModel):
    marker: int
    chunk_id: str


class GeneratedAnswer(BaseModel):
    answer: str = ""
    citations: list[Citation] = Field(default_factory=list)
    insufficient_context: bool = False


class AnswerGenerator:
    def __init__(self):
        self.llm = get_llm("rag_generation")

    async def generate(self, query: str, chunks: list[dict]) -> GeneratedAnswer:
        if not chunks:
            return GeneratedAnswer(insufficient_context=True)

        messages = [
            SystemMessage(content=RAG_GENERATION_SYSTEM_PROMPT),
            HumanMessage(content=build_rag_generation_human_message(query, chunks)),
        ]
        try:
            response = await self.llm.ainvoke(messages)
            content_dict = extract_json_from_llm(response.content)
            return GeneratedAnswer(**content_dict)
        except Exception as e:
            logger.error(f"Failed to generate RAG answer: {e}")
            return GeneratedAnswer(insufficient_context=True)

    async def regenerate_with_critique(
        self,
        query: str,
        chunks: list[dict],
        previous_answer: str,
        unsupported_claims: Optional[list[str]] = None,
    ) -> GeneratedAnswer:
        messages = [
            SystemMessage(content=RAG_REGENERATE_SYSTEM_PROMPT),
            HumanMessage(content=build_rag_regenerate_human_message(
                query, chunks, previous_answer, unsupported_claims or [],
            )),
        ]
        try:
            response = await self.llm.ainvoke(messages)
            content_dict = extract_json_from_llm(response.content)
            return GeneratedAnswer(**content_dict)
        except Exception as e:
            logger.error(f"Failed to regenerate RAG answer: {e}")
            return GeneratedAnswer(answer=previous_answer, insufficient_context=True)
