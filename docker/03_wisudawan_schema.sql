-- ============================================================
-- ITB WISUDAWAN SURVEY — TABLE SCHEMA
-- ============================================================

CREATE TYPE public.wisudawan_strata_enum AS ENUM ('S1', 'S2', 'S3', 'PR');

CREATE TYPE public.wisudawan_rekomendasi_enum AS ENUM (
    'Tidak merekomendasikan',
    'Kualitas dosen',
    'Fasilitas akademik',
    'Suasana akademik',
    'Lapangan pekerjaan',
    'Jejaring alumni',
    'Other'
);

CREATE TYPE public.wisudawan_rencana_lanjut_enum AS ENUM (
    'Ya',
    'Tidak'
);

CREATE TYPE public.wisudawan_lokasi_lanjut_studi_enum AS ENUM (
    'ITB',
    'Perguruan tinggi dalam negeri selain ITB',
    'Di luar negeri',
    'Tidak ada rencana studi lanjut'
);

CREATE TYPE public.wisudawan_kelanjutan_bidang_enum AS ENUM (
    'Ya, lanjut bidang sama',
    'Tidak, lanjut bidang serumpun',
    'Tidak, lanjut bidang yang masih butuh pengetahuan bidang lama',
    'Tidak, lanjut bidang sangat berbeda',
    'Tidak ada rencana studi lanjut'
);

CREATE TYPE public.wisudawan_answer_type_enum AS ENUM (
    'likert4_agree',
    'likert4_freq',
    'likert5_expect',
    'likert5_dev',
    'categorical',
    'text'
);

-- ============================================================
-- 1. STAGING TABLE — raw CSV dump, semua TEXT, idempotent
-- ============================================================
CREATE TABLE public.stg_wisudawan_raw (
    -- Meta
    stg_id          BIGSERIAL PRIMARY KEY,
    stg_loaded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    stg_source_file TEXT NOT NULL,                          -- nama file CSV asli

    -- LimeSurvey system columns
    response_id     TEXT,
    submitdate      TEXT,
    lastpage        TEXT,
    startlanguage   TEXT,
    seed            TEXT,
    startdate       TEXT,
    datestamp       TEXT,

    -- Attribute columns (metadata responden dari LimeSurvey)
    attr_kd_strata      TEXT,   -- S1 | S2 | S3 | PR
    attr_kd_fak         TEXT,   -- STEI | FMIPA | dst
    attr_no_ps          TEXT,   -- kode program studi numerik
    attr_periode_ijazah TEXT,   -- e.g. 202502

    -- Section A: Fasilitas ITB (U03[SQ001..012]) — Likert 4-point agree
    u03_sq001 TEXT, u03_sq002 TEXT, u03_sq003 TEXT, u03_sq004 TEXT,
    u03_sq005 TEXT, u03_sq006 TEXT, u03_sq007 TEXT, u03_sq008 TEXT,
    u03_sq009 TEXT, u03_sq010 TEXT, u03_sq011 TEXT, u03_sq012 TEXT,

    -- Section B1: Pendidikan prodi (U01[SQ001..012]) — Likert 4-point agree
    u01_sq001 TEXT, u01_sq002 TEXT, u01_sq003 TEXT, u01_sq004 TEXT,
    u01_sq005 TEXT, u01_sq006 TEXT, u01_sq007 TEXT, u01_sq008 TEXT,
    u01_sq009 TEXT, u01_sq010 TEXT, u01_sq011 TEXT, u01_sq012 TEXT,

    -- Section B2: Rekomendasi prodi — categorical + other text
    u02          TEXT,
    u02_other    TEXT,

    -- Section C1: Kemampuan softskill (U04[SQ001..009]) — Likert 4-point agree
    u04_sq001 TEXT, u04_sq002 TEXT, u04_sq003 TEXT, u04_sq004 TEXT,
    u04_sq005 TEXT, u04_sq006 TEXT, u04_sq007 TEXT, u04_sq008 TEXT,
    u04_sq009 TEXT,

    -- Section C2: Pengembangan karakter (U05[SQ001..007]) — Likert 4-point agree
    u05_sq001 TEXT, u05_sq002 TEXT, u05_sq003 TEXT, u05_sq004 TEXT,
    u05_sq005 TEXT, u05_sq006 TEXT, u05_sq007 TEXT,

    -- Section D1: Masalah studi (U06[SQ001..009]) — Likert 4-point frequency
    u06_sq001 TEXT, u06_sq002 TEXT, u06_sq003 TEXT, u06_sq004 TEXT,
    u06_sq005 TEXT, u06_sq006 TEXT, u06_sq007 TEXT, u06_sq008 TEXT,
    u06_sq009 TEXT,

    -- Section D2: Kepuasan dukungan (U07[SQ001..004]) — 5-point expectation (conditional)
    u07_sq001 TEXT, u07_sq002 TEXT, u07_sq003 TEXT, u07_sq004 TEXT,

    -- Section E: Pengalaman belajar & cita-cita — Open-ended
    g10q22 TEXT,  -- kebiasaan belajar
    g01q23 TEXT,  -- kesan & prestasi belajar
    g01q24 TEXT,  -- pengalaman berkesan
    g01q25 TEXT,  -- aktivitas kemahasiswaan
    g01q26 TEXT,  -- cita-cita karier
    g01q27 TEXT,  -- cita-cita hidup
    g01q28 TEXT,  -- motto
    g01q29 TEXT,  -- sifat khas diri

    -- Section F: Suka duka & pandangan ITB — Open-ended
    g11q30 TEXT,  -- suka duka ITB
    g01q31 TEXT,  -- segi positif
    g01q32 TEXT,  -- segi negatif
    g01q33 TEXT,  -- saran ITB
    g01q34 TEXT,  -- saran mahasiswa lain
    g01q35 TEXT,  -- catatan/komentar lain

    -- Section G: Sarjana (S1) — Rencana studi lanjut
    s101 TEXT,    -- punya rencana lanjut? Ya/Tidak
    s102 TEXT,    -- di mana rencana studi lanjut
    s103 TEXT,    -- apakah bidang lanjutan?
    -- Section G4: Matakuliah wajib ITB S1 (S104[SQ001..008]) — Likert 4-point agree
    s104_sq001 TEXT, s104_sq002 TEXT, s104_sq003 TEXT, s104_sq004 TEXT,
    s104_sq005 TEXT, s104_sq006 TEXT, s104_sq007 TEXT, s104_sq008 TEXT,

    -- Section H: Magister (S2) — Rencana studi lanjut
    m01 TEXT,     -- punya rencana lanjut? Ya/Tidak
    m02 TEXT,     -- di mana rencana studi lanjut
    m03 TEXT,     -- apakah bidang lanjutan?

    -- Section I: Doktor (S3) — Matakuliah wajib (D01[SQ001..004]) — Likert 4-point agree
    d01_sq001 TEXT, d01_sq002 TEXT, d01_sq003 TEXT, d01_sq004 TEXT,

    -- Section J: FSRD-specific
    -- J1: TPB FSRD (FSRD01[SQ001..005]) — 5-point expectation
    fsrd01_sq001 TEXT, fsrd01_sq002 TEXT, fsrd01_sq003 TEXT,
    fsrd01_sq004 TEXT, fsrd01_sq005 TEXT,
    -- J2: Perwalian FSRD (FSRD02[SQ001..003])
    fsrd02_sq001 TEXT, fsrd02_sq002 TEXT, fsrd02_sq003 TEXT,
    -- J3: MK Teori FSRD (FSRD03[SQ001..006])
    fsrd03_sq001 TEXT, fsrd03_sq002 TEXT, fsrd03_sq003 TEXT,
    fsrd03_sq004 TEXT, fsrd03_sq005 TEXT, fsrd03_sq006 TEXT,
    -- J4: MK Praktika FSRD (FSRD04[SQ001..006])
    fsrd04_sq001 TEXT, fsrd04_sq002 TEXT, fsrd04_sq003 TEXT,
    fsrd04_sq004 TEXT, fsrd04_sq005 TEXT, fsrd04_sq006 TEXT,
    -- J5: Tugas Akhir FSRD (FSRD05[SQ001..004])
    fsrd05_sq001 TEXT, fsrd05_sq002 TEXT, fsrd05_sq003 TEXT, fsrd05_sq004 TEXT,

    -- Section K: SBM-specific outcomes (SBM01[SQ001..032]) — 5-point development
    sbm01_sq001 TEXT, sbm01_sq002 TEXT, sbm01_sq003 TEXT, sbm01_sq004 TEXT,
    sbm01_sq005 TEXT, sbm01_sq006 TEXT, sbm01_sq007 TEXT, sbm01_sq008 TEXT,
    sbm01_sq009 TEXT, sbm01_sq010 TEXT, sbm01_sq011 TEXT, sbm01_sq012 TEXT,
    sbm01_sq013 TEXT, sbm01_sq014 TEXT, sbm01_sq015 TEXT, sbm01_sq016 TEXT,
    sbm01_sq017 TEXT, sbm01_sq018 TEXT, sbm01_sq019 TEXT, sbm01_sq020 TEXT,
    sbm01_sq021 TEXT, sbm01_sq022 TEXT, sbm01_sq023 TEXT, sbm01_sq024 TEXT,
    sbm01_sq025 TEXT, sbm01_sq026 TEXT, sbm01_sq027 TEXT, sbm01_sq028 TEXT,
    sbm01_sq029 TEXT, sbm01_sq030 TEXT, sbm01_sq031 TEXT, sbm01_sq032 TEXT
);

