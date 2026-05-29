-- ============================================================
-- MATERIALIZED VIEWS: evaluasi_wisudawan
-- Bergantung pada tabel di schema_evaluasi_wisudawan.sql
-- Jalankan setelah schema_evaluasi_wisudawan.sql berhasil dieksekusi
--
-- Arsitektur (3 MV, granularitas berbeda):
--
--   mv_distribusi_jawaban  ← base granular: 1 baris per
--                            (periode, strata, fak, pertanyaan, nilai)
--                            mencakup ordinal (tipe=O) dan nominal (tipe=N)
--                            → query top-2-box, incidence, distribusi
--
--   mv_skor_pertanyaan     ← aggregate: 1 baris per
--                            (periode, strata, fak, no_ps, pertanyaan)
--                            AVG, STDDEV, MIN, MAX — hanya ordinal (tipe=O)
--                            → dashboard chart rata-rata, ranking pertanyaan
--                            Dikembalikan sebagai MV (bukan VIEW) karena
--                            dashboard memerlukan pre-computed response cepat:
--                            Kimball (2013): aggregate table justified jika
--                            query berulang dengan pola sama oleh banyak user
--
--   mv_wide_respons        ← 1 baris per responden, semua jawaban sebagai
--                            kolom — analisis individual & Text-to-SQL
--
-- Kedua MV (distribusi & skor) tidak digabung karena granularitas berbeda:
--   distribusi: per (dimensi, pertanyaan, nilai) — shape untuk bar chart
--   skor      : per (dimensi, pertanyaan)        — shape untuk line/rank chart
--   Menggabungkan keduanya menghasilkan redundansi data (Kimball, 2013)
--   atau kehilangan fleksibilitas query (JSONB distribution)
--
-- Refresh semua setelah setiap batch import:
--   REFRESH MATERIALIZED VIEW CONCURRENTLY evaluasi_wisudawan.mv_distribusi_jawaban;
--   REFRESH MATERIALIZED VIEW CONCURRENTLY evaluasi_wisudawan.mv_skor_pertanyaan;
--   REFRESH MATERIALIZED VIEW CONCURRENTLY evaluasi_wisudawan.mv_wide_respons;
-- ============================================================


-- ============================================================
-- 1. mv_distribusi_jawaban
--    BASE granular MV — single source of truth untuk semua agregasi
--    Satu baris per (periode_ijazah_id, kd_strata, kd_fak,
--                    kd_pertanyaan, nilai)
--    Mencakup ordinal (tipe=O) DAN nominal (tipe=N)
--    Free-text (kd_set_opsi IS NULL) otomatis excluded via JOIN
--
--    Query dashboard yang bisa diturunkan dari MV ini:
--
--    % setuju (nilai >= 3) Section A per fak:
--      SELECT kd_fak, kd_pertanyaan,
--             SUM(n) FILTER (WHERE nilai >= 3) * 100.0 / SUM(n) AS pct_setuju
--      FROM evaluasi_wisudawan.mv_distribusi_jawaban
--      WHERE kd_set_opsi = 'S4_AGREE'
--      GROUP BY kd_fak, kd_pertanyaan;
--
--    % pernah mengalami masalah (nilai >= 2) Section D1:
--      SELECT kd_pertanyaan,
--             SUM(n) FILTER (WHERE nilai >= 2) * 100.0 / SUM(n) AS pct_pernah
--      FROM evaluasi_wisudawan.mv_distribusi_jawaban
--      WHERE kd_set_opsi = 'S4_FREQ'
--      GROUP BY kd_pertanyaan;
--
--    Distribusi pilihan rekomendasi prodi (U02, nominal):
--      SELECT d.nilai, o.label->>'id' AS pilihan, d.n, d.pct
--      FROM evaluasi_wisudawan.mv_distribusi_jawaban d
--      JOIN evaluasi_wisudawan.ref_opsi o
--          ON o.kd_set = d.kd_set_opsi AND o.nilai = d.nilai
--      WHERE d.kd_pertanyaan = 'U02'
--      ORDER BY d.nilai;
-- ============================================================

CREATE MATERIALIZED VIEW evaluasi_wisudawan.mv_distribusi_jawaban AS
SELECT
    r.periode_ijazah_id,
    r.kd_strata,
    r.kd_fak,
    r.no_ps,
    p.kd_pertanyaan,
    p.kd_grup,
    p.kd_set_opsi,
    s.tipe                                             AS tipe_opsi,
    -- O = ordinal Likert (nilai bermakna aritmetika)
    -- N = nominal kategoris (nilai hanya kode urut)
    (r.jawaban ->> p.kd_pertanyaan)::SMALLINT          AS nilai,
    COUNT(*)                                           AS n,
    ROUND(
        COUNT(*) * 100.0
        / SUM(COUNT(*)) OVER (
            PARTITION BY
                r.periode_ijazah_id,
                r.kd_strata,
                r.kd_fak,
                r.no_ps,
                p.kd_pertanyaan
        ),
        2
    )                                                  AS pct
FROM evaluasi_wisudawan.respons r
JOIN evaluasi_wisudawan.pertanyaan p
    ON r.jawaban ? p.kd_pertanyaan
JOIN evaluasi_wisudawan.ref_set_opsi s
    ON p.kd_set_opsi = s.kd_set
-- JOIN ke ref_set_opsi secara implisit exclude free-text
-- karena pertanyaan free-text punya kd_set_opsi = NULL
WHERE
    p.batasan IS NULL
    OR (p.batasan -> 'strata'   @> to_jsonb(r.kd_strata::TEXT))
    OR (p.batasan -> 'fakultas' @> to_jsonb(r.kd_fak::TEXT))
