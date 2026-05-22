from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from tools.rag.config import RAGConfig
from tools.rag.core.embedder import EmbeddingModel
from tools.rag.core.models import Chunk, RAGOutput, RawDocument, RetrievedChunk
from tools.rag.ingestion.chunker import DocumentChunker
from tools.rag.ingestion.indexer import VectorIndexer
from tools.rag.retrieval.hybrid_retriever import HybridRetriever

logger = logging.getLogger(__name__)


class RAGTool:
    def __init__(self, config: RAGConfig, dsn: Optional[str] = None, llm_fn=None):
        self.config = config
        self.dsn = dsn or config.postgres_dsn
        self._embedder = EmbeddingModel.get_instance(config.embedding)
        self._chunker = DocumentChunker(config.chunking)
        self._indexer = VectorIndexer(config.embedding, config.vector_db, self.dsn)
        # Lazy retrievers — one instance per domain
        self._llm_fn = llm_fn  # optional: enables HyDE for subjective queries
        self._retrievers: Dict[str, HybridRetriever] = {}

    def ensure_schema(self) -> None:
        """Idempotently create pgvector tables, HNSW indexes, GIN indexes."""
        self._indexer.ensure_schema()

    def ingest_documents(
        self,
        documents: List[RawDocument],
        batch_size: int = 64,
    ) -> int:
        """Chunk, embed, and index documents. Returns total chunk count."""
        chunks = self._chunker.chunk_documents(documents)
        logger.info(f"[RAGTool] {len(documents)} docs → {len(chunks)} chunks")
        return self._indexer.index_chunks(chunks, batch_size=batch_size)

    def ingest_chunks(self, chunks: List[Chunk], batch_size: int = 64) -> int:
        """Index pre-chunked objects directly."""
        return self._indexer.index_chunks(chunks, batch_size=batch_size)

    def delete_document(self, doc_id: str, domain: str) -> None:
        """Remove all chunks for a document from the vector store."""
        self._indexer.delete_by_doc_id(doc_id, domain)

    def retrieve(
        self,
        query: str,
        domain: str = "porto",
        metadata_filter: Optional[Dict[str, Any]] = None,
        top_k: Optional[int] = None,
        user_id: Optional[str] = None,
    ) -> List[RetrievedChunk]:
        retriever = self._get_retriever(domain, user_id)
        result = retriever.retrieve(query, metadata_filter=metadata_filter)
        chunks = result.chunks
        if top_k is not None:
            chunks = chunks[:top_k]
        return chunks

    def retrieve_raw(
        self,
        query: str,
        domain: str = "porto",
        metadata_filter: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ):
        """Return the full RetrievalResult (includes relevance flag, retry info)."""
        return self._get_retriever(domain, user_id).retrieve(
            query, metadata_filter=metadata_filter
        )

    def embed_query(self, query: str):
        return self._embedder.embed_query(query)

    def embed_passages(self, passages: List[str]):
        return self._embedder.embed_passages(passages)

    def _get_retriever(self, domain: str, user_id: Optional[str] = None) -> HybridRetriever:
        key = f"{domain}:{user_id}"
        if key not in self._retrievers:
            self._retrievers[key] = HybridRetriever(
                self.config.embedding,
                self.config.retrieval,
                self.config.vector_db,
                dsn=self.dsn,
                domain=domain,
                user_id=user_id,
                llm_fn=self._llm_fn,
            )
        return self._retrievers[key]