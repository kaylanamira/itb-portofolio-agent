import logging
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from agent.llm import get_llm
from core.utils import extract_json_from_llm
from agent.prompts.rag_prompts import CHUNK_GRADER_SYSTEM_PROMPT, build_chunk_grader_human_message

logger = logging.getLogger(__name__)

class GraderOutput(BaseModel):
    score: float = Field(..., description="Relevance score between 0.0 and 1.0")
    reasoning: str = Field(..., description="Reasoning for the score")

class ChunkGrader:
    def __init__(self):
        self.llm = get_llm("llm_evaluation")

    async def evaluate(self, query: str, chunk_text: str) -> GraderOutput:
        human_content = build_chunk_grader_human_message(query, chunk_text)
        
        messages = [
            SystemMessage(content=CHUNK_GRADER_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ]
        
        try:
            response = await self.llm.ainvoke(messages)
            content_dict = extract_json_from_llm(response.content)
            return GraderOutput(**content_dict)
        except Exception as e:
            logger.error(f"Failed to evaluate chunk: {e}")
            return GraderOutput(score=0.0, reasoning="Evaluation failed")
