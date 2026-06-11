-- ============================================================
-- SCHEMA: evaluasi_wisudawan
-- Sumber data : LimeSurvey export resultssurvey926755_2.csv
-- ============================================================

CREATE SCHEMA IF NOT EXISTS evaluasi_wisudawan;


-- ============================================================
-- 1. REFERENSI GRUP OPSI JAWABAN
--    Mendefinisikan set opsi jawaban — baik ordinal/Likert (tipe=O)
--    maupun nominal/kategoris (tipe=N).
--
--    kd_grup_opsi (VARCHAR) dipilih atas integer karena kode ini
--    bermakna secara domain (seperti kd_komponen='UKT','BPP' di bpp.ref_komponen)
--    sehingga membantu readability query dan Text-to-SQL agent.
--
--    Set ordinal   : SETUJU, FREKUENSI, HARAPAN, HARAPAN_FSRD, PERKEMBANGAN_SBM
--    Set nominal   : YA_TIDAK, LOKASI_STUDI_LANJUT, BIDANG_STUDI_LANJUT,
--                    REKOMENDASI_PRODI
-- ============================================================

CREATE TABLE evaluasi_wisudawan.ref_grup_opsi (
    kd_grup_opsi   VARCHAR(30) PRIMARY KEY,
    -- Konvensi penamaan: deskriptif Bahasa Indonesia
    -- Contoh: 'SETUJU', 'FREKUENSI', 'YA_TIDAK', 'REKOMENDASI_PRODI'

    nama            JSONB       NOT NULL,
    -- {"id": "...", "en": "..."} — bilingual, konsisten dengan ref lain di DB

    tipe            CHAR(1)     NOT NULL CHECK (tipe IN ('O','N')),

    -- O = Ordinal  : ada urutan, mean dapat diinterpretasikan secara praktis
    --               dipakai di mv_skor_pertanyaan untuk filter AVG/STDDEV

    -- N = Nominal  : tidak ada urutan, hanya distribusi/frekuensi yang bermakna
    -- Kolom ini dibutuhkan agar mv_skor_pertanyaan dapat auto-pickup
    -- pertanyaan ordinal baru tanpa perlu mengubah definisi MV

    active          BOOLEAN     NOT NULL DEFAULT true,
    ts_entry        TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id_entry   INTEGER     NOT NULL
);


-- ============================================================
-- 2. REFERENSI OPSI JAWABAN INDIVIDUAL
--    Opsi-opsi di dalam setiap jenis opsi.
--    PK komposit (kd_grup_opsi, nilai) — satu nilai per grup.
-- ============================================================

CREATE TABLE evaluasi_wisudawan.ref_opsi (
    kd_grup_opsi   VARCHAR(30) NOT NULL
                        REFERENCES evaluasi_wisudawan.ref_grup_opsi(kd_grup_opsi)
                        ON UPDATE CASCADE ON DELETE RESTRICT
                        DEFERRABLE INITIALLY DEFERRED,

    nilai           SMALLINT    NOT NULL,
    -- Ordinal : 1 = paling negatif … n = paling positif
    -- Nominal : 1, 2, 3, … urut sesuai urutan pilihan (tanpa makna aritmetika)

    label           JSONB       NOT NULL,
    -- {"id": "...", "en": "..."} — label teks per nilai per jenis opsi

    active          BOOLEAN     NOT NULL DEFAULT true,

    PRIMARY KEY (kd_grup_opsi, nilai),
    ts_entry        TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id_entry   INTEGER     NOT NULL
);


-- ============================================================
-- 3. KATALOG PERTANYAAN
--    Total: 137 pertanyaan valid (SBM01_SQ032 dieksklusi)
--    Breakdown:
--      Universal (A–F) : 55 ordinal + 14 free-text + 1 nominal = 70
--      S1 spesifik (G) : 3 nominal + 4 ordinal = 7
--      S2 spesifik (H) : 3 nominal = 3
--      S3 spesifik (I) : 4 ordinal = 4
--      FSRD spesifik (J): 24 ordinal = 24
--      SBM spesifik (K) : 31 ordinal = 31
--      Total            : 137
-- ============================================================

