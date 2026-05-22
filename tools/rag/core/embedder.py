from __future__ import annotations

import logging
from typing import List, Optional, Union

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from tools.rag.config import EmbeddingConfig

logger = logging.getLogger(__name__)


class EmbeddingModel:
    _instance: Optional["EmbeddingModel"] = None

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        logger.info(f"Loading embedding model: {config.model_name}")
        self.model = SentenceTransformer(
            config.model_name,
            device=config.device,
        )
        self.model.max_seq_length = config.max_length

    @classmethod
    def get_instance(cls, config: EmbeddingConfig) -> "EmbeddingModel":
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a single query string with the 'query: ' prefix."""
        prefixed = f"{self.config.query_prefix}{query}"
        return self._encode([prefixed])[0]

    def embed_passages(self, passages: List[str]) -> np.ndarray:
        """
        Embed a batch of passages (document chunks) with 'passage: ' prefix.
        Returns shape (N, D).
        """
        prefixed = [f"{self.config.passage_prefix}{p}" for p in passages]
        return self._encode(prefixed)

    def embed_queries(self, queries: List[str]) -> np.ndarray:
        """Batch embed multiple queries."""
        prefixed = [f"{self.config.query_prefix}{q}" for q in queries]
        return self._encode(prefixed)

    def _encode(self, texts: List[str]) -> np.ndarray:
        with torch.no_grad():
            embeddings = self.model.encode(
                texts,
                batch_size=self.config.batch_size,
                normalize_embeddings=self.config.normalize_embeddings,
                show_progress_bar=len(texts) > 100,
                convert_to_numpy=True,
            )
        return embeddings