GROUP BY
    r.periode_ijazah_id,
    r.kd_strata,
    r.kd_fak,
    r.no_ps,
    p.kd_pertanyaan,
    p.kd_grup,
    p.kd_set_opsi,
    s.tipe,
    (r.jawaban ->> p.kd_pertanyaan)::SMALLINT
WITH DATA;

CREATE UNIQUE INDEX ON evaluasi_wisudawan.mv_distribusi_jawaban
    (periode_ijazah_id, kd_strata, kd_fak, no_ps, kd_pertanyaan, nilai);
-- UNIQUE INDEX wajib untuk REFRESH CONCURRENTLY

CREATE INDEX ON evaluasi_wisudawan.mv_distribusi_jawaban (kd_set_opsi, nilai);
CREATE INDEX ON evaluasi_wisudawan.mv_distribusi_jawaban (kd_grup);
CREATE INDEX ON evaluasi_wisudawan.mv_distribusi_jawaban (tipe_opsi);
CREATE INDEX ON evaluasi_wisudawan.mv_distribusi_jawaban (kd_strata, kd_fak);
CREATE INDEX ON evaluasi_wisudawan.mv_distribusi_jawaban (no_ps);
CREATE INDEX ON evaluasi_wisudawan.mv_distribusi_jawaban (kd_strata, kd_fak, no_ps);


-- ============================================================
-- 2. mv_skor_pertanyaan
--    AVG, STDDEV, MIN, MAX per pertanyaan ordinal
--    Satu baris per (periode_ijazah_id, kd_strata, kd_fak,
--                    no_ps, kd_pertanyaan)
--    Hanya tipe='O' (ordinal) — nominal tidak boleh di-AVG
--
--    Dijadikan MV (bukan VIEW) karena dipakai oleh dashboard:
--    query berulang dengan pola sama oleh banyak user secara
--    bersamaan — pre-computed lebih efisien dari on-the-fly
--    (Kimball, 2013: aggregate table justified untuk repeated
--    queries with identical inputs)
-- ============================================================

CREATE MATERIALIZED VIEW evaluasi_wisudawan.mv_skor_pertanyaan AS
SELECT
    r.periode_ijazah_id,
    r.kd_strata,
    r.kd_fak,
    r.no_ps,
    p.kd_pertanyaan,
    p.kd_grup,
    p.kd_set_opsi,
    COUNT(*)                                             AS n_responden,
    ROUND(
        AVG((r.jawaban ->> p.kd_pertanyaan)::NUMERIC),
        4
    )                                                    AS rata_rata,
    ROUND(
        STDDEV((r.jawaban ->> p.kd_pertanyaan)::NUMERIC),
        4
    )                                                    AS std_dev,
    MIN((r.jawaban ->> p.kd_pertanyaan)::NUMERIC)        AS skor_min,
    MAX((r.jawaban ->> p.kd_pertanyaan)::NUMERIC)        AS skor_max
FROM evaluasi_wisudawan.respons r
JOIN evaluasi_wisudawan.pertanyaan p
    ON r.jawaban ? p.kd_pertanyaan
JOIN evaluasi_wisudawan.ref_set_opsi s
    ON p.kd_set_opsi = s.kd_set
WHERE
    s.tipe = 'O'
    AND (
        p.batasan IS NULL
        OR (p.batasan -> 'strata'   @> to_jsonb(r.kd_strata::TEXT))
        OR (p.batasan -> 'fakultas' @> to_jsonb(r.kd_fak::TEXT))
    )
GROUP BY
    r.periode_ijazah_id,
    r.kd_strata,
    r.kd_fak,
    r.no_ps,
    p.kd_pertanyaan,
    p.kd_grup,
    p.kd_set_opsi
WITH DATA;

CREATE UNIQUE INDEX ON evaluasi_wisudawan.mv_skor_pertanyaan
    (periode_ijazah_id, kd_strata, kd_fak, no_ps, kd_pertanyaan);
-- UNIQUE INDEX wajib untuk REFRESH CONCURRENTLY

CREATE INDEX ON evaluasi_wisudawan.mv_skor_pertanyaan (kd_grup);
CREATE INDEX ON evaluasi_wisudawan.mv_skor_pertanyaan (kd_strata, kd_fak);


-- ============================================================
-- 3. mv_wide_respons
--    Satu baris per responden, semua jawaban sebagai kolom.
--    Ordinal  → SMALLINT (integer 1–4 atau 1–5)
--    Nominal  → SMALLINT (integer sesuai ref_opsi.nilai)
--    Free-text → TEXT
--    NULL pada kolom section-specific = pertanyaan tidak berlaku
--    untuk responden tersebut (natural dari JSONB, bukan missing data)
-- ============================================================

