import logging

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from agent.llm import get_llm
from core.utils import extract_json_from_llm
from agent.prompts.rag_prompts import FAITHFULNESS_SYSTEM_PROMPT, build_faithfulness_human_message

logger = logging.getLogger(__name__)


class ClaimVerification(BaseModel):
    claim: str
    supported: bool
    supporting_chunk_id: str | None = None


class FaithfulnessOutput(BaseModel):
    claims: list[ClaimVerification] = Field(default_factory=list)
    score: float = 0.0


class FaithfulnessChecker:
    def __init__(self):
        self.llm = get_llm("rag_faithfulness")

    async def check(self, answer: str, chunks: list[dict]) -> FaithfulnessOutput:
        if not answer or not answer.strip():
            return FaithfulnessOutput(claims=[], score=0.0)

        messages = [
            SystemMessage(content=FAITHFULNESS_SYSTEM_PROMPT),
            HumanMessage(content=build_faithfulness_human_message(answer, chunks)),
        ]
        try:
            response = await self.llm.ainvoke(messages)
            content_dict = extract_json_from_llm(response.content)
            claims = [ClaimVerification(**c) for c in content_dict.get("claims", [])]
        except Exception as e:
            logger.error(f"Failed to check faithfulness: {e}")
            return FaithfulnessOutput(claims=[], score=0.0)

        score = (sum(1 for c in claims if c.supported) / len(claims)) if claims else 0.0
        return FaithfulnessOutput(claims=claims, score=round(score, 4))
