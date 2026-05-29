-- ============================================================
-- SCHEMA: evaluasi_wisudawan
-- Sumber data : LimeSurvey export resultssurvey926755_2.csv
--
-- Keputusan desain:
--   1. Tidak INHERITS (template.entry) — perlu konfirmasi DSI ITB
--   2. Survey anonim — tidak ada FK ke utama.mahasiswa
--   3. Surrogate PK (response_id SERIAL), LimeSurvey ID kolom terpisah
--   4. periode_ijazah_id NULLABLE FK ke wisuda.periode_ijazah
--      → Analisis 100% data: 66.6% NULL, tidak ada pola imputable
--   5. Semua jawaban disimpan sebagai INTEGER di jawaban JSONB:
--      - Likert (ordinal) : integer 1–4 atau 1–5
--      - Kategoris (nominal): integer sesuai ref_opsi.nilai
--      - Free-text         : TEXT string (satu-satunya pengecualian)
--   6. ref_set_opsi + ref_opsi: satu tabel terpadu untuk semua opsi jawaban
--      (ordinal Likert maupun nominal kategoris), dibedakan kolom tipe
--   7. Tidak ada tabel grup pertanyaan
--      kd_grup = LimeSurvey group prefix, VARCHAR biasa (bukan FK)
--   8. D2 (U07) dan FSRD pakai skala 5-poin yang berbeda di opsi ke-4:
--      D2   : "Sepenuhnya memenuhi harapan" → S5_EXPECT
--      FSRD : "Memenuhi harapan"            → S5_EXPECT_FSRD
-- ============================================================

CREATE SCHEMA IF NOT EXISTS evaluasi_wisudawan;


-- ============================================================
-- 1. REFERENSI OPSI JAWABAN
--    ref_set_opsi : definisi set opsi (ordinal atau nominal)
--    ref_opsi     : opsi individual per set
-- ============================================================

CREATE TABLE evaluasi_wisudawan.ref_set_opsi (
    kd_set          VARCHAR(20) PRIMARY KEY,
    nama            JSONB       NOT NULL,
    tipe            CHAR(1)     NOT NULL CHECK (tipe IN ('O','N')),
    -- O = Ordinal  : nilai bermakna aritmetika, boleh AVG/STDDEV
    -- N = Nominal  : nilai hanya kode urut, TIDAK boleh AVG
    jumlah_poin     SMALLINT,
    -- Diisi untuk tipe='O' (4 atau 5), NULL untuk tipe='N'
    active          BOOLEAN     NOT NULL DEFAULT true,
    ts_entry        TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id_entry   INTEGER     NOT NULL
);

CREATE TABLE evaluasi_wisudawan.ref_opsi (
    kd_set          VARCHAR(20) NOT NULL
                        REFERENCES evaluasi_wisudawan.ref_set_opsi(kd_set)
                        ON UPDATE CASCADE ON DELETE RESTRICT
                        DEFERRABLE INITIALLY DEFERRED,
    nilai           SMALLINT    NOT NULL,
    -- Ordinal : 1=paling negatif … n=paling positif
    -- Nominal : 1,2,3,… urut sesuai urutan pilihan (tidak ada makna aritmetika)
    label           JSONB       NOT NULL,
    PRIMARY KEY (kd_set, nilai),
    ts_entry        TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id_entry   INTEGER     NOT NULL
);

-- ── Seed ref_set_opsi ─────────────────────────────────────────
INSERT INTO evaluasi_wisudawan.ref_set_opsi
    (kd_set, nama, tipe, jumlah_poin, user_id_entry)
VALUES
-- Ordinal — Likert
('S4_AGREE',
    '{"id":"4-poin Persetujuan","en":"4-pt Agreement"}',
    'O', 4, 1),
('S4_FREQ',
    '{"id":"4-poin Frekuensi","en":"4-pt Frequency"}',
    'O', 4, 1),
('S5_EXPECT',
    '{"id":"5-poin Pemenuhan Harapan D2","en":"5-pt Expectation Fulfillment D2"}',
    'O', 5, 1),
('S5_EXPECT_FSRD',
    '{"id":"5-poin Pemenuhan Harapan FSRD","en":"5-pt Expectation Fulfillment FSRD"}',
    'O', 5, 1),
('S5_DEVELOP_SBM',
    '{"id":"5-poin Tingkat Perkembangan SBM","en":"5-pt Level of Development SBM"}',
    'O', 5, 1),

-- Nominal — kategoris
('OPT_YA_TIDAK',
    '{"id":"Ya/Tidak","en":"Yes/No"}',
    'N', NULL, 1),
('OPT_LOKASI_STUDI',
    '{"id":"Lokasi Studi Lanjut","en":"Further Study Location"}',
    'N', NULL, 1),
('OPT_KELANJUTAN_STUDI',
    '{"id":"Kelanjutan Bidang Studi","en":"Field of Study Continuation"}',
    'N', NULL, 1),
('OPT_U02',
    '{"id":"Rekomendasi Prodi","en":"Study Program Recommendation"}',
    'N', NULL, 1);

-- ── Seed ref_opsi ─────────────────────────────────────────────
INSERT INTO evaluasi_wisudawan.ref_opsi
    (kd_set, nilai, label, user_id_entry)
VALUES
-- S4_AGREE (Section A/B/C1/C2/G-S104/I-D01)
('S4_AGREE', 1, '{"id":"Tidak Setuju","en":"Strongly Disagree"}',         1),
('S4_AGREE', 2, '{"id":"Cenderung Tidak Setuju","en":"Disagree"}',        1),
('S4_AGREE', 3, '{"id":"Cenderung Setuju","en":"Agree"}',                 1),
('S4_AGREE', 4, '{"id":"Setuju","en":"Strongly Agree"}',                  1),

-- S4_FREQ (Section D1/U06)
('S4_FREQ',  1, '{"id":"Tidak pernah atau sama sekali tidak","en":"Never"}', 1),
('S4_FREQ',  2, '{"id":"Jarang atau kecil","en":"Rarely"}',                 1),
('S4_FREQ',  3, '{"id":"Sering atau cukup","en":"Often"}',                  1),
('S4_FREQ',  4, '{"id":"Selalu atau besar","en":"Always"}',                 1),

