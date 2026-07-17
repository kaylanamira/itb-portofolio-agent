import logging
import re
from typing import Optional

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from agent.llm import get_llm
from agent.state import DetectedEntities
from core.config import settings
from core.utils import extract_json_from_llm
from agent.prompts.rag_prompts import HYDE_SYSTEM_PROMPT, build_hyde_human_message

logger = logging.getLogger(__name__)

_SENTIMENT_VAGUE_PATTERN = re.compile(
    r"\b(kesal|puas|kecewa|senang|suka|benci|marah|keluhan|komplain|masalah|"
    r"bagaimana pendapat|bagaimana perasaan|apa pendapat|apa kesan|rangkum|"
    r"rangkuman|carikan|opini|sentimen|kritik|pujian)\b",
    re.IGNORECASE,
)

_VAGUE_WORD_COUNT_THRESHOLD = 12


class HydeHypotheses(BaseModel):
    hypotheses: list[str] = Field(default_factory=list)


def should_use_hyde(query: str, entities: Optional[DetectedEntities] = None) -> bool:
    if not settings.RAG_HYDE_ENABLED:
        return False

    if _SENTIMENT_VAGUE_PATTERN.search(query):
        return True

    if entities is not None:
        has_anchor = any([
            entities.resolved_dosen_id,
            entities.resolved_matkul_id,
            entities.resolved_prodi_id,
            entities.kode_matkul,
        ])
        if not has_anchor and len(query.split()) <= _VAGUE_WORD_COUNT_THRESHOLD:
            return True

    return False


class MultiHydeGenerator:
    def __init__(self):
        self.llm = get_llm("rag_hyde")

    async def generate(self, query: str, n: Optional[int] = None) -> list[str]:
        n = n or settings.RAG_HYDE_NUM_HYPOTHESES
        messages = [
            SystemMessage(content=HYDE_SYSTEM_PROMPT),
            HumanMessage(content=build_hyde_human_message(query, n)),
        ]
        try:
            response = await self.llm.ainvoke(messages)
            content_dict = extract_json_from_llm(response.content)
            hypotheses = HydeHypotheses(**content_dict).hypotheses
            return hypotheses[:n] if hypotheses else []
        except Exception as e:
            logger.error(f"Failed to generate HyDE hypotheses: {e}")
            return []
