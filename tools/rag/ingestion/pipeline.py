from __future__ import annotations

import argparse
import logging
from typing import Iterator, List

from tools.rag.config import RAGConfig
from tools.rag.core.models import RawDocument
from tools.rag.ingestion.chunker import PortoDocumentFactory, WisudawanDocumentFactory
from tools.rag.rag_tool import RAGTool

logger = logging.getLogger(__name__)

PORTO_TEKS_QUERY = """
SELECT
    tp.teks_id,
    tp.kelas_id,
    mk.matkul_id,
    ps.prodi_id,
    ps.kode_prodi,
    ps.fakultas_id,
    tp.tipe_konten,
    tp.konten,
    k.tahun_ajaran,
    k.semester,
    mk.kode_mk,
    mk.nama_mk,
    -- Aggregate dosen names
    array_agg(DISTINCT d.nama_dosen) FILTER (WHERE d.nama_dosen IS NOT NULL) AS dosen_names
FROM teks_portofolio tp
JOIN kelas k ON k.kelas_id = tp.kelas_id
JOIN mata_kuliah mk ON mk.matkul_id = k.matkul_id
JOIN program_studi ps ON ps.prodi_id = mk.prodi_id
LEFT JOIN pengajar_kelas pk ON pk.kelas_id = k.kelas_id
LEFT JOIN dosen d ON d.dosen_id = pk.dosen_id
WHERE tp.is_embedded = FALSE OR %(force_reindex)s
GROUP BY tp.teks_id, tp.kelas_id, mk.matkul_id, ps.prodi_id, ps.kode_prodi,
         ps.fakultas_id, tp.tipe_konten, tp.konten, k.tahun_ajaran,
         k.semester, mk.kode_mk, mk.nama_mk
ORDER BY tp.teks_id
"""

PORTO_KOMENTAR_QUERY = """
SELECT
    km.komentar_id,
    km.kelas_id,
    mk.matkul_id,
    ps.prodi_id,
    ps.fakultas_id,
    km.teks_komentar,
    k.tahun_ajaran,
    k.semester,
    mk.kode_mk
FROM komentar_mahasiswa km
JOIN kelas k ON k.kelas_id = km.kelas_id
JOIN mata_kuliah mk ON mk.matkul_id = k.matkul_id
JOIN program_studi ps ON ps.prodi_id = mk.prodi_id
WHERE (km.is_embedded = FALSE OR %(force_reindex)s)
  AND km.teks_komentar IS NOT NULL
  AND length(trim(km.teks_komentar)) > 10
ORDER BY km.komentar_id
"""

MARK_TEKS_EMBEDDED = """
UPDATE teks_portofolio
SET is_embedded = TRUE, embedded_at = NOW()
WHERE teks_id = ANY(%(ids)s::uuid[])
"""

MARK_KOMENTAR_EMBEDDED = """
UPDATE komentar_mahasiswa
SET is_embedded = TRUE, embedded_at = NOW()
WHERE komentar_id = ANY(%(ids)s::uuid[])
"""

WISUDAWAN_QUERY = """
SELECT
    r.responden_id,
    r.strata,
    r.kode_fak,
    r.kode_prodi,
    r.periode_ijazah,
    -- Open-ended text fields
    r.kebiasaan_belajar,
    r.kesan_prestasi,
    r.pengalaman_berkesan,
    r.aktivitas_kemahasiswaan,
    r.cita_karier,
    r.cita_hidup,
    r.motto,
    r.sifat_khas,
    r.suka_duka,
    r.segi_positif,
    r.segi_negatif,
    r.saran_itb,
    r.saran_mhs_lain,
    r.catatan_lain
FROM wisudawan_responden r
WHERE (r.is_embedded = FALSE OR %(force_reindex)s)
ORDER BY r.responden_id
"""

MARK_WISUDAWAN_EMBEDDED = """
UPDATE wisudawan_responden
SET is_embedded = TRUE, embedded_at = NOW()
WHERE responden_id = ANY(%(ids)s::uuid[])
"""

def _batched(iterable, n: int):
    """Yield successive n-size chunks from a list."""
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) == n:
            yield batch
            batch = []
    if batch:
        yield batch


def run_porto_pipeline(
    dsn: str,
    rag_tool: RAGTool,
    batch_size: int = 128,
    force_reindex: bool = False,
    user_id: str = "admin",
) -> None:
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(dsn)
    conn.execute(f"SET app.user_id = '{user_id}'")  # RLS context
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Index teks_portofolio
    cur.execute(PORTO_TEKS_QUERY, {"force_reindex": force_reindex})
    rows = cur.fetchall()
    logger.info(f"[Porto] {len(rows)} teks_portofolio rows to index")

    teks_ids = []
    for batch in _batched(rows, batch_size):
        docs = [PortoDocumentFactory.from_teks_row(dict(r)) for r in batch]
        rag_tool.ingest_documents(docs)
        teks_ids.extend([str(r["teks_id"]) for r in batch])

    if teks_ids:
        cur.execute(MARK_TEKS_EMBEDDED, {"ids": teks_ids})

    # Index komentar_mahasiswa
    cur.execute(PORTO_KOMENTAR_QUERY, {"force_reindex": force_reindex})
    rows = cur.fetchall()
    logger.info(f"[Porto] {len(rows)} komentar_mahasiswa rows to index")

    kom_ids = []
    for batch in _batched(rows, batch_size):
        docs = [PortoDocumentFactory.from_komentar_row(dict(r)) for r in batch]
        rag_tool.ingest_documents(docs)
        kom_ids.extend([str(r["komentar_id"]) for r in batch])

    if kom_ids:
        cur.execute(MARK_KOMENTAR_EMBEDDED, {"ids": kom_ids})

    conn.commit()
    cur.close()
    conn.close()
    logger.info("[Porto] Ingestion pipeline complete.")


def run_wisudawan_pipeline(
    dsn: str,
    rag_tool: RAGTool,
    batch_size: int = 64,
    force_reindex: bool = False,
) -> None:
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(dsn)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(WISUDAWAN_QUERY, {"force_reindex": force_reindex})
    rows = cur.fetchall()
    logger.info(f"[Wisudawan] {len(rows)} responden rows to index")

    resp_ids = []
    for batch in _batched(rows, batch_size):
        docs: List[RawDocument] = []
        for row in batch:
            docs.extend(WisudawanDocumentFactory.from_responden_row(dict(row)))
        rag_tool.ingest_documents(docs)
        resp_ids.extend([str(r["responden_id"]) for r in batch])

    if resp_ids:
        cur.execute(MARK_WISUDAWAN_EMBEDDED, {"ids": resp_ids})

    conn.commit()
    cur.close()
    conn.close()
    logger.info("[Wisudawan] Ingestion pipeline complete.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="RAG Ingestion Pipeline")
    parser.add_argument("domain", choices=["porto", "wisudawan"])
    parser.add_argument("--dsn", required=True, help="PostgreSQL DSN")
    parser.add_argument("--force", action="store_true", help="Force reindex all")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    cfg = RAGConfig()
    cfg.postgres_dsn = args.dsn
    tool = RAGTool(cfg, dsn=args.dsn)
    tool.ensure_schema()

    if args.domain == "porto":
        run_porto_pipeline(args.dsn, tool, args.batch_size, args.force)
    else:
        run_wisudawan_pipeline(args.dsn, tool, args.batch_size, args.force)