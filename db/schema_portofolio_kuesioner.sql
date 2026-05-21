-- ================================================================
-- SCHEMA : Data Portofolio & Kuesioner Akademik ITB
-- Urutan : Jalankan file ini SEBELUM schema_auth_and_ingestion.sql
-- ================================================================
--
--  CATATAN :
--  Semua PK = UUID surrogate. Natural key SIX (integer) disimpan
--       di kolom six_*_id dengan UNIQUE. Gunakan six_*_id sebagai
--       lookup key saat upsert dari CSV.
--
--  distribusi_nilai = tabel terpisah row-based (bukan wide table).
--       Repeating groups melanggar 1NF (Codd, 1970).
--
--  hadir_dosen NULLABLE, tidak ada di CSV SIX saat ini.
--
--  komentar_mahasiswa = tabel terpisah untuk Q103 (saran teks bebas mahasiswa). Data belum ada di CSV SIX ITB saat ini.
--
--  ts_dna: dua kolom, ts_dna_raw TEXT (as-is dari CSV) +
--       ts_dna TIMESTAMPTZ (nullable, diisi setelah format dikonfirmasi).
--       Kleppmann (DDIA, 2017), Ch.3: simpan raw source untuk re-parsing.
--
--  Format lama (kd_pertanyaan 1–11, kd_grup 1–5): is_active=FALSE.
--       Format baru (kd_pertanyaan 12–19, kd_grup 6–9): is_active=TRUE.
--       Tidak ada enum format_versi — infer dari nilai kd_* alami.
--
--  no_ps di kelas: transitive dependency (kelas→no_ps→prodi_id).
--       Disimpan untuk ETL traceability — Kimball & Ross (The Data
--       Warehouse Toolkit, 3rd ed., 2013, pp.53–54): pertahankan
--       source system natural key untuk auditabilitas.
--
--   vector_chunks: filter keys (kode_mk, nama_prodi, dll.)
--       didenormalisasi untuk efisiensi RAG vector search tanpa JOIN.
--
-- UPSERT KEY MAP saat import CSV:
--   dosen.csv        : dosen_id (int)       → six_dosen_id
--   mata_kuliah.csv  : matkul_id (int)  → six_matkul_id
--   kelas.csv        : kelas_id (int)        → six_kelas_id
--                    : no_ps → kode_prodi → prodi_id
--                    : matkul_id → six_matkul_id → matkul_id
--   pengajar.csv     : kelas_id+dosen_id → six_* → UUID FK
--   nilai_kelas.csv  : kelas_id → six_kelas_id
--                    : JSON kuesioner keys → kd_pertanyaan → pertanyaan_kuesioner_id
--   nilai_dosen.csv  : kelas_id+dosen_id → six_* → UUID FK
--                    : JSON kuesioner keys → pertanyaan_kuesioner_id
--                    : JSON skor_kues keys (1,2,3) → agregat_kuesioner_key
--   portofolio.csv   : kelas_id → six_kelas_id
--                    : JSON isian keys → kd_pertanyaan → pertanyaan_portofolio_id
--                    : JSON komentar keys → kd_grup → pertanyaan_grup_id
-- ================================================================


-- ============================================================
-- SECTION 0 — EXTENSIONS
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- Trigram fuzzy search
CREATE EXTENSION IF NOT EXISTS "vector";     -- pgvector untuk embedding


-- ============================================================
-- SECTION 1 — ENUM TYPES
-- ============================================================

CREATE TYPE jenjang_prodi AS ENUM ('S1', 'S2', 'S3', 'Profesi');

CREATE TYPE jenis_nilai_mk AS ENUM ('ABCDE', 'PassFail');

-- Digunakan HANYA di vector_chunks sebagai metadata label filter.
CREATE TYPE tipe_konten_enum AS ENUM (
    'metode_perkuliahan',       -- kd_pertanyaan 1 (lama), 12 (baru)
    'sistem_penilaian',         -- kd_pertanyaan 3 (lama), 13 (baru)
    'statistik_kelas',          -- kd_pertanyaan 7 (lama), 14 (baru)
    'analisis_capaian_kelas',   -- kd_pertanyaan 8 (lama), 15 (baru)
    'komentar_kuesioner',       -- kd_pertanyaan 9 (lama), 16 (baru)
    'refleksi_pelaksanaan',     -- kd_pertanyaan 5 (lama), 17 (baru)
    'usulan_perbaikan_dosen',   -- kd_pertanyaan 10 (lama), 18 (baru)
    'usulan_perbaikan_itb'      -- kd_pertanyaan 11 (lama), 19 (baru)
);


-- ============================================================
-- SECTION 2 — REFERENCE TABLES
-- ============================================================

