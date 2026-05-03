"""
Fuzzy entity resolution.

Thresholds:
  - nama_mk, nama_dosen, nama_prodi, nama_fakultas: similarity >= 0.25 (lenient, short strings common)
  - kode_mk, kode_fakultas:             similarity >= 0.6  (codes are short; stricter)
  
Only fields present on DetectedEntities are resolved.
UUID fields (resolved_*) are populated if a match is found.
"""

import logging
import re
from agent.state import DetectedEntities
from core.database import get_db_connection

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD_NAME = 0.22 
SIMILARITY_THRESHOLD_CODE = 0.60

# Pattern to strip Indonesian honorifics
CLEAN_HONORIFICS_PATTERN = re.compile(r"^(pak|bu|prof|dr|ir|drs|dra)\.?\s+", re.IGNORECASE)

async def fuzzy_resolve_entities(entities: DetectedEntities) -> DetectedEntities:
    """
    Resolve entity mentions in `entities` to canonical DB values via pg_trgm.
    """
    updates: dict = {}

    try:
        async with get_db_connection() as conn:

            # ── Resolve mata_kuliah ───────────────────────────────────────────
            if entities.nama_mk and not entities.resolved_kelas_id:
                row = await _query_one(conn, """
                    SELECT matkul_id, kode_mk, nama_mk,
                        GREATEST(
                            similarity(nama_mk, %s),
                            similarity(COALESCE(nama_mk_en, ''), %s)
                        ) AS sim
                    FROM mata_kuliah
                    WHERE is_active = TRUE
                    ORDER BY sim DESC
                    LIMIT 1
                """, (entities.nama_mk, entities.nama_mk))

                if row and row["sim"] >= SIMILARITY_THRESHOLD_NAME:
                    logger.debug("Resolved nama_mk '%s' → '%s' (%.2f)",
                                 entities.nama_mk, row["nama_mk"], row["sim"])
                    updates["nama_mk"] = row["nama_mk"]
                    updates["kode_mk"] = updates.get("kode_mk") or row["kode_mk"]

            # ── Resolve kode_mk (if not already resolved via nama_mk) ─────────
            if entities.kode_mk and not updates.get("kode_mk"):
                row = await _query_one(conn, """
                    SELECT matkul_id, kode_mk, nama_mk,
                           similarity(kode_mk, %s) AS sim
                    FROM mata_kuliah
                    WHERE is_active = TRUE
                    ORDER BY sim DESC
                    LIMIT 1
                """, (entities.kode_mk.upper(),))

                if row and row["sim"] >= SIMILARITY_THRESHOLD_CODE:
                    logger.debug("Resolved kode_mk '%s' → '%s' (%.2f)",
                                 entities.kode_mk, row["kode_mk"], row["sim"])
                    updates["kode_mk"] = row["kode_mk"]
                    updates["nama_mk"] = updates.get("nama_mk") or row["nama_mk"]

            # ── Resolve nama_dosen ────────────────────────────────────────────
            if entities.nama_dosen and not entities.resolved_dosen_id:
                # Clean mention: strip "Pak", "Bu", etc.
                mention = entities.nama_dosen.strip()
                clean_mention = CLEAN_HONORIFICS_PATTERN.sub("", mention)
                
                # Narrow first by kode_prodi if available (faster + more accurate)
                if entities.kode_prodi:
                    row = await _query_one(conn, """
                        SELECT d.dosen_id, d.nama_dosen,
                               GREATEST(
                                   similarity(d.nama_dosen, %s),
                                   similarity(d.nama_dosen, %s)
                               ) AS sim
                        FROM dosen d
                        JOIN kelompok_keahlian kk ON kk.kk_id = d.kk_id
                        JOIN program_studi ps ON ps.fakultas_id = kk.fakultas_id
                        WHERE ps.kode_prodi = %s
                          AND d.is_active = TRUE
                        ORDER BY sim DESC
                        LIMIT 1
                    """, (mention, clean_mention, entities.kode_prodi))
                else:
                    row = await _query_one(conn, """
                        SELECT dosen_id, nama_dosen,
                               GREATEST(
                                   similarity(nama_dosen, %s),
                                   similarity(nama_dosen, %s)
                               ) AS sim
                        FROM dosen
                        WHERE is_active = TRUE
                        ORDER BY sim DESC
                        LIMIT 1
                    """, (mention, clean_mention))

                if row and row["sim"] >= SIMILARITY_THRESHOLD_NAME:
                    logger.debug("Resolved nama_dosen '%s' → '%s' (%.2f)",
                                 entities.nama_dosen, row["nama_dosen"], row["sim"])
                    updates["nama_dosen"] = row["nama_dosen"]
                    updates["resolved_dosen_id"] = row["dosen_id"]

            # ── Resolve kode_prodi ────────────────────────────────────────────
            if entities.kode_prodi and not entities.resolved_prodi_id:
                row = await _query_one(conn, """
                    SELECT prodi_id, kode_prodi, singkatan_prodi, nama_prodi,
                           GREATEST(
                               similarity(kode_prodi, %s),
                               similarity(COALESCE(singkatan_prodi,''), %s),
                               similarity(nama_prodi, %s),
                           ) AS sim
                    FROM program_studi
                    WHERE is_active = TRUE
                    ORDER BY sim DESC
                    LIMIT 1
                """, (entities.kode_prodi, entities.kode_prodi, entities.kode_prodi))

                if row and row["sim"] >= SIMILARITY_THRESHOLD_NAME:
                    logger.debug("Resolved kode_prodi '%s' → '%s' (%.2f)",
                                 entities.kode_prodi, row["kode_prodi"], row["sim"])
                    updates["kode_prodi"] = row["kode_prodi"]
                    updates["resolved_prodi_id"] = row["prodi_id"]

            # ── Resolve kode_fakultas ─────────────────────────────────────────
            if entities.kode_fakultas:
                row = await _query_one(conn, """
                    SELECT fakultas_id, kode_fakultas, singkatan_fakultas, nama_fakultas,
                           GREATEST(
                               similarity(kode_fakultas, %s),
                               similarity(COALESCE(singkatan_fakultas,''), %s),
                               similarity(nama_fakultas, %s)
                           ) AS sim
                    FROM fakultas
                    WHERE is_active = TRUE
                    ORDER BY sim DESC
                    LIMIT 1
                """, (entities.kode_fakultas, entities.kode_fakultas, entities.kode_fakultas))

                if row and row["sim"] >= SIMILARITY_THRESHOLD_NAME:
                    logger.debug("Resolved kode_fakultas '%s' → '%s' (%.2f)",
                                 entities.kode_fakultas, row["kode_fakultas"], row["sim"])
                    updates["kode_fakultas"] = row["kode_fakultas"]

    except Exception as exc:
        logger.warning("fuzzy_resolve_entities failed: %s", exc)

    if updates:
        return entities.model_copy(update=updates)
    return entities


async def _query_one(conn, sql: str, params: tuple) -> dict | None:
    """Execute a query and return the first row as a dict, or None."""
    cur = await conn.execute(sql, params)
    row = await cur.fetchone()
    if row is None:
        return None
    cols = [desc[0] for desc in cur.description]
    return dict(zip(cols, row))