CREATE MATERIALIZED VIEW evaluasi_wisudawan.mv_wide_respons AS
SELECT
    -- Identitas & demografi
    r.response_id,
    r.survey_platform_response_id,
    r.kd_strata,
    r.kd_fak,
    r.no_ps,
    r.periode_ijazah_id,
    r.submit_date,

    -- ── Section A: Fasilitas & Kepuasan ITB (U03, S4_AGREE) ──
    (r.jawaban->>'U03_SQ001')::SMALLINT  AS u03_sq001,
    (r.jawaban->>'U03_SQ002')::SMALLINT  AS u03_sq002,
    (r.jawaban->>'U03_SQ003')::SMALLINT  AS u03_sq003,
    (r.jawaban->>'U03_SQ004')::SMALLINT  AS u03_sq004,
    (r.jawaban->>'U03_SQ005')::SMALLINT  AS u03_sq005,
    (r.jawaban->>'U03_SQ006')::SMALLINT  AS u03_sq006,
    (r.jawaban->>'U03_SQ007')::SMALLINT  AS u03_sq007,
    (r.jawaban->>'U03_SQ008')::SMALLINT  AS u03_sq008,
    (r.jawaban->>'U03_SQ009')::SMALLINT  AS u03_sq009,
    (r.jawaban->>'U03_SQ010')::SMALLINT  AS u03_sq010,
    (r.jawaban->>'U03_SQ011')::SMALLINT  AS u03_sq011,
    (r.jawaban->>'U03_SQ012')::SMALLINT  AS u03_sq012,

    -- ── Section B: Pendidikan di Prodi (U01, S4_AGREE) ───────
    (r.jawaban->>'U01_SQ001')::SMALLINT  AS u01_sq001,
    (r.jawaban->>'U01_SQ002')::SMALLINT  AS u01_sq002,
    (r.jawaban->>'U01_SQ003')::SMALLINT  AS u01_sq003,
    (r.jawaban->>'U01_SQ004')::SMALLINT  AS u01_sq004,
    (r.jawaban->>'U01_SQ005')::SMALLINT  AS u01_sq005,
    (r.jawaban->>'U01_SQ006')::SMALLINT  AS u01_sq006,
    (r.jawaban->>'U01_SQ007')::SMALLINT  AS u01_sq007,
    (r.jawaban->>'U01_SQ008')::SMALLINT  AS u01_sq008,
    (r.jawaban->>'U01_SQ009')::SMALLINT  AS u01_sq009,
    (r.jawaban->>'U01_SQ010')::SMALLINT  AS u01_sq010,
    (r.jawaban->>'U01_SQ011')::SMALLINT  AS u01_sq011,
    (r.jawaban->>'U01_SQ012')::SMALLINT  AS u01_sq012,
    (r.jawaban->>'U02')::SMALLINT        AS u02,
    r.jawaban->>'U02_other'              AS u02_other,

    -- ── Section C1: Softskills (U04, S4_AGREE) ───────────────
    (r.jawaban->>'U04_SQ001')::SMALLINT  AS u04_sq001,
    (r.jawaban->>'U04_SQ002')::SMALLINT  AS u04_sq002,
    (r.jawaban->>'U04_SQ003')::SMALLINT  AS u04_sq003,
    (r.jawaban->>'U04_SQ004')::SMALLINT  AS u04_sq004,
    (r.jawaban->>'U04_SQ005')::SMALLINT  AS u04_sq005,
    (r.jawaban->>'U04_SQ006')::SMALLINT  AS u04_sq006,
    (r.jawaban->>'U04_SQ007')::SMALLINT  AS u04_sq007,
    (r.jawaban->>'U04_SQ008')::SMALLINT  AS u04_sq008,
    (r.jawaban->>'U04_SQ009')::SMALLINT  AS u04_sq009,

    -- ── Section C2: Karakter (U05, S4_AGREE) ─────────────────
    (r.jawaban->>'U05_SQ001')::SMALLINT  AS u05_sq001,
    (r.jawaban->>'U05_SQ002')::SMALLINT  AS u05_sq002,
    (r.jawaban->>'U05_SQ003')::SMALLINT  AS u05_sq003,
    (r.jawaban->>'U05_SQ004')::SMALLINT  AS u05_sq004,
    (r.jawaban->>'U05_SQ005')::SMALLINT  AS u05_sq005,
    (r.jawaban->>'U05_SQ006')::SMALLINT  AS u05_sq006,
    (r.jawaban->>'U05_SQ007')::SMALLINT  AS u05_sq007,

    -- ── Section D1: Permasalahan Studi (U06, S4_FREQ) ────────
    (r.jawaban->>'U06_SQ001')::SMALLINT  AS u06_sq001,
    (r.jawaban->>'U06_SQ002')::SMALLINT  AS u06_sq002,
    (r.jawaban->>'U06_SQ003')::SMALLINT  AS u06_sq003,
    (r.jawaban->>'U06_SQ004')::SMALLINT  AS u06_sq004,
    (r.jawaban->>'U06_SQ005')::SMALLINT  AS u06_sq005,
    (r.jawaban->>'U06_SQ006')::SMALLINT  AS u06_sq006,
    (r.jawaban->>'U06_SQ007')::SMALLINT  AS u06_sq007,
    (r.jawaban->>'U06_SQ008')::SMALLINT  AS u06_sq008,
    (r.jawaban->>'U06_SQ009')::SMALLINT  AS u06_sq009,

    -- ── Section D2: Ketersediaan Dukungan (U07, S5_EXPECT) ───
    (r.jawaban->>'U07_SQ001')::SMALLINT  AS u07_sq001,
    (r.jawaban->>'U07_SQ002')::SMALLINT  AS u07_sq002,
    (r.jawaban->>'U07_SQ003')::SMALLINT  AS u07_sq003,
    (r.jawaban->>'U07_SQ004')::SMALLINT  AS u07_sq004,

    -- ── Section E: Free-text (universal) ──────────────────────
    r.jawaban->>'G10Q22'  AS g10q22,
    r.jawaban->>'G01Q23'  AS g01q23,
    r.jawaban->>'G01Q24'  AS g01q24,
    r.jawaban->>'G01Q25'  AS g01q25,
    r.jawaban->>'G01Q26'  AS g01q26,
    r.jawaban->>'G01Q27'  AS g01q27,
    r.jawaban->>'G01Q28'  AS g01q28,
    r.jawaban->>'G01Q29'  AS g01q29,

    -- ── Section F: Free-text (universal) ──────────────────────
    r.jawaban->>'G11Q30'  AS g11q30,
    r.jawaban->>'G01Q31'  AS g01q31,
    r.jawaban->>'G01Q32'  AS g01q32,
    r.jawaban->>'G01Q33'  AS g01q33,
    r.jawaban->>'G01Q34'  AS g01q34,
    r.jawaban->>'G01Q35'  AS g01q35,

    -- ── Section G: S1 khusus (NULL untuk strata lain) ────────
    (r.jawaban->>'S101')::SMALLINT       AS s101,
    (r.jawaban->>'S102')::SMALLINT       AS s102,
    (r.jawaban->>'S103')::SMALLINT       AS s103,
    (r.jawaban->>'S104_SQ001')::SMALLINT AS s104_sq001,
    (r.jawaban->>'S104_SQ002')::SMALLINT AS s104_sq002,
    (r.jawaban->>'S104_SQ003')::SMALLINT AS s104_sq003,
    (r.jawaban->>'S104_SQ004')::SMALLINT AS s104_sq004,

    -- ── Section H: S2 khusus (NULL untuk strata lain) ────────
    (r.jawaban->>'M01')::SMALLINT        AS m01,
    (r.jawaban->>'M02')::SMALLINT        AS m02,
    (r.jawaban->>'M03')::SMALLINT        AS m03,

    -- ── Section I: S3 khusus (NULL untuk strata lain) ────────
    (r.jawaban->>'D01_SQ001')::SMALLINT  AS d01_sq001,
    (r.jawaban->>'D01_SQ002')::SMALLINT  AS d01_sq002,
    (r.jawaban->>'D01_SQ003')::SMALLINT  AS d01_sq003,
    (r.jawaban->>'D01_SQ004')::SMALLINT  AS d01_sq004,

    -- ── Section J: FSRD khusus (NULL untuk fak lain) ─────────
    (r.jawaban->>'FSRD01_SQ001')::SMALLINT AS fsrd01_sq001,
    (r.jawaban->>'FSRD01_SQ002')::SMALLINT AS fsrd01_sq002,
    (r.jawaban->>'FSRD01_SQ003')::SMALLINT AS fsrd01_sq003,
    (r.jawaban->>'FSRD01_SQ004')::SMALLINT AS fsrd01_sq004,
    (r.jawaban->>'FSRD01_SQ005')::SMALLINT AS fsrd01_sq005,
    (r.jawaban->>'FSRD02_SQ001')::SMALLINT AS fsrd02_sq001,
    (r.jawaban->>'FSRD02_SQ002')::SMALLINT AS fsrd02_sq002,
    (r.jawaban->>'FSRD02_SQ003')::SMALLINT AS fsrd02_sq003,
    (r.jawaban->>'FSRD03_SQ001')::SMALLINT AS fsrd03_sq001,
    (r.jawaban->>'FSRD03_SQ002')::SMALLINT AS fsrd03_sq002,
    (r.jawaban->>'FSRD03_SQ003')::SMALLINT AS fsrd03_sq003,
    (r.jawaban->>'FSRD03_SQ004')::SMALLINT AS fsrd03_sq004,
    (r.jawaban->>'FSRD03_SQ005')::SMALLINT AS fsrd03_sq005,
    (r.jawaban->>'FSRD03_SQ006')::SMALLINT AS fsrd03_sq006,
    (r.jawaban->>'FSRD04_SQ001')::SMALLINT AS fsrd04_sq001,
    (r.jawaban->>'FSRD04_SQ002')::SMALLINT AS fsrd04_sq002,
    (r.jawaban->>'FSRD04_SQ003')::SMALLINT AS fsrd04_sq003,
    (r.jawaban->>'FSRD04_SQ004')::SMALLINT AS fsrd04_sq004,
    (r.jawaban->>'FSRD04_SQ005')::SMALLINT AS fsrd04_sq005,
    (r.jawaban->>'FSRD04_SQ006')::SMALLINT AS fsrd04_sq006,
    (r.jawaban->>'FSRD05_SQ001')::SMALLINT AS fsrd05_sq001,
    (r.jawaban->>'FSRD05_SQ002')::SMALLINT AS fsrd05_sq002,
    (r.jawaban->>'FSRD05_SQ003')::SMALLINT AS fsrd05_sq003,
    (r.jawaban->>'FSRD05_SQ004')::SMALLINT AS fsrd05_sq004,

    -- ── Section K: SBM khusus (NULL untuk fak lain) ──────────
    (r.jawaban->>'SBM01_SQ001')::SMALLINT AS sbm01_sq001,
    (r.jawaban->>'SBM01_SQ002')::SMALLINT AS sbm01_sq002,
    (r.jawaban->>'SBM01_SQ003')::SMALLINT AS sbm01_sq003,
    (r.jawaban->>'SBM01_SQ004')::SMALLINT AS sbm01_sq004,
    (r.jawaban->>'SBM01_SQ005')::SMALLINT AS sbm01_sq005,
    (r.jawaban->>'SBM01_SQ006')::SMALLINT AS sbm01_sq006,
    (r.jawaban->>'SBM01_SQ007')::SMALLINT AS sbm01_sq007,
    (r.jawaban->>'SBM01_SQ008')::SMALLINT AS sbm01_sq008,
    (r.jawaban->>'SBM01_SQ009')::SMALLINT AS sbm01_sq009,
    (r.jawaban->>'SBM01_SQ010')::SMALLINT AS sbm01_sq010,
    (r.jawaban->>'SBM01_SQ011')::SMALLINT AS sbm01_sq011,
    (r.jawaban->>'SBM01_SQ012')::SMALLINT AS sbm01_sq012,
    (r.jawaban->>'SBM01_SQ013')::SMALLINT AS sbm01_sq013,
    (r.jawaban->>'SBM01_SQ014')::SMALLINT AS sbm01_sq014,
    (r.jawaban->>'SBM01_SQ015')::SMALLINT AS sbm01_sq015,
    (r.jawaban->>'SBM01_SQ016')::SMALLINT AS sbm01_sq016,
    (r.jawaban->>'SBM01_SQ017')::SMALLINT AS sbm01_sq017,
    (r.jawaban->>'SBM01_SQ018')::SMALLINT AS sbm01_sq018,
    (r.jawaban->>'SBM01_SQ019')::SMALLINT AS sbm01_sq019,
    (r.jawaban->>'SBM01_SQ020')::SMALLINT AS sbm01_sq020,
    (r.jawaban->>'SBM01_SQ021')::SMALLINT AS sbm01_sq021,
    (r.jawaban->>'SBM01_SQ022')::SMALLINT AS sbm01_sq022,
    (r.jawaban->>'SBM01_SQ023')::SMALLINT AS sbm01_sq023,
    (r.jawaban->>'SBM01_SQ024')::SMALLINT AS sbm01_sq024,
    (r.jawaban->>'SBM01_SQ025')::SMALLINT AS sbm01_sq025,
    (r.jawaban->>'SBM01_SQ026')::SMALLINT AS sbm01_sq026,
    (r.jawaban->>'SBM01_SQ027')::SMALLINT AS sbm01_sq027,
    (r.jawaban->>'SBM01_SQ028')::SMALLINT AS sbm01_sq028,
    (r.jawaban->>'SBM01_SQ029')::SMALLINT AS sbm01_sq029,
    (r.jawaban->>'SBM01_SQ030')::SMALLINT AS sbm01_sq030,
    (r.jawaban->>'SBM01_SQ031')::SMALLINT AS sbm01_sq031