-- Index untuk idempotency check saat re-ingest
CREATE INDEX idx_stg_wisudawan_response_id
    ON public.stg_wisudawan_raw (response_id, attr_periode_ijazah);


-- ============================================================
-- 2. INGESTION LOG untuk pipeline wisudawan
-- ============================================================

CREATE TABLE public.wisudawan_ingestion_log (
    log_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_file     TEXT NOT NULL,
    periode_wisuda  VARCHAR(6) NOT NULL,       -- e.g. '202502'
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          VARCHAR(20) NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running', 'success', 'failed')),
    rows_raw        INTEGER,
    rows_loaded     INTEGER,
    rows_skipped    INTEGER,
    error_message   TEXT
);


-- ============================================================
-- 3. KATALOG PERTANYAAN
-- ============================================================
-- Lookup statis. Diisi sekali dari seed di bawah.
-- Tidak perlu di-update tiap ingest kecuali kuesioner berubah.
--
-- answer_type values:
--   likert4_agree  → 1=Tidak Setuju .. 4=Setuju
--   likert4_freq   → 1=Tidak pernah .. 4=Selalu
--   likert5_expect → 1=Tidak sesuai harapan .. 5=Melampaui harapan
--   likert5_dev    → 1=Undeveloped .. 5=Highly Developed
--   categorical    → pilihan diskret (enum / multi-select)
--   text           → jawaban bebas (essay)
-- ============================================================

CREATE TABLE public.wisudawan_pertanyaan (
    question_code   VARCHAR(30) PRIMARY KEY,    -- persis seperti di header CSV (e.g. 'U03[SQ001]')
    question_group  VARCHAR(15) NOT NULL,        -- prefix grup LimeSurvey (e.g. 'U03', 'FSRD01')
    question_text   TEXT        NOT NULL,        -- teks pertanyaan/sub-pertanyaan
    answer_type     public.wisudawan_answer_type_enum NOT NULL
);

CREATE INDEX idx_wisudawan_pertanyaan_group
    ON public.wisudawan_pertanyaan (question_group);

COMMENT ON TABLE public.wisudawan_pertanyaan IS
    'Katalog pertanyaan kuesioner wisudawan ITB. '
    'Seed dari header CSV Data Ulasan Wisudawan. Update manual jika kuesioner berubah.';

COMMENT ON COLUMN public.wisudawan_pertanyaan.question_code IS
    'Kode persis dari header CSV Data Ulasan Wisudawan, e.g. U03[SQ001], G01Q23';
COMMENT ON COLUMN public.wisudawan_pertanyaan.question_group IS
    'Grup/modul Data Ulasan Wisudawan: U01, U03, G01, G10, G11, S104, FSRD01, SBM01, dst';
COMMENT ON COLUMN public.wisudawan_pertanyaan.answer_type IS
    'Tipe skala: likert4_agree | likert4_freq | likert5_expect | likert5_dev | categorical | text';


-- ============================================================
-- SEED DATA — pertanyaan dari CSV export LimeSurvey
-- Di-generate dari header CSV aktual (resultssurvey926755_2.csv)
-- ============================================================

INSERT INTO public.wisudawan_pertanyaan (question_code, question_group, question_text, answer_type) VALUES

-- ── Section A: Fasilitas ITB (U03) ─────────────────────────
('U03[SQ001]', 'U03', 'Tersedia cukup ruang kelas', 'likert4_agree'),
('U03[SQ002]', 'U03', 'Ruang kelas menyediakan lingkungan yang kondusif untuk pembelajaran', 'likert4_agree'),
('U03[SQ003]', 'U03', 'Laboratorium menyediakan lingkungan yang kondusif untuk pembelajaran', 'likert4_agree'),
('U03[SQ004]', 'U03', 'Akses internet tersedia secara memadai', 'likert4_agree'),
('U03[SQ005]', 'U03', 'Tersedia fasilitas untuk mendorong pengembangan keprofesian saya', 'likert4_agree'),
('U03[SQ006]', 'U03', 'Tersedia akses terhadap sumber pustaka yang layak', 'likert4_agree'),
('U03[SQ007]', 'U03', 'Fasilitas yang ada memungkinkan saya untuk belajar menggunakan perangkat kerja yang up-to-date', 'likert4_agree'),
('U03[SQ008]', 'U03', 'Tersedia cukup fasilitas toilet yang layak', 'likert4_agree'),
('U03[SQ009]', 'U03', 'Tersedia cukup fasilitas kantin yang layak', 'likert4_agree'),
('U03[SQ010]', 'U03', 'Tersedia fasilitas rekreasional, seperti fasilitas olahraga atau kesenian, yang layak', 'likert4_agree'),
('U03[SQ011]', 'U03', 'Tersedia fasilitas kesehatan yang layak', 'likert4_agree'),
('U03[SQ012]', 'U03', 'Secara keseluruhan, saya puas dengan pendidikan yang saya peroleh di ITB', 'likert4_agree'),

-- ── Section B1: Kepuasan Program Studi (U01) ───────────────
('U01[SQ001]', 'U01', 'Wali akademik selalu ada setiap saya butuhkan', 'likert4_agree'),
('U01[SQ002]', 'U01', 'Wali akademik membantu saya dalam memahami persyaratan yang dibutuhkan untuk menyelesaikan studi saya', 'likert4_agree'),
('U01[SQ003]', 'U01', 'Dosen prodi memberi kesempatan yang cukup bagi mahasiswa untuk berinteraksi secara informal', 'likert4_agree'),
('U01[SQ004]', 'U01', 'Dosen prodi memberi perhatian terhadap proses pembelajaran dan pemahaman mahasiswa', 'likert4_agree'),
('U01[SQ005]', 'U01', 'Dosen prodi mempunyai kemampuan profesional yang baik', 'likert4_agree'),
('U01[SQ006]', 'U01', 'Kuliah wajib prodi memberikan dasar pengetahuan yang diperlukan untuk mengikuti matakuliah pilihan dalam prodi', 'likert4_agree'),
('U01[SQ007]', 'U01', 'Jumlah matakuliah pilihan yang ditawarkan memberi saya keleluasaan dalam memilih', 'likert4_agree'),
('U01[SQ008]', 'U01', 'Pengetahuan dan keterampilan yang diberikan di laboratorium/studio sejalan dengan teori yang diberikan di kelas', 'likert4_agree'),
('U01[SQ009]', 'U01', 'Kualitas sarana perkuliahan/laboratorium/studio di prodi memadai', 'likert4_agree'),
('U01[SQ010]', 'U01', 'Prodi memberikan gambaran yang jelas tentang lapangan kerja', 'likert4_agree'),
('U01[SQ011]', 'U01', 'Saya menyenangi bidang studi yang saya pelajari di prodi', 'likert4_agree'),
('U01[SQ012]', 'U01', 'Jika saya mulai dari awal lagi, saya akan memilih prodi yang sama seperti sekarang', 'likert4_agree'),

-- ── Section B2: Rekomendasi Prodi (U02) ────────────────────
('U02',        'U02', 'Kalau Saudara diminta merekomendasikan prodi dimana Saudara menyelesaikan studi, aspek apa yang akan Saudara paling tonjolkan?', 'categorical'),
('U02[other]', 'U02', 'Kalau Saudara diminta merekomendasikan prodi — aspek lain (teks bebas)', 'categorical'),

-- ── Section C1: Kemampuan Softskill (U04) ──────────────────
('U04[SQ001]', 'U04', 'Berkomunikasi lisan', 'likert4_agree'),
('U04[SQ002]', 'U04', 'Berkomunikasi tertulis', 'likert4_agree'),
('U04[SQ003]', 'U04', 'Berbahasa asing', 'likert4_agree'),
('U04[SQ004]', 'U04', 'Menyelesaikan masalah secara sistematis', 'likert4_agree'),
('U04[SQ005]', 'U04', 'Melakukan penilaian kritis terhadap pendapat orang lain', 'likert4_agree'),
('U04[SQ006]', 'U04', 'Mengkritisi pemikiran diri sendiri', 'likert4_agree'),
('U04[SQ007]', 'U04', 'Memilih cara mengemukakan pendapat', 'likert4_agree'),
('U04[SQ008]', 'U04', 'Bekerja dalam tim', 'likert4_agree'),
('U04[SQ009]', 'U04', 'Bekerja mandiri', 'likert4_agree'),