CREATE TABLE evaluasi_wisudawan.pertanyaan (
    kd_pertanyaan   VARCHAR(20) PRIMARY KEY,
    -- Contoh: 'U03_SQ001', 'G01Q23', 'S101', 'FSRD01_SQ001'

    header_csv_raw  VARCHAR(500),
    -- Teks lengkap header kolom dari file CSV LimeSurvey export
    -- Contoh: 'U03[SQ001]. Pernyataan-pernyataan dalam bagian ini
    --          berhubungan dengan ITB secara keseluruhan. 
    --          [Tersedia cukup ruang kelas]'
    -- Disimpan untuk traceability — memungkinkan ingest script
    -- memetakan kolom CSV ke kd_pertanyaan tanpa hardcode

    kd_grup         VARCHAR(15) NOT NULL,
    -- LimeSurvey question group prefix — VARCHAR biasa, bukan FK
    -- Contoh: 'U03','U01','U02','U04','U05','U06','U07',
    --         'G01','G10','G11','S1','M','D01',
    --         'FSRD01'..'FSRD05','SBM01'

    pertanyaan      JSONB       NOT NULL,
    -- {"id": "...", "en": "..."}

    kd_grup_opsi   VARCHAR(30)
                        REFERENCES evaluasi_wisudawan.ref_grup_opsi(kd_grup_opsi)
                        ON UPDATE CASCADE ON DELETE RESTRICT
                        DEFERRABLE INITIALLY DEFERRED,
    -- Ordinal  : 'SETUJU', 'FREKUENSI', 'HARAPAN', 'HARAPAN_FSRD',
    --            'PERKEMBANGAN_SBM'
    -- Nominal  : 'YA_TIDAK', 'LOKASI_STUDI_LANJUT', 'BIDANG_STUDI_LANJUT',
    --            'REKOMENDASI_PRODI'
    -- Free-text: NULL

    batasan         JSONB,
    -- NULL = universal (semua strata & fakultas)
    -- {"strata": ["S1"]}     → Section G
    -- {"strata": ["S2"]}     → Section H
    -- {"strata": ["S3"]}     → Section I
    -- {"fakultas": ["FSRD"]} → Section J
    -- {"fakultas": ["SBM"]}  → Section K
    -- Catatan: PR hanya mengisi Section A–D, tidak ada batasan khusus PR

    urutan          SMALLINT,
    -- Urutan tampil dalam grup/section, untuk rendering UI

    active          BOOLEAN     NOT NULL DEFAULT true,
    ts_entry        TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id_entry   INTEGER     NOT NULL
);

CREATE INDEX ON evaluasi_wisudawan.pertanyaan (kd_grup);
CREATE INDEX ON evaluasi_wisudawan.pertanyaan (kd_grup_opsi);


-- ============================================================
-- 4. TABEL RESPONS UTAMA
-- ============================================================