FROM evaluasi_wisudawan.respons r
WITH DATA;

CREATE UNIQUE INDEX ON evaluasi_wisudawan.mv_wide_respons (response_id);
CREATE INDEX ON evaluasi_wisudawan.mv_wide_respons (kd_strata);
CREATE INDEX ON evaluasi_wisudawan.mv_wide_respons (kd_fak);
CREATE INDEX ON evaluasi_wisudawan.mv_wide_respons (periode_ijazah_id);
CREATE INDEX ON evaluasi_wisudawan.mv_wide_respons (kd_strata, kd_fak);

COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.response_id IS 'Surrogate primary key internal database';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.survey_platform_response_id IS 'ID response asli dari LimeSurvey (bisa NULL jika tidak tercatat)';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.kd_strata IS 'Jenjang pendidikan: S1=Sarjana, S2=Magister, S3=Doktor, PR=Profesi (71)';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.kd_fak IS 'Kode fakultas/sekolah, contoh: STEI, SBM, FSRD, FMIPA, FTSL, dst. FK ke utama.fakultas';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.no_ps IS 'Kode numerik program studi, contoh: 135=Teknik Informatika S1, 290=Manajemen SBM. FK ke utama.program_studi';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.periode_ijazah_id IS 'Periode wisuda format YYYYMM, contoh: 202502=Februari 2025. FK ke wisuda.periode_ijazah';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.submit_date IS 'Timestamp pengisian kuesioner oleh wisudawan';