-- ── Section C2: Pengembangan Karakter (U05) ────────────────
('U05[SQ001]', 'U05', 'Kejujuran', 'likert4_agree'),
('U05[SQ002]', 'U05', 'Memelihara komitmen', 'likert4_agree'),
('U05[SQ003]', 'U05', 'Menjaga jaga_emosi', 'likert4_agree'),
('U05[SQ004]', 'U05', 'Memiliki kepedulian terhadap orang lain', 'likert4_agree'),
('U05[SQ005]', 'U05', 'Bersikap obyektif', 'likert4_agree'),
('U05[SQ006]', 'U05', 'Memiliki sikap tidak mudah menyerah', 'likert4_agree'),
('U05[SQ007]', 'U05', 'Kepatuhan pada aturan dan/atau hukum yang berlaku', 'likert4_agree'),

-- ── Section D1: Masalah Studi & Dampak (U06) ───────────────
('U06[SQ001]', 'U06', 'Saya pernah mengalami masalah akademis (dalam mengikuti perkuliahan atau pun keseluruhan studi)', 'likert4_freq'),
('U06[SQ002]', 'U06', 'Saya pernah mengalami masalah keuangan', 'likert4_freq'),
('U06[SQ003]', 'U06', '[Untuk yang pernah mengalami masalah keuangan] Masalah keuangan tersebut mempengaruhi prestasi akademis saya', 'likert4_freq'),
('U06[SQ004]', 'U06', 'Saya pernah mengalami masalah psikologis', 'likert4_freq'),
('U06[SQ005]', 'U06', '[Untuk yang pernah mengalami masalah psikologis] Masalah psikologis tersebut mempengaruhi prestasi akademis saya', 'likert4_freq'),
('U06[SQ006]', 'U06', 'Saya pernah mengalami masalah dalam interaksi sosial dan/atau budaya', 'likert4_freq'),
('U06[SQ007]', 'U06', '[Untuk yang pernah mengalami masalah interaksi sosial atau budaya] Masalah interaksi tersebut mempengaruhi prestasi akademis saya', 'likert4_freq'),
('U06[SQ008]', 'U06', 'Saya pernah mengalami masalah kesehatan', 'likert4_freq'),
('U06[SQ009]', 'U06', '[Untuk yang pernah mengalami masalah kesehatan] Masalah kesehatan tersebut mempengaruhi prestasi akademis saya', 'likert4_freq'),

-- ── Section D2: Kepuasan Dukungan ITB (U07, conditional) ───
('U07[SQ001]', 'U07', 'Beasiswa atau pinjaman, ketika Saudara menghadapi masalah keuangan', 'likert5_expect'),
('U07[SQ002]', 'U07', 'Bimbingan dan konseling, ketika Saudara menghadapi masalah psikologis dan interaksi sosial/kultural', 'likert5_expect'),
('U07[SQ003]', 'U07', 'Bimbingan atau nasehat dari dosen wali, ketika Saudara menghadapi masalah akademis', 'likert5_expect'),
('U07[SQ004]', 'U07', 'Bimbingan atau nasehat dari dosen matakuliah, ketika Saudara menghadapi masalah akademis pada matakuliah yang bersangkutan', 'likert5_expect'),

-- ── Section E: Pengalaman Belajar & Cita-cita ──────────────
('G10Q22', 'G10', 'Kebiasaan belajar (cara belajar, waktu dan lama belajar, hal-hal lain yang mendorong belajar, dan sebagainya)', 'text'),
('G01Q23', 'G01', 'Kesan-kesan dan prestasi dalam belajar (di SD, SLTP, SLTA, Perguruan Tinggi)', 'text'),
('G01Q24', 'G01', 'Pengalaman lain yang sangat berkesan', 'text'),
('G01Q25', 'G01', 'Aktivitas kemahasiswaan', 'text'),
('G01Q26', 'G01', 'Cita-cita dalam karier', 'text'),
('G01Q27', 'G01', 'Cita-cita dalam hidup', 'text'),
('G01Q28', 'G01', 'Motto untuk sukses studi di ITB', 'text'),
('G01Q29', 'G01', 'Sifat khas diri sendiri', 'text'),

-- ── Section F: Suka Duka & Pandangan Terhadap ITB ──────────
('G11Q30', 'G11', 'Suka duka menempuh studi di ITB', 'text'),
('G01Q31', 'G01', 'Segi Positif studi di ITB', 'text'),
('G01Q32', 'G01', 'Segi Negatif studi di ITB', 'text'),
('G01Q33', 'G01', 'Saran untuk perbaikan proses, sarana, dan prasarana pendidikan di ITB', 'text'),
('G01Q34', 'G01', 'Saran untuk mahasiswa lain dalam menempuh studi di ITB', 'text'),
('G01Q35', 'G01', 'Catatan / Komentar Lain', 'text'),

-- ── Section G: Sarjana (S1) — Rencana Studi Lanjut ─────────
('S101', 'S101', 'Apakah Sdr. mempunyai rencana untuk melanjutkan ke tingkat pendidikan yang lebih tinggi?', 'categorical'),
('S102', 'S102', 'Di mana rencana Sdr. melanjutkan ke tingkat pendidikan yang lebih tinggi', 'categorical'),
('S103', 'S103', 'Apakah bidang studi lanjutan yang Saudara rencanakan merupakan kelanjutan dari bidang studi yang baru Saudara selesaikan di ITB?', 'categorical'),

-- ── Section G4: Matakuliah Wajib ITB (S1 / S104) ───────────
('S104[SQ001]', 'S104', 'Saya mengalami kesulitan untuk bisa mengambil matakuliah agama dan etika karena keterbatasan kuota', 'likert4_agree'),
('S104[SQ002]', 'S104', 'Matakuliah agama dan etika yang saya ambil berpengaruh besar dalam membentuk sikap dan perilaku saya', 'likert4_agree'),
('S104[SQ003]', 'S104', 'Saya mengalami kesulitan untuk bisa mengambil matakuliah Pancasila dan kewarganegaraan', 'likert4_agree'),
('S104[SQ004]', 'S104', 'Matakuliah Pancasila dan kewarganegaraan yang saya ambil berpengaruh besar dalam membentuk sikap dan perilaku saya', 'likert4_agree'),
('S104[SQ005]', 'S104', 'Saya mengalami kesulitan untuk bisa mengambil matakuliah manajemen', 'likert4_agree'),
('S104[SQ006]', 'S104', 'Matakuliah manajemen yang saya ambil berpengaruh besar dalam membuka wawasan pentingnya peranan manajemen', 'likert4_agree'),
('S104[SQ007]', 'S104', 'Saya mengalami kesulitan untuk bisa mengambil matakuliah lingkungan', 'likert4_agree'),
('S104[SQ008]', 'S104', 'Matakuliah lingkungan yang saya ambil berpengaruh besar dalam memberikan wawasan dan membentuk perilaku ramah lingkungan', 'likert4_agree'),

-- ── Section H: Magister (S2) — Rencana Studi Lanjut ────────
('M01', 'M01', 'Apakah Sdr. mempunyai rencana untuk melanjutkan ke tingkat pendidikan yang lebih tinggi?', 'categorical'),
('M02', 'M02', 'Di mana rencana Sdr. melanjutkan ke tingkat pendidikan yang lebih tinggi', 'categorical'),
('M03', 'M03', 'Apakah bidang studi lanjutan yang Saudara rencanakan merupakan kelanjutan dari bidang studi yang baru Saudara selesaikan di ITB?', 'categorical'),

-- ── Section I: Doktor (S3) — Matakuliah Wajib (D01) ────────
('D01[SQ001]', 'D01', 'Saya mengalami kesulitan untuk bisa mengambil matakuliah filsafat ilmu', 'likert4_agree'),
('D01[SQ002]', 'D01', 'Matakuliah filsafat ilmu yang saya ambil berpengaruh besar dalam memberikan wawasan dan sikap dalam pengembangan ilmu pengetahuan', 'likert4_agree'),
('D01[SQ003]', 'D01', 'Saya mengalami kesulitan untuk bisa mengambil matakuliah metodologi penelitian', 'likert4_agree'),
('D01[SQ004]', 'D01', 'Matakuliah metodologi penelitian yang saya ambil bermanfaat besar dalam penelitian saya', 'likert4_agree'),