-- ── 2.1 Fakultas ─────────────────────────────────────────────────────────────
CREATE TABLE fakultas (
    fakultas_id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_fakultas_id  UUID         REFERENCES fakultas(fakultas_id) ON DELETE SET NULL,
    -- NULLABLE. Untuk hierarki sub-unit di bawah fakultas induk.
    -- Belum ada data ini di CSV; disediakan just-in-case.
    kode_fakultas       VARCHAR(20)  UNIQUE NOT NULL,
    -- e.g. 'FMIPA', 'STEI', 'FITB', 'SBM'
    nama_fakultas       VARCHAR(200) NOT NULL,
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_fakultas_parent ON fakultas (parent_fakultas_id);
COMMENT ON TABLE  fakultas                      IS 'Hierarki fakultas/sekolah ITB. Self-referencing via parent_fakultas_id untuk struktur sub-kampus.';
COMMENT ON COLUMN fakultas.kode_fakultas        IS 'Kode singkat sesuai SIX ITB, e.g. STEI, FITB, SBM.';
COMMENT ON COLUMN fakultas.parent_fakultas_id   IS 'NULL untuk fakultas induk. Diisi untuk sub-sekolah/kampus.';

-- ── 2.2 Kelompok Keahlian ────────────────────────────────────────────────────
CREATE TABLE kelompok_keahlian (
    kk_id       UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    fakultas_id UUID         NOT NULL REFERENCES fakultas(fakultas_id) ON DELETE RESTRICT,
    nama_kk     VARCHAR(300) NOT NULL,
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_kk_fakultas ON kelompok_keahlian (fakultas_id);
COMMENT ON TABLE kelompok_keahlian IS 'KK berada di level fakultas. Dosen berafiliasi ke KK, bukan langsung ke prodi.';

-- ── 2.3 Program Studi ────────────────────────────────────────────────────────
CREATE TABLE program_studi (
    prodi_id        UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    fakultas_id     UUID          NOT NULL REFERENCES fakultas(fakultas_id) ON DELETE RESTRICT,
    kode_prodi      VARCHAR(10)   UNIQUE NOT NULL,
    -- HARUS identik dengan no_ps di kelas.csv SIX ITB.
    -- e.g. '102'=Fisika, '230'=Teknik Kimia.
    singkatan_prodi VARCHAR(10),
    nama_prodi      VARCHAR(300)  NOT NULL,
    jenjang         jenjang_prodi NOT NULL DEFAULT 'S1',
    is_active       BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_prodi_fakultas ON program_studi (fakultas_id);
CREATE INDEX idx_prodi_kode     ON program_studi (kode_prodi);
-- idx_prodi_kode: KRITIS untuk ETL — lookup no_ps→prodi_id saat import kelas.csv
COMMENT ON TABLE  program_studi             IS '1 prodi hanya dimiliki 1 fakultas (no sharing). Relasi N:1 ke fakultas.';
COMMENT ON COLUMN program_studi.kode_prodi IS
    'Natural key SIX ITB: harus identik dengan nilai no_ps. '
    'Kode PDDikti, e.g. 102=Fisika, 230=Teknik Kimia. '
    'Dipakai sebagai lookup key di ETL saat import kelas.csv (no_ps -> prodi_id).';
COMMENT ON COLUMN program_studi.singkatan_prodi   IS 'Singkatan lazim, e.g. IF, STI — dipakai di label UI.';
COMMENT ON COLUMN program_studi.jenjang     IS 'S1, S2, S3, atau Profesi.';

-- ── 2.4 Dosen ────────────────────────────────────────────────────────────────
CREATE TABLE dosen (
    dosen_id        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    six_dosen_id    INTEGER      UNIQUE,
    -- Natural key dari dosen.csv SIX ITB (kolom dosen_id).

    kk_id           UUID         NOT NULL REFERENCES kelompok_keahlian(kk_id) ON DELETE RESTRICT,

    prodi_id UUID REFERENCES program_studi(prodi_id),
    nama_dosen      VARCHAR(300) NOT NULL,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_dosen_kk        ON dosen (kk_id);
CREATE INDEX idx_dosen_nama_trgm ON dosen USING GIN (nama_dosen gin_trgm_ops);
-- idx_dosen_nama_trgm: GIN trigram untuk fuzzy search nama dosen (chatbot & UI).

-- ── 2.5 Mata Kuliah ──────────────────────────────────────────────────────────
CREATE TABLE mata_kuliah (
    matkul_id       UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    six_matkul_id   INTEGER        UNIQUE,
    -- Natural key dari mata_kuliah.csv SIX ITB (kolom matkul_id).

    prodi_id        UUID           NOT NULL REFERENCES program_studi(prodi_id) ON DELETE RESTRICT,

    kode_mk       VARCHAR(20)    NOT NULL,
    -- e.g. 'FI1101', 'TK3101', 'WI1111'.
    -- Bukan UNIQUE sendirian: MK yang sama bisa ada di beberapa th_kur.

    nama_mk         VARCHAR(300)   NOT NULL,
    nama_mk_en         VARCHAR(300),
    tahun_kurikulum          SMALLINT NOT NULL,
    -- Tahun kurikulum: 2019, 2024, 2026.

    sks             SMALLINT       NOT NULL CHECK (sks > 0 AND sks <= 12),
    -- sks = atribut mata_kuliah, BUKAN kelas. Sesuai struktur mata_kuliah.csv.

    jenis_nilai     jenis_nilai_mk,
    -- NULLABLE. Tidak ada di CSV. Diisi manual admin.

    is_active       BOOLEAN        NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_mata_kuliah_prodi  ON mata_kuliah (prodi_id);
CREATE INDEX idx_mata_kuliah_kode_mk     ON mata_kuliah (kode_mk);
CREATE INDEX idx_mata_kuliah_th_kur ON mata_kuliah (tahun_kurikulum);
COMMENT ON TABLE  mata_kuliah IS
    'Katalog mata kuliah ITB. '
    'Satu kode_mk bisa muncul di beberapa tahun_kurikulum (MK sama, kurikulum berbeda).';
COMMENT ON COLUMN mata_kuliah.six_matkul_id IS
    'Natural key integer dari SIX ITB. '
    'Dipakai lookup ETL saat import kelas.csv.';
COMMENT ON COLUMN mata_kuliah.kode_mk IS
    'Kode MK, e.g. FI1101, TK3101, WI1111. '
    'Bukan UNIQUE sendirian karena MK yang sama bisa ada di beberapa tahun_kurikulum. '
    'Prefix WI = MK lintas-prodi (prodi_id = 179 untuk S1 dan prodi_id = 387 untuk S2 & S3).';
COMMENT ON COLUMN mata_kuliah.tahun_kurikulum IS
    'Tahun kurikulum: 2019, 2024, atau 2026 berdasarkan data aktual CSV.';
COMMENT ON COLUMN mata_kuliah.sks IS
    'Jumlah SKS mata kuliah. Atribut MK, bukan kelas. ';
COMMENT ON COLUMN mata_kuliah.jenis_nilai IS
    'Sistem penilaian: ABCDE (mayoritas Mata Kuliah) atau PassFail ';

-- ============================================================
-- SECTION 3 — QUESTIONNAIRE & PORTFOLIO REFERENCE TABLES
-- ============================================================

-- ── 3.1 Pertanyaan Kuesioner ─────────────────────────────────────────────────
-- 36 pertanyaan total. Keys yang muncul di data CSV:

--   nilai_kelas.kuesioner : Q21,22,23,24,28,29,30,35,37 (level kelas)
--   nilai_dosen.kuesioner : Q21-30,35,37 (termasuk Q25,26,27 per dosen)
--   is_spesifik_dosen=TRUE: Q25,Q26,Q27 — berbeda nilainya per dosen dalam kelas yang sama (TERVERIFIKASI dari data team-teaching)
--   is_teks_bebas=TRUE    : Q103 — data belum ada di CSV 

CREATE TABLE pertanyaan_kuesioner (
    pertanyaan_kuesioner_id UUID     PRIMARY KEY DEFAULT gen_random_uuid(),
    kd_pertanyaan           SMALLINT UNIQUE NOT NULL,
    -- Natural key dari pertanyaan_kuesioner.csv SIX ITB.

    pertanyaan              TEXT     NOT NULL,
    
    dimensi                 VARCHAR(60),
    -- 'capaian_pembelajaran'    → Q21,22,23
    -- 'pelaksanaan_perkuliahan' → Q24,25,26,27,28
    -- 'sarana_prasarana'        → Q29,30
    -- 'perilaku_mahasiswa'      → Q35,37
    -- 'saran'                   → Q103
    -- NULL                      → Q128–Q152

    is_spesifik_dosen       BOOLEAN  NOT NULL DEFAULT FALSE,
    -- TRUE untuk Q25,26,27. Skor di skor_kuesioner_dosen (per dosen per kelas).
    -- FALSE → skor di skor_kuesioner_kelas (level kelas, identik untuk semua dosen).
    -- tambahin comment di table

    is_teks_bebas           BOOLEAN  NOT NULL DEFAULT FALSE,
    -- TRUE untuk Q103. Tidak ada skor numerik. Teks di komentar_mahasiswa.

    is_active               BOOLEAN  NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  pertanyaan_kuesioner IS
    'Master data pertanyaan kuesioner evaluasi perkuliahan yang diisi oleh mahasiswa. '
    'Source: pertanyaan_kuesioner.csv SIX ITB. '
    'kd_pertanyaan adalah natural key dari CSV. '
    'Pertanyaan level kelas (Q21-24,28-30,35,37) skornya di skor_kuesioner_kelas. '
    'Pertanyaan spesifik dosen (Q25,26,27) skornya di skor_kuesioner_dosen. '
    'Pertanyaan teks bebas (Q103) jawabannya di komentar_mahasiswa.';
COMMENT ON COLUMN pertanyaan_kuesioner.kd_pertanyaan IS
    'Natural key integer dari pertanyaan_kuesioner.csv SIX ITB. '
    'Range aktual: Q21-Q37, Q103, Q128-Q152.';
COMMENT ON COLUMN pertanyaan_kuesioner.dimensi IS
    'Kategori dimensi evaluasi untuk agregasi dashboard. '
    'NULL untuk pertanyaan tambahan (Q128-Q152) yang belum dikategorikan.';
COMMENT ON COLUMN pertanyaan_kuesioner.is_spesifik_dosen IS
    'TRUE untuk Q25, Q26, Q27 saja. '
    'Pertanyaan ini menilai dosen secara individual sehingga skornya berbeda per dosen '
    'dalam kelas yang sama (team-teaching). Skor disimpan di skor_kuesioner_dosen. '
    'TERVERIFIKASI 100% dari cross-check nilai_kelas.csv x nilai_dosen.csv (1.960 baris).';
COMMENT ON COLUMN pertanyaan_kuesioner.is_teks_bebas IS
    'TRUE untuk Q103 (saran bebas mahasiswa). '
    'Tidak menghasilkan skor numerik — jawaban teks ada di komentar_mahasiswa. '
    'Data Q103 belum tersedia di CSV SIX ITB saat ini.';
COMMENT ON COLUMN pertanyaan_kuesioner.is_active IS
    'TRUE jika pertanyaan masih aktif digunakan. FALSE jika sudah tidak dipakai.';



-- ── 3.2 Grup Pertanyaan Portofolio ───────────────────────────────────────────
-- 9 grup: kd_grup 1–5 (lama, is_active=FALSE), kd_grup 6–9 (baru, is_active=TRUE).
-- Data aktual portofolio.csv komentar: kd_grup 6,7,8,9 saja.
-- Tidak ada kolom format_versi — infer dari kd_grup (1–5=lama, 6–9=baru).

CREATE TABLE pertanyaan_grup_portofolio (
    pertanyaan_grup_id  UUID     PRIMARY KEY DEFAULT gen_random_uuid(),
    kd_grup             SMALLINT UNIQUE NOT NULL,
    -- Natural key dari pertanyaan_grup_portofolio.csv SIX ITB.
    -- 1=Pencapaian, 2=Pelaksanaan, 3=Refleksi, 4=RTL, 5=Rekomendasi (lama)
    -- 6=Penyelenggaraan, 7=Ketercapaian, 8=Refleksi Dosen, 9=Rekomendasi (baru)


    nama_grup           TEXT     NOT NULL,
    is_active           BOOLEAN  NOT NULL DEFAULT TRUE,
    -- FALSE untuk kd_grup 1–5 (format lama). TRUE untuk kd_grup 6–9 (aktif).
    -- tambah comment kalau is_active = true pertanyaan terpakai atau masih aktif sekarang, kalau false sudah tidak aktif
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE  pertanyaan_grup_portofolio IS
    'Master data 9 grup pertanyaan portofolio. '
    'Source: pertanyaan_grup_portofolio.csv SIX ITB. '
    'kd_grup 1-5 = format lama (is_active=FALSE, sebelum migrasi SIX). '
    'kd_grup 6-9 = format baru aktif (is_active=TRUE, data aktual portofolio.csv). '
    'Digunakan sebagai lookup FK dari komentar_verifikator (JSON komentar portofolio.csv).';
COMMENT ON COLUMN pertanyaan_grup_portofolio.kd_grup IS
    'Natural key integer dari pertanyaan_grup_portofolio.csv. '
    'Sama dengan key di JSON komentar di portofolio.csv. '
    'kd_grup 6=Penyelenggaraan Perkuliahan, 7=Ketercapaian Outcomes, '
    '8=Refleksi dan Evaluasi Dosen, 9=Rekomendasi Tindak Lanjut.';
COMMENT ON COLUMN pertanyaan_grup_portofolio.is_active IS
    'TRUE = grup pertanyaan ini masih aktif dan digunakan saat ini (format baru, kd_grup 6-9). '
    'FALSE = grup dari format lama yang sudah tidak digunakan (kd_grup 1-5, sebelum migrasi SIX).';

-- ── 3.3 Pertanyaan Portofolio ────────────────────────────────────────────────
-- 19 pertanyaan: kd 1–11 lama (is_active=FALSE), kd 12–19 baru (is_active=TRUE).
-- Data aktual portofolio.csv isian: kd 12–19 saja.

-- Tanpa urutan_dalam_grup (kolom tidak ada di CSV) — gunakan ORDER BY kd_pertanyaan.
-- Tanpa format_versi — infer dari kd_pertanyaan (1–11=lama, 12–19=baru).

CREATE TABLE pertanyaan_portofolio (
    pertanyaan_portofolio_id UUID     PRIMARY KEY DEFAULT gen_random_uuid(),
    pertanyaan_grup_id       UUID     NOT NULL REFERENCES pertanyaan_grup_portofolio(pertanyaan_grup_id),

    kd_pertanyaan            SMALLINT UNIQUE NOT NULL,
    -- Natural key dari pertanyaan_portofolio.csv SIX ITB.
    -- kd 1–11 = format lama | kd 12–19 = format baru (aktif).

    pertanyaan               TEXT     NOT NULL,
    deskripsi                TEXT,
    -- Panduan pengisian dosen. Dari kolom deskripsi CSV.

    is_active                BOOLEAN  NOT NULL DEFAULT TRUE,
    -- FALSE untuk kd 1–11 (lama). TRUE untuk kd 12–19 (baru aktif).
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
    
);
CREATE INDEX idx_pp_grup      ON pertanyaan_portofolio (pertanyaan_grup_id);
CREATE INDEX idx_pp_is_active ON pertanyaan_portofolio (is_active);
COMMENT ON TABLE  pertanyaan_portofolio IS
    'Master data pertanyaan isian portofolio dosen. '
    'Source: pertanyaan_portofolio.csv SIX ITB. '
    'kd 1-11 = format lama (is_active=FALSE). kd 12-19 = format baru aktif (is_active=TRUE). '
    'Digunakan sebagai lookup FK dari teks_portofolio (JSON isian portofolio.csv). '
    'Untuk urutan tampil: gunakan ORDER BY kd_pertanyaan.';
COMMENT ON COLUMN pertanyaan_portofolio.kd_pertanyaan IS
    'Natural key integer dari pertanyaan_portofolio.csv. '
    'Sama dengan key di JSON isian di portofolio.csv. '
    'kd 1-11 = format lama | kd 12-19 = format baru aktif.';
COMMENT ON COLUMN pertanyaan_portofolio.deskripsi IS
    'Panduan atau petunjuk pengisian untuk dosen. '
    'Dari kolom deskripsi di pertanyaan_portofolio.csv. NULLABLE.';
COMMENT ON COLUMN pertanyaan_portofolio.is_active IS
    'TRUE = pertanyaan ini masih aktif digunakan (format baru, kd 12-19). '
    'FALSE = pertanyaan dari format lama yang sudah tidak digunakan (kd 1-11).';
 

-- ============================================================
-- SECTION 4 — CORE TRANSACTION TABLES
-- ============================================================

-- ── 4.1 Kelas ────────────────────────────────────────────────────────────────
-- Menyimpan no_ps DAN prodi_id:
--   no_ps    = ETL traceability (source system key dari SIX ITB)
--   prodi_id = UUID FK untuk JOIN efisien di semua query aplikasi
-- Secara ketat ini adalah transitive dependency (melanggar 3NF),
-- tapi diterima sebagai pragmatic exception — Kimball (2013).

CREATE TABLE kelas (
    kelas_id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    six_kelas_id    INTEGER     UNIQUE,
    -- Natural key dari kelas.csv SIX ITB (kolom kelas_id).

    matkul_id       UUID        NOT NULL REFERENCES mata_kuliah(matkul_id) ON DELETE RESTRICT,
    no_kelas        SMALLINT    NOT NULL,
    -- Nomor kelas paralel, e.g. 1, 2, 3, 41, 42. Dari kolom no_kelas CSV.
    
    semester        SMALLINT    NOT NULL CHECK (semester IN (1, 2, 3)),
    -- 1=Ganjil, 2=Genap, 3=Semester Pendek.
    
    tahun           SMALLINT    NOT NULL,
    -- Tahun ajaran dapat diinfer dari semester, kalau tahun 2024 semester ganjil, berarti nanti tahun ajaran 2024/2025, kalau semester genap berarti 2023/2024

    prodi_id        UUID        NOT NULL REFERENCES program_studi(prodi_id) ON DELETE RESTRICT,
    -- Lookup: no_ps → kode_prodi di program_studi → prodi_id.

    no_ps           SMALLINT    NOT NULL,
    -- Natural key SIX ITB dari kolom no_ps kelas.csv. Disimpan untuk ETL traceability.

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_kelas_matkul          ON kelas (matkul_id);
CREATE INDEX idx_kelas_prodi           ON kelas (prodi_id);
CREATE INDEX idx_kelas_tahun_sem       ON kelas (tahun, semester);
CREATE INDEX idx_kelas_prodi_tahun_sem ON kelas (prodi_id, tahun, semester);
-- idx_kelas_prodi_tahun_sem: COMPOSITE — query paling umum di dashboard:
-- "semua kelas prodi X semester Y tahun Z". Menggabungkan 3 WHERE sekaligus.
COMMENT ON TABLE  kelas IS
    '1 baris = 1 penyelenggaraan kelas dalam 1 semester. '
    'Menyimpan no_ps (natural key SIX) dan prodi_id (UUID FK) secara bersamaan ';
COMMENT ON COLUMN kelas.six_kelas_id IS
    'Natural key integer dari SIX ITB (kolom kelas_id di kelas.csv). ';
COMMENT ON COLUMN kelas.no_kelas IS
    'Nomor kelas paralel';
COMMENT ON COLUMN kelas.semester IS
    '1=Ganjil, 2=Genap, 3=Semester Pendek.';
COMMENT ON COLUMN kelas.tahun IS
    'Tahun berlangsungnya kelas. Tahun ajaran yang berlaku akan sesuai dengan semester berlangsungnya kelas, e.g. 2024 pada semester 1 untuk TA 2024/2025. '
    'Untuk semester ganjil (1): TA adalah tahun/tahun+1. '
    'Untuk semester genap (2): TA adalah tahun-1/tahun.';
COMMENT ON COLUMN kelas.no_ps IS
    'Disimpan untuk audit: jika mapping prodi_id salah, bisa di-trace dari no_ps asli. '
    'Nilai ini harus identik dengan kode_prodi di tabel program_studi.';
 

-- ── 4.2 Pengajar Kelas ───────────────────────────────────────────────────────
CREATE TABLE pengajar_kelas (
    pengajar_kelas_id   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    kelas_id            UUID        NOT NULL REFERENCES kelas(kelas_id) ON DELETE CASCADE,
    dosen_id            UUID        NOT NULL REFERENCES dosen(dosen_id) ON DELETE RESTRICT,
    weight              SMALLINT    NOT NULL DEFAULT 100 CHECK (weight >= 0),
    is_utama            BOOLEAN     NOT NULL DEFAULT TRUE,
    -- TRUE = dosen pengampu utama. FALSE = co-lecturer / asisten dosen.

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (kelas_id, dosen_id)
);
CREATE INDEX idx_pengajar_kelas_dosen       ON pengajar_kelas (dosen_id);
-- idx_pengajar_kelas_dosen: lookup "dosen X mengajar kelas apa?" — dipakai profil dosen & RLS
CREATE INDEX idx_pengajar_kelas_kelas       ON pengajar_kelas (kelas_id);
CREATE INDEX idx_pengajar_kelas_kelas_utama ON pengajar_kelas (kelas_id, is_utama);
-- idx_pengajar_kelas_kelas_utama: filter dosen utama saja untuk aggregasi di dashboard
COMMENT ON TABLE  pengajar_kelas IS
    'Relasi many-to-many antara kelas dan dosen (team-teaching). '
    '1 dosen bisa mengajar banyak kelas; 1 kelas bisa diampu banyak dosen. '
    'Surrogate UUID PK + UNIQUE(kelas_id, dosen_id) untuk konsistensi referensi. '
    'Tabel ini tidak memerlukan RLS — informasi siapa mengajar apa tidak sensitif.';
COMMENT ON COLUMN pengajar_kelas.is_utama IS
    'TRUE = dosen pengampu utama. FALSE = co-lecturer, asisten, atau koordinator. ';

-- ============================================================
-- SECTION 5 — ASSESSMENT TABLES
-- ============================================================

-- ── 5.1 Statistik Kelas ────────────────────────────
-- konten tabel ini adalah statistik operasional (kehadiran, IP, DNA), bukan nilai grading.
-- Shared PK (= kelas_id): relasi 1:1 dengan kelas.

CREATE TABLE statistik_kelas (
    kelas_id        UUID         PRIMARY KEY REFERENCES kelas(kelas_id) ON DELETE CASCADE,
    -- Shared PK: 1:1 dengan kelas. Kelas_id langsung sebagai PK.

    pct_kehadiran_mahasiswa       NUMERIC(5,2) CHECK (pct_kehadiran_mahasiswa IS NULL OR pct_kehadiran_mahasiswa BETWEEN 0 AND 100),

    pct_kehadiran_dosen     NUMERIC(5,2) CHECK (pct_kehadiran_dosen IS NULL OR pct_kehadiran_dosen BETWEEN 0 AND 100),
    -- NULLABLE — tidak ada di CSV SIX saat ini. 

    ip_mhs          NUMERIC(4,2) CHECK (ip_mhs IS NULL OR ip_mhs BETWEEN 0 AND 4),

    jumlah_mahasiswa SMALLINT    CHECK (jumlah_mahasiswa IS NULL OR jumlah_mahasiswa >= 0),
    -- Total peserta kelas. NULLABLE — bisa diisi dari sumber suplemen.
    -- di csv juga tidak ada jumlah_mahasiswa

    skor_dna        SMALLINT NOT NULL,
    -- Skor dari sistem DNA SIX ITB. Makna resmi belum terkonfirmasi.

    ts_dna_raw      TEXT NOT NULL,
    -- Nilai ts_dna as-is dari CSV SIX ITB. Format belum dikonfirmasi.
    -- Disimpan untuk audit/traceability. Kleppmann (DDIA, 2017): raw source
    -- memungkinkan re-parse jika format berubah di masa depan.

    ts_dna          TIMESTAMPTZ,
    -- Hasil parse ts_dna_raw. Gunakan kolom ini untuk filter periode di dashboard setelah terisi.

    ip_mhs_dna      NUMERIC(4,2) CHECK (ip_mhs_dna IS NULL OR ip_mhs_dna BETWEEN 0 AND 4),
    -- IP mahasiswa versi DNA. NULLABLE.

    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_sk_ts_dna ON statistik_kelas (ts_dna) WHERE ts_dna IS NOT NULL;
-- Partial index: hanya baris yang ts_dna sudah di-parse. Dipakai filter periode.
COMMENT ON TABLE  statistik_kelas IS
    'Statistik operasional per kelas: kehadiran, IP mahasiswa, dan data DNA SIX ITB. '
    'Relasi 1:1 dengan kelas (shared PK = kelas_id). ';
COMMENT ON COLUMN statistik_kelas.pct_kehadiran_mahasiswa IS
    'Persentase kehadiran mahasiswa (0.00-100.00). ';
COMMENT ON COLUMN statistik_kelas.pct_kehadiran_dosen IS
    'Persentase kehadiran dosen.';
COMMENT ON COLUMN statistik_kelas.ts_dna_raw IS
    'Nilai ts_dna as-is dari file CSV SIX. NOT NULL. Format belum dikonfirmasi. '
    'Disimpan untuk audit agar bisa di-re-parse jika format terkonfirmasi nantinya.';
COMMENT ON COLUMN statistik_kelas.ts_dna IS
    'Hasil parse ts_dna_raw ke TIMESTAMPTZ. ';
 

-- ── 5.2 Distribusi Nilai (row-based) ────────────────────────────────────
-- Terpisah dari statistik_kelas. Alasan row-based:
--   1. Wide 14 kolom nullable melanggar 1NF (repeating groups, Codd 1970)
--   2. Extensible: grade baru = INSERT baris, bukan ALTER TABLE
--   3. Mixed grading (ABCDE vs Pass/Fail) handled via grade CHECK

-- Data belum ada di CSV SIX ITB

CREATE TABLE distribusi_nilai (
    distribusi_id   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    kelas_id        UUID         NOT NULL REFERENCES kelas(kelas_id) ON DELETE CASCADE,
    grade           VARCHAR(5)   NOT NULL CHECK (grade IN ('A','AB','B','BC','C','D','E','Pass','Fail')),
    jumlah          SMALLINT     NOT NULL DEFAULT 0 CHECK (jumlah >= 0),
    persentase      NUMERIC(5,2) CHECK (persentase IS NULL OR persentase BETWEEN 0 AND 100),
    CONSTRAINT uq_distribusi_kelas_grade UNIQUE (kelas_id, grade)
);
CREATE INDEX idx_distribusi_kelas ON distribusi_nilai (kelas_id);

COMMENT ON TABLE  distribusi_nilai IS
    'Distribusi nilai per kelas, row-based (1 baris per grade per kelas). '
    'Jenis grade yang diisi mengikuti jenis_nilai di mata_kuliah: '
    'ABCDE -> grade A/AB/B/BC/C/D/E; PassFail -> grade Pass/Fail. ';
COMMENT ON COLUMN distribusi_nilai.grade IS
    'Nilai huruf. ABCDE system: A/AB/B/BC/C/D/E. PassFail system: Pass/Fail. '
    'Harus konsisten dengan jenis_nilai di mata_kuliah untuk kelas tersebut.';
COMMENT ON COLUMN distribusi_nilai.persentase IS
    'Persentase mahasiswa yang mendapat grade ini (0.00-100.00). ';

-- ── 5.3 Nilai Dosen ───────────────────────────────────────────────────────────
-- Final composite score per dosen per kelas.
-- PRIVAT: dosen hanya bisa akses nilai_akhir miliknya sendiri. dipisah dari pengajar_kelas untuk mendukung rls.

-- Detail per pertanyaan → skor_kuesioner_dosen.
-- Skor dimensi agregat (key 1,2,3) → skor_agregat_kuesioner_dosen.

CREATE TABLE nilai_dosen (
    nilai_dosen_id  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    kelas_id        UUID         NOT NULL REFERENCES kelas(kelas_id) ON DELETE CASCADE,
    dosen_id        UUID         NOT NULL REFERENCES dosen(dosen_id) ON DELETE RESTRICT,

    nilai_akhir     NUMERIC(6,4) CHECK (nilai_akhir IS NULL OR nilai_akhir BETWEEN 0 AND 4),
    -- Nilai akhir komposit dari nilai_dosen.csv. Range data aktual: 2.016–4.000.
    -- Formula komposit belum dikonfirmasi secara resmi (bukan avg sederhana key 1,2,3).
    -- PRIVAT: tidak boleh diakses dosen lain. 

    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (kelas_id, dosen_id)
);
CREATE INDEX idx_nilai_dosen_dosen ON nilai_dosen (dosen_id);
-- idx_nilai_dosen_dosen: KRITIS untuk RLS — filter per dosen di setiap query dosen.
CREATE INDEX idx_nilai_dosen_kelas ON nilai_dosen (kelas_id);
COMMENT ON TABLE  nilai_dosen IS
    'Nilai akhir komposit per dosen per kelas. '
    'PRIVAT (RLS): dosen hanya bisa mengakses nilai_akhir miliknya sendiri, bukan nilai_akhir dosen lain. '
    'Detail skor per pertanyaan ada di skor_kuesioner_dosen. '
    'Skor dimensi agregat ada di skor_agregat_kuesioner_dosen.';
COMMENT ON COLUMN nilai_dosen.nilai_akhir IS
    'Nilai akhir komposit dari nilai_dosen.csv. Skala 0.0000-4.0000. '
    'PRIVAT: RLS memastikan dosen hanya bisa melihat nilai miliknya sendiri.';
 

-- ============================================================
-- SECTION 6 — QUESTIONNAIRE SCORE TABLES
-- ============================================================

-- ── 6.1 Skor Kuesioner per Kelas ─────────────────────────────────────────────
-- Skor rata-rata per pertanyaan pada LEVEL KELAS (bukan per dosen).
-- Source: nilai_kelas.csv kolom kuesioner (JSON).

-- Pertanyaan: Q21,Q22,Q23,Q24,Q28,Q29,Q30,Q35,Q37
-- (9 pertanyaan — TERVERIFIKASI dari nilai_kelas.kuesioner keys)

CREATE TABLE skor_kuesioner_kelas (
    skor_kelas_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    kelas_id                UUID         NOT NULL REFERENCES kelas(kelas_id) ON DELETE CASCADE,
    pertanyaan_kuesioner_id UUID         NOT NULL REFERENCES pertanyaan_kuesioner(pertanyaan_kuesioner_id),
    rata_skor                    NUMERIC(5,4) NOT NULL CHECK (rata_skor BETWEEN 1 AND 4),
    -- Skor Likert rata-rata 1.0000–4.0000. NOT NULL: semua Q di nilai_kelas.csv punya nilai.
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (kelas_id, pertanyaan_kuesioner_id)
);
CREATE INDEX idx_skor_kuesioner_kelas_kelas      ON skor_kuesioner_kelas (kelas_id);
CREATE INDEX idx_skor_kuesioner_kelas_pertanyaan ON skor_kuesioner_kelas (pertanyaan_kuesioner_id);
COMMENT ON TABLE  skor_kuesioner_kelas IS
    'Skor Likert rata-rata per pertanyaan kuesioner pada level kelas. '
    'Nilai di tabel ini identik untuk semua dosen dalam satu kelas. '
    'Pertanyaan yang ada: Q21,Q22,Q23,Q24,Q28,Q29,Q30,Q35,Q37 '
    'Tidak ada RLS ketat — data skor level kelas bukan privat per dosen.';
COMMENT ON COLUMN skor_kuesioner_kelas.rata_skor IS
    'Rata-rata skor Likert (1.0000-4.0000) dari seluruh mahasiswa yang mengisi. ';
 

-- ── 6.2 Skor Kuesioner per Dosen ─────────────────────────────────────────────
-- Skor per pertanyaan yang SPESIFIK per individu dosen.
-- Source: nilai_dosen.csv kolom kuesioner (JSON).

-- Pertanyaan: Q25,Q26,Q27
-- (3 pertanyaan spesifik dosen — TERVERIFIKASI dari nilai_dosen.kuesioner keys)
-- Bukti: nilai Q25,26,27 berbeda per dosen dalam kelas yang sama (team-teaching).

-- PRIVAT: dosen hanya bisa akses skor miliknya sendiri. 
CREATE TABLE skor_kuesioner_dosen (
    skor_dosen_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    kelas_id                UUID         NOT NULL REFERENCES kelas(kelas_id) ON DELETE CASCADE,
    dosen_id                UUID         NOT NULL REFERENCES dosen(dosen_id) ON DELETE RESTRICT,
    pertanyaan_kuesioner_id UUID         NOT NULL REFERENCES pertanyaan_kuesioner(pertanyaan_kuesioner_id),
    rata_skor                    NUMERIC(5,4) NOT NULL CHECK (rata_skor BETWEEN 1 AND 4),
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (kelas_id, dosen_id, pertanyaan_kuesioner_id)
);
CREATE INDEX idx_skor_kuesioner_dosen_dosen      ON skor_kuesioner_dosen (dosen_id);
-- idx_skor_kuesioner_dosen_dosen: KRITIS untuk RLS — setiap query dosen filter by dosen_id.
CREATE INDEX idx_skor_kuesioner_dosen_kelas      ON skor_kuesioner_dosen (kelas_id);
CREATE INDEX idx_skor_kuesioner_dosen_pertanyaan ON skor_kuesioner_dosen (pertanyaan_kuesioner_id);
COMMENT ON TABLE  skor_kuesioner_dosen IS
    'Skor Likert per pertanyaan kuesioner yang spesifik per individu dosen. '
    'Hanya Q25, Q26, Q27 — TERVERIFIKASI berbeda nilainya per dosen dalam team-teaching. '
    'PRIVAT (RLS): dosen hanya bisa mengakses skor Q25/26/27 miliknya sendiri.';
COMMENT ON COLUMN skor_kuesioner_dosen.dosen_id IS
    'FK ke dosen. RLS memastikan pengguna dengan role dosen hanya bisa mengakses baris dengan dosen_id milik mereka sendiri (via app.dosen_id).';
COMMENT ON COLUMN skor_kuesioner_dosen.rata_skor IS
    'Rata-rata skor Likert (1.0000-4.0000) dari seluruh mahasiswa yang mengisi pertanyaan yang ditujukan khusus ke dosen ini.';
 

-- ── 6.3 Skor Dimensi per Dosen ───────────────────────────────────
-- Skor agregat 3 dimensi dari skor_kues JSON di nilai_dosen.csv.
-- TERVERIFIKASI 100% pada 1.960 baris:
--   dimensi_key=1: avg(Q21,Q22,Q23)               -- Q21-23 dari nilai_kelas.kuesioner
--   dimensi_key=2: avg(Q24,Q25,Q26,Q27,Q28)        -- Q25-27 dari nilai_dosen.kuesioner
--   dimensi_key=3: avg(Q35,Q37)                    -- Q35,37 dari nilai_kelas.kuesioner

CREATE TABLE skor_agregat_kuesioner_dosen (
    skor_agregat_id UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    kelas_id        UUID         NOT NULL REFERENCES kelas(kelas_id) ON DELETE CASCADE,
    dosen_id        UUID         NOT NULL REFERENCES dosen(dosen_id) ON DELETE RESTRICT,
    agregat_kuesioner_key     SMALLINT     NOT NULL CHECK (agregat_kuesioner_key IN (1, 2, 3)),
    -- Integer key sesuai key di JSON skor_kues nilai_dosen.csv.

    agregat_kuesioner_nama    VARCHAR(60),
    -- NULLABLE. Label diperkirakan berdasarkan verifikasi data:
    -- 1 → 'capaian_pembelajaran' | 2 → 'pelaksanaan_perkuliahan' | 3 → 'perilaku_mahasiswa'

    rata_skor            NUMERIC(5,4) NOT NULL CHECK (rata_skor BETWEEN 1 AND 4),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (kelas_id, dosen_id, agregat_kuesioner_key)
);
CREATE INDEX idx_skor_agregat_kuesioner_dosen_dosen ON skor_agregat_kuesioner_dosen (dosen_id);
CREATE INDEX idx_skor_agregat_kuesioner_dosen_kelas ON skor_agregat_kuesioner_dosen (kelas_id);

COMMENT ON TABLE  skor_agregat_kuesioner_dosen IS
    'Skor agregat 3 dimensi kuesioner per dosen per kelas. Row-based. '
    'Source: kolom skor_kues (JSON, key 1/2/3) di nilai_dosen.csv SIX ITB. '
    'PRIVAT (RLS): sama level privasi dengan skor_kuesioner_dosen.';
COMMENT ON COLUMN skor_agregat_kuesioner_dosen.agregat_kuesioner_key IS
    'Integer key dari JSON skor_kues di nilai_dosen.csv (1, 2, atau 3). '
    'Key 1 = avg(Q21,22,23). '
    'Key 2 = avg(Q24,25,26,27,28). '
    'Key 3 = avg(Q35,37). ';
COMMENT ON COLUMN skor_agregat_kuesioner_dosen.agregat_kuesioner_nama IS
    'Label tekstual untuk dimensi agregat.';
COMMENT ON COLUMN skor_agregat_kuesioner_dosen.rata_skor IS
    'Rata-rata skor Likert hasil agregasi (1.0000-4.0000).';

-- ============================================================
-- SECTION 7 — PORTFOLIO TEXT TABLES
-- ============================================================

-- ── 7.1 Teks Portofolio ───────────────────────
-- Teks isian dosen per pertanyaan portofolio per kelas.
-- Source: portofolio.csv kolom isian (JSON {kd_pertanyaan: teks}).
-- Data aktual: kd_pertanyaan 12–19. Historis (jika diimpor): kd 1–11.

-- Menggunakan FK ke pertanyaan_portofolio (bukan enum) untuk scalability.
-- "teks_bersih" = HTML tags di-strip via regex.
-- HTML entities (&nbsp;, dll.) TIDAK dibersihkan di DB — cleaning lebih
-- dalam dilakukan di ETL layer Python (html.unescape, BeautifulSoup).

CREATE TABLE teks_portofolio (
    teks_portofolio_id       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    kelas_id                 UUID        NOT NULL REFERENCES kelas(kelas_id) ON DELETE CASCADE,
    pertanyaan_portofolio_id UUID        NOT NULL REFERENCES pertanyaan_portofolio(pertanyaan_portofolio_id),

    teks_raw                 TEXT,
    -- Konten asli dari JSON SIX ITB. Dapat mengandung HTML tags. Disimpan as-is.

    teks_bersih              TEXT GENERATED ALWAYS AS (
        regexp_replace(COALESCE(teks_raw, ''), E'<[^>]*>', '', 'g')
    ) STORED,

    is_embedded              BOOLEAN     NOT NULL DEFAULT FALSE,
    embedded_at              TIMESTAMPTZ,
    -- NULL = belum di-embed. Diisi pipeline setelah sukses embed ke vector store.

    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (kelas_id, pertanyaan_portofolio_id)
);
CREATE INDEX idx_teks_portofolio_kelas      ON teks_portofolio (kelas_id);
CREATE INDEX idx_teks_portofolio_pertanyaan ON teks_portofolio (pertanyaan_portofolio_id);
CREATE INDEX idx_teks_portofolio_embedded   ON teks_portofolio (is_embedded) WHERE is_embedded = FALSE;
-- idx_teks_portofolio_embedded: partial index hanya baris belum di-embed. Pipeline scan lebih efisien.
CREATE INDEX idx_teks_portofolio_fts        ON teks_portofolio
    USING GIN (to_tsvector('indonesian', COALESCE(teks_bersih, '')));
-- idx_teks_portofolio_fts: GIN full-text search untuk pencarian konten portofolio di chatbot.

COMMENT ON TABLE  teks_portofolio IS
    'Teks isian portofolio dosen per pertanyaan per kelas. '
    'Data aktual: kd_pertanyaan 12-19 (format baru). '
    'Data historis (jika diimpor): kd 1-11 (format lama, is_active=FALSE). '
    'teks_raw disimpan as-is dari CSV (bisa mengandung HTML). '
    'is_embedded + embedded_at untuk tracking status RAG vector store.';
COMMENT ON COLUMN teks_portofolio.teks_raw IS
    'Konten isian portofolio as-is dari JSON SIX ITB. '
    'Dapat mengandung HTML tags (p, br, nbsp, dll.). '
    'Digunakan untuk rendering UI (tampilkan dengan HTML rendering).';
COMMENT ON COLUMN teks_portofolio.teks_bersih IS
    'Generated column: teks_raw dengan HTML tags di-strip via regexp_replace. ';
COMMENT ON COLUMN teks_portofolio.is_embedded IS
    'FALSE = teks belum pernah di-embed ke vector store. '
    'TRUE = teks sudah di-embed (pipeline embedding selesai). '
    'Set ke FALSE kembali jika teks_raw diupdate.';
COMMENT ON COLUMN teks_portofolio.embedded_at IS
    'Timestamp saat embedding berhasil di-upsert ke vector store. '
    'NULL jika belum pernah di-embed.';

-- ── 7.2 Komentar Verifikator ─────────────────────────────────────────────────
-- Komentar reviewer/verifikator per grup pertanyaan per kelas.
-- Source: portofolio.csv kolom komentar (JSON {kd_grup: teks}).
-- BUKAN komentar mahasiswa — ini komentar VERIFIKATOR portofolio.
-- Data aktual: kd_grup 6,7,8,9.
CREATE TABLE komentar_verifikator (
    komentar_verifikator_id UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    kelas_id                UUID        NOT NULL REFERENCES kelas(kelas_id) ON DELETE CASCADE,
    pertanyaan_grup_id      UUID        NOT NULL REFERENCES pertanyaan_grup_portofolio(pertanyaan_grup_id),

    komentar_raw            TEXT,
    -- Komentar verifikator as-is dari CSV (mungkin ada HTML).

    komentar_bersih         TEXT GENERATED ALWAYS AS (
        regexp_replace(COALESCE(komentar_raw, ''), E'<[^>]*>', '', 'g')
    ) STORED,

    is_embedded              BOOLEAN     NOT NULL DEFAULT FALSE,
    embedded_at              TIMESTAMPTZ,
    -- NULL = belum di-embed. Diisi pipeline setelah sukses embed ke vector store.

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (kelas_id, pertanyaan_grup_id)
);
CREATE INDEX idx_komentar_verifikator_kelas ON komentar_verifikator (kelas_id);
CREATE INDEX idx_komentar_verifikator_grup  ON komentar_verifikator (pertanyaan_grup_id);
CREATE INDEX idx_komentar_verifikator_embedded   ON komentar_verifikator (is_embedded) WHERE is_embedded = FALSE;
CREATE INDEX idx_komentar_verifikator_fts   ON komentar_verifikator
    USING GIN (to_tsvector('indonesian', COALESCE(komentar_bersih, '')));

COMMENT ON TABLE  komentar_verifikator IS
    'Komentar verifikator/reviewer portofolio per grup pertanyaan per kelas. '
    'BUKAN komentar mahasiswa — ini adalah feedback dari verifikator SIX ITB. '
    'Data aktual: kd_grup 6=Penyelenggaraan, 7=Ketercapaian, 8=Refleksi, 9=Rekomendasi. '
    'is_embedded + embedded_at untuk tracking pipeline RAG vector store.';
COMMENT ON COLUMN komentar_verifikator.komentar_raw IS
    'Komentar verifikator as-is dari JSON SIX ITB. Bisa mengandung HTML tags.';
COMMENT ON COLUMN komentar_verifikator.komentar_bersih IS
    'Generated column: komentar_raw dengan HTML tags di-strip. ';
COMMENT ON COLUMN komentar_verifikator.is_embedded IS
    'FALSE = komentar belum di-embed ke vector store. TRUE = sudah di-embed.';
 

-- ── 7.3 Komentar Mahasiswa (Q103 – Saran Teks Bebas) ─────────────────────────
-- Jawaban teks bebas mahasiswa. Dipisah dari skor_kuesioner_kelas untuk:
--   1. Tipe data berbeda (TEXT vs NUMERIC — access pattern berbeda)
--   2. Mendukung pipeline embedding (is_embedded, embedded_at)
CREATE TABLE komentar_mahasiswa (
    komentar_mahasiswa_id   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    kelas_id                UUID        NOT NULL REFERENCES kelas(kelas_id) ON DELETE CASCADE,
    pertanyaan_kuesioner_id UUID        NOT NULL REFERENCES pertanyaan_kuesioner(pertanyaan_kuesioner_id),
    -- FK ke pertanyaan_kuesioner (Q103 = kd_pertanyaan 103).
    
    no_komentar     SMALLINT        NOT NULL CHECK (no_komentar > 0),

    komentar_raw            TEXT,
    -- Teks saran mahasiswa as-is. Dapat mengandung HTML.

    komentar_bersih         TEXT GENERATED ALWAYS AS (
        regexp_replace(COALESCE(komentar_raw, ''), E'<[^>]*>', '', 'g')
    ) STORED,
    is_embedded             BOOLEAN     NOT NULL DEFAULT FALSE,
    embedded_at             TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (kelas_id, pertanyaan_kuesioner_id, no_komentar)
);
CREATE INDEX idx_komentar_mahasiswa_kelas    ON komentar_mahasiswa (kelas_id);
CREATE INDEX idx_komentar_mahasiswa_embedded ON komentar_mahasiswa (is_embedded) WHERE is_embedded = FALSE;
-- Partial index: pipeline embedding hanya scan baris belum di-embed.
CREATE INDEX idx_komentar_mahasiswa_fts      ON komentar_mahasiswa
    USING GIN (to_tsvector('indonesian', COALESCE(komentar_bersih, '')));

COMMENT ON TABLE  komentar_mahasiswa IS
    'Teks saran bebas mahasiswa per kelas. '
    'Dipisah dari skor_kuesioner_kelas karena tipe data berbeda (TEXT bukan numerik) '
    'dan perlu mendukung pipeline embedding RAG (is_embedded, embedded_at). ';
COMMENT ON COLUMN komentar_mahasiswa.pertanyaan_kuesioner_id IS
    'FK ke pertanyaan_kuesioner dengan kd_pertanyaan=Q103 (saran bebas mahasiswa). '
    'Menggunakan FK (bukan enum tipe_konten) untuk scalability: '
    'jika ada pertanyaan teks bebas baru di masa depan, tidak perlu ALTER TYPE.';
COMMENT ON COLUMN komentar_mahasiswa.is_embedded IS
    'FALSE = komentar belum di-embed. TRUE = sudah di-embed ke vector store. '
    'Partial index idx_komentar_mahasiswa_embedded hanya scan baris FALSE.';
COMMENT ON COLUMN komentar_mahasiswa.no_komentar IS 'Urutan dalam kelas. Dipakai sebagai dedup key saat re-ingest (ON CONFLICT DO UPDATE).';


-- ============================================================
-- SECTION 8 — AI / VECTOR TABLES
-- ============================================================

-- ── 8.1 Vector Chunks ─────────────────────────────────────────────────────────
-- Hasil chunking teks portofolio & komentar mahasiswa beserta embedding.
-- source_type menentukan tabel asal source_id:
--   'teks_portofolio'    → source_id = teks_portofolio_id
--   'komentar_mahasiswa' → source_id = komentar_mahasiswa_id
-- Filter keys didenormalisasi untuk RAG query efficiency [V1].
CREATE TABLE vector_chunks (
    chunk_id         UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type      VARCHAR(20)     NOT NULL CHECK (source_type IN ('teks_portofolio','komentar_mahasiswa')),
    source_id        UUID            NOT NULL,
    -- UUID PK dari tabel asal. Tidak ada FK constraint (polymorphic reference).
    kelas_id         UUID            NOT NULL REFERENCES kelas(kelas_id) ON DELETE CASCADE,
    tipe_konten      tipe_konten_enum,
    -- NULLABLE. Label konten untuk source_type='teks_portofolio'.
    chunk_index      SMALLINT        NOT NULL DEFAULT 0,
    -- Urutan chunk dalam satu source. Dedup key saat re-ingest.
    chunk_text       TEXT            NOT NULL,
    -- Teks chunk sudah dibersihkan, siap di-embed.
    embedding        VECTOR(1536),
    -- pgvector embedding (dimensi 1536 untuk text-embedding-3-small).
    -- NULL jika belum di-embed.
    model_used       VARCHAR(100),
    embedded_at      TIMESTAMPTZ,

    -- === Filter Keys — denormalisasi untuk RAG query [V1] ===
    kode_mk          VARCHAR(20)     NOT NULL,
    kode_prodi       VARCHAR(10)     NOT NULL,
    kode_fakultas    VARCHAR(20)     NOT NULL,
    no_kelas         SMALLINT        NOT NULL,
    semester         SMALLINT        NOT NULL,
    tahun            SMALLINT        NOT NULL,
    nama_mk          VARCHAR(200)    NOT NULL,
    nama_prodi       VARCHAR(200)    NOT NULL,
    nama_fakultas    VARCHAR(200)    NOT NULL,
    jenjang          jenjang_prodi   NOT NULL,
    semua_dosen_id   UUID[]          NOT NULL DEFAULT '{}',
    semua_dosen_nama TEXT[]          NOT NULL DEFAULT '{}',
    kelas_label      TEXT            NOT NULL,
    -- e.g. "FI1101 Kelas 2 | Fisika S1 | Ganjil 2024/2025"

    created_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_chunk_source_idx UNIQUE (source_id, chunk_index)
);
CREATE INDEX idx_vector_chunks_kelas_id   ON vector_chunks (kelas_id);
CREATE INDEX idx_vector_chunks_source     ON vector_chunks (source_type, source_id);
CREATE INDEX idx_vector_chunks_kode_mk    ON vector_chunks (kode_mk, semester, tahun)    WHERE embedding IS NOT NULL;
CREATE INDEX idx_vector_chunks_kode_prodi ON vector_chunks (kode_prodi, semester, tahun) WHERE embedding IS NOT NULL;
CREATE INDEX idx_vector_chunks_kode_fak   ON vector_chunks (kode_fakultas, semester, tahun) WHERE embedding IS NOT NULL;
CREATE INDEX idx_vector_chunks_tipe       ON vector_chunks (tipe_konten)                  WHERE tipe_konten IS NOT NULL AND embedding IS NOT NULL;
CREATE INDEX idx_vector_chunks_dosen      ON vector_chunks USING GIN (semua_dosen_id);
-- idx_vector_chunks_dosen: GIN array index untuk query "chunk dari kelas yang diajar dosen X"
COMMENT ON TABLE  vector_chunks IS 'Chunks teks portofolio/komentar mahasiswa + embedding vector untuk RAG. Filter keys didenormalisasi untuk efisiensi similarity search tanpa JOIN runtime.';
COMMENT ON COLUMN vector_chunks.source_id IS 'UUID PK dari tabel asal. Tidak ada FK constraint karena polymorphic (source_type menentukan tabel). Resolve di application layer.';


-- ── 8.2 LLM Analysis Cache ────────────────────────────────────────────────────
CREATE TABLE llm_analysis_cache (
    cache_id            VARCHAR(64)  PRIMARY KEY,
    -- SHA256(sorted kelas_ids + analysis_type). Dihitung di application layer.
    analysis_type       VARCHAR(50)  NOT NULL,
    kelas_ids           UUID[]       NOT NULL,
    result_json         JSONB        NOT NULL,
    model_used          VARCHAR(100),
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    generated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ
);
CREATE INDEX idx_llm_cache_kelas_ids ON llm_analysis_cache USING GIN (kelas_ids);
CREATE INDEX idx_llm_cache_expires   ON llm_analysis_cache (expires_at) WHERE expires_at IS NOT NULL;
-- idx_cache_expires: partial index untuk cleanup job cache expired.
COMMENT ON TABLE  llm_analysis_cache IS 'Cache hasil LLM call. cache_id = SHA256(sorted kelas_ids + analysis_type) dari application layer. expires_at NULL = permanen.';


-- ============================================================
-- SECTION 9 — TRIGGER FUNCTION & AUTO updated_at TRIGGERS
-- ============================================================

CREATE OR REPLACE FUNCTION fn_auto_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;
COMMENT ON FUNCTION fn_auto_updated_at() IS 'Auto-set updated_at=NOW() pada setiap UPDATE. Digunakan oleh semua tabel dengan kolom updated_at. Juga dipanggil dari schema_auth_and_ingestion.sql.';

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'fakultas', 'kelompok_keahlian', 'program_studi', 'dosen', 'mata_kuliah',
        'pertanyaan_grup_portofolio', 'pertanyaan_portofolio',
        'kelas', 'pengajar_kelas',
        'statistik_kelas', 'nilai_dosen',
        'skor_kuesioner_kelas', 'skor_kuesioner_dosen', 'skor_agregat_kuesioner_dosen',
        'teks_portofolio', 'komentar_verifikator', 'komentar_mahasiswa'
    ] LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_updated_at_%I
             BEFORE UPDATE ON %I
             FOR EACH ROW EXECUTE FUNCTION fn_auto_updated_at()',
            t, t
        );
    END LOOP;
END;
$$;


-- ============================================================
-- SECTION 10 — ROW-LEVEL SECURITY (RLS) POLICIES
-- ============================================================
--
-- Backend set session variables sebelum setiap transaksi:
--   SET LOCAL app.user_id     = '<UUID>';
--   SET LOCAL app.role        = '<user_role_enum>';
--   SET LOCAL app.prodi_id    = '<UUID>';   -- scope dosen/prodi
--   SET LOCAL app.dosen_id    = '<UUID>';   -- scope dosen individual
--   SET LOCAL app.fakultas_id = '<UUID>';   -- scope dekanat
--
-- Gunakan PgBouncer mode 'transaction' agar SET LOCAL tidak bocor.
--
-- GROUPING ROLE:
--   global_reader  : admin, direktorat
--   level_fakultas : dekan, jajaran_dekanat
--   level_prodi    : kaprodi, jajaran_prodi
--   level_dosen    : dosen (scope prodi + privasi individual)
-- ============================================================

CREATE OR REPLACE FUNCTION fn_is_global_reader()
RETURNS BOOLEAN LANGUAGE plpgsql STABLE SECURITY DEFINER AS $$
BEGIN
    RETURN current_setting('app.role', true) IN ('admin', 'direktorat');
EXCEPTION WHEN OTHERS THEN RETURN FALSE;
END;
$$;

CREATE OR REPLACE FUNCTION fn_is_dekanat_scope(p_kelas_id UUID)
RETURNS BOOLEAN LANGUAGE plpgsql STABLE SECURITY DEFINER AS $$
DECLARE v_fak UUID;
BEGIN
    IF current_setting('app.role', true) NOT IN ('dekan', 'jajaran_dekanat') THEN RETURN FALSE; END IF;
    v_fak := NULLIF(current_setting('app.fakultas_id', true), '')::UUID;
    IF v_fak IS NULL THEN RETURN FALSE; END IF;
    RETURN EXISTS (
        SELECT 1 FROM kelas k JOIN program_studi ps ON ps.prodi_id = k.prodi_id
        WHERE k.kelas_id = p_kelas_id AND ps.fakultas_id = v_fak
    );
EXCEPTION WHEN OTHERS THEN RETURN FALSE;
END;
$$;

CREATE OR REPLACE FUNCTION fn_is_prodi_scope(p_prodi_id UUID)
RETURNS BOOLEAN LANGUAGE plpgsql STABLE SECURITY DEFINER AS $$
DECLARE v_prodi UUID;
BEGIN
    IF current_setting('app.role', true) NOT IN ('kaprodi', 'jajaran_prodi', 'dosen') THEN RETURN FALSE; END IF;
    v_prodi := NULLIF(current_setting('app.prodi_id', true), '')::UUID;
    RETURN v_prodi IS NOT NULL AND v_prodi = p_prodi_id;
EXCEPTION WHEN OTHERS THEN RETURN FALSE;
END;
$$;

CREATE OR REPLACE FUNCTION fn_is_own_dosen(p_dosen_id UUID)
RETURNS BOOLEAN LANGUAGE plpgsql STABLE SECURITY DEFINER AS $$
DECLARE v_dosen UUID;
BEGIN
    IF current_setting('app.role', true) <> 'dosen' THEN RETURN FALSE; END IF;
    v_dosen := NULLIF(current_setting('app.dosen_id', true), '')::UUID;
    RETURN v_dosen IS NOT NULL AND v_dosen = p_dosen_id;
EXCEPTION WHEN OTHERS THEN RETURN FALSE;
END;
$$;

CREATE OR REPLACE FUNCTION fn_kelas_in_prodi(p_kelas_id UUID)
RETURNS BOOLEAN LANGUAGE plpgsql STABLE SECURITY DEFINER AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM kelas k WHERE k.kelas_id = p_kelas_id AND fn_is_prodi_scope(k.prodi_id)
    );
EXCEPTION WHEN OTHERS THEN RETURN FALSE;
END;
$$;

CREATE OR REPLACE FUNCTION fn_dosen_is_pengajar(p_kelas_id UUID)
RETURNS BOOLEAN LANGUAGE plpgsql STABLE SECURITY DEFINER AS $$
DECLARE v_dosen UUID;
BEGIN
    IF current_setting('app.role', true) <> 'dosen' THEN RETURN FALSE; END IF;
    v_dosen := NULLIF(current_setting('app.dosen_id', true), '')::UUID;
    IF v_dosen IS NULL THEN RETURN FALSE; END IF;
    RETURN EXISTS (
        SELECT 1 FROM pengajar_kelas pk
        WHERE pk.kelas_id = p_kelas_id
          AND pk.dosen_id = v_dosen
    );
EXCEPTION WHEN OTHERS THEN RETURN FALSE;
END;
$$;
COMMENT ON FUNCTION fn_dosen_is_pengajar(UUID) IS
'ABAC: TRUE jika dosen (app.dosen_id) terdaftar di pengajar_kelas untuk kelas ini.
Menangani dosen cross-prodi (MK WI, team-teaching lintas fakultas).
Berbeda dari fn_kelas_in_prodi yang berbasis prodi scope registrasi.';


-- ── statistik_kelas ──────────────────────────────────────────────────────────
ALTER TABLE statistik_kelas ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_statistik_kelas ON statistik_kelas FOR SELECT USING (
    fn_is_global_reader() OR fn_is_dekanat_scope(kelas_id) OR fn_kelas_in_prodi(kelas_id) OR fn_dosen_is_pengajar(kelas_id)
);

-- ── distribusi_nilai ─────────────────────────────────────────────────────────
ALTER TABLE distribusi_nilai ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_distribusi_nilai ON distribusi_nilai FOR SELECT USING (
    fn_is_global_reader() OR fn_is_dekanat_scope(kelas_id) OR fn_kelas_in_prodi(kelas_id) OR fn_dosen_is_pengajar(kelas_id)
);

-- ── nilai_dosen: PRIVAT — dosen hanya lihat nilai_akhir miliknya [F1] ────────
ALTER TABLE nilai_dosen ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_nilai_dosen ON nilai_dosen FOR SELECT USING (
    fn_is_global_reader()
    OR fn_is_dekanat_scope(kelas_id)
    OR (current_setting('app.role', true) IN ('kaprodi', 'jajaran_prodi') AND fn_kelas_in_prodi(kelas_id))
    OR fn_is_own_dosen(dosen_id)
);

-- ── skor_kuesioner_kelas ─────────────────────────────────────────────────────
ALTER TABLE skor_kuesioner_kelas ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_skor_kues_kelas ON skor_kuesioner_kelas FOR SELECT USING (
    fn_is_global_reader() OR fn_is_dekanat_scope(kelas_id) OR fn_kelas_in_prodi(kelas_id) OR fn_dosen_is_pengajar(kelas_id)
);

-- ── skor_kuesioner_dosen: PRIVAT — dosen hanya lihat skor miliknya [F1] ──────
ALTER TABLE skor_kuesioner_dosen ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_skor_kues_dosen ON skor_kuesioner_dosen FOR SELECT USING (
    fn_is_global_reader()
    OR fn_is_dekanat_scope(kelas_id)
    OR (current_setting('app.role', true) IN ('kaprodi', 'jajaran_prodi') AND fn_kelas_in_prodi(kelas_id))
    OR fn_is_own_dosen(dosen_id)
);

-- ── skor_agregat_kuesioner_dosen: PRIVAT — sama dengan skor_kuesioner_dosen ─────────
ALTER TABLE skor_agregat_kuesioner_dosen ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_skor_agregat_kuesioner_dosen ON skor_agregat_kuesioner_dosen FOR SELECT USING (
    fn_is_global_reader()
    OR fn_is_dekanat_scope(kelas_id)
    OR (current_setting('app.role', true) IN ('kaprodi', 'jajaran_prodi') AND fn_kelas_in_prodi(kelas_id))
    OR fn_is_own_dosen(dosen_id)
);

-- ── teks_portofolio ──────────────────────────────────────────────────────────
ALTER TABLE teks_portofolio ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_teks_porto ON teks_portofolio FOR SELECT USING (
    fn_is_global_reader() OR fn_is_dekanat_scope(kelas_id) OR fn_kelas_in_prodi(kelas_id) OR fn_dosen_is_pengajar(kelas_id)
);

-- ── komentar_verifikator ─────────────────────────────────────────────────────
ALTER TABLE komentar_verifikator ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_komentar_verif ON komentar_verifikator FOR SELECT USING (
    fn_is_global_reader() OR fn_is_dekanat_scope(kelas_id) OR fn_kelas_in_prodi(kelas_id) OR fn_dosen_is_pengajar(kelas_id)
);

-- ── komentar_mahasiswa ───────────────────────────────────────────────────────
ALTER TABLE komentar_mahasiswa ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_komentar_mhs ON komentar_mahasiswa FOR SELECT USING (
    fn_is_global_reader() OR fn_is_dekanat_scope(kelas_id) OR fn_kelas_in_prodi(kelas_id) OR fn_dosen_is_pengajar(kelas_id)
);

-- ── vector_chunks ────────────────────────────────────────────────────────────
ALTER TABLE vector_chunks ENABLE ROW LEVEL SECURITY;
CREATE POLICY pol_vector_chunks ON vector_chunks FOR SELECT USING (
    fn_is_global_reader() OR fn_is_dekanat_scope(kelas_id) OR fn_kelas_in_prodi(kelas_id) OR fn_dosen_is_pengajar(kelas_id)
);

-- Tabel yang TIDAK memerlukan RLS (data tidak sensitif, bisa dibaca semua):
-- fakultas, kelompok_keahlian, program_studi, dosen, mata_kuliah, kelas, pengajar,
-- pertanyaan_kuesioner, pertanyaan_grup_portofolio, pertanyaan_portofolio,
-- llm_analysis_cache (dibaca di application layer)


-- ============================================================
-- SECTION 11 — RINGKASAN
-- ============================================================
-- TOTAL: 21 TABEL
-- [REF]   fakultas, kelompok_keahlian, program_studi, dosen, mata_kuliah,
--         pertanyaan_kuesioner, pertanyaan_grup_portofolio, pertanyaan_portofolio
-- [CORE]  kelas, pengajar_kelas
-- [ASSM]  statistik_kelas, distribusi_nilai, nilai_dosen
-- [KUES]  skor_kuesioner_kelas, skor_kuesioner_dosen, skor_agregat_kuesioner_dosen
-- [PORTO] teks_portofolio, komentar_verifikator, komentar_mahasiswa
-- [AI]    vector_chunks, llm_analysis_cache
-- ============================================================