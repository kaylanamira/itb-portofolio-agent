"""
Fuzzy entity resolution via pg_trgm similarity.

Resolves entity mentions from a query to canonical DB values.
Unambiguous matches set resolved_* UUID and canonical name.
Ambiguous matches populate entity_candidates for ILIKE fallback in SQL generation.

Thresholds:
  SIMILARITY_THRESHOLD_NAME: minimum similarity for name fields
  SIMILARITY_THRESHOLD_UUID: minimum similarity to commit a UUID resolution
  SIMILARITY_THRESHOLD_CODE: stricter threshold for code fields (kode_mk, kode_fakultas)
  AMBIGUITY_GAP: top match must exceed runner-up by this margin to hard-resolve
"""

import logging
import re
from agent.state import DetectedEntities
from core.database import get_db_connection

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD_NAME = 0.22
SIMILARITY_THRESHOLD_UUID = 0.55
SIMILARITY_THRESHOLD_CODE = 0.60
AMBIGUITY_GAP = 0.15

CLEAN_HONORIFICS_PATTERN = re.compile(r"^(pak|bu|prof|dr|ir|drs|dra)\.?\s+", re.IGNORECASE)


def _is_unambiguous(rows: list[dict], uuid_resolve: bool = False) -> bool:
    """
    Returns True if the top match is clearly better than the runner-up.

    Args:
        rows: similarity-ranked result rows, each with a 'sim' key.
        uuid_resolve: if True, also requires top score >= SIMILARITY_THRESHOLD_UUID.
    """
    if not rows:
        return False
    top_sim = rows[0]["sim"]
    if uuid_resolve and top_sim < SIMILARITY_THRESHOLD_UUID:
        return False
    if len(rows) == 1:
        return True
    return (top_sim - rows[1]["sim"]) >= AMBIGUITY_GAP