-- ── Section J: Khusus FSRD ─────────────────────────────────
-- J1: TPB (FSRD01)
('FSRD01[SQ001]', 'FSRD01', 'Pemahaman Prinsip Estetik', 'likert5_expect'),
('FSRD01[SQ002]', 'FSRD01', 'Penguasaan Proses Kreatif', 'likert5_expect'),
('FSRD01[SQ003]', 'FSRD01', 'Penguasaan kemampuan menggambar (Drawing) dan membentuk (Forming)', 'likert5_expect'),
('FSRD01[SQ004]', 'FSRD01', 'Pengetahuan tentang program studi yang ada di FSRD', 'likert5_expect'),
('FSRD01[SQ005]', 'FSRD01', 'Penguasaan kemampuan menulis secara ilmiah', 'likert5_expect'),
-- J2: Perwalian (FSRD02)
('FSRD02[SQ001]', 'FSRD02', 'Pelaksanaan sistem perwalian tatap muka', 'likert5_expect'),
('FSRD02[SQ002]', 'FSRD02', 'Pelaksanaan sistem perwalian on line', 'likert5_expect'),
('FSRD02[SQ003]', 'FSRD02', 'Bantuan dan respon dosen wali terkait permasalahan akademik yang dihadapi', 'likert5_expect'),
-- J3: MK Teori (FSRD03)
('FSRD03[SQ001]', 'FSRD03', 'Pemahaman tentang sejarah Seni, Kria atau Desain', 'likert5_expect'),
('FSRD03[SQ002]', 'FSRD03', 'Pemahaman tentang perkembangan Seni, Kria atau Desain di Indonesia', 'likert5_expect'),
('FSRD03[SQ003]', 'FSRD03', 'Pemahaman tentang perkembangan Seni, Kria atau Desain di Dunia', 'likert5_expect'),
('FSRD03[SQ004]', 'FSRD03', 'Penguasaan metoda dan prosedur penciptaan/perancangan', 'likert5_expect'),
('FSRD03[SQ005]', 'FSRD03', 'Penguasaan kemampuan analisis-kritis sebuah karya Seni, Kria atau Desain', 'likert5_expect'),
('FSRD03[SQ006]', 'FSRD03', 'Kesesuaian antara jumlah SKS sesuai dengan jumlah dan materi tugas yang diberikan', 'likert5_expect'),
-- J4: MK Praktika (FSRD04)
('FSRD04[SQ001]', 'FSRD04', 'Pemahaman teknik penciptaan/perancangan karya', 'likert5_expect'),
('FSRD04[SQ002]', 'FSRD04', 'Penguasaan wawasan estetik dan kaitannya dengan proses penciptaan/perancangan karya', 'likert5_expect'),
('FSRD04[SQ003]', 'FSRD04', 'Kesesuaian antara jumlah SKS sesuai dengan jumlah dan materi tugas yang diberikan', 'likert5_expect'),
('FSRD04[SQ004]', 'FSRD04', 'Proses asistensi/pembimbingan yang memadai dan mengakomodir proses penciptaan/perancangan karya', 'likert5_expect'),
('FSRD04[SQ005]', 'FSRD04', 'Kesesuaian antara proses dan hasil penilaian kualitas karya hasil penciptaan/perancangan', 'likert5_expect'),
('FSRD04[SQ006]', 'FSRD04', 'Kesesuaian antara pengetahuan yang diperoleh semasa studi dengan aplikasinya pada mata kuliah kerja profesi/pemagangan', 'likert5_expect'),
-- J5: Tugas Akhir (FSRD05)
('FSRD05[SQ001]', 'FSRD05', 'Pengetahuan teoritikal dan praktika yang diperoleh menunjang pelaksanaan tugas akhir', 'likert5_expect'),
('FSRD05[SQ002]', 'FSRD05', 'Proses asistensi/pembimbingan yang diberikan selama menjalani tugas akhir', 'likert5_expect'),
('FSRD05[SQ003]', 'FSRD05', 'Ketersediaan sarana dan prasarana untuk menunjang pelaksanaan tugas akhir', 'likert5_expect'),
('FSRD05[SQ004]', 'FSRD05', 'Ketersediaan buku dan sumber literatur di perpustakaan yang menunjang pelaksanaan tugas akhir', 'likert5_expect'),

-- ── Section K: Khusus SBM (SBM01) ─────────────────────────
('SBM01[SQ001]', 'SBM01', 'Ability to communicate orally / Kemampuan berkomunikasi secara lisan', 'likert5_dev'),
('SBM01[SQ002]', 'SBM01', 'Ability to communicate in writing / Kemampuan berkomunikasi dalam tulisan', 'likert5_dev'),
('SBM01[SQ003]', 'SBM01', 'Ability to apply knowledge of marketing / Kemampuan menggunakan pengetahuan marketing', 'likert5_dev'),
('SBM01[SQ004]', 'SBM01', 'Ability to apply knowledge of operation management / Kemampuan menggunakan pengetahuan manajemen operasi', 'likert5_dev'),
('SBM01[SQ005]', 'SBM01', 'Ability to apply knowledge of Human Resources Management / Kemampuan menggunakan pengetahuan manajemen sumber daya manusia', 'likert5_dev'),
('SBM01[SQ006]', 'SBM01', 'Ability to apply knowledge of finance / Kemampuan menggunakan pengetahuan keuangan', 'likert5_dev'),
('SBM01[SQ007]', 'SBM01', 'Ability to apply knowledge of Decision Making & Negotiation / Kemampuan menggunakan pengetahuan Pengambilan Keputusan dan Negosiasi', 'likert5_dev'),
('SBM01[SQ008]', 'SBM01', 'Ability to apply knowledge of entrepreneurship / Kemampuan menggunakan pengetahuan kewirausahaan', 'likert5_dev'),
('SBM01[SQ009]', 'SBM01', 'Ability to perform in front of the public/audience / Kemampuan untuk tampil di depan publik/penonton', 'likert5_dev'),
('SBM01[SQ010]', 'SBM01', 'Depth of knowledge in at least one concentration / Pengetahuan yang mendalam pada sekurangnya satu konsentrasi', 'likert5_dev'),
('SBM01[SQ011]', 'SBM01', 'Knowledge of probability and statistics, including its applications to data analysis in Final Project / Pengetahuan tentang probabilitas dan statistik, termasuk aplikasinya dalam menganalisis data dalam tugas akhir', 'likert5_dev'),
('SBM01[SQ012]', 'SBM01', 'Ability to interpret data / Kemampuan untuk menginterpretasi data', 'likert5_dev'),
('SBM01[SQ013]', 'SBM01', 'Ability to identify problems / Kemampuan mengidentifikasi masalah', 'likert5_dev'),
('SBM01[SQ014]', 'SBM01', 'Ability to solve problems / Kemampuan menyelesaikan masalah', 'likert5_dev'),
('SBM01[SQ015]', 'SBM01', 'Ability to conduct business research / Kemampuan melakukan riset bisnis', 'likert5_dev'),
('SBM01[SQ016]', 'SBM01', 'Ability to use internet for information/knowledge acquisition and sharing / Kemampuan menggunakan internet untuk memperoleh dan berbagi informasi/pengetahuan', 'likert5_dev'),
('SBM01[SQ017]', 'SBM01', 'Ability to build networks / Kemampuan untuk membangun jejaring', 'likert5_dev'),
('SBM01[SQ018]', 'SBM01', 'Ability to establish a new business / Kemampuan untuk mendirikan usaha baru', 'likert5_dev'),
('SBM01[SQ019]', 'SBM01', 'Ability to work in teams / Kemampuan bekerjasama dalam tim', 'likert5_dev'),
('SBM01[SQ020]', 'SBM01', 'Ability to identify business opportunities / Kemampuan mengidentifikasi peluang-peluang bisnis', 'likert5_dev'),
('SBM01[SQ021]', 'SBM01', 'Ability to identify opportunities for improving community''s existing condition / Kemampuan mengidentifikasi peluang-peluang untuk meningkatkan/memperbaiki kondisi saat ini suatu komunitas', 'likert5_dev'),
('SBM01[SQ022]', 'SBM01', 'Ability to design or create a new product (Innovative) / Kemampuan untuk merancang dan menciptakan produk baru', 'likert5_dev'),
('SBM01[SQ023]', 'SBM01', 'Ability to adapt within social constraints / Kemampuan beradaptasi dalam kendala sosial', 'likert5_dev'),
('SBM01[SQ024]', 'SBM01', 'Ability to work/study within resources constraints / Kemampuan bekerja/belajar dalam kendala sumberdaya', 'likert5_dev'),
('SBM01[SQ025]', 'SBM01', 'Ability to work/study within ethical constraints / Kemampuan bekerja/belajar dalam kendala etika', 'likert5_dev'),
('SBM01[SQ026]', 'SBM01', 'Ability to work/study within health and safety constraints / Kemampuan bekerja/belajar dalam kendala kesehatan dan keamanan', 'likert5_dev'),
('SBM01[SQ027]', 'SBM01', 'Understanding of professional responsibility / Memahami tanggung jawab profesional', 'likert5_dev'),
('SBM01[SQ028]', 'SBM01', 'Understanding of ethical responsibility / Memahami tanggung jawab etis', 'likert5_dev'),
('SBM01[SQ029]', 'SBM01', 'Recognition of the need for life-long learning / Pengakuan perlunya belajar seumur hidup', 'likert5_dev'),
('SBM01[SQ030]', 'SBM01', 'Ability to engage in life-long learning / Kemampuan untuk terlibat dalam pembelajaran seumur hidup', 'likert5_dev'),
('SBM01[SQ031]', 'SBM01', 'Knowledge sufficiency to pursue further education/graduate study / Pengetahuan pendukung untuk studi pasca sarjana', 'likert5_dev'),
-- SBM01[SQ032]: kosong di CSV export, placeholder
('SBM01[SQ032]', 'SBM01', '(Pertanyaan cadangan SBM — teks tidak tersedia di export)', 'likert5_dev')

