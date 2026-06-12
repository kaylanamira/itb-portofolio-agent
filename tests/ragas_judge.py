import json
from pydantic import BaseModel
from typing import Any
from agent.llm import get_llm
from core.config import settings

try:
    from ragas.llms.base import BaseRagasLLM
    from ragas.embeddings.base import BaseRagasEmbeddings
    from langchain_community.embeddings import HuggingFaceBgeEmbeddings
    HAS_RAGAS = True
except ImportError:
    HAS_RAGAS = False
    BaseRagasLLM = object
    BaseRagasEmbeddings = object

class CustomRagasLLM(BaseRagasLLM):
    def __init__(self, model_name: str = "llm_evaluation"):
        self.model_name = model_name
        self.llm = get_llm(self.model_name, force_json=False)
    
    def generate_text(self, prompt: str, **kwargs) -> str:
        res = self.llm.invoke(prompt)
        return res.content

    async def agenerate_text(self, prompt: str, **kwargs) -> str:
        res = await self.llm.ainvoke(prompt)
        return res.content

    def set_run_config(self, run_config):
        pass

class CustomRagasEmbeddings(BaseRagasEmbeddings):
    def __init__(self):
        self.embeddings = HuggingFaceBgeEmbeddings(
            model_name="BAAI/bge-small-en-v1.5",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True}
        )

    def embed_query(self, text: str) -> list[float]:
        return self.embeddings.embed_query(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embeddings.embed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        return self.embed_query(text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_documents(texts)

    def set_run_config(self, run_config):
        pass

ragas_llm = CustomRagasLLM("llm_evaluation") if HAS_RAGAS else None
ragas_embeddings = CustomRagasEmbeddings() if HAS_RAGAS else None