-- S5_EXPECT (Section D2/U07) — opsi ke-4: "Sepenuhnya memenuhi harapan"
('S5_EXPECT', 1, '{"id":"Tidak sesuai harapan","en":"Does not meet expectations"}',          1),
('S5_EXPECT', 2, '{"id":"Ada yang memenuhi harapan","en":"Partially meets expectations"}',   1),
('S5_EXPECT', 3, '{"id":"Sebagian besar memenuhi harapan","en":"Mostly meets expectations"}',1),
('S5_EXPECT', 4, '{"id":"Sepenuhnya memenuhi harapan","en":"Fully meets expectations"}',     1),
('S5_EXPECT', 5, '{"id":"Melampaui harapan","en":"Exceeds expectations"}',                   1),

-- S5_EXPECT_FSRD (Section J/FSRD) — opsi ke-4: "Memenuhi harapan"
('S5_EXPECT_FSRD', 1, '{"id":"Tidak sesuai harapan","en":"Does not meet expectations"}',          1),
('S5_EXPECT_FSRD', 2, '{"id":"Ada yang memenuhi harapan","en":"Partially meets expectations"}',   1),
('S5_EXPECT_FSRD', 3, '{"id":"Sebagian besar memenuhi harapan","en":"Mostly meets expectations"}',1),
('S5_EXPECT_FSRD', 4, '{"id":"Memenuhi harapan","en":"Meets expectations"}',                      1),
('S5_EXPECT_FSRD', 5, '{"id":"Melampaui harapan","en":"Exceeds expectations"}',                   1),

-- S5_DEVELOP_SBM (Section K/SBM01)
('S5_DEVELOP_SBM', 1, '{"id":"Undeveloped – Tidak berkembang","en":"Undeveloped"}',                         1),
('S5_DEVELOP_SBM', 2, '{"id":"Slightly Developed – Sedikit berkembang","en":"Slightly Developed"}',         1),
('S5_DEVELOP_SBM', 3, '{"id":"Moderately Developed – Cukup berkembang","en":"Moderately Developed"}',       1),
('S5_DEVELOP_SBM', 4, '{"id":"Substantially Developed – Berkembang secara substansial","en":"Substantially Developed"}', 1),
('S5_DEVELOP_SBM', 5, '{"id":"Highly Developed – Berkembang dengan sangat tinggi","en":"Highly Developed"}', 1),

-- OPT_YA_TIDAK (S101, M01)
('OPT_YA_TIDAK', 1, '{"id":"Ya","en":"Yes"}',     1),
('OPT_YA_TIDAK', 2, '{"id":"Tidak","en":"No"}',   1),

-- OPT_LOKASI_STUDI (S102, M02)
('OPT_LOKASI_STUDI', 1, '{"id":"ITB","en":"ITB"}',                                                    1),
('OPT_LOKASI_STUDI', 2, '{"id":"Perguruan tinggi dalam negeri selain ITB","en":"Other domestic university"}', 1),
('OPT_LOKASI_STUDI', 3, '{"id":"Di luar negeri","en":"Abroad"}',                                      1),
('OPT_LOKASI_STUDI', 4, '{"id":"Tidak ada rencana studi lanjut","en":"No further study plans"}',      1),

-- OPT_KELANJUTAN_STUDI (S103, M03)
('OPT_KELANJUTAN_STUDI', 1, '{"id":"Ya, bidang studi tersebut merupakan kelanjutan dari bidang studi yang baru saya selesaikan di ITB","en":"Yes, continuation of ITB field"}',           1),
('OPT_KELANJUTAN_STUDI', 2, '{"id":"Tidak, tetapi bidang studi tersebut masih serumpun dengan bidang studi yang baru saya selesaikan di ITB","en":"No, but related field"}',             1),
('OPT_KELANJUTAN_STUDI', 3, '{"id":"Tidak, tetapi bidang studi tersebut masih membutuhkan pengetahuan dari bidang studi yang baru saya selesaikan di ITB","en":"No, but requires ITB field knowledge"}', 1),
('OPT_KELANJUTAN_STUDI', 4, '{"id":"Tidak, bidang studi tersebut sangat berbeda dari bidang studi yang baru saya selesaikan di ITB","en":"No, very different field"}',                  1),
('OPT_KELANJUTAN_STUDI', 5, '{"id":"Tidak ada rencana studi lanjut","en":"No further study plans"}',  1),

-- OPT_U02 (7 opsi)
('OPT_U02', 1, '{"id":"Kualitas dosen","en":"Lecturer quality"}',            1),
('OPT_U02', 2, '{"id":"Suasana akademik","en":"Academic atmosphere"}',       1),
('OPT_U02', 3, '{"id":"Jejaring alumni","en":"Alumni network"}',             1),
('OPT_U02', 4, '{"id":"Lapangan pekerjaan","en":"Job prospects"}',           1),
('OPT_U02', 5, '{"id":"Fasilitas akademik","en":"Academic facilities"}',     1),
('OPT_U02', 6, '{"id":"Tidak merekomendasikan","en":"Would not recommend"}', 1),
('OPT_U02', 7, '{"id":"Other","en":"Other"}',                                1);


-- ============================================================
-- 2. KATALOG PERTANYAAN
--    Total: 137 pertanyaan valid (SBM01_SQ032 dieksklusi)
--    Breakdown:
--      Universal (A–D, E, F) : 54 Likert + 14 free-text + 1 nominal = 69
--      S1 spesifik (G)        : 3 nominal + 4 Likert = 7
--      S2 spesifik (H)        : 3 nominal = 3
--      S3 spesifik (I)        : 4 Likert = 4
--      FSRD spesifik (J)      : 24 Likert = 24
--      SBM spesifik (K)       : 31 Likert = 31
-- ============================================================