ON CONFLICT (question_code) DO UPDATE
    SET question_text = EXCLUDED.question_text,
        answer_type   = EXCLUDED.answer_type;


-- ============================================================
-- 4. CORE: wisudawan_responden
-- ============================================================
-- Satu baris per responden per periode wisuda.
-- ============================================================

CREATE TABLE public.wisudawan_responden (
    responden_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Source identity (dari LimeSurvey)
    response_id     INTEGER NOT NULL,
    periode_wisuda  VARCHAR(6) NOT NULL,       -- e.g. '202502', '202504'

    -- Demografi akademik
    strata          public.wisudawan_strata_enum NOT NULL,
    kd_fak          VARCHAR(20) NOT NULL,
    prodi_id        UUID
                        REFERENCES public.program_studi(prodi_id) ON DELETE SET NULL,

    -- Data kualitas pengisian
    lastpage        SMALLINT,                   -- halaman terakhir yang dijangkau
    submit_at       TIMESTAMPTZ,
    start_at        TIMESTAMPTZ,

    -- Audit
    loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Unique: satu response per periode
    CONSTRAINT uq_responden_response_periode UNIQUE (response_id, periode_wisuda)
);

CREATE INDEX idx_wisudawan_responden_prodi    ON public.wisudawan_responden (prodi_id);
CREATE INDEX idx_wisudawan_responden_periode  ON public.wisudawan_responden (periode_wisuda, strata);
CREATE INDEX idx_wisudawan_responden_fak      ON public.wisudawan_responden (kd_fak, periode_wisuda);


-- ============================================================
-- 5. SKOR FASILITAS ITB — Section A (U03, 12 items)
-- ============================================================
-- Skala: 4-point agree (1=Tidak Setuju .. 4=Setuju)
-- ============================================================

CREATE TABLE public.wisudawan_skor_itb (
    responden_id UUID PRIMARY KEY
        REFERENCES public.wisudawan_responden (responden_id) ON DELETE CASCADE,

    -- U03[SQ001..012]: Fasilitas ITB
    ruang_kelas         SMALLINT CHECK (ruang_kelas         BETWEEN 1 AND 4),
    kelas_kondusif      SMALLINT CHECK (kelas_kondusif      BETWEEN 1 AND 4),
    lab_kondusif        SMALLINT CHECK (lab_kondusif        BETWEEN 1 AND 4),
    internet            SMALLINT CHECK (internet            BETWEEN 1 AND 4),
    fasil_keprofesian   SMALLINT CHECK (fasil_keprofesian   BETWEEN 1 AND 4),
    pustaka             SMALLINT CHECK (pustaka             BETWEEN 1 AND 4),
    perangkat_uptodate  SMALLINT CHECK (perangkat_uptodate  BETWEEN 1 AND 4),
    toilet              SMALLINT CHECK (toilet              BETWEEN 1 AND 4),
    kantin              SMALLINT CHECK (kantin              BETWEEN 1 AND 4),
    rekreasi            SMALLINT CHECK (rekreasi            BETWEEN 1 AND 4),
    kesehatan           SMALLINT CHECK (kesehatan           BETWEEN 1 AND 4),
    kepuasan_umum       SMALLINT CHECK (kepuasan_umum       BETWEEN 1 AND 4),

    -- Computed aggregate
    skor_avg            NUMERIC(4,2) GENERATED ALWAYS AS (
        ROUND(
            (COALESCE(ruang_kelas,0) + COALESCE(kelas_kondusif,0) + COALESCE(lab_kondusif,0) +
             COALESCE(internet,0) + COALESCE(fasil_keprofesian,0) + COALESCE(pustaka,0) +
             COALESCE(perangkat_uptodate,0) + COALESCE(toilet,0) + COALESCE(kantin,0) +
             COALESCE(rekreasi,0) + COALESCE(kesehatan,0) + COALESCE(kepuasan_umum,0))::NUMERIC /
            NULLIF(
                (CASE WHEN ruang_kelas        IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN kelas_kondusif     IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN lab_kondusif       IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN internet           IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN fasil_keprofesian  IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN pustaka            IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN perangkat_uptodate IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN toilet             IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN kantin             IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN rekreasi           IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN kesehatan          IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN kepuasan_umum      IS NOT NULL THEN 1 ELSE 0 END), 0
            ), 2
        )
    ) STORED
);


-- ============================================================
-- 6. SKOR PROGRAM STUDI — Section B (U01 12 items + B2 categorical)
-- ============================================================
-- Skala: 4-point agree (1=Tidak Setuju .. 4=Setuju)
-- ============================================================

CREATE TABLE public.wisudawan_skor_prodi (
    responden_id UUID PRIMARY KEY
        REFERENCES public.wisudawan_responden (responden_id) ON DELETE CASCADE,

    -- U01[SQ001..012]: Kepuasan pendidikan prodi
    dosen_wali_tersedia       SMALLINT CHECK (dosen_wali_tersedia       BETWEEN 1 AND 4),  -- wali selalu ada
    dosen_wali_membantu       SMALLINT CHECK (dosen_wali_membantu       BETWEEN 1 AND 4),  -- wali membantu persyaratan
    dosen_prodi_interaksi_informal      SMALLINT CHECK (dosen_prodi_interaksi_informal      BETWEEN 1 AND 4),  -- dosen beri kesempatan informal
    dosen_prodi_perhatian     SMALLINT CHECK (dosen_prodi_perhatian     BETWEEN 1 AND 4),  -- dosen perhatian proses belajar
    dosen_prodi_profesional   SMALLINT CHECK (dosen_prodi_profesional   BETWEEN 1 AND 4),  -- dosen kemampuan profesional
    mk_wajib_pengetahuan        SMALLINT CHECK (mk_wajib_pengetahuan        BETWEEN 1 AND 4),  -- mk wajib beri dasar pengetahuan
    mk_pilihan_luas        SMALLINT CHECK (mk_pilihan_luas        BETWEEN 1 AND 4),  -- banyak MK pilihan
    lab_selaras         SMALLINT CHECK (lab_selaras         BETWEEN 1 AND 4),  -- lab selaras teori
    sarana_prodi        SMALLINT CHECK (sarana_prodi        BETWEEN 1 AND 4),  -- kualitas sarana prodi
    gambaran_kerja      SMALLINT CHECK (gambaran_kerja      BETWEEN 1 AND 4),  -- gambaran lapangan kerja
    senang_prodi        SMALLINT CHECK (senang_prodi        BETWEEN 1 AND 4),  -- menyenangi prodi
    pilih_prodi_yang_sama          SMALLINT CHECK (pilih_prodi_yang_sama          BETWEEN 1 AND 4),  -- akan pilih prodi yang sama

    -- U02: Rekomendasi prodi
    rekomendasi_aspek   public.wisudawan_rekomendasi_enum,
    rekomendasi_other   TEXT,

    -- Computed
    skor_avg            NUMERIC(4,2) GENERATED ALWAYS AS (
        ROUND(
            (COALESCE(dosen_wali_tersedia,0) + COALESCE(dosen_wali_membantu,0) + COALESCE(dosen_prodi_interaksi_informal,0) +
             COALESCE(dosen_prodi_perhatian,0) + COALESCE(dosen_prodi_profesional,0) + COALESCE(mk_wajib_pengetahuan,0) +
             COALESCE(mk_pilihan_luas,0) + COALESCE(lab_selaras,0) + COALESCE(sarana_prodi,0) +
             COALESCE(gambaran_kerja,0) + COALESCE(senang_prodi,0) + COALESCE(pilih_prodi_yang_sama,0))::NUMERIC /
            NULLIF(
                (CASE WHEN dosen_wali_tersedia     IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN dosen_wali_membantu     IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN dosen_prodi_interaksi_informal    IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN dosen_prodi_perhatian   IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN dosen_prodi_profesional IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN mk_wajib_pengetahuan      IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN mk_pilihan_luas      IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN lab_selaras       IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN sarana_prodi      IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN gambaran_kerja    IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN senang_prodi      IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN pilih_prodi_yang_sama        IS NOT NULL THEN 1 ELSE 0 END), 0
            ), 2
        )
    ) STORED
);