CREATE TABLE evaluasi_wisudawan.respons (
    response_id                 SERIAL PRIMARY KEY,
    survey_platform_response_id INTEGER,
    -- LimeSurvey internal response ID — bukan PK karena bisa overlap
    -- antar export batch jika survey di-recreate di LimeSurvey

    submit_date     TIMESTAMPTZ,
    start_date      TIMESTAMPTZ,
    last_page       SMALLINT,
    -- last_page = 11 untuk responden yang complete (>99.9% data)

    -- ── Filter axes ────────────────────────────────────────────
    kd_strata       CHAR(2)     NOT NULL,
    -- Nilai: 'S1' (3930), 'S2' (3185), 'S3' (349), 'PR' (71)
    -- PR hanya mengisi Section A–D, tidak ada section khusus

    kd_fak          VARCHAR     NOT NULL
                        REFERENCES utama.fakultas(kd_fak)
                        ON UPDATE CASCADE ON DELETE RESTRICT
                        DEFERRABLE INITIALLY DEFERRED,

    no_ps           INTEGER     NOT NULL
                        REFERENCES utama.program_studi(no_ps)
                        ON UPDATE CASCADE ON DELETE RESTRICT
                        DEFERRABLE INITIALLY DEFERRED,

    periode_ijazah_id INTEGER,
    -- NULLABLE — analisis 100% data (7535 baris):
    --   66.6% (5015 baris) NULL — bukan anomali, bukan missing data
    --   PR: 0% NULL, S1: 81.7% NULL, S2: 51.8% NULL, S3: 43.6% NULL
    --   NULL dan non-NULL coexist dalam bulan & fak yang sama
    --   Nilai non-NULL: integer YYYYMM (202502, 202504, 202507, 202509, 202602, 202604)

    -- ── Payload jawaban ────────────────────────────────────────
    jawaban         JSONB,
    -- key = kd_pertanyaan (VARCHAR, sesuai evaluasi_wisudawan.pertanyaan)
    -- value:
    --   Ordinal Likert  → INTEGER (1–4 atau 1–5)
    --   Nominal         → INTEGER sesuai ref_opsi.nilai
    --   Free-text       → TEXT string
    --
    -- key 'U02_other' muncul ketika U02 = nilai-Other,  value = TEXT bebas
    -- Hanya key yang dijawab yang ada — tidak ada NULL value di dalam JSONB
    --
    -- Contoh row S1 STEI:
    -- {
    --   "U03_SQ001": 4, "U03_SQ002": 3,
    --   "U06_SQ004": 2,
    --   "U07_SQ001": 3,
    --   "G01Q23": "Senang bisa belajar di ITB...",
    --   "U02": 1,
    --   "S101": 1,
    --   "S102": 1,
    --   "S103": 1,
    --   "S104_SQ001": 4
    -- }

    ts_entry        TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id_entry   INTEGER     NOT NULL
);

CREATE INDEX ON evaluasi_wisudawan.respons (kd_strata);
CREATE INDEX ON evaluasi_wisudawan.respons (kd_fak);
CREATE INDEX ON evaluasi_wisudawan.respons (no_ps);
CREATE INDEX ON evaluasi_wisudawan.respons (periode_ijazah_id);
CREATE INDEX ON evaluasi_wisudawan.respons (kd_strata, kd_fak);
CREATE INDEX ON evaluasi_wisudawan.respons (kd_strata, periode_ijazah_id);
CREATE INDEX ON evaluasi_wisudawan.respons USING GIN (jawaban);

CREATE UNIQUE INDEX ON evaluasi_wisudawan.respons (survey_platform_response_id)
    WHERE survey_platform_response_id IS NOT NULL;


-- ============================================================
-- CATATAN UNTUK PENGEMBANG
-- ============================================================
--
-- PROSES INGEST DARI CSV (lihat ingest_evaluasi_wisudawan.sql):
--   1. Ordinal Likert  : konversi teks → integer via ref_opsi.label
--   2. Nominal         : konversi teks → integer via ref_opsi.label
--   3. Free-text       : simpan as-is sebagai TEXT
--   4. U02 = "Other"   : simpan {"U02": <nilai-other>, "U02_other": "<teks>"}
--   5. PR strata       : hanya isi Section A–D
--
-- TEMPLATE.ENTRY:
--   ts_entry dan user_id_entry didefinisikan manual di sini.
--   Jika INHERITS (template.entry) diputuskan bersama DSI ITB,
--   hapus kedua kolom dan attach trigger update_ts_entry ke setiap tabel.
--
-- PERBEDAAN SKALA HARAPAN vs HARAPAN_FSRD:
--   D2  (U07) nilai=4 → "Sepenuhnya memenuhi harapan" (HARAPAN)
--   FSRD (J)  nilai=4 → "Memenuhi harapan"            (HARAPAN_FSRD)
--   Jangan campurkan AVG D2 dan FSRD dalam satu agregasi tanpa normalisasi.
-- ============================================================