async def fuzzy_resolve_entities(entities: DetectedEntities) -> DetectedEntities:
    """
    Resolves entity mentions to canonical DB values via pg_trgm.

    Args:
        entities: DetectedEntities with raw LLM-extracted values.

    Returns:
        Updated DetectedEntities where unambiguous matches have resolved_* UUID
        and canonical name set; ambiguous matches have entity_candidates populated.
    """
    updates: dict = {}
    candidates: dict[str, list[dict]] = {}

    try:
        async with get_db_connection() as conn:

            if entities.nama_mk and not entities.resolved_matkul_id:
                rows = await _query_many(conn, """
                    SELECT matkul_id, kode_mk, nama_mk,
                        GREATEST(
                            similarity(nama_mk, %s),
                            similarity(COALESCE(nama_mk_en, ''), %s)
                        ) AS sim
                    FROM mata_kuliah
                    WHERE is_active = TRUE
                    ORDER BY sim DESC
                    LIMIT 3
                """, (entities.nama_mk, entities.nama_mk), threshold=SIMILARITY_THRESHOLD_NAME)

                if rows:
                    updates["nama_mk"] = rows[0]["nama_mk"]
                    if _is_unambiguous(rows, uuid_resolve=True):
                        updates["kode_mk"] = updates.get("kode_mk") or rows[0]["kode_mk"]
                        updates["resolved_matkul_id"] = rows[0]["matkul_id"]
                    else:
                        candidates["nama_mk"] = [
                            {"nama_mk": r["nama_mk"], "kode_mk": r["kode_mk"], "sim": r["sim"]}
                            for r in rows
                        ]

            if entities.kode_mk and not updates.get("kode_mk") and not entities.resolved_matkul_id:
                rows = await _query_many(conn, """
                    SELECT matkul_id, kode_mk, nama_mk,
                           similarity(kode_mk, %s) AS sim
                    FROM mata_kuliah
                    WHERE is_active = TRUE
                    ORDER BY sim DESC
                    LIMIT 3
                """, (entities.kode_mk.upper(),), threshold=SIMILARITY_THRESHOLD_CODE)

                if rows:
                    if _is_unambiguous(rows, uuid_resolve=True):
                        updates["kode_mk"] = rows[0]["kode_mk"]
                        updates["nama_mk"] = updates.get("nama_mk") or rows[0]["nama_mk"]
                        updates["resolved_matkul_id"] = rows[0]["matkul_id"]
                    else:
                        candidates["kode_mk"] = [
                            {"kode_mk": r["kode_mk"], "nama_mk": r["nama_mk"], "sim": r["sim"]}
                            for r in rows
                        ]

            if entities.nama_dosen and not entities.resolved_dosen_id:
                mention = entities.nama_dosen.strip()
                clean_mention = CLEAN_HONORIFICS_PATTERN.sub("", mention)

                rows = await _query_many(conn, """
                    SELECT dosen_id, nama_dosen,
                           GREATEST(
                               similarity(nama_dosen, %s),
                               similarity(nama_dosen, %s)
                           ) AS sim
                    FROM dosen
                    WHERE is_active = TRUE
                    ORDER BY sim DESC
                    LIMIT 3
                """, (mention, clean_mention), threshold=SIMILARITY_THRESHOLD_NAME)

                if rows:
                    updates["nama_dosen"] = rows[0]["nama_dosen"]
                    if _is_unambiguous(rows, uuid_resolve=True):
                        updates["resolved_dosen_id"] = rows[0]["dosen_id"]
                    else:
                        candidates["nama_dosen"] = [
                            {"nama_dosen": r["nama_dosen"], "dosen_id": str(r["dosen_id"]), "sim": r["sim"]}
                            for r in rows
                        ]

            if entities.kode_prodi and not entities.resolved_prodi_id:
                rows = await _query_many(conn, """
                    SELECT prodi_id, kode_prodi, singkatan_prodi, nama_prodi,
                           GREATEST(
                               similarity(kode_prodi, %s),
                               similarity(COALESCE(singkatan_prodi,''), %s),
                               similarity(nama_prodi, %s)
                           ) AS sim
                    FROM program_studi
                    WHERE is_active = TRUE
                    ORDER BY sim DESC
                    LIMIT 3
                """, (entities.kode_prodi, entities.kode_prodi, entities.kode_prodi),
                    threshold=SIMILARITY_THRESHOLD_NAME)

                if rows:
                    if _is_unambiguous(rows, uuid_resolve=True):
                        updates["kode_prodi"] = rows[0]["kode_prodi"]
                        updates["resolved_prodi_id"] = rows[0]["prodi_id"]
                    else:
                        candidates["kode_prodi"] = [
                            {"kode_prodi": r["kode_prodi"], "nama_prodi": r["nama_prodi"], "sim": r["sim"]}
                            for r in rows
                        ]

            if entities.kode_fakultas:
                rows = await _query_many(conn, """
                    SELECT fakultas_id, kode_fakultas, nama_fakultas,
                           GREATEST(
                               similarity(kode_fakultas, %s),
                               similarity(nama_fakultas, %s)
                           ) AS sim
                    FROM fakultas
                    WHERE is_active = TRUE
                    ORDER BY sim DESC
                    LIMIT 3
                """, (entities.kode_fakultas, entities.kode_fakultas),
                    threshold=SIMILARITY_THRESHOLD_CODE)

                if rows:
                    if _is_unambiguous(rows):
                        updates["kode_fakultas"] = rows[0]["kode_fakultas"]
                    else:
                        candidates["kode_fakultas"] = [
                            {"kode_fakultas": r["kode_fakultas"], "nama_fakultas": r["nama_fakultas"], "sim": r["sim"]}
                            for r in rows
                        ]

    except Exception as exc:
        logger.warning("fuzzy_resolve_entities failed: %s", exc)

    if candidates:
        updates["entity_candidates"] = candidates

    if updates:
        return entities.model_copy(update=updates)
    return entities


async def _query_many(conn, sql: str, params: tuple, threshold: float) -> list[dict]:
    """
    Executes a similarity query and returns rows above threshold.

    Args:
        conn: async DB connection.
        sql: query string with %s placeholders.
        params: query parameters.
        threshold: minimum 'sim' value to include a row.

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