-- ============================================================
-- 7. SKOR SOFTSKILL — Section C (U04 9 items + U05 7 items)
-- ============================================================
-- Skala: 4-point agree (1=Tidak Setuju .. 4=Setuju)
-- ============================================================

CREATE TABLE public.wisudawan_skor_softskill (
    responden_id UUID PRIMARY KEY
        REFERENCES public.wisudawan_responden (responden_id) ON DELETE CASCADE,

    -- U04[SQ001..009]: Kemampuan softskill (C1)
    komunikasi_lisan    SMALLINT CHECK (komunikasi_lisan    BETWEEN 1 AND 4),
    komunikasi_tertulis SMALLINT CHECK (komunikasi_tertulis BETWEEN 1 AND 4),
    bahasa_asing        SMALLINT CHECK (bahasa_asing        BETWEEN 1 AND 4),
    problem_solving     SMALLINT CHECK (problem_solving     BETWEEN 1 AND 4),
    kritisi_pendapat_orang_lain   SMALLINT CHECK (kritisi_pendapat_orang_lain   BETWEEN 1 AND 4),  -- penilaian kritis thd pendapat orang lain
    kritisi_diri         SMALLINT CHECK (kritisi_diri         BETWEEN 1 AND 4),  -- mengkritisi pemikiran diri sendiri
    cara_berpendapat    SMALLINT CHECK (cara_berpendapat    BETWEEN 1 AND 4),
    kerja_tim           SMALLINT CHECK (kerja_tim           BETWEEN 1 AND 4),
    kerja_mandiri       SMALLINT CHECK (kerja_mandiri       BETWEEN 1 AND 4),

    -- U05[SQ001..007]: Pengembangan karakter (C2)
    kejujuran           SMALLINT CHECK (kejujuran           BETWEEN 1 AND 4),
    komitmen            SMALLINT CHECK (komitmen            BETWEEN 1 AND 4),
    jaga_emosi               SMALLINT CHECK (jaga_emosi               BETWEEN 1 AND 4),  -- menjaga emosi
    kepedulian          SMALLINT CHECK (kepedulian          BETWEEN 1 AND 4),
    objektif            SMALLINT CHECK (objektif            BETWEEN 1 AND 4),
    pantang_menyerah    SMALLINT CHECK (pantang_menyerah    BETWEEN 1 AND 4),
    kepatuhan_aturan    SMALLINT CHECK (kepatuhan_aturan    BETWEEN 1 AND 4),

    -- Computed per sub-section
    skor_avg_kemampuan  NUMERIC(4,2) GENERATED ALWAYS AS (
        ROUND(
            (COALESCE(komunikasi_lisan,0) + COALESCE(komunikasi_tertulis,0) + COALESCE(bahasa_asing,0) +
             COALESCE(problem_solving,0) + COALESCE(kritisi_pendapat_orang_lain,0) + COALESCE(kritisi_diri,0) +
             COALESCE(cara_berpendapat,0) + COALESCE(kerja_tim,0) + COALESCE(kerja_mandiri,0))::NUMERIC /
            NULLIF(
                (CASE WHEN komunikasi_lisan    IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN komunikasi_tertulis IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN bahasa_asing        IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN problem_solving     IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN kritisi_pendapat_orang_lain   IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN kritisi_diri         IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN cara_berpendapat    IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN kerja_tim           IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN kerja_mandiri       IS NOT NULL THEN 1 ELSE 0 END), 0
            ), 2
        )
    ) STORED,

    skor_avg_karakter   NUMERIC(4,2) GENERATED ALWAYS AS (
        ROUND(
            (COALESCE(kejujuran,0) + COALESCE(komitmen,0) + COALESCE(jaga_emosi,0) +
             COALESCE(kepedulian,0) + COALESCE(objektif,0) + COALESCE(pantang_menyerah,0) +
             COALESCE(kepatuhan_aturan,0))::NUMERIC /
            NULLIF(
                (CASE WHEN kejujuran        IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN komitmen         IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN jaga_emosi            IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN kepedulian       IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN objektif         IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN pantang_menyerah IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN kepatuhan_aturan IS NOT NULL THEN 1 ELSE 0 END), 0
            ), 2
        )
    ) STORED
);


-- ============================================================
-- 8. MASALAH STUDI — Section D (U06 + U07)
-- ============================================================
-- D1 (U06): 4-point frequency scale
--   1=Tidak pernah/sama sekali  2=Jarang/kecil
--   3=Sering/cukup              4=Selalu/besar
-- D2 (U07): 5-point expectation scale (conditional, bisa NULL)
--   1=Tidak sesuai harapan  2=Ada yang memenuhi  3=Sebagian besar
--   4=Memenuhi              5=Melampaui harapan
-- ============================================================

CREATE TABLE public.wisudawan_masalah_studi (
    responden_id UUID PRIMARY KEY
        REFERENCES public.wisudawan_responden (responden_id) ON DELETE CASCADE,

    -- U06[SQ001..009]: Pengalaman masalah & dampak
    masalah_akademis        SMALLINT CHECK (masalah_akademis        BETWEEN 1 AND 4),
    masalah_keuangan        SMALLINT CHECK (masalah_keuangan        BETWEEN 1 AND 4),
    dampak_keuangan         SMALLINT CHECK (dampak_keuangan         BETWEEN 1 AND 4),  -- conditional
    masalah_psikologis      SMALLINT CHECK (masalah_psikologis      BETWEEN 1 AND 4),
    dampak_psikologis       SMALLINT CHECK (dampak_psikologis       BETWEEN 1 AND 4),  -- conditional
    masalah_sosial_budaya   SMALLINT CHECK (masalah_sosial_budaya   BETWEEN 1 AND 4),  -- masalah interaksi sosial/budaya
    dampak_sosial_budaya    SMALLINT CHECK (dampak_sosial_budaya    BETWEEN 1 AND 4),  -- conditional
    masalah_kesehatan       SMALLINT CHECK (masalah_kesehatan       BETWEEN 1 AND 4),
    dampak_kesehatan        SMALLINT CHECK (dampak_kesehatan        BETWEEN 1 AND 4),  -- conditional

    -- U07[SQ001..004]: Kepuasan dukungan ITB (5-point, conditional)
    dukungan_beasiswa       SMALLINT CHECK (dukungan_beasiswa       BETWEEN 1 AND 5),
    dukungan_konseling      SMALLINT CHECK (dukungan_konseling      BETWEEN 1 AND 5),
    dukungan_dosen_wali           SMALLINT CHECK (dukungan_dosen_wali           BETWEEN 1 AND 5),  -- bimbingan dosen wali
    dukungan_dosen_mk       SMALLINT CHECK (dukungan_dosen_mk       BETWEEN 1 AND 5)
);


-- ============================================================
-- 9. ESSAY — Section E & F (open-ended text)
-- ============================================================
-- EAV untuk teks: banyak pertanyaan essay, sparse, cocok untuk
-- NLP/embedding per-jawaban.
-- ============================================================

CREATE TABLE public.wisudawan_essay (
    essay_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    responden_id    UUID NOT NULL
        REFERENCES public.wisudawan_responden (responden_id) ON DELETE CASCADE,

    -- Identifikasi pertanyaan
    question_code   VARCHAR(20) NOT NULL
        REFERENCES public.wisudawan_pertanyaan (question_code)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,

    question_group  VARCHAR(15) NOT NULL,

    -- Konten jawaban
    teks            TEXT NOT NULL,

    -- NLP pipeline (opsional, diisi kemudian)
    embedding       public.vector(1536),    -- OpenAI text-embedding-3-small atau sejenisnya
    is_embedded     BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT uq_essay_responden_question UNIQUE (responden_id, question_code)
);

-- Kode pertanyaan essay yang valid:
-- G10Q22: Kebiasaan belajar          G01Q23: Kesan & prestasi belajar
-- G01Q24: Pengalaman berkesan        G01Q25: Aktivitas kemahasiswaan
-- G01Q26: Cita-cita karier           G01Q27: Cita-cita hidup
-- G01Q28: Motto                      G01Q29: Sifat khas diri
-- G11Q30: Suka duka ITB              G01Q31: Segi positif ITB
-- G01Q32: Segi negatif ITB           G01Q33: Saran perbaikan ITB
-- G01Q34: Saran untuk mahasiswa lain G01Q35: Catatan/komentar lain

