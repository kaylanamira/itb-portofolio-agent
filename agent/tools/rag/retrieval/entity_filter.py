import logging
from typing import Literal, Optional

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

from agent.llm import get_llm
from agent.state import DetectedEntities
from core.utils import extract_json_from_llm
from agent.tools.fuzzy_search import fuzzy_resolve_entities, FuzzyResolutionError
from agent.prompts.rag_prompts import (
    ENTITY_EXTRACTION_SYSTEM_PROMPT,
    build_entity_extraction_human_message,
)

logger = logging.getLogger(__name__)


class RagEntityExtraction(BaseModel):
    dosen_mention: Optional[str] = None
    kode_matkul: Optional[str] = None
    nama_matkul: Optional[str] = None
    tahun: Optional[int] = None
    tahun_ajaran: Optional[str] = None
    no_prodi: Optional[int] = None
    kode_prodi: Optional[str] = None
    semester: Optional[int] = None
    sentiment_hint: Optional[Literal["positive", "negative", "neutral"]] = None
    is_verifikator: Optional[bool] = None


class RetrievalFilters(BaseModel):
    dosen_ids: list[int] = Field(default_factory=list)
    tahun: list[int] = Field(default_factory=list)
    tahun_ajaran: Optional[str] = None
    no_prodi: Optional[int] = None
    kode_matkul: Optional[str] = None
    semester: Optional[int] = None
    sentiment_hint: Optional[Literal["positive", "negative", "neutral"]] = None
    # None = no preference (both dosen narrative and verifikator/reviewer comments);
    # True = only verifikator (reviewer) comments; False = only the dosen's own content.
    is_verifikator: Optional[bool] = None

    def is_empty(self) -> bool:
        return not any([
            self.dosen_ids, self.tahun, self.tahun_ajaran, self.no_prodi,
            self.kode_matkul, self.semester, self.is_verifikator is not None,
        ])

    def to_sql_predicates(self) -> tuple[list[str], list]:
        """Returns (clauses, params) — clauses use %s placeholders in the same
        order as params, meant to be AND-ed onto an existing WHERE clause."""
        clauses: list[str] = []
        params: list = []

        if self.dosen_ids:
            clauses.append("dosen_ids @> %s::int[]")
            params.append(self.dosen_ids)
        if self.tahun:
            clauses.append("tahun = ANY(%s)")
            params.append(self.tahun)
        if self.tahun_ajaran:
            clauses.append("tahun_ajaran = %s")
            params.append(self.tahun_ajaran)
        if self.no_prodi is not None:
            clauses.append("no_prodi = %s")
            params.append(self.no_prodi)
        if self.kode_matkul:
            clauses.append("kode_matkul = %s")
            params.append(self.kode_matkul)
        if self.semester is not None:
            clauses.append("semester = %s")
            params.append(self.semester)
        if self.is_verifikator is not None:
            clauses.append("is_verifikator = %s")
            params.append(self.is_verifikator)

        return clauses, params


class EntityFilterExtractor:
    def __init__(self):
        self.llm = get_llm("rag_entity_extraction")

    async def extract(self, task: str) -> RagEntityExtraction:
        messages = [
            SystemMessage(content=ENTITY_EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=build_entity_extraction_human_message(task)),
        ]
        try:
            response = await self.llm.ainvoke(messages)
            content_dict = extract_json_from_llm(response.content)
            return RagEntityExtraction(**content_dict)
        except Exception as e:
            logger.error(f"Failed to extract RAG entities: {e}")
            return RagEntityExtraction()


async def resolve_filters(task: str) -> RetrievalFilters:
    """Extracts entity mentions from a RAG task and resolves name mentions to
    canonical DB IDs, degrading gracefully (empty name-based filters) on any
    resolution failure rather than blocking retrieval."""
    extraction = await EntityFilterExtractor().extract(task)

    dosen_ids: list[int] = []
    no_prodi: Optional[int] = None
    kode_matkul = extraction.kode_matkul

    has_name_mention = any([
        extraction.dosen_mention, extraction.kode_matkul, extraction.nama_matkul,
        extraction.no_prodi, extraction.kode_prodi,
    ])
    if has_name_mention:
        entities = DetectedEntities(
            nama_dosen=extraction.dosen_mention,
            kode_matkul=extraction.kode_matkul,
            nama_matkul=extraction.nama_matkul,
            no_prodi=str(extraction.no_prodi) if extraction.no_prodi else None,
            kode_prodi=extraction.kode_prodi,
        )
        try:
            resolved = await fuzzy_resolve_entities(entities)
        except FuzzyResolutionError as e:
            logger.warning(f"Entity resolution failed, proceeding without name-based filters: {e}")
            resolved = entities

        dosen_ids = [resolved.resolved_dosen_id] if resolved.resolved_dosen_id else []
        no_prodi = resolved.resolved_prodi_id
        kode_matkul = resolved.kode_matkul or kode_matkul

    return RetrievalFilters(
        dosen_ids=dosen_ids,
        tahun=[extraction.tahun] if extraction.tahun else [],
        tahun_ajaran=extraction.tahun_ajaran,
        no_prodi=no_prodi,
        kode_matkul=kode_matkul,
        semester=extraction.semester,
        sentiment_hint=extraction.sentiment_hint,
        is_verifikator=extraction.is_verifikator,
    )
