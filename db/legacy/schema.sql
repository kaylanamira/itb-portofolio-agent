-- ============================================================
-- PORTOFOLIO AKADEMIK ITB — PostgreSQL Schema
-- ============================================================


-- ── EXTENSIONS ────────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "vector";


-- ── ENUM TYPES ────────────────────────────────────────────────────────────────

CREATE TYPE tipe_konten_enum AS ENUM (
    'metode_perkuliahan',       -- Metode mengajar dosen 
    'sistem_penilaian',         -- Deskripsi sistem penilaian
    'analisis_capaian_kelas',   -- Analisis capaian outcomes per kelas
    'tambahan_info_statistik',  -- Narasi tambahan terkait statistik kelas
    'refleksi_pelaksanaan',     -- Refleksi dosen atas pelaksanaan kuliah
    'usulan_perbaikan_dosen',   -- Saran untuk dosen pengajar berikutnya
    'usulan_perbaikan_itb'      -- Saran untuk institusi ITB
);

CREATE TYPE user_role_enum AS ENUM (
    'admin',            -- System admin: full access + ingestion management
    -- 'direktorat',       -- Direktorat: akses semua fakultas
    'wram',             -- WRAM/pusat: akses semua fakultas
    'dekan',            -- Dekan: akses seluruh fakultas
    'jajaran_dekanat',  -- Wakil dekan / staf dekanat: akses seluruh fakultas
    'kaprodi',          -- Kepala prodi: akses seluruh prodi
    'jajaran_prodi',    -- Sekretaris/staf prodi: akses seluruh prodi
    'dosen'             -- Pengajar: hanya akses kelas yang diajar sendiri
);