-- Section A: Fasilitas & Kepuasan ITB (U03)
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u03_sq001 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Tersedia cukup ruang kelas';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u03_sq002 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Ruang kelas kondusif untuk pembelajaran';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u03_sq003 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Laboratorium kondusif untuk pembelajaran';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u03_sq004 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Akses internet memadai';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u03_sq005 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Fasilitas keprofesian memadai';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u03_sq006 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Akses perpustakaan memadai';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u03_sq007 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Perangkat pembelajaran up-to-date';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u03_sq008 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Fasilitas toilet memadai';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u03_sq009 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Fasilitas kantin memadai';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u03_sq010 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Fasilitas rekreasi/olahraga memadai';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u03_sq011 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Fasilitas kesehatan memadai';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u03_sq012 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Secara keseluruhan saya puas dengan fasilitas ITB';

-- Section B: Pendidikan di Prodi (U01 + U02)
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u01_sq001 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Wali akademik selalu tersedia saat dibutuhkan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u01_sq002 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Wali akademik membantu memenuhi persyaratan akademik';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u01_sq003 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Dosen berinteraksi secara informal dengan mahasiswa';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u01_sq004 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Dosen memperhatikan proses pembelajaran mahasiswa';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u01_sq005 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Dosen memiliki kemampuan profesional yang baik';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u01_sq006 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Matakuliah wajib memberikan dasar yang baik';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u01_sq007 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Matakuliah pilihan memberikan keleluasaan eksplorasi';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u01_sq008 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Praktikum sejalan dengan teori di kelas';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u01_sq009 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Sarana program studi memadai';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u01_sq010 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Program studi memberikan gambaran dunia kerja';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u01_sq011 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Saya menikmati bidang studi saya';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u01_sq012 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Saya akan memilih program studi yang sama lagi';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u02 IS 'Section B (U02) | Aspek yang paling Anda tonjolkan dalam merekomendasikan prodi | Populasi: semua | Nominal (OPT_U02): 1=Kualitas dosen · 2=Suasana akademik · 3=Jejaring alumni · 4=Lapangan pekerjaan · 5=Fasilitas akademik · 6=Tidak merekomendasikan · 7=Other';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u02_other IS 'Section B (U02) | Teks bebas jika u02=7 (Other). NULL jika u02 bukan 7';

-- Section C1: Softskills (U04)
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u04_sq001 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan komunikasi lisan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u04_sq002 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan komunikasi tertulis';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u04_sq003 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan berbahasa asing';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u04_sq004 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan penyelesaian masalah';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u04_sq005 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan berpikir kritis';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u04_sq006 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan introspeksi diri';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u04_sq007 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan menyampaikan pendapat';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u04_sq008 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan kerja tim';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u04_sq009 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan kerja mandiri';

