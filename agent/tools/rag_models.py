from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RAGChunk(BaseModel):
    chunk_id: UUID
    source_type: Literal["teks_portofolio", "komentar_mahasiswa"]
    source_id: UUID
    kelas_id: UUID
    chunk_index: int
    chunk_text: str
    score: float = 0.0
    dense_rank: int | None = None
    lexical_rank: int | None = None
    rrf_score: float = 0.0
    tipe_konten: str | None = None
    kode_mk: str
    kode_prodi: str
    kode_fakultas: str
    no_kelas: str
    semester: int
    tahun_ajaran: str
    nama_mk: str
    nama_prodi: str
    nama_fakultas: str
    jenjang: str
    semua_dosen_id: list[UUID] = Field(default_factory=list)
    semua_dosen_nama: list[str] = Field(default_factory=list)
    kelas_label: str
    expanded_from_parent: bool = False


class RAGRetrievalRequest(BaseModel):
    query: str
    user_id: UUID
    source_types: list[str] | None = None
    tipe_konten: list[str] | None = None
    scope_override: dict | None = None
    keywords: list[str] = Field(default_factory=list)
    top_k: int
    top_k_after_rrf: int
    query_type: str | None = None


class RAGRetrievalResult(BaseModel):
    query: str
    chunks: list[RAGChunk]
    cache_hit: bool = False


class CRAGEvaluation(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0)
    action: Literal["accept", "refine", "fallback"]
    refine_suggestion: str | None = None
    reasoning: str = ""


class FaithfulnessEvaluation(BaseModel):
    grounding_score: float = Field(ge=0.0, le=1.0)
    action: Literal["accept", "revise", "flag"]
    unsupported_claims: list[str] = Field(default_factory=list)
    reasoning: str = ""