CREATE TABLE evaluasi_wisudawan.pertanyaan (
    kd_pertanyaan   VARCHAR(20) PRIMARY KEY,
    -- Contoh: 'U03_SQ001', 'G01Q23', 'S101', 'FSRD01_SQ001'

    limesurvey_key  VARCHAR(50),
    -- Original key di CSV, contoh: 'U03[SQ001]' — untuk traceability

    kd_grup         VARCHAR(15) NOT NULL,
    -- LimeSurvey question group prefix — VARCHAR biasa, bukan FK
    -- Contoh: 'U03','U01','U02','U04','U05','U06','U07',
    --         'G01','G10','G11','S1','M','D01',
    --         'FSRD01'..'FSRD05','SBM01'

    pertanyaan      JSONB       NOT NULL,
    -- {"id": "...", "en": "..."}

    kd_set_opsi     VARCHAR(20)
                        REFERENCES evaluasi_wisudawan.ref_set_opsi(kd_set)
                        ON UPDATE CASCADE ON DELETE RESTRICT
                        DEFERRABLE INITIALLY DEFERRED,
    -- Ordinal Likert : 'S4_AGREE', 'S4_FREQ', 'S5_EXPECT', dst.
    -- Nominal        : 'OPT_YA_TIDAK', 'OPT_LOKASI_STUDI', 'OPT_U02', dst.
    -- Free-text      : NULL

    batasan         JSONB,
    -- NULL = universal (semua strata & fakultas)
    -- {"strata": ["S1"]}     → Section G (S101, S102, S103, S104)
    -- {"strata": ["S2"]}     → Section H (M01, M02, M03)
    -- {"strata": ["S3"]}     → Section I (D01)
    -- {"fakultas": ["FSRD"]} → Section J (FSRD01–FSRD05)
    -- {"fakultas": ["SBM"]}  → Section K (SBM01)
    -- Catatan: PR hanya mengisi Section A–D, tidak ada batasan khusus PR

    urutan          SMALLINT,
    -- Urutan tampil dalam grup/section

    active          BOOLEAN     NOT NULL DEFAULT true,
    ts_entry        TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id_entry   INTEGER     NOT NULL
);

CREATE INDEX ON evaluasi_wisudawan.pertanyaan (kd_grup);
CREATE INDEX ON evaluasi_wisudawan.pertanyaan (kd_set_opsi);

-- ── Seed pertanyaan ───────────────────────────────────────────
-- Kolom: (kd_pertanyaan, limesurvey_key, kd_grup,
--         pertanyaan, kd_set_opsi, batasan, urutan, user_id_entry)

-- Section A: U03 — Fasilitas & Kepuasan ITB (12 items, S4_AGREE, universal)
INSERT INTO evaluasi_wisudawan.pertanyaan
    (kd_pertanyaan, limesurvey_key, kd_grup,
     pertanyaan, kd_set_opsi, batasan, urutan, user_id_entry)
VALUES
('U03_SQ001','U03[SQ001]','U03',
 '{"id":"Tersedia cukup ruang kelas","en":"There are sufficient classrooms available"}',
 'S4_AGREE',NULL,1,1),
('U03_SQ002','U03[SQ002]','U03',
 '{"id":"Ruang kelas kondusif untuk pembelajaran","en":"Classrooms are conducive for learning"}',
 'S4_AGREE',NULL,2,1),
('U03_SQ003','U03[SQ003]','U03',
 '{"id":"Laboratorium kondusif untuk pembelajaran","en":"Laboratories are conducive for learning"}',
 'S4_AGREE',NULL,3,1),
('U03_SQ004','U03[SQ004]','U03',
 '{"id":"Akses internet memadai","en":"Internet access is adequate"}',
 'S4_AGREE',NULL,4,1),
('U03_SQ005','U03[SQ005]','U03',
 '{"id":"Fasilitas keprofesian memadai","en":"Professional facilities are adequate"}',
 'S4_AGREE',NULL,5,1),
('U03_SQ006','U03[SQ006]','U03',
 '{"id":"Akses perpustakaan memadai","en":"Library access is adequate"}',
 'S4_AGREE',NULL,6,1),
('U03_SQ007','U03[SQ007]','U03',
 '{"id":"Perangkat pembelajaran up-to-date","en":"Learning equipment is up-to-date"}',
 'S4_AGREE',NULL,7,1),
('U03_SQ008','U03[SQ008]','U03',
 '{"id":"Fasilitas toilet memadai","en":"Toilet facilities are adequate"}',
 'S4_AGREE',NULL,8,1),
('U03_SQ009','U03[SQ009]','U03',
 '{"id":"Fasilitas kantin memadai","en":"Canteen facilities are adequate"}',
 'S4_AGREE',NULL,9,1),
('U03_SQ010','U03[SQ010]','U03',
 '{"id":"Fasilitas rekreasi/olahraga memadai","en":"Recreation and sports facilities are adequate"}',
 'S4_AGREE',NULL,10,1),
('U03_SQ011','U03[SQ011]','U03',
 '{"id":"Fasilitas kesehatan memadai","en":"Health facilities are adequate"}',
 'S4_AGREE',NULL,11,1),
('U03_SQ012','U03[SQ012]','U03',
 '{"id":"Secara keseluruhan saya puas dengan fasilitas ITB","en":"Overall I am satisfied with ITB facilities"}',
 'S4_AGREE',NULL,12,1),

-- Section B: U01 — Pendidikan di Prodi (12 items, S4_AGREE, universal)
('U01_SQ001','U01[SQ001]','U01',
 '{"id":"Wali akademik selalu tersedia saat dibutuhkan","en":"Academic advisor is always available when needed"}',
 'S4_AGREE',NULL,1,1),
('U01_SQ002','U01[SQ002]','U01',
 '{"id":"Wali akademik membantu memenuhi persyaratan akademik","en":"Academic advisor helps meet academic requirements"}',
 'S4_AGREE',NULL,2,1),
('U01_SQ003','U01[SQ003]','U01',
 '{"id":"Dosen berinteraksi secara informal dengan mahasiswa","en":"Lecturers interact informally with students"}',
 'S4_AGREE',NULL,3,1),
('U01_SQ004','U01[SQ004]','U01',
 '{"id":"Dosen memperhatikan proses pembelajaran mahasiswa","en":"Lecturers pay attention to the student learning process"}',
 'S4_AGREE',NULL,4,1),