-- Section C2: Karakter (U05)
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u05_sq001 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kejujuran';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u05_sq002 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Komitmen';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u05_sq003 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kecerdasan emosi';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u05_sq004 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kepedulian terhadap sesama';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u05_sq005 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Objektivitas';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u05_sq006 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Ketidakmudahan menyerah (Perseverance)';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u05_sq007 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kepatuhan terhadap aturan';

-- Section D1: Permasalahan Studi (U06)
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u06_sq001 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah · 2=Jarang · 3=Sering · 4=Selalu | nilai≥2 berarti pernah mengalami | Pertanyaan: Permasalahan akademis';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u06_sq002 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah · 2=Jarang · 3=Sering · 4=Selalu | nilai≥2 berarti pernah mengalami | Pertanyaan: Permasalahan keuangan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u06_sq003 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah · 2=Jarang · 3=Sering · 4=Selalu | nilai≥2 berarti pernah mengalami | Pertanyaan: Pengaruh keuangan terhadap akademis';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u06_sq004 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah · 2=Jarang · 3=Sering · 4=Selalu | nilai≥2 berarti pernah mengalami | Pertanyaan: Permasalahan psikologis';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u06_sq005 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah · 2=Jarang · 3=Sering · 4=Selalu | nilai≥2 berarti pernah mengalami | Pertanyaan: Pengaruh psikologis terhadap studi';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u06_sq006 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah · 2=Jarang · 3=Sering · 4=Selalu | nilai≥2 berarti pernah mengalami | Pertanyaan: Permasalahan sosial budaya';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u06_sq007 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah · 2=Jarang · 3=Sering · 4=Selalu | nilai≥2 berarti pernah mengalami | Pertanyaan: Pengaruh sosial budaya terhadap studi';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u06_sq008 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah · 2=Jarang · 3=Sering · 4=Selalu | nilai≥2 berarti pernah mengalami | Pertanyaan: Permasalahan kesehatan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u06_sq009 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah · 2=Jarang · 3=Sering · 4=Selalu | nilai≥2 berarti pernah mengalami | Pertanyaan: Pengaruh kesehatan terhadap studi';

-- Section D2: Ketersediaan Dukungan (U07)
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u07_sq001 IS 'Section D2 (U07) | Ketersediaan Dukungan | Populasi: semua strata & fakultas | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Sepenuhnya memenuhi · 5=Melampaui harapan | Pertanyaan: Ketersediaan beasiswa atau pinjaman';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u07_sq002 IS 'Section D2 (U07) | Ketersediaan Dukungan | Populasi: semua strata & fakultas | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Sepenuhnya memenuhi · 5=Melampaui harapan | Pertanyaan: Bimbingan konseling';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u07_sq003 IS 'Section D2 (U07) | Ketersediaan Dukungan | Populasi: semua strata & fakultas | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Sepenuhnya memenuhi · 5=Melampaui harapan | Pertanyaan: Nasehat dari wali akademik';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.u07_sq004 IS 'Section D2 (U07) | Ketersediaan Dukungan | Populasi: semua strata & fakultas | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Sepenuhnya memenuhi · 5=Melampaui harapan | Pertanyaan: Nasehat dari dosen matakuliah';

-- Section E: Free-text Pengalaman Belajar
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.g10q22 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text TEXT, NULL jika tidak diisi (opsional) | Pertanyaan: Kebiasaan belajar (cara belajar, waktu, hal-hal yang mendorong belajar)';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.g01q23 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text TEXT, NULL jika tidak diisi (opsional) | Pertanyaan: Kesan-kesan dan prestasi dalam belajar';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.g01q24 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text TEXT, NULL jika tidak diisi (opsional) | Pertanyaan: Pengalaman lain yang sangat berkesan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.g01q25 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text TEXT, NULL jika tidak diisi (opsional) | Pertanyaan: Aktivitas kemahasiswaan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.g01q26 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text TEXT, NULL jika tidak diisi (opsional) | Pertanyaan: Cita-cita dalam karier';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.g01q27 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text TEXT, NULL jika tidak diisi (opsional) | Pertanyaan: Cita-cita dalam hidup';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.g01q28 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text TEXT, NULL jika tidak diisi (opsional) | Pertanyaan: Motto untuk sukses studi di ITB';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.g01q29 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text TEXT, NULL jika tidak diisi (opsional) | Pertanyaan: Sifat khas diri sendiri';

-- Section F: Free-text Pandangan ITB
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.g11q30 IS 'Section F | Pandangan tentang ITB | Populasi: semua | Free-text TEXT, NULL jika tidak diisi (opsional) | Pertanyaan: Suka duka menempuh studi di ITB';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.g01q31 IS 'Section F | Pandangan tentang ITB | Populasi: semua | Free-text TEXT, NULL jika tidak diisi (opsional) | Pertanyaan: Segi positif studi di ITB';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.g01q32 IS 'Section F | Pandangan tentang ITB | Populasi: semua | Free-text TEXT, NULL jika tidak diisi (opsional) | Pertanyaan: Segi negatif studi di ITB';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.g01q33 IS 'Section F | Pandangan tentang ITB | Populasi: semua | Free-text TEXT, NULL jika tidak diisi (opsional) | Pertanyaan: Saran untuk perbaikan proses dan sarana pendidikan di ITB';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.g01q34 IS 'Section F | Pandangan tentang ITB | Populasi: semua | Free-text TEXT, NULL jika tidak diisi (opsional) | Pertanyaan: Saran untuk mahasiswa lain dalam menempuh studi di ITB';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.g01q35 IS 'Section F | Pandangan tentang ITB | Populasi: semua | Free-text TEXT, NULL jika tidak diisi (opsional) | Pertanyaan: Catatan atau komentar lain';

