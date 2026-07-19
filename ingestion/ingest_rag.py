import argparse
import asyncio
import logging
from typing import List, Dict, Any, Optional

from psycopg.rows import dict_row
from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.database import get_db_connection, init_db_pool, close_db_pool
from core.config import settings
from agent.tools.rag.core.embedder import aembed_passage_texts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PORTOFOLIO_COLUMNS = [
    "metode_perkuliahan",
    "sistem_penilaian",
    "statistik_kelas",
    "analisis_terhadap_statistik_kelas_dan_ketercapaian_outcomes",
    "komentar_terhadap_hasil_kuesioner_mahasiswa",
    "refleksi_pelaksanaan_perkuliahan",
    "usulan_perbaikan_oleh_dosen_berikutnya",
    "usulan_perbaikan_oleh_itb",
    "verifikator_penyelenggaraan_perkuliahan",
    "verifikator_ketercapaian_outcomes",
    "verifikator_refleksi_dosen",
    "verifikator_rekomendasi_tindak_lanjut",
]

_METADATA_SELECT_KOMENTAR = """
    kelas_id, jawaban_id::text AS source_id, komentar_teks, 'komentar' AS tipe_konten,
    kode_matkul, nama_matkul_id AS nama_matkul, sks, no_kelas, semester, tahun, tahun_ajaran,
    no_prodi, kode_prodi, nama_prodi_id AS nama_prodi, jenjang, kode_fakultas,
    nama_fakultas_id AS nama_fakultas, semua_dosen_id AS dosen_ids, semua_dosen_nama_gelar AS dosen_names
"""

_METADATA_SELECT_PORTOFOLIO = """
    kelas_id, kelas_id::text AS source_id,
    kode_matkul, nama_matkul_id AS nama_matkul, sks, no_kelas, semester, tahun, tahun_ajaran,
    no_prodi, kode_prodi, nama_prodi_id AS nama_prodi, jenjang, kode_fakultas,
    nama_fakultas_id AS nama_fakultas, semua_dosen_id AS dosen_ids, semua_dosen_nama_gelar AS dosen_names,
    nilai_portofolio, lengkap, tanggal_entri,
    metode_perkuliahan, sistem_penilaian, statistik_kelas,
    analisis_terhadap_statistik_kelas_dan_ketercapaian_outcomes,
    komentar_terhadap_hasil_kuesioner_mahasiswa, refleksi_pelaksanaan_perkuliahan,
    usulan_perbaikan_oleh_dosen_berikutnya, usulan_perbaikan_oleh_itb,
    verifikator_penyelenggaraan_perkuliahan, verifikator_ketercapaian_outcomes,
    verifikator_refleksi_dosen, verifikator_rekomendasi_tindak_lanjut
"""

SQL_INSERT_CHUNK = """
    INSERT INTO analitik.vector_chunks (
        source_type, source_id, kelas_id, tipe_konten, chunk_index, chunk_text, embedding,
        kode_matkul, nama_matkul, sks, no_kelas, semester, tahun, tahun_ajaran,
        no_prodi, kode_prodi, nama_prodi, jenjang, kode_fakultas, nama_fakultas,
        dosen_ids, dosen_names, nilai_portofolio, lengkap, tanggal_entri, is_verifikator
    )
    VALUES (
        %(source_type)s, %(source_id)s, %(kelas_id)s, %(tipe_konten)s, %(chunk_index)s,
        %(chunk_text)s, %(embedding)s::vector,
        %(kode_matkul)s, %(nama_matkul)s, %(sks)s, %(no_kelas)s, %(semester)s, %(tahun)s, %(tahun_ajaran)s,
        %(no_prodi)s, %(kode_prodi)s, %(nama_prodi)s, %(jenjang)s, %(kode_fakultas)s, %(nama_fakultas)s,
        %(dosen_ids)s, %(dosen_names)s, %(nilai_portofolio)s, %(lengkap)s, %(tanggal_entri)s, %(is_verifikator)s
    )
"""

_VERIFIKATOR_PREFIX = "verifikator_"


def _filter_clause(kode_prodi: Optional[str], tahun: Optional[int]) -> tuple[str, tuple]:
    clauses, params = [], []
    if kode_prodi:
        clauses.append("kode_prodi = %s")
        params.append(kode_prodi)
    if tahun:
        clauses.append("tahun = %s")
        params.append(tahun)
    return (" AND " + " AND ".join(clauses)) if clauses else "", tuple(params)