('U01_SQ005','U01[SQ005]','U01',
 '{"id":"Dosen memiliki kemampuan profesional yang baik","en":"Lecturers have good professional competence"}',
 'S4_AGREE',NULL,5,1),
('U01_SQ006','U01[SQ006]','U01',
 '{"id":"Matakuliah wajib memberikan dasar yang baik","en":"Compulsory courses provide a good foundation"}',
 'S4_AGREE',NULL,6,1),
('U01_SQ007','U01[SQ007]','U01',
 '{"id":"Matakuliah pilihan memberikan keleluasaan eksplorasi","en":"Elective courses provide freedom of exploration"}',
 'S4_AGREE',NULL,7,1),
('U01_SQ008','U01[SQ008]','U01',
 '{"id":"Praktikum sejalan dengan teori di kelas","en":"Laboratory work is aligned with classroom theory"}',
 'S4_AGREE',NULL,8,1),
('U01_SQ009','U01[SQ009]','U01',
 '{"id":"Sarana program studi memadai","en":"Study program facilities are adequate"}',
 'S4_AGREE',NULL,9,1),
('U01_SQ010','U01[SQ010]','U01',
 '{"id":"Program studi memberikan gambaran dunia kerja","en":"Study program provides a picture of the working world"}',
 'S4_AGREE',NULL,10,1),
('U01_SQ011','U01[SQ011]','U01',
 '{"id":"Saya menikmati bidang studi saya","en":"I enjoy my field of study"}',
 'S4_AGREE',NULL,11,1),
('U01_SQ012','U01[SQ012]','U01',
 '{"id":"Saya akan memilih program studi yang sama lagi","en":"I would choose the same study program again"}',
 'S4_AGREE',NULL,12,1),

-- Section B: U02 — Rekomendasi Prodi (nominal, universal)
('U02','U02','U02',
 '{"id":"Aspek yang paling Anda tonjolkan dalam merekomendasikan prodi","en":"Aspect you would most highlight when recommending the study program"}',
 'OPT_U02',NULL,13,1),

-- Section C1: U04 — Kemampuan Softskills (9 items, S4_AGREE, universal)
('U04_SQ001','U04[SQ001]','U04',
 '{"id":"Kemampuan komunikasi lisan","en":"Oral communication skills"}',
 'S4_AGREE',NULL,1,1),
('U04_SQ002','U04[SQ002]','U04',
 '{"id":"Kemampuan komunikasi tertulis","en":"Written communication skills"}',
 'S4_AGREE',NULL,2,1),
('U04_SQ003','U04[SQ003]','U04',
 '{"id":"Kemampuan berbahasa asing","en":"Foreign language skills"}',
 'S4_AGREE',NULL,3,1),
('U04_SQ004','U04[SQ004]','U04',
 '{"id":"Kemampuan penyelesaian masalah","en":"Problem-solving skills"}',
 'S4_AGREE',NULL,4,1),
('U04_SQ005','U04[SQ005]','U04',
 '{"id":"Kemampuan berpikir kritis","en":"Critical thinking skills"}',
 'S4_AGREE',NULL,5,1),
('U04_SQ006','U04[SQ006]','U04',
 '{"id":"Kemampuan introspeksi diri","en":"Self-reflection skills"}',
 'S4_AGREE',NULL,6,1),
('U04_SQ007','U04[SQ007]','U04',
 '{"id":"Kemampuan menyampaikan pendapat","en":"Ability to express opinions"}',
 'S4_AGREE',NULL,7,1),
('U04_SQ008','U04[SQ008]','U04',
 '{"id":"Kemampuan kerja tim","en":"Teamwork skills"}',
 'S4_AGREE',NULL,8,1),
('U04_SQ009','U04[SQ009]','U04',
 '{"id":"Kemampuan kerja mandiri","en":"Independent work skills"}',
 'S4_AGREE',NULL,9,1),

-- Section C2: U05 — Pengembangan Karakter (7 items, S4_AGREE, universal)
('U05_SQ001','U05[SQ001]','U05',
 '{"id":"Kejujuran","en":"Honesty"}',
 'S4_AGREE',NULL,1,1),
('U05_SQ002','U05[SQ002]','U05',
 '{"id":"Komitmen","en":"Commitment"}',
 'S4_AGREE',NULL,2,1),
('U05_SQ003','U05[SQ003]','U05',
 '{"id":"Kecerdasan emosi","en":"Emotional intelligence"}',
 'S4_AGREE',NULL,3,1),
('U05_SQ004','U05[SQ004]','U05',
 '{"id":"Kepedulian terhadap sesama","en":"Empathy towards others"}',
 'S4_AGREE',NULL,4,1),
('U05_SQ005','U05[SQ005]','U05',
 '{"id":"Objektivitas","en":"Objectivity"}',
 'S4_AGREE',NULL,5,1),
('U05_SQ006','U05[SQ006]','U05',
 '{"id":"Ketidakmudahan menyerah","en":"Perseverance"}',
 'S4_AGREE',NULL,6,1),
('U05_SQ007','U05[SQ007]','U05',
 '{"id":"Kepatuhan terhadap aturan","en":"Compliance with rules"}',
 'S4_AGREE',NULL,7,1),

-- Section D1: U06 — Permasalahan Selama Studi (9 items, S4_FREQ, universal)
('U06_SQ001','U06[SQ001]','U06',
 '{"id":"Permasalahan akademis","en":"Academic problems"}',
 'S4_FREQ',NULL,1,1),
('U06_SQ002','U06[SQ002]','U06',
 '{"id":"Permasalahan keuangan","en":"Financial problems"}',
 'S4_FREQ',NULL,2,1),
('U06_SQ003','U06[SQ003]','U06',
 '{"id":"Pengaruh keuangan terhadap akademis","en":"Financial impact on academics"}',
 'S4_FREQ',NULL,3,1),
('U06_SQ004','U06[SQ004]','U06',
 '{"id":"Permasalahan psikologis","en":"Psychological problems"}',
 'S4_FREQ',NULL,4,1),
