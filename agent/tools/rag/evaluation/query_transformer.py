import logging
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from agent.llm import get_llm
from core.utils import extract_json_from_llm
from agent.prompts.rag_prompts import QUERY_TRANSFORMER_SYSTEM_PROMPT, build_query_transformer_human_message

logger = logging.getLogger(__name__)

class TransformerOutput(BaseModel):
    refined_query: str = Field(..., description="The refined query optimized for retrieval")

class QueryTransformer:
    def __init__(self):
        self.llm = get_llm("query_rewriter")

    async def transform(self, query: str, critique: str) -> str:
        human_content = build_query_transformer_human_message(query, critique)
        
        messages = [
            SystemMessage(content=QUERY_TRANSFORMER_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ]
        
        try:
            response = await self.llm.ainvoke(messages)
            content_dict = extract_json_from_llm(response.content)
            output = TransformerOutput(**content_dict)
            return output.refined_query
        except Exception as e:
            logger.error(f"Failed to transform query: {e}")
            return query