def _row_metadata(row: Dict[str, Any], is_portofolio: bool) -> Dict[str, Any]:
    return {
        "kode_matkul": row.get("kode_matkul"),
        "nama_matkul": row.get("nama_matkul"),
        "sks": row.get("sks"),
        "no_kelas": row.get("no_kelas"),
        "semester": row.get("semester"),
        "tahun": row.get("tahun"),
        "tahun_ajaran": row.get("tahun_ajaran"),
        "no_prodi": row.get("no_prodi"),
        "kode_prodi": row.get("kode_prodi"),
        "nama_prodi": row.get("nama_prodi"),
        "jenjang": row.get("jenjang"),
        "kode_fakultas": row.get("kode_fakultas"),
        "nama_fakultas": row.get("nama_fakultas"),
        "dosen_ids": list(row.get("dosen_ids") or []),
        "dosen_names": list(row.get("dosen_names") or []),
        "nilai_portofolio": row.get("nilai_portofolio") if is_portofolio else None,
        "lengkap": row.get("lengkap") if is_portofolio else None,
        "tanggal_entri": row.get("tanggal_entri") if is_portofolio else None,
    }


async def fetch_komentar(conn, kode_prodi: Optional[str], tahun: Optional[int]) -> List[Dict[str, Any]]:
    filter_sql, params = _filter_clause(kode_prodi, tahun)
    sql = f"""
        SELECT {_METADATA_SELECT_KOMENTAR}
        FROM analitik.v_akademik_komentar_mahasiswa
        WHERE komentar_teks IS NOT NULL AND length(komentar_teks) > 10
        {filter_sql};
    """
    async with conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute("SET LOCAL app.role = 'admin';")
        await cursor.execute(sql, params)
        return await cursor.fetchall()


async def fetch_portofolio(conn, kode_prodi: Optional[str], tahun: Optional[int]) -> List[Dict[str, Any]]:
    filter_sql, params = _filter_clause(kode_prodi, tahun)
    sql = f"""
        SELECT {_METADATA_SELECT_PORTOFOLIO}
        FROM analitik.v_akademik_portofolio
        WHERE true
        {filter_sql};
    """
    async with conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute("SET LOCAL app.role = 'admin';")
        await cursor.execute(sql, params)
        return await cursor.fetchall()


async def _flush_batch(conn, pending: List[Dict[str, Any]]) -> int:
    """Embeds a batch of pending chunk rows (one aembed_passage_texts call, not
    one call per chunk) and bulk-inserts them."""
    if not pending:
        return 0

    texts = [p["chunk_text"] for p in pending]
    embeddings = await aembed_passage_texts(texts)
    for row, embedding in zip(pending, embeddings):
        row["embedding"] = f"[{','.join(map(str, embedding))}]"

    async with conn.cursor() as cursor:
        await cursor.executemany(SQL_INSERT_CHUNK, pending)

    return len(pending)


async def process_komentar(conn, kode_prodi: Optional[str], tahun: Optional[int]):
    async with conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute("INSERT INTO analitik.rag_ingestion_log (source_type, status) VALUES ('komentar_mahasiswa', 'running') RETURNING log_id;")
        log_id = (await cursor.fetchone())['log_id']
        await conn.commit()

    try:
        query_existing = "SELECT DISTINCT source_id FROM analitik.vector_chunks WHERE source_type = 'komentar_mahasiswa';"
        async with conn.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(query_existing)
            existing_ids = {row['source_id'] for row in await cursor.fetchall()}

        rows = await fetch_komentar(conn, kode_prodi, tahun)
        rows_to_process = [r for r in rows if str(r["source_id"]) not in existing_ids]

        logger.info(f"[Komentar] Found {len(rows)} total rows, {len(existing_ids)} already ingested. Processing {len(rows_to_process)} rows.")

        chunks_gen = 0
        pending: List[Dict[str, Any]] = []
        for i, row in enumerate(rows_to_process, 1):
            chunk_text = (row.get("komentar_teks") or "").strip()
            if len(chunk_text) < 10:
                continue

            pending.append({
                "source_type": "komentar_mahasiswa",
                "source_id": row["source_id"],
                "kelas_id": row["kelas_id"],
                "tipe_konten": row["tipe_konten"],
                "chunk_index": 0,
                "chunk_text": chunk_text,
                "is_verifikator": False,
                **_row_metadata(row, is_portofolio=False),
            })

            if len(pending) >= settings.RAG_INGEST_BATCH_SIZE:
                chunks_gen += await _flush_batch(conn, pending)
                pending = []

            if i % 500 == 0:
                logger.info(f"[Komentar] Progress: {i}/{len(rows_to_process)}, {chunks_gen} chunks ingested so far.")

        chunks_gen += await _flush_batch(conn, pending)

        async with conn.cursor() as cursor:
            await cursor.execute(
                "UPDATE analitik.rag_ingestion_log SET status = 'completed', finished_at = NOW(), total_processed = %(proc)s, chunks_generated = %(chunks)s WHERE log_id = %(log_id)s",
                {"proc": len(rows_to_process), "chunks": chunks_gen, "log_id": log_id}
            )
        await conn.commit()
        logger.info(f"[Komentar] Completed. Ingested {chunks_gen} new chunks.")
    except Exception as e:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "UPDATE analitik.rag_ingestion_log SET status = 'failed', finished_at = NOW(), error_message = %(err)s WHERE log_id = %(log_id)s",
                {"err": str(e), "log_id": log_id}
            )
        await conn.commit()
        raise