('U06_SQ005','U06[SQ005]','U06',
 '{"id":"Pengaruh psikologis terhadap studi","en":"Psychological impact on studies"}',
 'S4_FREQ',NULL,5,1),
('U06_SQ006','U06[SQ006]','U06',
 '{"id":"Permasalahan sosial budaya","en":"Socio-cultural problems"}',
 'S4_FREQ',NULL,6,1),
('U06_SQ007','U06[SQ007]','U06',
 '{"id":"Pengaruh sosial budaya terhadap studi","en":"Socio-cultural impact on studies"}',
 'S4_FREQ',NULL,7,1),
('U06_SQ008','U06[SQ008]','U06',
 '{"id":"Permasalahan kesehatan","en":"Health problems"}',
 'S4_FREQ',NULL,8,1),
('U06_SQ009','U06[SQ009]','U06',
 '{"id":"Pengaruh kesehatan terhadap studi","en":"Health impact on studies"}',
 'S4_FREQ',NULL,9,1),

-- Section D2: U07 — Ketersediaan Dukungan (4 items, S5_EXPECT, universal)
-- Hanya untuk yang pernah menghadapi permasalahan selama studi
('U07_SQ001','U07[SQ001]','U07',
 '{"id":"Ketersediaan beasiswa atau pinjaman","en":"Availability of scholarships or loans"}',
 'S5_EXPECT',NULL,1,1),
('U07_SQ002','U07[SQ002]','U07',
 '{"id":"Bimbingan konseling","en":"Counseling services"}',
 'S5_EXPECT',NULL,2,1),
('U07_SQ003','U07[SQ003]','U07',
 '{"id":"Nasehat dari wali akademik","en":"Advice from academic advisor"}',
 'S5_EXPECT',NULL,3,1),
('U07_SQ004','U07[SQ004]','U07',
 '{"id":"Nasehat dari dosen matakuliah","en":"Advice from course lecturers"}',
 'S5_EXPECT',NULL,4,1),

-- Section E: free-text (universal)
-- Catatan: G01Q23–G01Q29 dan G01Q31–G01Q35 berbagi LimeSurvey group G01
-- (mencakup Section E dan F) — anomali LimeSurvey, bukan kesalahan desain
('G10Q22','G10Q22','G10',
 '{"id":"Kebiasaan belajar","en":"Study habits"}',
 NULL,NULL,1,1),
('G01Q23','G01Q23','G01',
 '{"id":"Kesan dan prestasi dalam belajar","en":"Impressions and achievements in learning"}',
 NULL,NULL,2,1),
('G01Q24','G01Q24','G01',
 '{"id":"Pengalaman lain yang sangat berkesan","en":"Other memorable experiences"}',
 NULL,NULL,3,1),
('G01Q25','G01Q25','G01',
 '{"id":"Aktivitas kemahasiswaan","en":"Student activities"}',
 NULL,NULL,4,1),
('G01Q26','G01Q26','G01',
 '{"id":"Cita-cita dalam karier","en":"Career aspirations"}',
 NULL,NULL,5,1),
('G01Q27','G01Q27','G01',
 '{"id":"Cita-cita dalam hidup","en":"Life aspirations"}',
 NULL,NULL,6,1),
('G01Q28','G01Q28','G01',
 '{"id":"Motto untuk sukses studi di ITB","en":"Motto for successful study at ITB"}',
 NULL,NULL,7,1),
('G01Q29','G01Q29','G01',
 '{"id":"Sifat khas diri sendiri","en":"Personal characteristic traits"}',
 NULL,NULL,8,1),

-- Section F: free-text (universal)
('G11Q30','G11Q30','G11',
 '{"id":"Suka duka menempuh studi di ITB","en":"Joys and sorrows of studying at ITB"}',
 NULL,NULL,1,1),
('G01Q31','G01Q31','G01',
 '{"id":"Segi positif studi di ITB","en":"Positive aspects of studying at ITB"}',
 NULL,NULL,2,1),
('G01Q32','G01Q32','G01',
 '{"id":"Segi negatif studi di ITB","en":"Negative aspects of studying at ITB"}',
 NULL,NULL,3,1),
('G01Q33','G01Q33','G01',
 '{"id":"Saran untuk perbaikan proses dan sarana pendidikan di ITB","en":"Suggestions for improving ITB education processes and facilities"}',
 NULL,NULL,4,1),
('G01Q34','G01Q34','G01',
 '{"id":"Saran untuk mahasiswa lain dalam menempuh studi di ITB","en":"Advice for other students studying at ITB"}',
 NULL,NULL,5,1),
('G01Q35','G01Q35','G01',
 '{"id":"Catatan atau komentar lain","en":"Other notes or comments"}',
 NULL,NULL,6,1),

-- Section G: S1 khusus
('S101','S101','S1',
 '{"id":"Rencana melanjutkan ke pendidikan lebih tinggi","en":"Plan to pursue higher education"}',
 'OPT_YA_TIDAK','{"strata":["S1"]}',1,1),
('S102','S102','S1',
 '{"id":"Lokasi rencana studi lanjut","en":"Location of planned further study"}',
 'OPT_LOKASI_STUDI','{"strata":["S1"]}',2,1),
('S103','S103','S1',
 '{"id":"Apakah bidang studi lanjutan merupakan kelanjutan bidang studi di ITB","en":"Whether the planned further study is a continuation of the current field of study pursued in ITB"}',
 'OPT_KELANJUTAN_STUDI','{"strata":["S1"]}',3,1),
('S104_SQ001','S104[SQ001]','S1',
 '{"id":"Matakuliah wajib ITB membekali kemampuan softskill","en":"ITB compulsory courses provide softskill capabilities"}',
 'S4_AGREE','{"strata":["S1"]}',4,1),
('S104_SQ002','S104[SQ002]','S1',
 '{"id":"Matakuliah wajib ITB membekali kemampuan hardskill","en":"ITB compulsory courses provide hardskill capabilities"}',
 'S4_AGREE','{"strata":["S1"]}',5,1),