CREATE INDEX idx_wisudawan_essay_responden  ON public.wisudawan_essay (responden_id);
CREATE INDEX idx_wisudawan_essay_question   ON public.wisudawan_essay (question_code);
CREATE INDEX idx_wisudawan_essay_unembedded ON public.wisudawan_essay (is_embedded)
    WHERE is_embedded = FALSE;

-- Vector similarity index (aktifkan jika row > 10.000):
-- CREATE INDEX idx_wisudawan_essay_vec
--     ON public.wisudawan_essay USING hnsw (embedding vector_cosine_ops)
--     WITH (m = 16, ef_construction = 64);


-- ============================================================
-- 10. RENCANA STUDI LANJUT — Section G (S1) & H (S2)
-- ============================================================
-- Struktur pertanyaan S1 dan S2 identik, digabung satu tabel.
-- Kolom diisi sesuai strata responden; strata lain NULL.
-- S3 tidak memiliki section rencana lanjut di kuesioner ini.
-- ============================================================

CREATE TABLE public.wisudawan_rencana_lanjut (
    responden_id    UUID PRIMARY KEY
        REFERENCES public.wisudawan_responden (responden_id) ON DELETE CASCADE,

    punya_rencana       public.wisudawan_rencana_lanjut_enum,         -- Ya / Tidak
    lokasi_lanjut_studi public.wisudawan_lokasi_lanjut_studi_enum,
    kelanjutan_bidang   public.wisudawan_kelanjutan_bidang_enum
);


-- ============================================================
-- 11. MATAKULIAH WAJIB — Section G4 (S1: S104) & I (S3: D01)
-- ============================================================
-- S1 mengisi kolom s1_*; S3 mengisi kolom s3_*. Kolom lain NULL.
-- Skala: 4-point agree (1=Tidak Setuju .. 4=Setuju)
-- ============================================================

CREATE TABLE public.wisudawan_matkul_wajib (
    responden_id    UUID PRIMARY KEY
        REFERENCES public.wisudawan_responden (responden_id) ON DELETE CASCADE,

    -- S104[SQ001..008]: Matakuliah Wajib ITB untuk S1
    s1_agama_sulit_ambil        SMALLINT CHECK (s1_agama_sulit_ambil        BETWEEN 1 AND 4),
    s1_agama_pengaruh           SMALLINT CHECK (s1_agama_pengaruh           BETWEEN 1 AND 4),
    s1_pancasila_sulit_ambil    SMALLINT CHECK (s1_pancasila_sulit_ambil    BETWEEN 1 AND 4),
    s1_pancasila_pengaruh       SMALLINT CHECK (s1_pancasila_pengaruh       BETWEEN 1 AND 4),
    s1_manajemen_sulit_ambil    SMALLINT CHECK (s1_manajemen_sulit_ambil    BETWEEN 1 AND 4),
    s1_manajemen_pengaruh       SMALLINT CHECK (s1_manajemen_pengaruh       BETWEEN 1 AND 4),
    s1_lingkungan_sulit_ambil   SMALLINT CHECK (s1_lingkungan_sulit_ambil   BETWEEN 1 AND 4),
    s1_lingkungan_pengaruh      SMALLINT CHECK (s1_lingkungan_pengaruh      BETWEEN 1 AND 4),

    -- D01[SQ001..004]: Matakuliah Wajib ITB untuk S3 (Doktor)
    s3_filsafat_sulit_ambil     SMALLINT CHECK (s3_filsafat_sulit_ambil     BETWEEN 1 AND 4),
    s3_filsafat_pengaruh        SMALLINT CHECK (s3_filsafat_pengaruh        BETWEEN 1 AND 4),
    s3_metodologi_sulit_ambil   SMALLINT CHECK (s3_metodologi_sulit_ambil   BETWEEN 1 AND 4),
    s3_metodologi_pengaruh      SMALLINT CHECK (s3_metodologi_pengaruh      BETWEEN 1 AND 4)
);


-- ============================================================
-- 12. SKOR KHUSUS FSRD — Section J (FSRD01–FSRD05)
-- ============================================================
-- Skala: 5-point expectation
--   1=Tidak sesuai harapan  2=Ada yang memenuhi  3=Sebagian besar
--   4=Memenuhi harapan      5=Melampaui harapan
-- Hanya diisi untuk responden dari FSRD.
-- ============================================================

CREATE TABLE public.wisudawan_khusus_fsrd (
    responden_id    UUID PRIMARY KEY
        REFERENCES public.wisudawan_responden (responden_id) ON DELETE CASCADE,

    -- J1: TPB FSRD (FSRD01[SQ001..005])
    tpb_prinsip_estetik     SMALLINT CHECK (tpb_prinsip_estetik     BETWEEN 1 AND 5),
    tpb_proses_kreatif      SMALLINT CHECK (tpb_proses_kreatif      BETWEEN 1 AND 5),
    tpb_drawing_forming     SMALLINT CHECK (tpb_drawing_forming     BETWEEN 1 AND 5),
    tpb_pengetahuan_prodi   SMALLINT CHECK (tpb_pengetahuan_prodi   BETWEEN 1 AND 5),
    tpb_menulis_ilmiah      SMALLINT CHECK (tpb_menulis_ilmiah      BETWEEN 1 AND 5),

    -- J2: Sistem perwalian FSRD (FSRD02[SQ001..003])
    perwalian_tatap_muka    SMALLINT CHECK (perwalian_tatap_muka    BETWEEN 1 AND 5),
    perwalian_online        SMALLINT CHECK (perwalian_online        BETWEEN 1 AND 5),
    perwalian_respon_masalah SMALLINT CHECK (perwalian_respon_masalah BETWEEN 1 AND 5),

    -- J3: Matakuliah Teori FSRD (FSRD03[SQ001..006])
    teori_sejarah               SMALLINT CHECK (teori_sejarah               BETWEEN 1 AND 5),
    teori_perkemb_indo          SMALLINT CHECK (teori_perkemb_indo          BETWEEN 1 AND 5),
    teori_perkemb_dunia         SMALLINT CHECK (teori_perkemb_dunia         BETWEEN 1 AND 5),
    teori_metoda_penciptaan     SMALLINT CHECK (teori_metoda_penciptaan     BETWEEN 1 AND 5),
    teori_analisis_kritis       SMALLINT CHECK (teori_analisis_kritis       BETWEEN 1 AND 5),
    teori_kesesuaian_beban_sks  SMALLINT CHECK (teori_kesesuaian_beban_sks  BETWEEN 1 AND 5),

    -- J4: Matakuliah Praktika/Studio FSRD (FSRD04[SQ001..006])
    praktika_teknik_penciptaan          SMALLINT CHECK (praktika_teknik_penciptaan          BETWEEN 1 AND 5),
    praktika_wawasan_estetik            SMALLINT CHECK (praktika_wawasan_estetik            BETWEEN 1 AND 5),
    praktika_kesesuaian_beban_sks       SMALLINT CHECK (praktika_kesesuaian_beban_sks       BETWEEN 1 AND 5),
    praktika_asistensi                  SMALLINT CHECK (praktika_asistensi                  BETWEEN 1 AND 5),
    praktika_penilaian                  SMALLINT CHECK (praktika_penilaian                  BETWEEN 1 AND 5),
    praktika_pengetahuan_sesuai_profesi SMALLINT CHECK (praktika_pengetahuan_sesuai_profesi BETWEEN 1 AND 5),

    -- J5: Tugas Akhir FSRD (FSRD05[SQ001..004])
    ta_teori_praktika_menunjang     SMALLINT CHECK (ta_teori_praktika_menunjang     BETWEEN 1 AND 5),
    ta_asistensi                    SMALLINT CHECK (ta_asistensi                    BETWEEN 1 AND 5),
    ta_ketersediaan_sarana_prasarana SMALLINT CHECK (ta_ketersediaan_sarana_prasarana BETWEEN 1 AND 5),
    ta_ketersediaan_pustaka         SMALLINT CHECK (ta_ketersediaan_pustaka         BETWEEN 1 AND 5)
);


-- ============================================================
-- 13. SKOR KHUSUS SBM — Section K (SBM01, 31 items aktif)
-- ============================================================
-- Skala: 5-point development
--   1=Undeveloped  2=Slightly  3=Moderately  4=Substantially  5=Highly
-- Hanya diisi untuk responden dari SBM.
-- ============================================================