CREATE TABLE IF NOT EXISTS fakultas (
    fakultas_id         UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    kode_fakultas       VARCHAR(20)     UNIQUE NOT NULL,
    nama_fakultas       VARCHAR(100)    NOT NULL,
    parent_fakultas_id  UUID            REFERENCES fakultas(fakultas_id),
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  fakultas                      IS 'Hierarki fakultas/sekolah ITB. Self-referencing via parent_fakultas_id untuk struktur sub-kampus.';
COMMENT ON COLUMN fakultas.kode_fakultas        IS 'Kode singkat sesuai SIX ITB, e.g. STEI, FITB, SBM.';
COMMENT ON COLUMN fakultas.parent_fakultas_id   IS 'NULL untuk fakultas induk. Diisi untuk sub-sekolah/kampus.';


-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS program_studi (
    prodi_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    fakultas_id     UUID            NOT NULL REFERENCES fakultas(fakultas_id)
                                    ON UPDATE CASCADE,
    kode_prodi      VARCHAR(10)     UNIQUE NOT NULL,
    -- e.g. '135' 
    singkatan_prodi VARCHAR(10),
    -- e.g. 'IF', 'STI', 'EL'
    nama_prodi      VARCHAR(150)    NOT NULL,
    jenjang         VARCHAR(10)     NOT NULL CHECK (jenjang IN ('S1','S2','S3','Profesi')),
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  program_studi             IS '1 prodi hanya dimiliki 1 fakultas (no sharing). Relasi N:1 ke fakultas.';
COMMENT ON COLUMN program_studi.kode_prodi  IS 'Kode PDDikti, e.g. 135 untuk Informatika.';
COMMENT ON COLUMN program_studi.singkatan_prodi   IS 'Singkatan lazim, e.g. IF, STI — dipakai di label UI.';
COMMENT ON COLUMN program_studi.jenjang     IS 'S1, S2, S3, atau Profesi.';

CREATE INDEX idx_prodi_fakultas ON program_studi(fakultas_id);

-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS mata_kuliah (
    matkul_id           UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    prodi_id            UUID            NOT NULL REFERENCES program_studi(prodi_id)
                                        ON UPDATE CASCADE,
    kode_mk             VARCHAR(20)     NOT NULL,
    nama_mk             VARCHAR(200)    NOT NULL,
    nama_mk_en          VARCHAR(200)    NOT NULL,
    kategori            VARCHAR(100)    NOT NULL DEFAULT 'Kuliah',
    jenis_nilai         VARCHAR(10)     NOT NULL DEFAULT 'ABCDE'
                                        CHECK (jenis_nilai IN ('ABCDE', 'Pass/Fail')),
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_kode_mk_prodi UNIQUE (kode_mk, prodi_id)
);

COMMENT ON COLUMN mata_kuliah.kode_mk   IS 'e.g. IF4044. Unik per prodi (UNIQUE + prodi_id). NOT NULL.';
COMMENT ON COLUMN mata_kuliah.nama_mk   IS 'Nama mata kuliah dalam bahasa Indonesia.';
COMMENT ON COLUMN mata_kuliah.nama_mk_en IS 'Nama mata kuliah dalam bahasa Inggris.';

CREATE INDEX idx_matkul_prodi ON mata_kuliah(prodi_id);
-- Filter semua MK dalam satu prodi


-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS kelompok_keahlian (
    kk_id           UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    fakultas_id     UUID            NOT NULL REFERENCES fakultas(fakultas_id)
                                    ON UPDATE CASCADE,
    nama_kk         VARCHAR(200)    NOT NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE kelompok_keahlian IS 'KK berada di level fakultas. Dosen berafiliasi ke KK, bukan langsung ke prodi.';

CREATE INDEX idx_kk_fakultas ON kelompok_keahlian(fakultas_id);
-- Filter semua KK dalam satu fakultas

CREATE TABLE IF NOT EXISTS dosen (
    dosen_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    kk_id           UUID            REFERENCES kelompok_keahlian(kk_id)
                                    ON UPDATE CASCADE,
    nama_dosen      VARCHAR(150)    NOT NULL,
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_dosen_kk ON dosen(kk_id);

-- GIN trigram indexes for similarity() and ILIKE searches on name/code columns
CREATE INDEX idx_trgm_nama_dosen    ON dosen              USING GIN (nama_dosen          gin_trgm_ops);
CREATE INDEX idx_trgm_nama_mk       ON mata_kuliah        USING GIN (nama_mk             gin_trgm_ops);
CREATE INDEX idx_trgm_nama_mk_en    ON mata_kuliah        USING GIN (nama_mk_en          gin_trgm_ops);
CREATE INDEX idx_trgm_kode_mk       ON mata_kuliah        USING GIN (kode_mk             gin_trgm_ops);
CREATE INDEX idx_trgm_nama_prodi    ON program_studi      USING GIN (nama_prodi          gin_trgm_ops);
CREATE INDEX idx_trgm_kode_prodi    ON program_studi      USING GIN (kode_prodi          gin_trgm_ops);
CREATE INDEX idx_trgm_nama_fakultas ON fakultas           USING GIN (nama_fakultas       gin_trgm_ops);
CREATE INDEX idx_trgm_kode_fakultas ON fakultas           USING GIN (kode_fakultas       gin_trgm_ops);
CREATE INDEX idx_trgm_nama_kk       ON kelompok_keahlian  USING GIN (nama_kk             gin_trgm_ops);

CREATE TABLE IF NOT EXISTS kelas (
    kelas_id            UUID                    PRIMARY KEY DEFAULT gen_random_uuid(),
    matkul_id           UUID                    NOT NULL REFERENCES mata_kuliah(matkul_id)
                                                ON UPDATE CASCADE,
    no_kelas            VARCHAR(5)              NOT NULL,
    semester            SMALLINT                NOT NULL CHECK (semester IN (1, 2, 3)),
    tahun_ajaran        VARCHAR(9)              NOT NULL
                                                CHECK (tahun_ajaran ~ '^\d{4}/\d{4}$'),
    sks                 SMALLINT                NOT NULL CHECK (sks BETWEEN 1 AND 6),

    -- ── Statistik kelas ────────────
    pct_kehadiran_dosen     NUMERIC(5,2)    CHECK (pct_kehadiran_dosen BETWEEN 0 AND 100),
    pct_kehadiran_mahasiswa NUMERIC(5,2)    CHECK (pct_kehadiran_mahasiswa BETWEEN 0 AND 100),
    rata_rata_nilai         NUMERIC(4,2)    CHECK (rata_rata_nilai BETWEEN 0 AND 4),
    jumlah_mahasiswa        SMALLINT        CHECK (jumlah_mahasiswa >= 0) DEFAULT 0,

    -- ── Metadata portofolio ─────────────────────────────────────────────────
    nilai_portofolio    SMALLINT                CHECK (nilai_portofolio BETWEEN 1 AND 4),
    sumber_file         VARCHAR(500),
    is_synthetic        BOOLEAN                 NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ             NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ             NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_kelas_periode UNIQUE (matkul_id, no_kelas, semester, tahun_ajaran)
);

COMMENT ON TABLE  kelas                         IS '1 row = 1 dokumen portofolio unik';
COMMENT ON COLUMN kelas.no_kelas                IS 'Nomor kelas, e.g. 1, 2, 3.';
COMMENT ON COLUMN kelas.semester                IS '1=Ganjil, 2=Genap, 3=Semester Pendek (SBM/khusus ITB).';
COMMENT ON COLUMN kelas.sks                     IS 'Snapshot SKS saat kelas ini berjalan. CHECK 1..6 .';
COMMENT ON COLUMN kelas.rata_rata_nilai         IS 'Skala 0.00–4.00.';
COMMENT ON COLUMN kelas.nilai_portofolio        IS 'Skor verifikator 1–4. NULL jika belum diverifikasi.';

CREATE INDEX idx_kelas_matkul_sem   ON kelas(matkul_id, tahun_ajaran, semester);

CREATE INDEX idx_kelas_tahun_sem    ON kelas(tahun_ajaran, semester);

CREATE INDEX idx_kelas_matkul       ON kelas(matkul_id);

-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pengajar_kelas (
    kelas_id        UUID            NOT NULL REFERENCES kelas(kelas_id) ON DELETE CASCADE,
    dosen_id        UUID            NOT NULL REFERENCES dosen(dosen_id),
    -- is_primary      BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (kelas_id, dosen_id)
);

CREATE INDEX idx_pengajar_dosen ON pengajar_kelas(dosen_id);

CREATE TABLE IF NOT EXISTS distribusi_nilai (
    distribusi_id   UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    kelas_id        UUID            NOT NULL REFERENCES kelas(kelas_id) ON DELETE CASCADE,
    grade           VARCHAR(5)      NOT NULL CHECK (grade IN ('A','AB','B','BC','C','D','E','Pass','Fail')),
    jumlah          SMALLINT        NOT NULL DEFAULT 0 CHECK (jumlah >= 0),
    persentase      NUMERIC(5,2)    CHECK (persentase BETWEEN 0 AND 100),

    CONSTRAINT uq_distribusi_kelas_grade UNIQUE (kelas_id, grade)
);

CREATE INDEX idx_distribusi_kelas ON distribusi_nilai(kelas_id);

-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS skor_kuesioner (
    skor_id         UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    kelas_id        UUID            NOT NULL REFERENCES kelas(kelas_id) ON DELETE CASCADE,
    no_pertanyaan   SMALLINT        NOT NULL CHECK (no_pertanyaan BETWEEN 1 AND 12),
    -- Mapping dimensi :
    -- Q1-Q3  → capaian_pembelajaran
    -- Q4-Q8  → pelaksanaan_perkuliahan
    -- Q9-Q10 → sarana_prasarana
    -- Q11-Q12→ perilaku_mahasiswa
    rata_skor       NUMERIC(4,2)    NOT NULL CHECK (rata_skor BETWEEN 1 AND 4),
    CONSTRAINT uq_skor_kelas_pertanyaan UNIQUE (kelas_id, no_pertanyaan)
);

COMMENT ON TABLE  skor_kuesioner                IS '12 rows per kelas (Q1–Q12). Mapping dimensi: Q1-3=capaian, Q4-8=pelaksanaan, Q9-10=sarana, Q11-12=perilaku.';
COMMENT ON COLUMN skor_kuesioner.rata_skor      IS 'Skala Likert 1.00–4.00. CHECK 1..4';
COMMENT ON COLUMN skor_kuesioner.no_pertanyaan  IS 'Q1-Q3: capaian pembelajaran. Q4-Q8: pelaksanaan & fairness. Q9-Q10: sarana prasarana. Q11-Q12: perilaku & pengalaman mahasiswa.';

CREATE INDEX idx_skor_kelas ON skor_kuesioner(kelas_id);


CREATE TABLE IF NOT EXISTS teks_portofolio (
    teks_id         UUID                PRIMARY KEY DEFAULT gen_random_uuid(),
    kelas_id        UUID                NOT NULL REFERENCES kelas(kelas_id) ON DELETE CASCADE,
    tipe_konten     tipe_konten_enum    NOT NULL,
    konten          TEXT,
    is_embedded     BOOLEAN             NOT NULL DEFAULT FALSE,
    embedded_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ         NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_teks_kelas_tipe UNIQUE (kelas_id, tipe_konten)
);

COMMENT ON TABLE  teks_portofolio               IS 'Semua free-text dari portofolio, max 7 tipe per kelas. konten NULL valid (dosen tidak wajib isi semua field, terutama sistem_penilaian).';
COMMENT ON COLUMN teks_portofolio.tipe_konten   IS 'Section portfolio: metode_perkuliahan, analisis_capaian_kelas, refleksi_pelaksanaan, usulan_perbaikan_dosen, usulan_perbaikan_itb, tambahan_info_statistik, sistem_penilaian.';
COMMENT ON COLUMN teks_portofolio.embedded_at   IS 'NULL jika belum pernah di-embed. Diisi pipeline setelah sukses upsert ke vector store.';

CREATE INDEX idx_teks_kelas         ON teks_portofolio(kelas_id);
CREATE INDEX idx_teks_unembedded    ON teks_portofolio(is_embedded)
    WHERE is_embedded = FALSE;
-- Partial index: hanya index rows yang belum di-embed.

-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS komentar_mahasiswa (
    komentar_id     UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    kelas_id        UUID            NOT NULL REFERENCES kelas(kelas_id) ON DELETE CASCADE,
    no_komentar     SMALLINT        NOT NULL CHECK (no_komentar > 0),
    teks_komentar   TEXT            NOT NULL CHECK (LENGTH(TRIM(teks_komentar)) > 0),
    is_embedded     BOOLEAN         NOT NULL DEFAULT FALSE,
    embedded_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_komentar_kelas_no UNIQUE (kelas_id, no_komentar)
);

COMMENT ON TABLE  komentar_mahasiswa            IS 'Komentar bebas mahasiswa. 1 row = 1 komentar = 1 chunk di vector store. Di-split dari delimiter || saat ingestion CSV.';
COMMENT ON COLUMN komentar_mahasiswa.no_komentar IS 'Urutan dalam kelas. Dipakai sebagai dedup key saat re-ingest (ON CONFLICT DO UPDATE).';

CREATE INDEX idx_komentar_kelas     ON komentar_mahasiswa(kelas_id);
CREATE INDEX idx_komentar_unembedded ON komentar_mahasiswa(is_embedded)
    WHERE is_embedded = FALSE;

CREATE TABLE IF NOT EXISTS vector_chunks (
    chunk_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type     VARCHAR(20)     NOT NULL CHECK (source_type IN ('teks_portofolio', 'komentar_mahasiswa')),
    source_id       UUID            NOT NULL,
    kelas_id        UUID            NOT NULL REFERENCES kelas(kelas_id) ON DELETE CASCADE,
    tipe_konten     tipe_konten_enum,
    chunk_index     SMALLINT        NOT NULL DEFAULT 0,
    chunk_text      TEXT            NOT NULL,
    embedding       VECTOR(1536),
    model_used      VARCHAR(100),
    embedded_at     TIMESTAMPTZ,

    -- ── Filter keys ─────────

    kode_mk         VARCHAR(20)     NOT NULL,
    kode_prodi      VARCHAR(10)     NOT NULL,
    kode_fakultas   VARCHAR(20)     NOT NULL,
    no_kelas        VARCHAR(5)      NOT NULL,
    semester        SMALLINT        NOT NULL,
    tahun_ajaran    VARCHAR(9)      NOT NULL,
    nama_mk         VARCHAR(200)    NOT NULL,
    nama_prodi      VARCHAR(150)    NOT NULL,
    nama_fakultas   VARCHAR(100)    NOT NULL,
    jenjang         VARCHAR(10)     NOT NULL CHECK (jenjang IN ('S1','S2','S3','Profesi')),
    semua_dosen_id  UUID[]          NOT NULL,
    semua_dosen_nama TEXT[]         NOT NULL DEFAULT '{}',
    kelas_label     TEXT            NOT NULL,

    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_chunk_source_idx UNIQUE (source_id, chunk_index)
);

CREATE INDEX idx_vc_kelas_id    ON vector_chunks(kelas_id);
CREATE INDEX idx_vc_kode_mk    ON vector_chunks(kode_mk,      semester, tahun_ajaran) WHERE embedding IS NOT NULL;
CREATE INDEX idx_vc_kode_prodi ON vector_chunks(kode_prodi,   semester, tahun_ajaran) WHERE embedding IS NOT NULL;
CREATE INDEX idx_vc_kode_fak   ON vector_chunks(kode_fakultas, semester, tahun_ajaran) WHERE embedding IS NOT NULL;
CREATE INDEX idx_vc_tipe       ON vector_chunks(tipe_konten)   WHERE tipe_konten IS NOT NULL AND embedding IS NOT NULL;
CREATE INDEX idx_vc_source      ON vector_chunks(source_type, source_id);
CREATE INDEX idx_vc_dosen       ON vector_chunks USING GIN(semua_dosen_id);

CREATE TABLE IF NOT EXISTS pengguna (
    user_id         UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    username        VARCHAR(100)    UNIQUE NOT NULL,
    email           VARCHAR(200)    UNIQUE NOT NULL,
    nama_lengkap    VARCHAR(200)    NOT NULL,
    role            user_role_enum  NOT NULL,
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    last_login      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE pengguna IS 'Akun pengguna sistem. 1 user = 1 role. Scope data ditentukan oleh user_scope.';

CREATE INDEX idx_pengguna_role ON pengguna(role);

-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_scope (
    scope_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID            UNIQUE NOT NULL REFERENCES pengguna(user_id)
                                    ON DELETE CASCADE,
    dosen_id        UUID            REFERENCES dosen(dosen_id),
    kk_id           UUID            REFERENCES kelompok_keahlian(kk_id),
    prodi_id        UUID            REFERENCES program_studi(prodi_id)
                                    ON UPDATE CASCADE,
    fakultas_id     UUID            REFERENCES fakultas(fakultas_id)
                                    ON UPDATE CASCADE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  user_scope                IS 'Scope akses data per user. Satu user = satu row. Kolom dosen_id/prodi_id/fakultas_id menentukan batas data yang bisa dilihat. Validasi "setidaknya satu diisi sesuai role" dilakukan di application layer (bukan CHECK constraint — subquery di CHECK anti-pattern di PostgreSQL).';
COMMENT ON COLUMN user_scope.dosen_id       IS 'Diisi untuk role=dosen. User hanya lihat kelas yang ia ampu via pengajar_kelas.';
COMMENT ON COLUMN user_scope.prodi_id       IS 'Diisi untuk role=kaprodi/jajaran_prodi. Akses semua kelas di prodi ini.';
COMMENT ON COLUMN user_scope.fakultas_id    IS 'Diisi untuk role=dekan/jajaran_dekanat. Akses semua kelas di semua prodi fakultas ini.';

CREATE INDEX idx_scope_dosen    ON user_scope(dosen_id)    WHERE dosen_id    IS NOT NULL;
CREATE INDEX idx_scope_prodi    ON user_scope(prodi_id)    WHERE prodi_id    IS NOT NULL;
CREATE INDEX idx_scope_fakultas ON user_scope(fakultas_id) WHERE fakultas_id IS NOT NULL;


CREATE TABLE IF NOT EXISTS llm_analysis_cache (
    cache_id            VARCHAR(64)     PRIMARY KEY,
    analysis_type       VARCHAR(50)     NOT NULL,
    kelas_ids           UUID[]          NOT NULL,
    result_json         JSONB           NOT NULL,
    model_used          VARCHAR(100),
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    generated_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ
    -- NULL = cache permanen. Set ke NOW() + INTERVAL '180 days' untuk TTL.
);

COMMENT ON TABLE  llm_analysis_cache            IS 'Cache hasil LLM call. cache_id = SHA256(sorted kelas_ids + analysis_type). TTL 180 hari via expires_at. result_json JSONB agar bisa query field tertentu.';
COMMENT ON COLUMN llm_analysis_cache.kelas_ids  IS 'Array UUID kelas yang menjadi input analisis.';

CREATE INDEX idx_cache_kelas_ids ON llm_analysis_cache USING GIN (kelas_ids);
CREATE INDEX idx_cache_expires      ON llm_analysis_cache(expires_at)
    WHERE expires_at IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ingestion_log (
    log_id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    kelas_id        UUID            REFERENCES kelas(kelas_id) ON DELETE SET NULL,
    sumber_file     VARCHAR(500)    NOT NULL,
    status          VARCHAR(20)     NOT NULL CHECK (status IN ('success','partial','failed','skipped')),
    rows_inserted   JSONB,
    error_message   TEXT,
    started_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ
);

COMMENT ON TABLE ingestion_log IS 'Audit trail setiap proses ingestion CSV. kelas_id NULL jika gagal sebelum kelas terbuat. rows_inserted JSONB untuk breakdown per tabel.';

CREATE INDEX idx_ingestion_status   ON ingestion_log(status, started_at DESC);


-- ╔══════════════════════════════════════════════════════════════╗
-- ║  MATERIALIZED VIEWS                                          ║
-- ╚══════════════════════════════════════════════════════════════╝
-- Design decisions:
--   MV1 mv_kelas: WIDE TABLE — distribusi pivot + skor pivot per kelas
--     Distribusi nilai: WIDE (jumlah_A, jumlah_AB, ...) karena:
--       • Set grade selalu tetap (A,AB,B,BC,C,D,E) — tidak dinamis
--       • Query frontend butuh semua 7 grade sekaligus untuk chart
--       • Pivot di MV = 1 row per kelas = O(1) lookup, vs LONG = 7 rows per kelas = GROUP BY
--     Skor kuesioner: WIDE (avg_q1..avg_q12 + avg per dimensi) karena:
--       • Set pertanyaan tetap (1–12) — tidak dinamis
--       • Radar chart butuh semua 12 nilai sekaligus
--       • Pivot di MV = 1 row per kelas
--   Teks portofolio & komentar: TIDAK dimasukkan ke MV karena:
--       • TEXT besar → MV jadi sangat berat (GB)
--       • Teks diakses via RAG (vector store), bukan SQL dashboard
--       • Jika perlu summary LLM, pakai llm_analysis_cache
--       • Agent query teks langsung ke tabel teks_portofolio jika perlu lookup spesifik

-- ─────────────────────────────────────────────────────────────────────────────
-- MV 1: mv_kelas
-- Primary query surface untuk Text-to-SQL agent dan dashboard.
-- 1 row = 1 kelas portofolio, semua dimensi dan statistik ter-flatten.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE MATERIALIZED VIEW mv_kelas AS
SELECT
    -- ── Identitas kelas ──────────────────────────────────────────────────────
    k.kelas_id,
    k.matkul_id,
    k.no_kelas,
    k.semester,
    k.tahun_ajaran,
    k.sks,

    -- ── Mata kuliah ───────────────────────────────────────────────────────────
    mk.kode_mk,
    mk.nama_mk,

    -- ── Prodi & Fakultas ─────────────────────────────────────────────────────
    ps.prodi_id,
    ps.kode_prodi,
    ps.singkatan_prodi,
    ps.nama_prodi,
    ps.jenjang,
    f.fakultas_id,
    f.kode_fakultas,
    f.nama_fakultas,

    -- ── Dosen ─────────────────────────────────────────────────────────────────
    array_agg( d.dosen_id   ORDER BY d.dosen_id)   AS semua_dosen_id,
    array_agg( d.nama_dosen ORDER BY d.dosen_id) AS semua_dosen_nama,
 
    -- ── Statistik kelas ───────────────────────────────
    k.pct_kehadiran_dosen,
    k.pct_kehadiran_mahasiswa,
    k.rata_rata_nilai,
    k.jumlah_mahasiswa,
    k.nilai_portofolio,
    k.is_synthetic,

    -- ── Distribusi nilai ───────────────────────────────
    COALESCE(MAX(dn.jumlah)     FILTER (WHERE dn.grade = 'A'),  0) AS dist_jumlah_A,
    COALESCE(MAX(dn.jumlah)     FILTER (WHERE dn.grade = 'AB'), 0) AS dist_jumlah_AB,
    COALESCE(MAX(dn.jumlah)     FILTER (WHERE dn.grade = 'B'),  0) AS dist_jumlah_B,
    COALESCE(MAX(dn.jumlah)     FILTER (WHERE dn.grade = 'BC'), 0) AS dist_jumlah_BC,
    COALESCE(MAX(dn.jumlah)     FILTER (WHERE dn.grade = 'C'),  0) AS dist_jumlah_C,
    COALESCE(MAX(dn.jumlah)     FILTER (WHERE dn.grade = 'D'),  0) AS dist_jumlah_D,
    COALESCE(MAX(dn.jumlah)     FILTER (WHERE dn.grade = 'E'),  0) AS dist_jumlah_E,
    COALESCE(MAX(dn.jumlah)     FILTER (WHERE dn.grade = 'Pass'), 0) AS dist_jumlah_pass,
    COALESCE(MAX(dn.jumlah)     FILTER (WHERE dn.grade = 'Fail'), 0) AS dist_jumlah_fail,

    COALESCE(MAX(dn.persentase) FILTER (WHERE dn.grade = 'A'),  0) AS dist_pct_A,
    COALESCE(MAX(dn.persentase) FILTER (WHERE dn.grade = 'AB'), 0) AS dist_pct_AB,
    COALESCE(MAX(dn.persentase) FILTER (WHERE dn.grade = 'B'),  0) AS dist_pct_B,
    COALESCE(MAX(dn.persentase) FILTER (WHERE dn.grade = 'BC'), 0) AS dist_pct_BC,
    COALESCE(MAX(dn.persentase) FILTER (WHERE dn.grade = 'C'),  0) AS dist_pct_C,
    COALESCE(MAX(dn.persentase) FILTER (WHERE dn.grade = 'D'),  0) AS dist_pct_D,
    COALESCE(MAX(dn.persentase) FILTER (WHERE dn.grade = 'E'),  0) AS dist_pct_E,
    COALESCE(MAX(dn.persentase) FILTER (WHERE dn.grade = 'Pass'), 0) AS dist_pct_pass,
    COALESCE(MAX(dn.persentase) FILTER (WHERE dn.grade = 'Fail'), 0) AS dist_pct_fail,
    CASE mk.jenis_nilai
        WHEN 'ABCDE' THEN
            COALESCE(MAX(dn.persentase) FILTER (WHERE dn.grade = 'A'),  0) +
            COALESCE(MAX(dn.persentase) FILTER (WHERE dn.grade = 'AB'), 0) +
            COALESCE(MAX(dn.persentase) FILTER (WHERE dn.grade = 'B'),  0) +
            COALESCE(MAX(dn.persentase) FILTER (WHERE dn.grade = 'BC'), 0) +
            COALESCE(MAX(dn.persentase) FILTER (WHERE dn.grade = 'C'),  0)
        WHEN 'Pass/Fail' THEN
            COALESCE(MAX(dn.persentase) FILTER (WHERE dn.grade = 'Pass'), 0)
    END AS dist_pct_lulus,

    -- ── Skor kuesioner ───────────────
    ROUND(MAX(sk.rata_skor) FILTER (WHERE sk.no_pertanyaan = 1)::NUMERIC,  2) AS skor_q1,
    ROUND(MAX(sk.rata_skor) FILTER (WHERE sk.no_pertanyaan = 2)::NUMERIC,  2) AS skor_q2,
    ROUND(MAX(sk.rata_skor) FILTER (WHERE sk.no_pertanyaan = 3)::NUMERIC,  2) AS skor_q3,
    ROUND(MAX(sk.rata_skor) FILTER (WHERE sk.no_pertanyaan = 4)::NUMERIC,  2) AS skor_q4,
    ROUND(MAX(sk.rata_skor) FILTER (WHERE sk.no_pertanyaan = 5)::NUMERIC,  2) AS skor_q5,
    ROUND(MAX(sk.rata_skor) FILTER (WHERE sk.no_pertanyaan = 6)::NUMERIC,  2) AS skor_q6,
    ROUND(MAX(sk.rata_skor) FILTER (WHERE sk.no_pertanyaan = 7)::NUMERIC,  2) AS skor_q7,
    ROUND(MAX(sk.rata_skor) FILTER (WHERE sk.no_pertanyaan = 8)::NUMERIC,  2) AS skor_q8,
    ROUND(MAX(sk.rata_skor) FILTER (WHERE sk.no_pertanyaan = 9)::NUMERIC,  2) AS skor_q9,
    ROUND(MAX(sk.rata_skor) FILTER (WHERE sk.no_pertanyaan = 10)::NUMERIC, 2) AS skor_q10,
    ROUND(MAX(sk.rata_skor) FILTER (WHERE sk.no_pertanyaan = 11)::NUMERIC, 2) AS skor_q11,
    ROUND(MAX(sk.rata_skor) FILTER (WHERE sk.no_pertanyaan = 12)::NUMERIC, 2) AS skor_q12,
    -- Avg per dimensi 
    ROUND(AVG(sk.rata_skor) FILTER (WHERE sk.no_pertanyaan BETWEEN 1  AND 3)::NUMERIC,  2) AS skor_avg_capaian,
    ROUND(AVG(sk.rata_skor) FILTER (WHERE sk.no_pertanyaan BETWEEN 4  AND 8)::NUMERIC,  2) AS skor_avg_pelaksanaan,
    ROUND(AVG(sk.rata_skor) FILTER (WHERE sk.no_pertanyaan BETWEEN 9  AND 10)::NUMERIC, 2) AS skor_avg_sarana,
    ROUND(AVG(sk.rata_skor) FILTER (WHERE sk.no_pertanyaan BETWEEN 11 AND 12)::NUMERIC, 2) AS skor_avg_perilaku,
    ROUND(AVG(sk.rata_skor)::NUMERIC, 2)                                                    AS skor_avg_overall

FROM kelas k
JOIN mata_kuliah mk         ON mk.matkul_id   = k.matkul_id
JOIN program_studi ps       ON ps.prodi_id    = mk.prodi_id
JOIN fakultas f             ON f.fakultas_id  = ps.fakultas_id
LEFT JOIN pengajar_kelas pk ON pk.kelas_id = k.kelas_id
LEFT JOIN dosen          d  ON d.dosen_id  = pk.dosen_id
LEFT JOIN distribusi_nilai dn ON dn.kelas_id = k.kelas_id
LEFT JOIN skor_kuesioner sk   ON sk.kelas_id = k.kelas_id
GROUP BY
    k.kelas_id, k.matkul_id, k.no_kelas, k.semester, k.tahun_ajaran, k.sks,
    mk.kode_mk, mk.nama_mk, mk.jenis_nilai, 
    ps.prodi_id, ps.kode_prodi, ps.singkatan_prodi, ps.nama_prodi, ps.jenjang,
    f.fakultas_id, f.kode_fakultas, f.nama_fakultas,
    k.pct_kehadiran_dosen, k.pct_kehadiran_mahasiswa,
    k.rata_rata_nilai, k.jumlah_mahasiswa, k.nilai_portofolio, k.is_synthetic;

CREATE UNIQUE INDEX idx_mv_pk          ON mv_kelas(kelas_id);
CREATE INDEX        idx_mv_prodi_sem   ON mv_kelas(prodi_id, semester, tahun_ajaran);
CREATE INDEX        idx_mv_fak_sem     ON mv_kelas(fakultas_id, semester, tahun_ajaran);
CREATE INDEX        idx_mv_matkul_sem  ON mv_kelas(kode_mk, semester, tahun_ajaran);
CREATE INDEX        idx_mv_dosen_arr   ON mv_kelas USING GIN (semua_dosen_id);

COMMENT ON MATERIALIZED VIEW mv_kelas IS
'1 row = 1 kelas portofolio, semua dimensi ter-flatten';
COMMENT ON COLUMN mv_kelas.semua_dosen_id IS 
'Array UUID dosen pengampu. Filter: WHERE dosen_id_target = ANY(semua_dosen_id). 
 Untuk join ke dosen: LEFT JOIN LATERAL unnest(semua_dosen_id) AS d(id) ON TRUE.';
-- ─────────────────────────────────────────────────────────────────────────────
-- MV 2: mv_statistik_prodi
-- Agregasi per prodi per semester+periode. Untuk View Prodi dan View Fakultas.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE MATERIALIZED VIEW mv_statistik_prodi AS
SELECT
    f.prodi_id,
    f.singkatan_prodi,
    f.nama_prodi,
    f.jenjang,
    f.fakultas_id,
    f.kode_fakultas,
    f.nama_fakultas,
    f.semester,
    f.tahun_ajaran,

    COUNT(DISTINCT f.kelas_id)              AS jumlah_kelas,
    COUNT(DISTINCT f.matkul_id)             AS jumlah_matkul_aktif,
    COUNT(DISTINCT d_unnest.dosen_id) AS jumlah_dosen_aktif,

    -- Statistik kehadiran & nilai
    ROUND(AVG(f.pct_kehadiran_dosen)::NUMERIC,      2) AS avg_kehadiran_dosen,
    ROUND(AVG(f.pct_kehadiran_mahasiswa)::NUMERIC,  2) AS avg_kehadiran_mahasiswa,
    ROUND(AVG(f.rata_rata_nilai)::NUMERIC,           3) AS avg_nilai,

    -- Distribusi nilai agregat (sum jumlah, avg pct)
    SUM(f.dist_jumlah_A)    AS total_mhs_A,
    SUM(f.dist_jumlah_AB)   AS total_mhs_AB,
    SUM(f.dist_jumlah_B)    AS total_mhs_B,
    SUM(f.dist_jumlah_BC)   AS total_mhs_BC,
    SUM(f.dist_jumlah_C)    AS total_mhs_C,
    SUM(f.dist_jumlah_D)    AS total_mhs_D,
    SUM(f.dist_jumlah_E)    AS total_mhs_E,
    ROUND(AVG(f.dist_pct_lulus)::NUMERIC, 2) AS avg_pct_lulus,

    -- Skor kuesioner per dimensi
    ROUND(AVG(f.skor_avg_capaian)::NUMERIC,     2) AS avg_skor_capaian,
    ROUND(AVG(f.skor_avg_pelaksanaan)::NUMERIC, 2) AS avg_skor_pelaksanaan,
    ROUND(AVG(f.skor_avg_sarana)::NUMERIC,      2) AS avg_skor_sarana,
    ROUND(AVG(f.skor_avg_perilaku)::NUMERIC,    2) AS avg_skor_perilaku,
    ROUND(AVG(f.skor_avg_overall)::NUMERIC,     2) AS avg_skor_overall

FROM mv_kelas f
LEFT JOIN LATERAL unnest(f.semua_dosen_id) AS d_unnest(dosen_id) ON TRUE
 
GROUP BY
    f.prodi_id, f.singkatan_prodi, f.nama_prodi, f.jenjang,
    f.fakultas_id, f.kode_fakultas, f.nama_fakultas,
    f.semester, f.tahun_ajaran;

CREATE UNIQUE INDEX idx_mv_prodi_pk  ON mv_statistik_prodi(prodi_id, semester, tahun_ajaran);
CREATE INDEX        idx_mv_prodi_fak ON mv_statistik_prodi(fakultas_id, semester, tahun_ajaran);

COMMENT ON MATERIALIZED VIEW mv_statistik_prodi IS
'Agregasi statistik per prodi per semester+periode. 
 Digunakan oleh View Prodi (overview) dan View Fakultas (perbandingan antar prodi).
 REFRESH: jalankan setelah refresh mv_kelas.';


-- ─────────────────────────────────────────────────────────────────────────────
-- MV 3: mv_statistik_dosen
-- Agregasi per dosen per semester+periode. Untuk View Dosen (overview).
-- ─────────────────────────────────────────────────────────────────────────────

CREATE MATERIALIZED VIEW mv_statistik_dosen AS
SELECT
    d_unnest.dosen_id                                      AS dosen_id,
    d.nama_dosen,
    d.kk_id                                               AS kk_id_dosen,
    kk.nama_kk,
    kk.fakultas_id                                          AS fakultas_id_dosen,
    f.semester,
    f.tahun_ajaran,

    COUNT(DISTINCT f.kelas_id)                              AS jumlah_kelas,
    COUNT(DISTINCT f.matkul_id)                             AS jumlah_matkul,
    SUM(f.sks)                                              AS total_sks_diajar,

    ROUND(AVG(f.pct_kehadiran_dosen)::NUMERIC,      2)     AS avg_kehadiran_dosen,
    ROUND(AVG(f.pct_kehadiran_mahasiswa)::NUMERIC,  2)     AS avg_kehadiran_mahasiswa,
    ROUND(AVG(f.rata_rata_nilai)::NUMERIC,           3)     AS avg_nilai,

    ROUND(AVG(f.skor_avg_capaian)::NUMERIC,     2)         AS avg_skor_capaian,
    ROUND(AVG(f.skor_avg_pelaksanaan)::NUMERIC, 2)         AS avg_skor_pelaksanaan,
    ROUND(AVG(f.skor_avg_sarana)::NUMERIC,      2)         AS avg_skor_sarana,
    ROUND(AVG(f.skor_avg_perilaku)::NUMERIC,    2)         AS avg_skor_perilaku,
    ROUND(AVG(f.skor_avg_overall)::NUMERIC,     2)         AS avg_skor_overall,

    array_agg(f.kelas_id ORDER BY f.matkul_id, f.no_kelas) AS kelas_ids,
    array_agg(f.kode_mk  ORDER BY f.matkul_id, f.no_kelas) AS kode_mk_list

FROM mv_kelas f
JOIN LATERAL unnest(f.semua_dosen_id) AS d_unnest(dosen_id) ON TRUE
JOIN dosen d ON d.dosen_id = d_unnest.dosen_id
JOIN kelompok_keahlian kk ON kk.kk_id = d.kk_id
GROUP BY
    d_unnest.dosen_id, d.nama_dosen, d.kk_id, kk.nama_kk, kk.fakultas_id,
    f.semester, f.tahun_ajaran;

CREATE UNIQUE INDEX idx_mv_dosen_pk     ON mv_statistik_dosen(dosen_id, semester, tahun_ajaran);
CREATE INDEX        idx_mv_dosen_kk     ON mv_statistik_dosen(kk_id_dosen, semester, tahun_ajaran);
CREATE INDEX        idx_mv_dosen_fak    ON mv_statistik_dosen(fakultas_id_dosen, semester, tahun_ajaran);

COMMENT ON MATERIALIZED VIEW mv_statistik_dosen IS
'Agregasi performa dosen per semester+periode.
 Digunakan oleh View Dosen (overview lintas kelas) dan View Prodi (profil dosen tab).
 REFRESH: jalankan setelah refresh mv_kelas.';


-- ╔══════════════════════════════════════════════════════════════╗
-- ║  REFRESH ORDER (jalankan setelah setiap ingestion batch)    ║
-- ╚══════════════════════════════════════════════════════════════╝
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mv_kelas;
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mv_statistik_prodi;
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mv_statistik_dosen;


-- ╔══════════════════════════════════════════════════════════════╗
-- ║  ROW LEVEL SECURITY                                         ║
-- ╚══════════════════════════════════════════════════════════════╝
-- Application layer set: SET LOCAL app.user_id = '<uuid>';

ALTER TABLE kelas               ENABLE ROW LEVEL SECURITY;
ALTER TABLE teks_portofolio     ENABLE ROW LEVEL SECURITY;
ALTER TABLE komentar_mahasiswa  ENABLE ROW LEVEL SECURITY;
ALTER TABLE vector_chunks       ENABLE ROW LEVEL SECURITY;

CREATE POLICY rls_kelas_all_roles ON kelas FOR SELECT USING (
    EXISTS (
        SELECT 1 FROM pengguna p
        WHERE p.user_id = current_setting('app.user_id', TRUE)::uuid
          AND p.role IN ('admin', 'wram')
    )
    OR
    EXISTS (
        SELECT 1 FROM pengajar_kelas pk
        JOIN user_scope us ON us.dosen_id = pk.dosen_id
        WHERE pk.kelas_id = kelas.kelas_id
          AND us.user_id  = current_setting('app.user_id', TRUE)::uuid
    )
    OR
    EXISTS (
        SELECT 1 FROM mata_kuliah mk
        JOIN user_scope us ON us.prodi_id = mk.prodi_id
        WHERE mk.matkul_id = kelas.matkul_id
          AND us.user_id   = current_setting('app.user_id', TRUE)::uuid
    )
    OR
    EXISTS (
        SELECT 1 FROM mata_kuliah mk
        JOIN program_studi ps ON ps.prodi_id    = mk.prodi_id
        JOIN user_scope us    ON us.fakultas_id = ps.fakultas_id
        WHERE mk.matkul_id = kelas.matkul_id
          AND us.user_id   = current_setting('app.user_id', TRUE)::uuid
    )
);

CREATE OR REPLACE FUNCTION user_can_see_kelas(p_kelas_id UUID)
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT EXISTS (
        SELECT 1 FROM pengguna p
        WHERE p.user_id = current_setting('app.user_id', TRUE)::uuid
          AND p.role IN ('admin', 'wram')
    )
    OR EXISTS (
        SELECT 1 FROM kelas k
        JOIN mata_kuliah mk ON mk.matkul_id = k.matkul_id
        WHERE k.kelas_id = p_kelas_id AND (
            EXISTS (
                SELECT 1 FROM pengajar_kelas pk
                JOIN user_scope us ON us.dosen_id = pk.dosen_id
                WHERE pk.kelas_id = p_kelas_id
                  AND us.user_id = current_setting('app.user_id',TRUE)::uuid
            )
            OR EXISTS (
                SELECT 1 FROM user_scope us
                WHERE us.prodi_id = mk.prodi_id
                  AND us.user_id = current_setting('app.user_id',TRUE)::uuid
            )
            OR EXISTS (
                SELECT 1 FROM program_studi ps
                JOIN user_scope us ON us.fakultas_id = ps.fakultas_id
                WHERE ps.prodi_id = mk.prodi_id
                  AND us.user_id = current_setting('app.user_id',TRUE)::uuid
            )
        )
    );
$$;

CREATE OR REPLACE FUNCTION fn_teks_reset_embedding()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.konten IS DISTINCT FROM OLD.konten THEN
        NEW.is_embedded := FALSE;
        NEW.embedded_at := NULL;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_teks_reset_embedding
    BEFORE UPDATE ON teks_portofolio
    FOR EACH ROW EXECUTE FUNCTION fn_teks_reset_embedding();

CREATE OR REPLACE FUNCTION fn_komentar_reset_embedding()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.teks_komentar IS DISTINCT FROM OLD.teks_komentar THEN
        NEW.is_embedded := FALSE;
        NEW.embedded_at := NULL;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_komentar_reset_embedding
    BEFORE UPDATE ON komentar_mahasiswa
    FOR EACH ROW EXECUTE FUNCTION fn_komentar_reset_embedding();

CREATE POLICY rls_vector_chunks ON vector_chunks FOR SELECT USING (
    user_can_see_kelas(kelas_id)
);
CREATE POLICY rls_teks ON teks_portofolio FOR SELECT USING (
    user_can_see_kelas(kelas_id)
);
CREATE POLICY rls_komentar ON komentar_mahasiswa FOR SELECT USING (
    user_can_see_kelas(kelas_id)
);