async def process_portofolio(conn, kode_prodi: Optional[str], tahun: Optional[int]):
    async with conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute("INSERT INTO analitik.rag_ingestion_log (source_type, status) VALUES ('teks_portofolio', 'running') RETURNING log_id;")
        log_id = (await cursor.fetchone())['log_id']
        await conn.commit()

    try:
        query_existing = "SELECT DISTINCT source_id, tipe_konten FROM analitik.vector_chunks WHERE source_type = 'teks_portofolio';"
        async with conn.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(query_existing)
            existing_pairs = {(str(row['source_id']), row['tipe_konten']) for row in await cursor.fetchall()}

        rows = await fetch_portofolio(conn, kode_prodi, tahun)

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=80,
            separators=["\n\n", "\n", ".", " ", ""]
        )

        logger.info(f"[Portofolio] Found {len(rows)} classes to process.")

        processed_count = 0
        chunks_gen = 0
        pending: List[Dict[str, Any]] = []
        for i, row in enumerate(rows, 1):
            metadata = _row_metadata(row, is_portofolio=True)
            for field in PORTOFOLIO_COLUMNS:
                content = row.get(field)
                if not content or (str(row["source_id"]), field) in existing_pairs:
                    continue

                for chunk_index, chunk_text in enumerate(splitter.split_text(content)):
                    if len(chunk_text.strip()) < 10:
                        continue
                    pending.append({
                        "source_type": "teks_portofolio",
                        "source_id": row["source_id"],
                        "kelas_id": row["kelas_id"],
                        "tipe_konten": field,
                        "chunk_index": chunk_index,
                        "chunk_text": chunk_text,
                        "is_verifikator": field.startswith(_VERIFIKATOR_PREFIX),
                        **metadata,
                    })

                    if len(pending) >= settings.RAG_INGEST_BATCH_SIZE:
                        chunks_gen += await _flush_batch(conn, pending)
                        pending = []

            processed_count += 1
            if i % 200 == 0:
                logger.info(f"[Portofolio] Progress: {i}/{len(rows)} classes processed. Total chunks so far: {chunks_gen}")

        chunks_gen += await _flush_batch(conn, pending)

        logger.info(f"[Portofolio] Completed. Ingested {chunks_gen} new chunks.")

        async with conn.cursor() as cursor:
            await cursor.execute(
                "UPDATE analitik.rag_ingestion_log SET status = 'completed', finished_at = NOW(), total_processed = %(proc)s, chunks_generated = %(chunks)s WHERE log_id = %(log_id)s",
                {"proc": processed_count, "chunks": chunks_gen, "log_id": log_id}
            )
        await conn.commit()
    except Exception as e:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "UPDATE analitik.rag_ingestion_log SET status = 'failed', finished_at = NOW(), error_message = %(err)s WHERE log_id = %(log_id)s",
                {"err": str(e), "log_id": log_id}
            )
        await conn.commit()
        raise


async def main():
    parser = argparse.ArgumentParser(description="Ingest analitik.v_akademik_{portofolio,komentar_mahasiswa} into analitik.vector_chunks")
    parser.add_argument("--kode-prodi", default=None, help="Optional 2-letter prodi code filter (e.g. IF). Omit to ingest all prodi.")
    parser.add_argument("--tahun", type=int, default=None, help="Optional academic year filter (e.g. 2024). Omit to ingest all years.")
    args = parser.parse_args()

    await init_db_pool()
    try:
        async with get_db_connection() as conn:
            await process_komentar(conn, args.kode_prodi, args.tahun)
            await process_portofolio(conn, args.kode_prodi, args.tahun)
            await conn.commit()
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())
