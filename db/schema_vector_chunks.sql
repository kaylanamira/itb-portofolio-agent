CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS analitik.vector_chunks (
    chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type VARCHAR(50) NOT NULL, -- 'teks_portofolio' or 'komentar_mahasiswa'
    source_id VARCHAR(100) NOT NULL, -- stores kelas_id or jawaban_id as string
    kelas_id INTEGER NOT NULL,
    tipe_konten VARCHAR(100), -- e.g., 'refleksi_pelaksanaan'
    chunk_text TEXT NOT NULL,
    embedding vector(768),
    fts_vector tsvector,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for HNSW (Dense Search)
CREATE INDEX IF NOT EXISTS vector_chunks_embedding_idx ON analitik.vector_chunks USING hnsw (embedding vector_cosine_ops);

-- Index for BM25 (Sparse Search)
CREATE INDEX IF NOT EXISTS vector_chunks_fts_idx ON analitik.vector_chunks USING GIN (fts_vector);

-- Index for filtering
CREATE INDEX IF NOT EXISTS vector_chunks_source_idx ON analitik.vector_chunks(source_type, kelas_id);

CREATE TABLE IF NOT EXISTS analitik.rag_ingestion_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    finished_at TIMESTAMP WITH TIME ZONE,
    source_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'running',
    total_processed INTEGER DEFAULT 0,
    chunks_generated INTEGER DEFAULT 0,
    error_message TEXT
);