('S104_SQ003','S104[SQ003]','S1',
 '{"id":"Matakuliah wajib ITB membangun karakter","en":"ITB compulsory courses build character"}',
 'S4_AGREE','{"strata":["S1"]}',6,1),
('S104_SQ004','S104[SQ004]','S1',
 '{"id":"Matakuliah wajib ITB memperluas wawasan","en":"ITB compulsory courses broaden perspectives"}',
 'S4_AGREE','{"strata":["S1"]}',7,1),

-- Section H: S2 khusus
('M01','M01','M',
 '{"id":"Rencana melanjutkan ke pendidikan lebih tinggi","en":"Plan to pursue higher education"}',
 'OPT_YA_TIDAK','{"strata":["S2"]}',1,1),
('M02','M02','M',
 '{"id":"Lokasi rencana studi lanjut","en":"Location of planned further study"}',
 'OPT_LOKASI_STUDI','{"strata":["S2"]}',2,1),
('M03','M03','M',
 '{"id":"Apakah bidang studi lanjutan merupakan kelanjutan bidang studi di ITB","en":"Whether the planned further study is a continuation of the current field of study pursued in ITB"}',
 'OPT_KELANJUTAN_STUDI','{"strata":["S2"]}',3,1),

-- Section I: S3 khusus (4 items, S4_AGREE)
('D01_SQ001','D01[SQ001]','D01',
 '{"id":"Matakuliah wajib ITB membekali kemampuan softskill","en":"ITB compulsory courses provide softskill capabilities"}',
 'S4_AGREE','{"strata":["S3"]}',1,1),
('D01_SQ002','D01[SQ002]','D01',
 '{"id":"Matakuliah wajib ITB membekali kemampuan hardskill","en":"ITB compulsory courses provide hardskill capabilities"}',
 'S4_AGREE','{"strata":["S3"]}',2,1),
('D01_SQ003','D01[SQ003]','D01',
 '{"id":"Matakuliah wajib ITB membangun karakter","en":"ITB compulsory courses build character"}',
 'S4_AGREE','{"strata":["S3"]}',3,1),
('D01_SQ004','D01[SQ004]','D01',
 '{"id":"Matakuliah wajib ITB memperluas wawasan","en":"ITB compulsory courses broaden perspectives"}',
 'S4_AGREE','{"strata":["S3"]}',4,1),

-- Section J: FSRD khusus (S5_EXPECT_FSRD)
-- FSRD01: 5 items — Tahap Persiapan Bersama
('FSRD01_SQ001','FSRD01[SQ001]','FSRD01',
 '{"id":"Pemahaman Prinsip Estetik (TPB)","en":"Understanding of Aesthetic Principles (TPB)"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',1,1),
('FSRD01_SQ002','FSRD01[SQ002]','FSRD01',
 '{"id":"Penguasaan Proses Kreatif (TPB)","en":"Mastery of Creative Process (TPB)"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',2,1),
('FSRD01_SQ003','FSRD01[SQ003]','FSRD01',
 '{"id":"Penguasaan kemampuan menggambar (Drawing) dan membentuk (Forming) (TPB)","en":"Mastery of Drawing and Forming skills (TPB)"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',3,1),
('FSRD01_SQ004','FSRD01[SQ004]','FSRD01',
 '{"id":"Pengetahuan tentang program studi yang ada di FSRD (TPB)","en":"Knowledge of FSRD study programs (TPB)"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',4,1),
('FSRD01_SQ005','FSRD01[SQ005]','FSRD01',
 '{"id":"Penguasaan kemampuan menulis secara ilmiah (TPB)","en":"Mastery of scientific writing skills (TPB)"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',5,1),

-- FSRD02: 3 items — Perwalian
('FSRD02_SQ001','FSRD02[SQ001]','FSRD02',
 '{"id":"Pelaksanaan sistem perwalian tatap muka","en":"Face-to-face academic advising system implementation"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',1,1),
('FSRD02_SQ002','FSRD02[SQ002]','FSRD02',
 '{"id":"Pelaksanaan sistem perwalian online","en":"Online academic advising system implementation"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',2,1),
('FSRD02_SQ003','FSRD02[SQ003]','FSRD02',
 '{"id":"Bantuan dan respon dosen wali terkait permasalahan akademik","en":"Academic advisor assistance and response regarding academic problems"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',3,1),

-- FSRD03: 6 items — Mata Kuliah Teori
('FSRD03_SQ001','FSRD03[SQ001]','FSRD03',
 '{"id":"Pemahaman tentang sejarah Seni, Kria atau Desain","en":"Understanding of the history of Art, Craft, or Design"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',1,1),
('FSRD03_SQ002','FSRD03[SQ002]','FSRD03',
 '{"id":"Pemahaman tentang perkembangan Seni, Kria atau Desain di Indonesia","en":"Understanding of Art, Craft, or Design development in Indonesia"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',2,1),
('FSRD03_SQ003','FSRD03[SQ003]','FSRD03',
 '{"id":"Pemahaman tentang perkembangan Seni, Kria atau Desain di Dunia","en":"Understanding of global Art, Craft, or Design development"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',3,1),
('FSRD03_SQ004','FSRD03[SQ004]','FSRD03',
 '{"id":"Penguasaan metoda dan prosedur penciptaan/perancangan","en":"Mastery of creative/design methods and procedures"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',4,1),
('FSRD03_SQ005','FSRD03[SQ005]','FSRD03',
 '{"id":"Penguasaan kemampuan analisis-kritis sebuah karya Seni, Kria atau Desain","en":"Mastery of critical analysis of an Art, Craft, or Design work"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',5,1),
('FSRD03_SQ006','FSRD03[SQ006]','FSRD03',
 '{"id":"Kesesuaian antara jumlah SKS dengan jumlah dan materi tugas","en":"Alignment between credit units and the volume and content of assignments"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',6,1),

-- FSRD04: 6 items — Mata Kuliah Praktika (Studio)
('FSRD04_SQ001','FSRD04[SQ001]','FSRD04',
 '{"id":"Pemahaman teknik penciptaan/perancangan karya","en":"Understanding of creative/design work techniques"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',1,1),
