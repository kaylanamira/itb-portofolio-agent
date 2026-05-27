"""Fuzzy entity resolution via pg_trgm similarity.

Resolves entity mentions from a query to canonical DB values using
the dev_six schema (utama.dosen, utama.mata_kuliah, etc.).

Configuration:
    All similarity thresholds are defined in FuzzyConfig and can be overridden
    via environment variables for tuning without code changes.
"""

import logging
import os
import re
from dataclasses import dataclass

from agent.state import DetectedEntities
from core.database import get_db_connection

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FuzzyConfig:
    """Configurable similarity thresholds for entity resolution.

    Args:
        name_threshold: Minimum pg_trgm similarity for name-field matches.
        id_threshold: Minimum similarity to commit to a hard-resolved ID.
        code_threshold: Stricter threshold for short code fields (kd_fak, kd_ps).
        ambiguity_gap: Top match must exceed runner-up by this margin to hard-resolve.
    """
    name_threshold: float = float(os.getenv("FUZZY_NAME_THRESHOLD", "0.22"))
    id_threshold: float = float(os.getenv("FUZZY_ID_THRESHOLD", "0.55"))
    code_threshold: float = float(os.getenv("FUZZY_CODE_THRESHOLD", "0.60"))
    ambiguity_gap: float = float(os.getenv("FUZZY_AMBIGUITY_GAP", "0.15"))


DEFAULT_CONFIG = FuzzyConfig()

CLEAN_HONORIFICS_PATTERN = re.compile(
    r"^(pak|bu|prof|dr|ir|drs|dra)\.?\s+", re.IGNORECASE
)


class FuzzyResolutionError(Exception):
    """Raised when entity resolution fails due to a DB or infrastructure error."""


def _is_unambiguous(rows: list[dict], config: FuzzyConfig = DEFAULT_CONFIG, require_id: bool = False) -> bool:
    """Returns True if the top match is clearly better than the runner-up.

    Args:
        rows: Similarity-ranked result rows, each with a 'sim' key.
        config: FuzzyConfig with thresholds.
        require_id: If True, also requires top score >= config.id_threshold.
    """
    if not rows:
        return False
    top_sim = rows[0]["sim"]
    if require_id and top_sim < config.id_threshold:
        return False
    if len(rows) == 1:
        return True
    return (top_sim - rows[1]["sim"]) >= config.ambiguity_gap