CREATE TABLE public.wisudawan_khusus_sbm (
    responden_id    UUID PRIMARY KEY
        REFERENCES public.wisudawan_responden (responden_id) ON DELETE CASCADE,

    -- SBM01[SQ001..031]: Learning outcomes SBM
    komunikasi_lisan                    SMALLINT CHECK (komunikasi_lisan                    BETWEEN 1 AND 5),  -- sq001
    komunikasi_tertulis                 SMALLINT CHECK (komunikasi_tertulis                 BETWEEN 1 AND 5),  -- sq002
    apply_marketing                     SMALLINT CHECK (apply_marketing                     BETWEEN 1 AND 5),  -- sq003
    apply_operation_management          SMALLINT CHECK (apply_operation_management          BETWEEN 1 AND 5),  -- sq004
    apply_hrm                           SMALLINT CHECK (apply_hrm                           BETWEEN 1 AND 5),  -- sq005
    apply_finance                       SMALLINT CHECK (apply_finance                       BETWEEN 1 AND 5),  -- sq006
    apply_decision_negosiasi            SMALLINT CHECK (apply_decision_negosiasi            BETWEEN 1 AND 5),  -- sq007
    apply_entrepreneurship              SMALLINT CHECK (apply_entrepreneurship              BETWEEN 1 AND 5),  -- sq008
    tampil_publik                       SMALLINT CHECK (tampil_publik                       BETWEEN 1 AND 5),  -- sq009
    kedalaman_konsentrasi_pengetahuan   SMALLINT CHECK (kedalaman_konsentrasi_pengetahuan   BETWEEN 1 AND 5),  -- sq010
    statistik_data                      SMALLINT CHECK (statistik_data                      BETWEEN 1 AND 5),  -- sq011
    interpretasi_data                   SMALLINT CHECK (interpretasi_data                   BETWEEN 1 AND 5),  -- sq012
    identifikasi_masalah                SMALLINT CHECK (identifikasi_masalah                BETWEEN 1 AND 5),  -- sq013
    problem_solving                     SMALLINT CHECK (problem_solving                     BETWEEN 1 AND 5),  -- sq014
    riset_bisnis                        SMALLINT CHECK (riset_bisnis                        BETWEEN 1 AND 5),  -- sq015
    internet_for_knowledge_acquisition  SMALLINT CHECK (internet_for_knowledge_acquisition  BETWEEN 1 AND 5),  -- sq016
    bangun_jejaring                     SMALLINT CHECK (bangun_jejaring                     BETWEEN 1 AND 5),  -- sq017
    dirikan_usaha                       SMALLINT CHECK (dirikan_usaha                       BETWEEN 1 AND 5),  -- sq018
    kerja_tim                           SMALLINT CHECK (kerja_tim                           BETWEEN 1 AND 5),  -- sq019
    peluang_bisnis                      SMALLINT CHECK (peluang_bisnis                      BETWEEN 1 AND 5),  -- sq020
    peluang_perbaiki_komunitas          SMALLINT CHECK (peluang_perbaiki_komunitas          BETWEEN 1 AND 5),  -- sq021
    inovasi_produk                      SMALLINT CHECK (inovasi_produk                      BETWEEN 1 AND 5),  -- sq022
    adaptasi_sosial                     SMALLINT CHECK (adaptasi_sosial                     BETWEEN 1 AND 5),  -- sq023
    kendala_sumber_daya                 SMALLINT CHECK (kendala_sumber_daya                 BETWEEN 1 AND 5),  -- sq024
    kendala_etika                       SMALLINT CHECK (kendala_etika                       BETWEEN 1 AND 5),  -- sq025
    kendala_k3                          SMALLINT CHECK (kendala_k3                          BETWEEN 1 AND 5),  -- sq026
    paham_tanggung_jawab_profesional    SMALLINT CHECK (paham_tanggung_jawab_profesional    BETWEEN 1 AND 5),  -- sq027
    paham_tanggung_jawab_etis           SMALLINT CHECK (paham_tanggung_jawab_etis           BETWEEN 1 AND 5),  -- sq028
    lifelong_learning_pengakuan         SMALLINT CHECK (lifelong_learning_pengakuan         BETWEEN 1 AND 5),  -- sq029
    lifelong_learning_kemampuan         SMALLINT CHECK (lifelong_learning_kemampuan         BETWEEN 1 AND 5),  -- sq030
    kecukupan_pengetahuan_untuk_s2      SMALLINT CHECK (kecukupan_pengetahuan_untuk_s2      BETWEEN 1 AND 5),  -- sq031

    -- Computed overall SBM avg (31 item aktif; sq032 kosong di export)
    skor_avg            NUMERIC(4,2) GENERATED ALWAYS AS (
        ROUND(
            (COALESCE(komunikasi_lisan,0) + COALESCE(komunikasi_tertulis,0) + COALESCE(apply_marketing,0) +
             COALESCE(apply_operation_management,0) + COALESCE(apply_hrm,0) + COALESCE(apply_finance,0) +
             COALESCE(apply_decision_negosiasi,0) + COALESCE(apply_entrepreneurship,0) + COALESCE(tampil_publik,0) +
             COALESCE(kedalaman_konsentrasi_pengetahuan,0) + COALESCE(statistik_data,0) + COALESCE(interpretasi_data,0) +
             COALESCE(identifikasi_masalah,0) + COALESCE(problem_solving,0) + COALESCE(riset_bisnis,0) +
             COALESCE(internet_for_knowledge_acquisition,0) + COALESCE(bangun_jejaring,0) + COALESCE(dirikan_usaha,0) +
             COALESCE(kerja_tim,0) + COALESCE(peluang_bisnis,0) + COALESCE(peluang_perbaiki_komunitas,0) +
             COALESCE(inovasi_produk,0) + COALESCE(adaptasi_sosial,0) + COALESCE(kendala_sumber_daya,0) +
             COALESCE(kendala_etika,0) + COALESCE(kendala_k3,0) + COALESCE(paham_tanggung_jawab_profesional,0) +
             COALESCE(paham_tanggung_jawab_etis,0) + COALESCE(lifelong_learning_pengakuan,0) +
             COALESCE(lifelong_learning_kemampuan,0) + COALESCE(kecukupan_pengetahuan_untuk_s2,0))::NUMERIC /
            NULLIF(31, 0), 2
        )
    ) STORED
);


-- ============================================================
-- 14. ENCODING HELPER FUNCTIONS — TEXT → SMALLINT
-- ============================================================
-- Gunakan fungsi ini di ETL pipeline Python/SQL.
-- ============================================================

-- 4-point agree scale (U03, U01, U04, U05, S104, D01)
CREATE OR REPLACE FUNCTION public.fn_likert4_agree(val TEXT)
RETURNS SMALLINT LANGUAGE SQL IMMUTABLE AS $$
    SELECT CASE TRIM(val)
        WHEN 'Setuju'                  THEN 4
        WHEN 'Cenderung Setuju'        THEN 3
        WHEN 'Cenderung Tidak Setuju'  THEN 2
        WHEN 'Tidak Setuju'            THEN 1
        ELSE NULL
    END;
$$;

-- 4-point frequency scale (U06)
CREATE OR REPLACE FUNCTION public.fn_likert4_freq(val TEXT)
RETURNS SMALLINT LANGUAGE SQL IMMUTABLE AS $$
    SELECT CASE TRIM(val)
        WHEN 'Selalu atau besar'               THEN 4
        WHEN 'Sering atau cukup'               THEN 3
        WHEN 'Jarang atau kecil'               THEN 2
        WHEN 'Tidak pernah atau sama sekali tidak' THEN 1
        ELSE NULL
    END;
$$;

-- 5-point expectation scale (U07, FSRD01–FSRD05)
CREATE OR REPLACE FUNCTION public.fn_likert5_expect(val TEXT)
RETURNS SMALLINT LANGUAGE SQL IMMUTABLE AS $$
    SELECT CASE TRIM(val)
        WHEN 'Melampaui harapan'               THEN 5
        WHEN 'Memenuhi harapan'                THEN 4
        WHEN 'Sebagian besar memenuhi harapan' THEN 3
        WHEN 'Ada yang memenuhi harapan'       THEN 2
        WHEN 'Tidak sesuai harapan'            THEN 1
        ELSE NULL
    END;
$$;

-- 5-point development scale (SBM01)
CREATE OR REPLACE FUNCTION public.fn_likert5_dev(val TEXT)
RETURNS SMALLINT LANGUAGE SQL IMMUTABLE AS $$
    SELECT CASE TRIM(val)
        WHEN 'Highly Developed – Berkembang dengan sangat tinggi'      THEN 5
        WHEN 'Substantially Developed – Berkembang secara substansial' THEN 4
        WHEN 'Moderately Developed – Cukup berkembang'                 THEN 3
        WHEN 'Slightly Developed – Sedikit berkembang'                 THEN 2
        WHEN 'Undeveloped – Tidak berkembang'                          THEN 1
        ELSE NULL
    END;
$$;