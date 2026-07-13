import asyncio
from typing import List, Dict, Any
from psycopg.rows import dict_row
from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.database import get_db_connection, init_db_pool, close_db_pool
from agent.tools.rag.core.embedder import embed_text

SQL_FETCH_KOMENTAR = """
    SELECT 
        kelas_id, 
        jawaban_id::text AS source_id, 
        komentar_teks, 
        'komentar' AS tipe_konten
    FROM analitik.v_akademik_komentar_mahasiswa
    WHERE komentar_teks IS NOT NULL 
      AND length(komentar_teks) > 10
      -- DEMO FILTER (Remove or comment out to ingest everything)
      AND kode_prodi = 'IF' AND tahun = 2024;
"""

SQL_FETCH_PORTOFOLIO = """
    SELECT 
        kelas_id, 
        kelas_id::text AS source_id, 
        metode_perkuliahan,
        sistem_penilaian,
        statistik_kelas,
        analisis_terhadap_statistik_kelas_dan_ketercapaian_outcomes,
        komentar_terhadap_hasil_kuesioner_mahasiswa,
        refleksi_pelaksanaan_perkuliahan,
        usulan_perbaikan_oleh_dosen_berikutnya,
        usulan_perbaikan_oleh_itb
    FROM analitik.v_akademik_portofolio
    WHERE true
      -- DEMO FILTER (Remove or comment out to ingest everything)
      AND kode_prodi = 'IF' AND tahun = 2024;
"""

SQL_INSERT_CHUNK = """
    INSERT INTO analitik.vector_chunks (
        source_type, source_id, kelas_id, tipe_konten, chunk_text, embedding, fts_vector
    )
    VALUES (
        %(source_type)s, %(source_id)s, %(kelas_id)s, %(tipe_konten)s, 
        %(chunk_text)s, %(embedding)s::vector, to_tsvector('indonesian', %(chunk_text)s)
    )
"""

PORTOFOLIO_COLUMNS = [
    "metode_perkuliahan",
    "sistem_penilaian",
    "statistik_kelas",
    "analisis_terhadap_statistik_kelas_dan_ketercapaian_outcomes",
    "komentar_terhadap_hasil_kuesioner_mahasiswa",
    "refleksi_pelaksanaan_perkuliahan",
    "usulan_perbaikan_oleh_dosen_berikutnya",
    "usulan_perbaikan_oleh_itb"
]

async def fetch_komentar(conn) -> List[Dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute("SET LOCAL app.role = 'admin';")
        await cursor.execute(SQL_FETCH_KOMENTAR)
        return await cursor.fetchall()

async def fetch_portofolio(conn) -> List[Dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute("SET LOCAL app.role = 'admin';")
        await cursor.execute(SQL_FETCH_PORTOFOLIO)
        return await cursor.fetchall()

async def ingest_chunk(conn, source_type: str, source_id: str, kelas_id: int, tipe_konten: str, chunk_text: str):
    if not chunk_text or len(chunk_text.strip()) < 10:
        return
        
    embedding = embed_text(chunk_text)
    embedding_str = f"[{','.join(map(str, embedding))}]"
    
    async with conn.cursor() as cursor:
        await cursor.execute(SQL_INSERT_CHUNK, {
            "source_type": source_type,
            "source_id": source_id,
            "kelas_id": kelas_id,
            "tipe_konten": tipe_konten,
            "chunk_text": chunk_text,
            "embedding": embedding_str
        })

async def process_komentar(conn):
    async with conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute("INSERT INTO analitik.rag_ingestion_log (source_type, status) VALUES ('komentar_mahasiswa', 'running') RETURNING log_id;")
        log_id = (await cursor.fetchone())['log_id']
        await conn.commit()

    try:
        query_existing = "SELECT DISTINCT source_id FROM analitik.vector_chunks WHERE source_type = 'komentar_mahasiswa';"
        async with conn.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(query_existing)
            existing_ids = {row['source_id'] for row in await cursor.fetchall()}

        rows = await fetch_komentar(conn)
        rows_to_process = [r for r in rows if str(r["source_id"]) not in existing_ids]
        
        print(f"[Komentar] Found {len(rows)} total rows, {len(existing_ids)} already ingested. Processing {len(rows_to_process)} rows.")
        
        chunks_gen = 0
        for i, row in enumerate(rows_to_process, 1):
            if i % 100 == 0:
                print(f"[Komentar] Progress: {i}/{len(rows_to_process)}")
            await ingest_chunk(
                conn=conn,
                source_type="komentar_mahasiswa",
                source_id=row["source_id"],
                kelas_id=row["kelas_id"],
                tipe_konten=row["tipe_konten"],
                chunk_text=row["komentar_teks"]
            )
            chunks_gen += 1
            
        async with conn.cursor() as cursor:
            await cursor.execute(
                "UPDATE analitik.rag_ingestion_log SET status = 'completed', finished_at = NOW(), total_processed = %(proc)s, chunks_generated = %(chunks)s WHERE log_id = %(log_id)s",
                {"proc": len(rows_to_process), "chunks": chunks_gen, "log_id": log_id}
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

async def process_portofolio(conn):
    async with conn.cursor(row_factory=dict_row) as cursor:
        await cursor.execute("INSERT INTO analitik.rag_ingestion_log (source_type, status) VALUES ('teks_portofolio', 'running') RETURNING log_id;")
        log_id = (await cursor.fetchone())['log_id']
        await conn.commit()

    try:
        query_existing = "SELECT DISTINCT source_id, tipe_konten FROM analitik.vector_chunks WHERE source_type = 'teks_portofolio';"
        async with conn.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(query_existing)
            existing_pairs = {(str(row['source_id']), row['tipe_konten']) for row in await cursor.fetchall()}

        rows = await fetch_portofolio(conn)
        
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=80,
            separators=["\\n\\n", "\\n", ".", " ", ""]
        )
        
        print(f"[Portofolio] Found {len(rows)} classes to process.")
        
        processed_count = 0
        chunks_gen = 0
        for i, row in enumerate(rows, 1):
            if i % 50 == 0:
                print(f"[Portofolio] Progress: {i}/{len(rows)} classes processed. Total chunks so far: {chunks_gen}")
            for field in PORTOFOLIO_COLUMNS:
                content = row.get(field)
                if content and (str(row["source_id"]), field) not in existing_pairs:
                    chunks = splitter.split_text(content)
                    for chunk in chunks:
                        await ingest_chunk(
                            conn=conn,
                            source_type="teks_portofolio",
                            source_id=row["source_id"],
                            kelas_id=row["kelas_id"],
                            tipe_konten=field,
                            chunk_text=chunk
                        )
                        chunks_gen += 1
            processed_count += 1
        
        print(f"[Portofolio] Completed. Ingested {chunks_gen} new chunks.")
        
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
    await init_db_pool()
    try:
        async with get_db_connection() as conn:
            await process_komentar(conn)
            await process_portofolio(conn)
            await conn.commit()
    finally:
        await close_db_pool()

if __name__ == "__main__":
    asyncio.run(main())