('FSRD04_SQ002','FSRD04[SQ002]','FSRD04',
 '{"id":"Penguasaan wawasan estetik dan kaitannya dengan proses penciptaan/perancangan","en":"Mastery of aesthetic understanding and its relation to the creative/design process"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',2,1),
('FSRD04_SQ003','FSRD04[SQ003]','FSRD04',
 '{"id":"Kesesuaian antara jumlah SKS dengan jumlah dan materi tugas praktika","en":"Alignment between credit units and volume and content of studio assignments"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',3,1),
('FSRD04_SQ004','FSRD04[SQ004]','FSRD04',
 '{"id":"Proses asistensi/pembimbingan yang memadai dan mengakomodir penciptaan/perancangan","en":"Adequate tutoring/mentoring process accommodating creative/design work"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',4,1),
('FSRD04_SQ005','FSRD04[SQ005]','FSRD04',
 '{"id":"Kesesuaian antara proses dan hasil penilaian kualitas karya","en":"Alignment between the assessment process and quality outcomes of creative work"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',5,1),
('FSRD04_SQ006','FSRD04[SQ006]','FSRD04',
 '{"id":"Kesesuaian pengetahuan yang diperoleh semasa studi dengan aplikasinya pada kerja profesi/pemagangan","en":"Alignment between knowledge gained during study and its application in professional work/internship"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',6,1),

-- FSRD05: 4 items — Tugas Akhir
('FSRD05_SQ001','FSRD05[SQ001]','FSRD05',
 '{"id":"Pengetahuan teoritikal dan praktika yang diperoleh menunjang pelaksanaan tugas akhir","en":"Theoretical and practical knowledge supports final project execution"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',1,1),
('FSRD05_SQ002','FSRD05[SQ002]','FSRD05',
 '{"id":"Proses asistensi/pembimbingan yang diberikan selama menjalani tugas akhir","en":"Tutoring/supervision process during the final project"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',2,1),
('FSRD05_SQ003','FSRD05[SQ003]','FSRD05',
 '{"id":"Ketersediaan sarana dan prasarana untuk menunjang pelaksanaan tugas akhir","en":"Availability of facilities to support final project execution"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',3,1),
('FSRD05_SQ004','FSRD05[SQ004]','FSRD05',
 '{"id":"Ketersediaan buku dan sumber literatur di perpustakaan yang menunjang tugas akhir","en":"Availability of books and literature sources in the library to support the final project"}',
 'S5_EXPECT_FSRD','{"fakultas":["FSRD"]}',4,1),

-- Section K: SBM khusus (31 items valid, SQ032 dieksklusi, S5_DEVELOP_SBM)
('SBM01_SQ001','SBM01[SQ001]','SBM01',
 '{"id":"Kemampuan berkomunikasi secara lisan","en":"Ability to communicate orally"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',1,1),
('SBM01_SQ002','SBM01[SQ002]','SBM01',
 '{"id":"Kemampuan berkomunikasi dalam tulisan","en":"Ability to communicate in writing"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',2,1),
('SBM01_SQ003','SBM01[SQ003]','SBM01',
 '{"id":"Kemampuan menggunakan pengetahuan marketing","en":"Ability to apply knowledge of marketing"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',3,1),
('SBM01_SQ004','SBM01[SQ004]','SBM01',
 '{"id":"Kemampuan menggunakan pengetahuan manajemen operasi","en":"Ability to apply knowledge of operation management"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',4,1),
('SBM01_SQ005','SBM01[SQ005]','SBM01',
 '{"id":"Kemampuan menggunakan pengetahuan manajemen sumber daya manusia","en":"Ability to apply knowledge of Human Resources Management"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',5,1),
('SBM01_SQ006','SBM01[SQ006]','SBM01',
 '{"id":"Kemampuan menggunakan pengetahuan keuangan","en":"Ability to apply knowledge of Finance"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',6,1),
('SBM01_SQ007','SBM01[SQ007]','SBM01',
 '{"id":"Kemampuan menggunakan pengetahuan Pengambilan Keputusan dan Negosiasi","en":"Ability to apply knowledge of Decision Making and Negotiation"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',7,1),
('SBM01_SQ008','SBM01[SQ008]','SBM01',
 '{"id":"Kemampuan menggunakan pengetahuan kewirausahaan","en":"Ability to apply knowledge of entrepreneurship"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',8,1),
('SBM01_SQ009','SBM01[SQ009]','SBM01',
 '{"id":"Kemampuan untuk tampil di depan publik/penonton","en":"Ability to perform in front of the public/audience"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',9,1),
('SBM01_SQ010','SBM01[SQ010]','SBM01',
 '{"id":"Pengetahuan yang mendalam pada sekurangnya satu konsentrasi","en":"Depth of knowledge in at least one concentration"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',10,1),
('SBM01_SQ011','SBM01[SQ011]','SBM01',
 '{"id":"Pengetahuan tentang probabilitas dan statistik termasuk aplikasinya dalam menganalisis data dalam tugas akhir","en":"Knowledge of probability and statistics including applications to data analysis in Final Project"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',11,1),
('SBM01_SQ012','SBM01[SQ012]','SBM01',
 '{"id":"Kemampuan untuk menginterpretasi data","en":"Ability to interpret data"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',12,1),
('SBM01_SQ013','SBM01[SQ013]','SBM01',
 '{"id":"Kemampuan mengidentifikasi masalah","en":"Ability to identify problems"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',13,1),
('SBM01_SQ014','SBM01[SQ014]','SBM01',
 '{"id":"Kemampuan menyelesaikan masalah","en":"Ability to solve problems"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',14,1),
('SBM01_SQ015','SBM01[SQ015]','SBM01',
 '{"id":"Kemampuan melakukan riset bisnis","en":"Ability to conduct business research"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',15,1),
('SBM01_SQ016','SBM01[SQ016]','SBM01',
 '{"id":"Kemampuan menggunakan internet untuk memperoleh dan berbagi informasi/pengetahuan","en":"Ability to use internet for information/knowledge acquisition and sharing"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',16,1),
