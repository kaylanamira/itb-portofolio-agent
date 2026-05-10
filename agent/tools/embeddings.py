from __future__ import annotations


import httpx

from agent.tools.cache import CacheKeys, cache
from core.config import settings


class EmbeddingClient:
    def __init__(
        self,
        api_url: str | None = settings.EMBEDDING_API_URL,
        api_key: str | None = settings.EMBEDDING_API_KEY,
        model: str = settings.EMBEDDING_MODEL,
    ):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model

    async def embed_query(self, text: str) -> list[float]:
        cache_key = CacheKeys.embedding(text)
        cached = await cache.get_json(cache_key)
        if cached:
            return [float(v) for v in cached]
        if not self.api_url:
            raise RuntimeError("EMBEDDING_API_URL must be configured for BGE-M3 retrieval.")

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {"model": self.model, "input": text}
        async with httpx.AsyncClient(timeout=settings.EMBEDDING_TIMEOUT_SECONDS) as client:
            response = await client.post(self.api_url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        embedding = _extract_embedding(data)
        if len(embedding) != settings.EMBEDDING_DIMS:
            raise ValueError(
                f"Expected {settings.EMBEDDING_DIMS} embedding dimensions, got {len(embedding)}."
            )
        await cache.set_json(cache_key, embedding, settings.CACHE_RAG_SESSION_TTL_SECONDS)
        return embedding


def _extract_embedding(data: dict) -> list[float]:
    if "data" in data and data["data"]:
        return [float(v) for v in data["data"][0]["embedding"]]
    if "embedding" in data:
        return [float(v) for v in data["embedding"]]
    if "embeddings" in data and data["embeddings"]:
        return [float(v) for v in data["embeddings"][0]]
    raise ValueError("Embedding API response did not contain an embedding.")


embedding_client = EmbeddingClient()