async def fuzzy_resolve_entities(
    entities: DetectedEntities,
    config: FuzzyConfig = DEFAULT_CONFIG,
) -> DetectedEntities:
    """Resolves entity mentions to canonical DB values via pg_trgm.

    Args:
        entities: DetectedEntities with raw LLM-extracted values.
        config: FuzzyConfig controlling similarity thresholds.

    Returns:
        Updated DetectedEntities with resolved IDs and canonical names.

    Raises:
        FuzzyResolutionError: If a database connectivity error occurs.
    """
    updates: dict = {}
    candidates: dict[str, list[dict]] = {}

    try:
        async with get_db_connection() as conn:

            # ── mata_kuliah by name ──
            if entities.nama_mk and not entities.resolved_matkul_id:
                rows = await _query_many(conn, """
                    SELECT mata_kuliah_id, kd_kuliah, nama->>'id' AS nama_id,
                        GREATEST(
                            similarity(nama->>'id', %s::text),
                            similarity(COALESCE(nama->>'en', ''), %s::text)
                        ) AS sim
                    FROM utama.mata_kuliah
                    WHERE active = TRUE
                    ORDER BY sim DESC
                    LIMIT 3
                """, (entities.nama_mk, entities.nama_mk), threshold=config.name_threshold)

                if rows:
                    updates["nama_mk"] = rows[0]["nama_id"]
                    if _is_unambiguous(rows, config, require_id=True):
                        updates["kode_mk"] = updates.get("kode_mk") or rows[0]["kd_kuliah"]
                        updates["resolved_matkul_id"] = rows[0]["mata_kuliah_id"]
                    else:
                        candidates["nama_mk"] = [
                            {"nama_mk": r["nama_id"], "kode_mk": r["kd_kuliah"], "sim": r["sim"]}
                            for r in rows
                        ]

            # ── mata_kuliah by code ──
            if entities.kode_mk and not updates.get("kode_mk") and not entities.resolved_matkul_id:
                rows = await _query_many(conn, """
                    SELECT mata_kuliah_id, kd_kuliah, nama->>'id' AS nama_id,
                           similarity(kd_kuliah::text, %s::text) AS sim
                    FROM utama.mata_kuliah
                    WHERE active = TRUE
                    ORDER BY sim DESC
                    LIMIT 3
                """, (entities.kode_mk.upper(),), threshold=config.code_threshold)

                if rows:
                    if _is_unambiguous(rows, config, require_id=True):
                        updates["kode_mk"] = rows[0]["kd_kuliah"]
                        updates["nama_mk"] = updates.get("nama_mk") or rows[0]["nama_id"]
                        updates["resolved_matkul_id"] = rows[0]["mata_kuliah_id"]
                    else:
                        candidates["kode_mk"] = [
                            {"kode_mk": r["kd_kuliah"], "nama_mk": r["nama_id"], "sim": r["sim"]}
                            for r in rows
                        ]

            # ── dosen by name ──
            if entities.nama_dosen and not entities.resolved_dosen_id:
                mention = entities.nama_dosen.strip()
                clean_mention = CLEAN_HONORIFICS_PATTERN.sub("", mention).strip()

                rows = await _query_many(conn, """
                    SELECT dosen_id, nama_gelar,
                           GREATEST(
                               similarity(nama_gelar::text, %s::text),
                               similarity(nama_gelar::text, %s::text)
                           ) AS sim
                    FROM utama.dosen
                    WHERE active = TRUE
                    ORDER BY sim DESC
                    LIMIT 3
                """, (mention, clean_mention), threshold=config.name_threshold)

                if rows:
                    updates["nama_dosen"] = rows[0]["nama_gelar"]
                    if _is_unambiguous(rows, config, require_id=True):
                        updates["resolved_dosen_id"] = rows[0]["dosen_id"]
                    else:
                        candidates["nama_dosen"] = [
                            {"nama_dosen": r["nama_gelar"], "dosen_id": r["dosen_id"], "sim": r["sim"]}
                            for r in rows
                        ]

            # ── program_studi by abbreviation ──
            if entities.singkatan_prodi and not entities.resolved_prodi_id:
                rows = await _query_many(conn, """
                    SELECT no_ps, kd_ps, nama->>'id' AS nama_id,
                           GREATEST(
                               similarity(kd_ps::text, %s::text),
                               similarity(nama->>'id', %s::text)
                           ) AS sim
                    FROM utama.program_studi
                    WHERE active = TRUE
                    ORDER BY sim DESC
                    LIMIT 3
                """, (entities.singkatan_prodi, entities.singkatan_prodi),
                    threshold=config.name_threshold)

                if rows:
                    if _is_unambiguous(rows, config, require_id=True):
                        updates["singkatan_prodi"] = rows[0]["kd_ps"]
                        updates["kode_prodi"] = str(rows[0]["no_ps"])
                        updates["resolved_prodi_id"] = rows[0]["no_ps"]
                    else:
                        candidates["singkatan_prodi"] = [
                            {"singkatan_prodi": r["kd_ps"], "nama_prodi": r["nama_id"], "sim": r["sim"]}
                            for r in rows
                        ]

            # ── program_studi by numeric code ──
            if (
                entities.kode_prodi
                and not updates.get("resolved_prodi_id")
                and not entities.resolved_prodi_id
            ):
                rows = await _query_many(conn, """
                    SELECT no_ps, kd_ps, nama->>'id' AS nama_id,
                           GREATEST(
                               similarity(no_ps::text, %s::text),
                               similarity(COALESCE(kd_ps,'')::text, %s::text),
                               similarity(nama->>'id', %s::text)
                           ) AS sim
                    FROM utama.program_studi
                    WHERE active = TRUE
                    ORDER BY sim DESC
                    LIMIT 3
                """, (entities.kode_prodi, entities.kode_prodi, entities.kode_prodi),
                    threshold=config.name_threshold)

                if rows:
                    if _is_unambiguous(rows, config, require_id=True):
                        updates["kode_prodi"] = str(rows[0]["no_ps"])
                        updates["singkatan_prodi"] = updates.get("singkatan_prodi") or rows[0]["kd_ps"]
                        updates["resolved_prodi_id"] = rows[0]["no_ps"]
                    else:
                        candidates["kode_prodi"] = [
                            {"kode_prodi": str(r["no_ps"]), "nama_prodi": r["nama_id"], "sim": r["sim"]}
                            for r in rows
                        ]

            # ── program_studi by name ──
            if (
                entities.nama_prodi
                and not updates.get("resolved_prodi_id")
                and not entities.resolved_prodi_id
            ):
                rows = await _query_many(conn, """
                    SELECT no_ps, kd_ps, nama->>'id' AS nama_id,
                           similarity(nama->>'id', %s::text) AS sim
                    FROM utama.program_studi
                    WHERE active = TRUE
                    ORDER BY sim DESC
                    LIMIT 3
                """, (entities.nama_prodi,),
                    threshold=config.name_threshold)

                if rows:
                    if _is_unambiguous(rows, config, require_id=True):
                        updates["kode_prodi"] = str(rows[0]["no_ps"])
                        updates["singkatan_prodi"] = updates.get("singkatan_prodi") or rows[0]["kd_ps"]
                        updates["resolved_prodi_id"] = rows[0]["no_ps"]
                        updates["nama_prodi"] = rows[0]["nama_id"]
                    else:
                        candidates["nama_prodi"] = [
                            {"kode_prodi": str(r["no_ps"]), "nama_prodi": r["nama_id"], "sim": r["sim"]}
                            for r in rows
                        ]

            # ── fakultas by code ──
            if entities.kode_fakultas and not updates.get("kode_fakultas"):
                rows = await _query_many(conn, """
                    SELECT kd_fak, nama->>'id' AS nama_id,
                           GREATEST(
                               similarity(kd_fak::text, %s::text),
                               similarity(nama->>'id', %s::text)
                           ) AS sim
                    FROM utama.fakultas
                    WHERE active = TRUE
                    ORDER BY sim DESC
                    LIMIT 3
                """, (entities.kode_fakultas, entities.kode_fakultas),
                    threshold=config.code_threshold)

                if rows:
                    if _is_unambiguous(rows, config):
                        updates["kode_fakultas"] = rows[0]["kd_fak"]
                        updates["nama_fakultas"] = updates.get("nama_fakultas") or rows[0]["nama_id"]
                    else:
                        candidates["kode_fakultas"] = [
                            {"kode_fakultas": r["kd_fak"], "nama_fakultas": r["nama_id"], "sim": r["sim"]}
                            for r in rows
                        ]

            # ── fakultas by name ──
            if entities.nama_fakultas and not updates.get("kode_fakultas"):
                rows = await _query_many(conn, """
                    SELECT kd_fak, nama->>'id' AS nama_id,
                           similarity(nama->>'id', %s::text) AS sim
                    FROM utama.fakultas
                    WHERE active = TRUE
                    ORDER BY sim DESC
                    LIMIT 3
                """, (entities.nama_fakultas,),
                    threshold=config.name_threshold)

                if rows:
                    if _is_unambiguous(rows, config):
                        updates["kode_fakultas"] = rows[0]["kd_fak"]
                        updates["nama_fakultas"] = rows[0]["nama_id"]
                    else:
                        candidates["nama_fakultas"] = [
                            {"kode_fakultas": r["kd_fak"], "nama_fakultas": r["nama_id"], "sim": r["sim"]}
                            for r in rows
                        ]

    except FuzzyResolutionError:
        raise
    except Exception as exc:
        raise FuzzyResolutionError(f"Entity resolution failed: {exc}") from exc

    if candidates:
        updates["entity_candidates"] = candidates

    if updates:
        return entities.model_copy(update=updates)
    return entities


async def _query_many(conn, sql: str, params: tuple, threshold: float) -> list[dict]:
    """Executes a similarity query and returns rows above threshold.

    Args:
        conn: Async DB connection.
        sql: Query string with %s placeholders.
        params: Query parameters.
        threshold: Minimum 'sim' value to include a row.

    Returns:
        List of dicts, each row as {column: value}, filtered by threshold.
    """
    cur = await conn.execute(sql, params)
    rows = await cur.fetchall()
    if not rows:
        return []
    cols = [desc[0] for desc in cur.description]
    sim_idx = cols.index("sim")
    return [
        dict(zip(cols, row))
        for row in rows
        if row[sim_idx] >= threshold
    ]