('SBM01_SQ017','SBM01[SQ017]','SBM01',
 '{"id":"Kemampuan untuk membangun jejaring","en":"Ability to build networks"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',17,1),
('SBM01_SQ018','SBM01[SQ018]','SBM01',
 '{"id":"Kemampuan untuk mendirikan usaha baru","en":"Ability to establish a new business"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',18,1),
('SBM01_SQ019','SBM01[SQ019]','SBM01',
 '{"id":"Kemampuan bekerjasama dalam tim","en":"Ability to work in teams"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',19,1),
('SBM01_SQ020','SBM01[SQ020]','SBM01',
 '{"id":"Kemampuan mengidentifikasi peluang bisnis","en":"Ability to identify business opportunities"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',20,1),
('SBM01_SQ021','SBM01[SQ021]','SBM01',
 '{"id":"Kemampuan mengidentifikasi peluang untuk meningkatkan/memperbaiki kondisi suatu komunitas","en":"Ability to identify opportunities for improving community conditions"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',21,1),
('SBM01_SQ022','SBM01[SQ022]','SBM01',
 '{"id":"Kemampuan untuk merancang dan menciptakan produk baru","en":"Ability to design or create a new product"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',22,1),
('SBM01_SQ023','SBM01[SQ023]','SBM01',
 '{"id":"Kemampuan beradaptasi dalam kendala sosial","en":"Ability to adapt within social constraints"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',23,1),
('SBM01_SQ024','SBM01[SQ024]','SBM01',
 '{"id":"Kemampuan bekerja/belajar dalam kendala sumberdaya","en":"Ability to work/study within resources constraints"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',24,1),
('SBM01_SQ025','SBM01[SQ025]','SBM01',
 '{"id":"Kemampuan bekerja/belajar dalam kendala etika","en":"Ability to work/study within ethical constraints"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',25,1),
('SBM01_SQ026','SBM01[SQ026]','SBM01',
 '{"id":"Kemampuan bekerja/belajar dalam kendala kesehatan dan keamanan","en":"Ability to work/study within health and safety constraints"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',26,1),
('SBM01_SQ027','SBM01[SQ027]','SBM01',
 '{"id":"Memahami tanggung jawab profesional","en":"Understanding of professional responsibility"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',27,1),
('SBM01_SQ028','SBM01[SQ028]','SBM01',
 '{"id":"Memahami tanggung jawab etis","en":"Understanding of ethical responsibility"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',28,1),
('SBM01_SQ029','SBM01[SQ029]','SBM01',
 '{"id":"Pengakuan perlunya belajar seumur hidup","en":"Recognition of the need for life-long learning"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',29,1),
('SBM01_SQ030','SBM01[SQ030]','SBM01',
 '{"id":"Kemampuan untuk terlibat dalam pembelajaran seumur hidup","en":"Ability to engage in life-long learning"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',30,1),
('SBM01_SQ031','SBM01[SQ031]','SBM01',
 '{"id":"Pengetahuan pendukung untuk studi pasca sarjana","en":"Knowledge sufficiency to pursue further education/graduate study"}',
 'S5_DEVELOP_SBM','{"fakultas":["SBM"]}',31,1);
-- SBM01_SQ032 dieksklusi: label kosong di CSV, dikonfirmasi tidak valid


-- ============================================================
-- 3. TABEL RESPONS UTAMA
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
    kd_strata       CHAR(2)     NOT NULL
                        REFERENCES referensi.strata(kd_strata)
                        ON UPDATE CASCADE ON DELETE RESTRICT
                        DEFERRABLE INITIALLY DEFERRED,
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

    periode_ijazah_id INTEGER
                        REFERENCES wisuda.periode_ijazah(periode_ijazah_id)
                        ON UPDATE CASCADE ON DELETE RESTRICT
                        DEFERRABLE INITIALLY DEFERRED,
    -- NULLABLE — analisis 100% data (7535 baris):
    --   66.6% (5015 baris) NULL
    --   PR: 0% NULL, S1: 81.7% NULL, S2: 51.8% NULL, S3: 43.6% NULL
    --   NULL dan non-NULL coexist dalam bulan & fak yang sama
    --   Nilai non-NULL: integer YYYYMM (202502, 202504, 202507, 202509, 202602, 202604)

    -- ── Payload jawaban ────────────────────────────────────────
    jawaban         JSONB,
    -- key = kd_pertanyaan
    -- value:
    --   Ordinal Likert  → INTEGER (1–4 atau 1–5)
    --   Nominal         → INTEGER sesuai ref_opsi.nilai
    --   Free-text       → TEXT string
    --
    -- key 'U02_other' muncul ketika U02 = 7 ("Other"), value = TEXT bebas
    -- Hanya key yang dijawab yang ada di JSONB
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
    -- S101=1 → "Ya", S102=1 → "ITB", S103=1 → "Ya, kelanjutan...", U02=1 → "Kualitas dosen"

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
-- PROSES INGEST DARI CSV:
--   1. Ordinal Likert  : konversi teks → integer via ref_opsi.label (kd_set ordinal)
--   2. Nominal         : konversi teks → integer via ref_opsi.label (kd_set nominal)
--   3. Free-text       : simpan as-is sebagai TEXT
--   4. U02 = "Other"   : simpan {"U02": 7, "U02_other": "<teks bebas>"}
--   5. PR strata       : hanya isi Section A–D, Section G/H/I/J/K tidak berlaku
--
-- TEMPLATE.ENTRY:
--   ts_entry dan user_id_entry didefinisikan manual.
--   Jika INHERITS (template.entry) diputuskan bersama DSI ITB,
--   hapus kedua kolom dan attach trigger update_ts_entry ke setiap tabel.
--
-- PERBEDAAN SKALA D2 vs FSRD:
--   D2 (U07) nilai=4 → "Sepenuhnya memenuhi harapan" (S5_EXPECT)
--   FSRD     nilai=4 → "Memenuhi harapan"            (S5_EXPECT_FSRD)
--   Jangan campurkan skor D2 dan FSRD dalam satu aggregasi tanpa normalisasi.
-- ============================================================