-- Section G: S1 Khusus
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.s101 IS 'Section G (S101) | Rencana melanjutkan ke pendidikan lebih tinggi | Hanya S1, NULL untuk strata lain | Nominal (OPT_YA_TIDAK): 1=Ya · 2=Tidak';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.s102 IS 'Section G (S102) | Lokasi rencana studi lanjut | Hanya S1, NULL untuk strata lain | Nominal (OPT_LOKASI_STUDI): 1=ITB · 2=Perguruan tinggi dalam negeri selain ITB · 3=Di luar negeri · 4=Tidak ada rencana studi lanjut';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.s103 IS 'Section G (S103) | Apakah bidang studi lanjutan merupakan kelanjutan bidang studi di ITB | Hanya S1, NULL untuk strata lain | Nominal (OPT_KELANJUTAN_STUDI): 1=Ya kelanjutan · 2=Tidak tapi serumpun · 3=Tidak tapi butuh pengetahuan ITB · 4=Tidak sangat berbeda · 5=Tidak ada rencana';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.s104_sq001 IS 'Section G (S104) | Penilaian Matakuliah Wajib ITB | Hanya S1, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Matakuliah wajib ITB membekali kemampuan softskill';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.s104_sq002 IS 'Section G (S104) | Penilaian Matakuliah Wajib ITB | Hanya S1, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Matakuliah wajib ITB membekali kemampuan hardskill';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.s104_sq003 IS 'Section G (S104) | Penilaian Matakuliah Wajib ITB | Hanya S1, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Matakuliah wajib ITB membangun karakter';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.s104_sq004 IS 'Section G (S104) | Penilaian Matakuliah Wajib ITB | Hanya S1, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Matakuliah wajib ITB memperluas wawasan';

-- Section H: S2 Khusus
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.m01 IS 'Section H (M01) | Rencana melanjutkan ke pendidikan lebih tinggi | Hanya S2, NULL untuk strata lain | Nominal (OPT_YA_TIDAK): 1=Ya · 2=Tidak';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.m02 IS 'Section H (M02) | Lokasi rencana studi lanjut | Hanya S2, NULL untuk strata lain | Nominal (OPT_LOKASI_STUDI): 1=ITB · 2=Perguruan tinggi dalam negeri selain ITB · 3=Di luar negeri · 4=Tidak ada rencana studi lanjut';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.m03 IS 'Section H (M03) | Apakah bidang studi lanjutan merupakan kelanjutan bidang studi di ITB | Hanya S2, NULL untuk strata lain | Nominal (OPT_KELANJUTAN_STUDI): 1=Ya kelanjutan · 2=Tidak tapi serumpun · 3=Tidak tapi butuh pengetahuan ITB · 4=Tidak sangat berbeda · 5=Tidak ada rencana';

-- Section I: S3 Khusus
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.d01_sq001 IS 'Section I (D01) | Penilaian Matakuliah Wajib ITB | Hanya S3, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Matakuliah wajib ITB membekali kemampuan softskill';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.d01_sq002 IS 'Section I (D01) | Penilaian Matakuliah Wajib ITB | Hanya S3, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Matakuliah wajib ITB membekali kemampuan hardskill';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.d01_sq003 IS 'Section I (D01) | Penilaian Matakuliah Wajib ITB | Hanya S3, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Matakuliah wajib ITB membangun karakter';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.d01_sq004 IS 'Section I (D01) | Penilaian Matakuliah Wajib ITB | Hanya S3, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Matakuliah wajib ITB memperluas wawasan';

