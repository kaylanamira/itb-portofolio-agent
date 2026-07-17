DROP TABLE IF EXISTS analitik.vector_chunks CASCADE;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE analitik.vector_chunks (
    chunk_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- identity / provenance
    source_type     VARCHAR(50)  NOT NULL CHECK (source_type IN ('teks_portofolio', 'komentar_mahasiswa')),
    source_id       VARCHAR(100) NOT NULL,      -- kelas_id or jawaban_id as text
    kelas_id        INTEGER      NOT NULL,
    tipe_konten     VARCHAR(100) NOT NULL,      -- e.g. 'refleksi_pelaksanaan_perkuliahan', 'komentar', 'verifikator_ketercapaian_outcomes'
    chunk_index     INTEGER      NOT NULL DEFAULT 0,  -- position within the parent field's split

    -- content + vectors
    chunk_text      TEXT NOT NULL,
    embedding       vector(1024),
    fts_vector      tsvector GENERATED ALWAYS AS (to_tsvector('indonesian', chunk_text)) STORED,

    -- denormalized metadata for filtering (sourced from v_akademik_portofolio / v_akademik_komentar_mahasiswa at ingestion time)
    kode_matkul     VARCHAR(6),
    nama_matkul     TEXT,
    sks             SMALLINT,
    no_kelas        INTEGER,
    semester        SMALLINT,
    tahun           INTEGER      NOT NULL,
    tahun_ajaran    VARCHAR(9),
    no_prodi        INTEGER      NOT NULL,
    kode_prodi      VARCHAR(2),
    nama_prodi      TEXT,
    jenjang         VARCHAR(2),
    kode_fakultas   VARCHAR(10),
    nama_fakultas   TEXT,
    dosen_ids       INTEGER[]    NOT NULL DEFAULT '{}',
    dosen_names     TEXT[]       NOT NULL DEFAULT '{}',
    nilai_portofolio INTEGER,             -- portofolio-only, NULL for komentar rows
    lengkap         BOOLEAN,              -- portofolio-only
    tanggal_entri   DATE,                 -- portofolio-only
    is_verifikator  BOOLEAN      NOT NULL DEFAULT FALSE,  -- TRUE for verifikator_* review-comment chunks;
                                                           -- FALSE for the dosen's own portofolio narrative
                                                           -- and for komentar_mahasiswa (student) chunks

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for HNSW (Dense Search)
CREATE INDEX vector_chunks_embedding_idx ON analitik.vector_chunks USING hnsw (embedding vector_cosine_ops);

-- Index for BM25-style ranking (Sparse Search)
CREATE INDEX vector_chunks_fts_idx ON analitik.vector_chunks USING GIN (fts_vector);

-- Existing composite
CREATE INDEX vector_chunks_source_idx ON analitik.vector_chunks (source_type, kelas_id);

-- Metadata filter indexes
CREATE INDEX vector_chunks_dosen_ids_idx ON analitik.vector_chunks USING GIN (dosen_ids);
CREATE INDEX vector_chunks_prodi_tahun_idx ON analitik.vector_chunks (no_prodi, tahun);
CREATE INDEX vector_chunks_fakultas_idx ON analitik.vector_chunks (kode_fakultas);

-- Speeds up ingestion's existing-pairs dedupe query
CREATE INDEX vector_chunks_dedup_idx ON analitik.vector_chunks (source_type, source_id, tipe_konten);

ALTER TABLE analitik.vector_chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY pol_vector_chunks ON analitik.vector_chunks FOR SELECT USING (
    CASE NULLIF(current_setting('app.role', true), '')
        WHEN 'admin'           THEN true
        WHEN 'direktorat'      THEN true
        WHEN 'dekan'           THEN kode_fakultas = NULLIF(current_setting('app.kd_fak', true), '')
        WHEN 'jajaran_dekanat' THEN kode_fakultas = NULLIF(current_setting('app.kd_fak', true), '')
        WHEN 'kaprodi'         THEN no_prodi = NULLIF(current_setting('app.no_ps', true), '')::integer
        WHEN 'jajaran_prodi'   THEN no_prodi = NULLIF(current_setting('app.no_ps', true), '')::integer
        WHEN 'dosen'           THEN CASE source_type
                                        WHEN 'teks_portofolio'    THEN no_prodi = NULLIF(current_setting('app.no_ps', true), '')::integer
                                        WHEN 'komentar_mahasiswa' THEN NULLIF(current_setting('app.dosen_id', true), '')::integer = ANY(dosen_ids)
                                        ELSE false
                                    END
        ELSE false
    END
);

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