-- Section J: FSRD Khusus
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd01_sq001 IS 'Section J FSRD01 (Tahap Persiapan Bersama) | Pemahaman Prinsip Estetik | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd01_sq002 IS 'Section J FSRD01 (Tahap Persiapan Bersama) | Penguasaan Proses Kreatif | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd01_sq003 IS 'Section J FSRD01 (Tahap Persiapan Bersama) | Penguasaan kemampuan menggambar dan membentuk | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd01_sq004 IS 'Section J FSRD01 (Tahap Persiapan Bersama) | Pengetahuan tentang program studi yang ada di FSRD | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd01_sq005 IS 'Section J FSRD01 (Tahap Persiapan Bersama) | Penguasaan kemampuan menulis secara ilmiah | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd02_sq001 IS 'Section J FSRD02 (Perwalian) | Pelaksanaan sistem perwalian tatap muka | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd02_sq002 IS 'Section J FSRD02 (Perwalian) | Pelaksanaan sistem perwalian online | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd02_sq003 IS 'Section J FSRD02 (Perwalian) | Bantuan dan respon dosen wali terkait permasalahan akademik | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd03_sq001 IS 'Section J FSRD03 (Mata Kuliah Teori) | Pemahaman tentang sejarah Seni, Kria atau Desain | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd03_sq002 IS 'Section J FSRD03 (Mata Kuliah Teori) | Pemahaman tentang perkembangan Seni, Kria atau Desain di Indonesia | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd03_sq003 IS 'Section J FSRD03 (Mata Kuliah Teori) | Pemahaman tentang perkembangan Seni, Kria atau Desain di Dunia | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd03_sq004 IS 'Section J FSRD03 (Mata Kuliah Teori) | Penguasaan metoda dan prosedur penciptaan/perancangan | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd03_sq005 IS 'Section J FSRD03 (Mata Kuliah Teori) | Penguasaan kemampuan analisis-kritis sebuah karya Seni, Kria atau Desain | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd03_sq006 IS 'Section J FSRD03 (Mata Kuliah Teori) | Kesesuaian antara jumlah SKS dengan jumlah dan materi tugas | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd04_sq001 IS 'Section J FSRD04 (Mata Kuliah Praktika/Studio) | Pemahaman teknik penciptaan/perancangan karya | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd04_sq002 IS 'Section J FSRD04 (Mata Kuliah Praktika/Studio) | Penguasaan wawasan estetik dan kaitannya dengan proses penciptaan/perancangan | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd04_sq003 IS 'Section J FSRD04 (Mata Kuliah Praktika/Studio) | Kesesuaian antara jumlah SKS dengan jumlah dan materi tugas praktika | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd04_sq004 IS 'Section J FSRD04 (Mata Kuliah Praktika/Studio) | Proses asistensi/pembimbingan yang memadai dan mengakomodir penciptaan/perancangan | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd04_sq005 IS 'Section J FSRD04 (Mata Kuliah Praktika/Studio) | Kesesuaian antara proses dan hasil penilaian kualitas karya | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd04_sq006 IS 'Section J FSRD04 (Mata Kuliah Praktika/Studio) | Kesesuaian pengetahuan semasa studi dengan aplikasinya pada kerja profesi/pemagangan | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd05_sq001 IS 'Section J FSRD05 (Tugas Akhir) | Pengetahuan teoritikal dan praktika menunjang pelaksanaan tugas akhir | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd05_sq002 IS 'Section J FSRD05 (Tugas Akhir) | Proses asistensi/pembimbingan selama menjalani tugas akhir | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd05_sq003 IS 'Section J FSRD05 (Tugas Akhir) | Ketersediaan sarana dan prasarana untuk menunjang tugas akhir | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.fsrd05_sq004 IS 'Section J FSRD05 (Tugas Akhir) | Ketersediaan buku dan sumber literatur di perpustakaan yang menunjang tugas akhir | Hanya fakultas FSRD, NULL untuk fakultas lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi · 3=Sebagian besar memenuhi · 4=Memenuhi harapan · 5=Melampaui harapan';

-- Section K: SBM Khusus
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq001 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan berkomunikasi secara lisan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq002 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan berkomunikasi dalam tulisan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq003 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menggunakan pengetahuan marketing';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq004 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menggunakan pengetahuan manajemen operasi';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq005 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menggunakan pengetahuan manajemen sumber daya manusia';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq006 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menggunakan pengetahuan keuangan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq007 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menggunakan pengetahuan Pengambilan Keputusan dan Negosiasi';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq008 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menggunakan pengetahuan kewirausahaan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq009 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan untuk tampil di depan publik/penonton';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq010 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Pengetahuan yang mendalam pada sekurangnya satu konsentrasi';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq011 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Pengetahuan tentang probabilitas dan statistik termasuk aplikasinya dalam menganalisis data dalam tugas akhir';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq012 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan untuk menginterpretasi data';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq013 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan mengidentifikasi masalah';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq014 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menyelesaikan masalah';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq015 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan melakukan riset bisnis';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq016 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menggunakan internet untuk memperoleh dan berbagi informasi/pengetahuan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq017 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan untuk membangun jejaring';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq018 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan untuk mendirikan usaha baru';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq019 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan bekerjasama dalam tim';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq020 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan mengidentifikasi peluang bisnis';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq021 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan mengidentifikasi peluang untuk meningkatkan/memperbaiki kondisi suatu komunitas';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq022 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan untuk merancang dan menciptakan produk baru';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq023 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan beradaptasi dalam kendala sosial';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq024 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan bekerja/belajar dalam kendala sumberdaya';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq025 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan bekerja/belajar dalam kendala etika';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq026 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan bekerja/belajar dalam kendala kesehatan dan keamanan';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq027 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Memahami tanggung jawab profesional';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq028 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Memahami tanggung jawab etis';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq029 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Pengakuan perlunya belajar seumur hidup';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq030 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan untuk terlibat dalam pembelajaran seumur hidup';
COMMENT ON COLUMN evaluasi_wisudawan.mv_wide_respons.sbm01_sq031 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya fakultas SBM, NULL untuk fakultas lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Pengetahuan pendukung untuk studi pasca sarjana';


-- ============================================================
-- REFRESH (jalankan setelah setiap batch import)

--   JANGAN gunakan CONCURRENTLY untuk mv_distribusi_jawaban dan mv_skor_pertanyaan.
--   Alasan: kolom periode_ijazah_id di kedua MV tersebut nullable (66.6% NULL
--   di data aktual). PostgreSQL UNIQUE index memperlakukan NULL ≠ NULL, sehingga
--   REFRESH CONCURRENTLY tidak dapat mencocokkan baris lama vs baru untuk row
--   dengan periode_ijazah_id = NULL — berisiko error atau data tidak konsisten.
--
--   mv_wide_respons aman pakai CONCURRENTLY karena UNIQUE INDEX-nya hanya
--   pada response_id (SERIAL, tidak pernah NULL).
--
--   Keputusan ini acceptable karena data survey diimport secara batch
--   (bukan real-time), sehingga downtime singkat saat refresh tidak berdampak.
--   Jika di masa depan periode_ijazah_id dijamin NOT NULL (semua baris
--   berhasil di-resolve), unique index bisa diganti dan CONCURRENTLY diaktifkan.

-- ============================================================

-- REFRESH MATERIALIZED VIEW evaluasi_wisudawan.mv_distribusi_jawaban;
-- REFRESH MATERIALIZED VIEW evaluasi_wisudawan.mv_skor_pertanyaan;
-- REFRESH MATERIALIZED VIEW CONCURRENTLY evaluasi_wisudawan.mv_wide_respons;