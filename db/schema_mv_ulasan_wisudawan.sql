-- ============================================================
-- MATERIALIZED VIEWS: analitik
-- Bergantung pada tabel di schema_evaluasi_wisudawan.sql dan
-- tabel master di utama.program_studi + utama.fakultas.
-- Jalankan setelah schema_evaluasi_wisudawan.sql berhasil dieksekusi.
--
-- Arsitektur (3 MV, granularitas berbeda):
--
--   mv_wisudawan_distribusi_jawaban  ← base granular: 1 baris per
--                            (periode, strata, fak, prodi, pertanyaan, nilai)
--                            mencakup ordinal (tipe=O) dan nominal (tipe=N)
--                            → query top-2-box, incidence, distribusi
--
--   mv_wisudawan_statistik_pertanyaan     ← aggregate: 1 baris per
--                            (periode, strata, fak, prodi, pertanyaan)
--                            AVG, MEDIAN, STDDEV, MIN, MAX — hanya ordinal (tipe=O)
--                            → dashboard chart rata-rata, ranking pertanyaan
--
--   mv_wisudawan_jawaban_responden        ← 1 baris per responden, semua jawaban sebagai
--                            kolom TEXT (decoded label) — Text-to-SQL & RAG
--
-- Seluruh MV menyertakan dimensi lengkap (prodi, fakultas, periode, tahun)
-- sehingga filtering tidak memerlukan JOIN tambahan.
--
-- Nama kolom kd_grup_opsi (bukan kd_set_opsi) sesuai schema evaluasi_wisudawan.
--
-- Tabel pendukung seremoni (wajib ada sebelum menjalankan script ini):
--   evaluasi_wisudawan.ijazah_to_seremoni          — mapping 1:1
--                                                    periode_ijazah_id_final → periode_seremoni_id
--   evaluasi_wisudawan.periode_seremoni_sementara  — master seremoni + tgl_seremoni
--   Lihat dummy_data_seremoni.sql dan patch_tgl_seremoni_dummy.sql
--
-- Kolom seremoni yang ditambahkan ke ketiga MV (setelah tahun_ijazah):
--   periode_seremoni_id  — ID seremoni (YYYYMM, contoh 202504)
--   tahun_seremoni       — tahun pelaksanaan seremoni
--   bulan_seremoni       — bulan pelaksanaan seremoni (1–12)
--   nama_seremoni        — nama seremoni (Bahasa Indonesia)
-- Semua via LEFT JOIN → NULL jika periode belum dipetakan.
--
-- Refresh semua setelah setiap batch import:
--   REFRESH MATERIALIZED VIEW analitik.mv_wisudawan_distribusi_jawaban;
--   REFRESH MATERIALIZED VIEW analitik.mv_wisudawan_statistik_pertanyaan;
--   REFRESH MATERIALIZED VIEW CONCURRENTLY analitik.mv_wisudawan_jawaban_responden;
-- ============================================================

CREATE SCHEMA IF NOT EXISTS analitik;


-- ============================================================
-- 1. mv_wisudawan_distribusi_jawaban
--    BASE granular MV — single source of truth untuk semua agregasi
--    Satu baris per (periode_ijazah_id, kd_strata, kd_fak, no_ps,
--                    kd_pertanyaan, nilai)
--    Mencakup ordinal (tipe=O) DAN nominal (tipe=N)
--    Free-text (kd_grup_opsi IS NULL) otomatis excluded via JOIN
--
--    Query dashboard yang bisa diturunkan dari MV ini:
--
--    % setuju (nilai >= 3) Section A per fak:
--      SELECT kode_fakultas, kd_pertanyaan,
--             SUM(n) FILTER (WHERE nilai >= 3) * 100.0 / SUM(n) AS pct_setuju
--      FROM analitik.mv_wisudawan_distribusi_jawaban
--      WHERE kd_grup_opsi = 'SETUJU'
--      GROUP BY kode_fakultas, kd_pertanyaan;
--
--    % pernah mengalami masalah (nilai >= 2) Section D1:
--      SELECT kd_pertanyaan,
--             SUM(n) FILTER (WHERE nilai >= 2) * 100.0 / SUM(n) AS pct_pernah
--      FROM analitik.mv_wisudawan_distribusi_jawaban
--      WHERE kd_grup_opsi = 'FREKUENSI'
--      GROUP BY kd_pertanyaan;
--
--    Distribusi pilihan rekomendasi prodi (U02, nominal):
--      SELECT d.nilai, o.label->>'id' AS pilihan, d.n, d.pct
--      FROM analitik.mv_wisudawan_distribusi_jawaban d
--      JOIN evaluasi_wisudawan.ref_opsi o
--          ON o.kd_grup_opsi = d.kd_grup_opsi AND o.nilai = d.nilai
--      WHERE d.kd_pertanyaan = 'U02'
--      ORDER BY d.nilai;
-- ============================================================

CREATE MATERIALIZED VIEW analitik.mv_wisudawan_distribusi_jawaban AS
SELECT
    -- Periode & dimensi organisasi (raw codes — dipakai UNIQUE INDEX)
    r.periode_ijazah_id,
    r.periode_ijazah_id_final,
    (r.periode_ijazah_id_final / 100)::INTEGER   AS tahun_ijazah,
    -- Dimensi seremoni wisuda (LEFT JOIN — NULL jika belum ada mapping)
    its.periode_seremoni_id                      AS periode_seremoni_id,
    EXTRACT(YEAR  FROM lower(ser.tgl_seremoni))::INTEGER AS tahun_seremoni,
    EXTRACT(MONTH FROM lower(ser.tgl_seremoni))::INTEGER AS bulan_seremoni,
    ser.nama->>'id'                              AS nama_seremoni,
    -- Dimensi deskriptif program studi & fakultas
    ps.no_ps                                     AS kode_prodi,
    ps.kd_ps                                     AS singkatan_prodi,
    ps.nama->>'id'                               AS nama_prodi_id,
    ps.nama->>'en'                               AS nama_prodi_en,
    ps.kd_strata                                 AS jenjang,
    f.kd_fak                                     AS kode_fakultas,
    f.nama->>'id'                                AS nama_fakultas_id,
    f.nama->>'en'                                AS nama_fakultas_en,
    -- Pertanyaan & distribusi jawaban
    p.kd_pertanyaan,
    p.kd_grup_pertanyaan,
    p.kd_grup_opsi,
    s.tipe                                       AS tipe_opsi,
    -- O = ordinal Likert (nilai bermakna aritmetika)
    -- N = nominal kategoris (nilai hanya kode urut)
    (r.jawaban ->> p.kd_pertanyaan)::SMALLINT    AS nilai,
    COUNT(*)                                     AS n,
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
    )                                            AS pct
FROM evaluasi_wisudawan.respons r
JOIN utama.program_studi ps ON ps.no_ps = r.no_ps
JOIN utama.fakultas      f  ON f.kd_fak = r.kd_fak
JOIN evaluasi_wisudawan.pertanyaan p
    ON r.jawaban ? p.kd_pertanyaan
JOIN evaluasi_wisudawan.ref_grup_opsi s
    ON p.kd_grup_opsi = s.kd_grup_opsi
LEFT JOIN evaluasi_wisudawan.ijazah_to_seremoni its
    ON its.periode_ijazah_id_final = r.periode_ijazah_id_final
LEFT JOIN evaluasi_wisudawan.periode_seremoni_sementara ser
    ON ser.periode_seremoni_id = its.periode_seremoni_id
-- LEFT JOIN agar baris dengan periode_ijazah_id_final belum dipetakan
-- tidak hilang dari MV (seremoni columns akan NULL).
WHERE
    p.batasan IS NULL
    OR (p.batasan -> 'strata'   @> to_jsonb(r.kd_strata::TEXT))
    OR (p.batasan -> 'fakultas' @> to_jsonb(r.kd_fak::TEXT))
GROUP BY
    r.periode_ijazah_id,
    r.periode_ijazah_id_final,
    r.kd_strata,
    r.kd_fak,
    r.no_ps,
    ps.kd_ps,
    ps.nama,
    ps.kd_strata,
    f.kd_fak,
    f.nama,
    p.kd_pertanyaan,
    p.kd_grup_pertanyaan,
    p.kd_grup_opsi,
    s.tipe,
    (r.jawaban ->> p.kd_pertanyaan)::SMALLINT,
    its.periode_seremoni_id,
    lower(ser.tgl_seremoni),
    ser.nama->>'id'
WITH DATA;

CREATE UNIQUE INDEX ON analitik.mv_wisudawan_distribusi_jawaban
    (periode_ijazah_id, kd_strata, kd_fak, no_ps, kd_pertanyaan, nilai);
-- UNIQUE INDEX wajib untuk REFRESH CONCURRENTLY
-- CATATAN: periode_ijazah_id nullable → gunakan REFRESH tanpa CONCURRENTLY

CREATE INDEX ON analitik.mv_wisudawan_distribusi_jawaban (kd_grup_opsi, nilai);
CREATE INDEX ON analitik.mv_wisudawan_distribusi_jawaban (kd_grup_pertanyaan);
CREATE INDEX ON analitik.mv_wisudawan_distribusi_jawaban (tipe_opsi);
CREATE INDEX ON analitik.mv_wisudawan_distribusi_jawaban (kd_strata, kd_fak);
CREATE INDEX ON analitik.mv_wisudawan_distribusi_jawaban (no_ps);
CREATE INDEX ON analitik.mv_wisudawan_distribusi_jawaban (kd_strata, kd_fak, no_ps);
CREATE INDEX ON analitik.mv_wisudawan_distribusi_jawaban (periode_ijazah_id_final);
CREATE INDEX ON analitik.mv_wisudawan_distribusi_jawaban (tahun_ijazah);
CREATE INDEX ON analitik.mv_wisudawan_distribusi_jawaban (periode_seremoni_id);


-- ============================================================
-- 2. mv_wisudawan_statistik_pertanyaan
--    AVG, MEDIAN, STDDEV, MIN, MAX per pertanyaan ordinal
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

CREATE MATERIALIZED VIEW analitik.mv_wisudawan_statistik_pertanyaan AS
SELECT
    -- Periode & dimensi organisasi (raw codes — dipakai UNIQUE INDEX)
    r.periode_ijazah_id,
    r.periode_ijazah_id_final,
    (r.periode_ijazah_id_final / 100)::INTEGER   AS tahun_ijazah,
    -- Dimensi seremoni wisuda (LEFT JOIN — NULL jika belum ada mapping)
    its.periode_seremoni_id                      AS periode_seremoni_id,
    EXTRACT(YEAR  FROM lower(ser.tgl_seremoni))::INTEGER AS tahun_seremoni,
    EXTRACT(MONTH FROM lower(ser.tgl_seremoni))::INTEGER AS bulan_seremoni,
    ser.nama->>'id'                              AS nama_seremoni,
    -- Dimensi deskriptif program studi & fakultas
    ps.no_ps                                     AS kode_prodi,
    ps.kd_ps                                     AS singkatan_prodi,
    ps.nama->>'id'                               AS nama_prodi_id,
    ps.nama->>'en'                               AS nama_prodi_en,
    ps.kd_strata                                 AS jenjang,
    f.kd_fak                                     AS kode_fakultas,
    f.nama->>'id'                                AS nama_fakultas_id,
    f.nama->>'en'                                AS nama_fakultas_en,
    -- Pertanyaan & statistik
    p.kd_pertanyaan,
    p.kd_grup_pertanyaan,
    p.kd_grup_opsi,
    COUNT(*)                                     AS n_responden,
    ROUND(
        AVG((r.jawaban ->> p.kd_pertanyaan)::NUMERIC),
        4
    )                                            AS rata_rata,
    ROUND(
        PERCENTILE_CONT(0.5) WITHIN GROUP (
            ORDER BY (r.jawaban ->> p.kd_pertanyaan)::NUMERIC
        ),
        4
    )                                            AS median,
    ROUND(
        STDDEV((r.jawaban ->> p.kd_pertanyaan)::NUMERIC),
        4
    )                                            AS std_dev,
    MIN((r.jawaban ->> p.kd_pertanyaan)::NUMERIC)  AS skor_min,
    MAX((r.jawaban ->> p.kd_pertanyaan)::NUMERIC)  AS skor_max
FROM evaluasi_wisudawan.respons r
JOIN utama.program_studi ps ON ps.no_ps = r.no_ps
JOIN utama.fakultas      f  ON f.kd_fak = r.kd_fak
JOIN evaluasi_wisudawan.pertanyaan p
    ON r.jawaban ? p.kd_pertanyaan
JOIN evaluasi_wisudawan.ref_grup_opsi s
    ON p.kd_grup_opsi = s.kd_grup_opsi
LEFT JOIN evaluasi_wisudawan.ijazah_to_seremoni its
    ON its.periode_ijazah_id_final = r.periode_ijazah_id_final
LEFT JOIN evaluasi_wisudawan.periode_seremoni_sementara ser
    ON ser.periode_seremoni_id = its.periode_seremoni_id
WHERE
    s.tipe = 'O'
    AND (
        p.batasan IS NULL
        OR (p.batasan -> 'strata'   @> to_jsonb(r.kd_strata::TEXT))
        OR (p.batasan -> 'fakultas' @> to_jsonb(r.kd_fak::TEXT))
    )
GROUP BY
    r.periode_ijazah_id,
    r.periode_ijazah_id_final,
    r.kd_strata,
    r.kd_fak,
    r.no_ps,
    ps.kd_ps,
    ps.nama,
    ps.kd_strata,
    f.kd_fak,
    f.nama,
    p.kd_pertanyaan,
    p.kd_grup_pertanyaan,
    p.kd_grup_opsi,
    its.periode_seremoni_id,
    lower(ser.tgl_seremoni),
    ser.nama->>'id'
WITH DATA;

CREATE UNIQUE INDEX ON analitik.mv_wisudawan_statistik_pertanyaan
    (periode_ijazah_id, kd_strata, kd_fak, no_ps, kd_pertanyaan);
-- UNIQUE INDEX wajib untuk REFRESH CONCURRENTLY
-- CATATAN: periode_ijazah_id nullable → gunakan REFRESH tanpa CONCURRENTLY

CREATE INDEX ON analitik.mv_wisudawan_statistik_pertanyaan (kd_grup_pertanyaan);
CREATE INDEX ON analitik.mv_wisudawan_statistik_pertanyaan (kd_grup_opsi);
CREATE INDEX ON analitik.mv_wisudawan_statistik_pertanyaan (kd_strata, kd_fak);
CREATE INDEX ON analitik.mv_wisudawan_statistik_pertanyaan (kd_strata, kd_fak, no_ps);
CREATE INDEX ON analitik.mv_wisudawan_statistik_pertanyaan (periode_ijazah_id_final);
CREATE INDEX ON analitik.mv_wisudawan_statistik_pertanyaan (tahun_ijazah);
CREATE INDEX ON analitik.mv_wisudawan_statistik_pertanyaan (periode_seremoni_id);


-- ============================================================
-- 3. mv_wisudawan_jawaban_responden
--    Satu baris per responden, semua jawaban sebagai kolom TEXT
--    (decoded label — bukan integer kode).
--
--    Skala → label:
--      SETUJU          : 'Tidak Setuju' | 'Cenderung Tidak Setuju' |
--                        'Cenderung Setuju' | 'Setuju'
--      FREKUENSI       : 'Tidak pernah atau sama sekali tidak' | 'Jarang atau kecil' |
--                        'Sering atau cukup' | 'Selalu atau besar'
--      HARAPAN         : 'Tidak sesuai harapan' | 'Ada yang memenuhi harapan' |
--                        'Sebagian besar memenuhi harapan' |
--                        'Sepenuhnya memenuhi harapan' | 'Melampaui harapan'
--      HARAPAN_FSRD    : sama kecuali nilai=4 → 'Memenuhi harapan' (bukan 'Sepenuhnya')
--      PERKEMBANGAN_SBM: 'Undeveloped – Tidak berkembang' | ... | 'Highly Developed – ...'
--      YA_TIDAK        : 'Ya' | 'Tidak'
--      LOKASI_STUDI    : 'ITB' | 'Perguruan tinggi dalam negeri selain ITB' | ...
--      BIDANG_STUDI    : label panjang (lihat COMMENT kolom s103/m03)
--      REKOMENDASI     : 'Kualitas dosen' | 'Suasana akademik' | ... | 'Other'
--
--    NULL pada kolom section-specific = pertanyaan tidak berlaku
--    untuk responden tersebut (natural dari JSONB, bukan missing data).
--
--    COMMENT per kolom menyertakan mapping angka=label sebagai referensi
--    untuk LLM / analyst — walaupun kolom menyimpan TEXT.
-- ============================================================

CREATE MATERIALIZED VIEW analitik.mv_wisudawan_jawaban_responden AS
SELECT
    -- ── Identitas responden ────────────────────────────────────
    r.response_id,
    r.survey_platform_response_id,

    -- ── Periode & dimensi organisasi (raw codes) ──────────────
    r.periode_ijazah_id,
    r.periode_ijazah_id_final,
    (r.periode_ijazah_id_final / 100)::INTEGER   AS tahun_ijazah,
    -- Dimensi seremoni wisuda (LEFT JOIN — NULL jika belum ada mapping)
    its.periode_seremoni_id                      AS periode_seremoni_id,
    EXTRACT(YEAR  FROM lower(ser.tgl_seremoni))::INTEGER AS tahun_seremoni,
    EXTRACT(MONTH FROM lower(ser.tgl_seremoni))::INTEGER AS bulan_seremoni,
    ser.nama->>'id'                              AS nama_seremoni,
    -- ─────────────────────────────────────────────────────────
    r.submit_date,

    -- ── Dimensi deskriptif program studi & fakultas ───────────
    ps.no_ps                                     AS kode_prodi,
    ps.kd_ps                                     AS singkatan_prodi,
    ps.nama->>'id'                               AS nama_prodi_id,
    ps.nama->>'en'                               AS nama_prodi_en,
    ps.kd_strata                                 AS jenjang,
    f.kd_fak                                     AS kode_fakultas,
    f.nama->>'id'                                AS nama_fakultas_id,
    f.nama->>'en'                                AS nama_fakultas_en,

    -- ── Section A: Fasilitas & Kepuasan ITB (U03, SETUJU) ─────
    CASE (r.jawaban->>'U03_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u03_sq001,
    CASE (r.jawaban->>'U03_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u03_sq002,
    CASE (r.jawaban->>'U03_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u03_sq003,
    CASE (r.jawaban->>'U03_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u03_sq004,
    CASE (r.jawaban->>'U03_SQ005')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u03_sq005,
    CASE (r.jawaban->>'U03_SQ006')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u03_sq006,
    CASE (r.jawaban->>'U03_SQ007')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u03_sq007,
    CASE (r.jawaban->>'U03_SQ008')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u03_sq008,
    CASE (r.jawaban->>'U03_SQ009')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u03_sq009,
    CASE (r.jawaban->>'U03_SQ010')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u03_sq010,
    CASE (r.jawaban->>'U03_SQ011')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u03_sq011,
    CASE (r.jawaban->>'U03_SQ012')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u03_sq012,

    -- ── Section B: Pendidikan di Prodi (U01, SETUJU) ──────────
    CASE (r.jawaban->>'U01_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u01_sq001,
    CASE (r.jawaban->>'U01_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u01_sq002,
    CASE (r.jawaban->>'U01_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u01_sq003,
    CASE (r.jawaban->>'U01_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u01_sq004,
    CASE (r.jawaban->>'U01_SQ005')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u01_sq005,
    CASE (r.jawaban->>'U01_SQ006')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u01_sq006,
    CASE (r.jawaban->>'U01_SQ007')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u01_sq007,
    CASE (r.jawaban->>'U01_SQ008')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u01_sq008,
    CASE (r.jawaban->>'U01_SQ009')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u01_sq009,
    CASE (r.jawaban->>'U01_SQ010')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u01_sq010,
    CASE (r.jawaban->>'U01_SQ011')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u01_sq011,
    CASE (r.jawaban->>'U01_SQ012')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u01_sq012,
    CASE (r.jawaban->>'U02')::SMALLINT
        WHEN 1 THEN 'Kualitas dosen'
        WHEN 2 THEN 'Suasana akademik'
        WHEN 3 THEN 'Jejaring alumni'
        WHEN 4 THEN 'Lapangan pekerjaan'
        WHEN 5 THEN 'Fasilitas akademik'
        WHEN 6 THEN 'Tidak merekomendasikan'
        WHEN 7 THEN 'Other'
    END AS u02,
    r.jawaban->>'U02_other'              AS u02_other,

    -- ── Section C1: Softskills (U04, SETUJU) ──────────────────
    CASE (r.jawaban->>'U04_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u04_sq001,
    CASE (r.jawaban->>'U04_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u04_sq002,
    CASE (r.jawaban->>'U04_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u04_sq003,
    CASE (r.jawaban->>'U04_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u04_sq004,
    CASE (r.jawaban->>'U04_SQ005')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u04_sq005,
    CASE (r.jawaban->>'U04_SQ006')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u04_sq006,
    CASE (r.jawaban->>'U04_SQ007')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u04_sq007,
    CASE (r.jawaban->>'U04_SQ008')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u04_sq008,
    CASE (r.jawaban->>'U04_SQ009')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u04_sq009,

    -- ── Section C2: Karakter (U05, SETUJU) ────────────────────
    CASE (r.jawaban->>'U05_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u05_sq001,
    CASE (r.jawaban->>'U05_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u05_sq002,
    CASE (r.jawaban->>'U05_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u05_sq003,
    CASE (r.jawaban->>'U05_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u05_sq004,
    CASE (r.jawaban->>'U05_SQ005')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u05_sq005,
    CASE (r.jawaban->>'U05_SQ006')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u05_sq006,
    CASE (r.jawaban->>'U05_SQ007')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS u05_sq007,

    -- ── Section D1: Permasalahan Studi (U06, FREKUENSI) ───────
    CASE (r.jawaban->>'U06_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak pernah atau sama sekali tidak'
        WHEN 2 THEN 'Jarang atau kecil'
        WHEN 3 THEN 'Sering atau cukup'
        WHEN 4 THEN 'Selalu atau besar'
    END AS u06_sq001,
    CASE (r.jawaban->>'U06_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak pernah atau sama sekali tidak'
        WHEN 2 THEN 'Jarang atau kecil'
        WHEN 3 THEN 'Sering atau cukup'
        WHEN 4 THEN 'Selalu atau besar'
    END AS u06_sq002,
    CASE (r.jawaban->>'U06_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak pernah atau sama sekali tidak'
        WHEN 2 THEN 'Jarang atau kecil'
        WHEN 3 THEN 'Sering atau cukup'
        WHEN 4 THEN 'Selalu atau besar'
    END AS u06_sq003,
    CASE (r.jawaban->>'U06_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak pernah atau sama sekali tidak'
        WHEN 2 THEN 'Jarang atau kecil'
        WHEN 3 THEN 'Sering atau cukup'
        WHEN 4 THEN 'Selalu atau besar'
    END AS u06_sq004,
    CASE (r.jawaban->>'U06_SQ005')::SMALLINT
        WHEN 1 THEN 'Tidak pernah atau sama sekali tidak'
        WHEN 2 THEN 'Jarang atau kecil'
        WHEN 3 THEN 'Sering atau cukup'
        WHEN 4 THEN 'Selalu atau besar'
    END AS u06_sq005,
    CASE (r.jawaban->>'U06_SQ006')::SMALLINT
        WHEN 1 THEN 'Tidak pernah atau sama sekali tidak'
        WHEN 2 THEN 'Jarang atau kecil'
        WHEN 3 THEN 'Sering atau cukup'
        WHEN 4 THEN 'Selalu atau besar'
    END AS u06_sq006,
    CASE (r.jawaban->>'U06_SQ007')::SMALLINT
        WHEN 1 THEN 'Tidak pernah atau sama sekali tidak'
        WHEN 2 THEN 'Jarang atau kecil'
        WHEN 3 THEN 'Sering atau cukup'
        WHEN 4 THEN 'Selalu atau besar'
    END AS u06_sq007,
    CASE (r.jawaban->>'U06_SQ008')::SMALLINT
        WHEN 1 THEN 'Tidak pernah atau sama sekali tidak'
        WHEN 2 THEN 'Jarang atau kecil'
        WHEN 3 THEN 'Sering atau cukup'
        WHEN 4 THEN 'Selalu atau besar'
    END AS u06_sq008,
    CASE (r.jawaban->>'U06_SQ009')::SMALLINT
        WHEN 1 THEN 'Tidak pernah atau sama sekali tidak'
        WHEN 2 THEN 'Jarang atau kecil'
        WHEN 3 THEN 'Sering atau cukup'
        WHEN 4 THEN 'Selalu atau besar'
    END AS u06_sq009,

    -- ── Section D2: Ketersediaan Dukungan (U07, HARAPAN) ──────
    CASE (r.jawaban->>'U07_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Sepenuhnya memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
    END AS u07_sq001,
    CASE (r.jawaban->>'U07_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Sepenuhnya memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
    END AS u07_sq002,
    CASE (r.jawaban->>'U07_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Sepenuhnya memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
    END AS u07_sq003,
    CASE (r.jawaban->>'U07_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Sepenuhnya memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
    END AS u07_sq004,

    -- ── Section E: Free-text Pengalaman Belajar (universal) ───
    r.jawaban->>'G10Q22'  AS g10q22,
    r.jawaban->>'G01Q23'  AS g01q23,
    r.jawaban->>'G01Q24'  AS g01q24,
    r.jawaban->>'G01Q25'  AS g01q25,
    r.jawaban->>'G01Q26'  AS g01q26,
    r.jawaban->>'G01Q27'  AS g01q27,
    r.jawaban->>'G01Q28'  AS g01q28,
    r.jawaban->>'G01Q29'  AS g01q29,

    -- ── Section F: Free-text Pandangan ITB (universal) ────────
    r.jawaban->>'G11Q30'  AS g11q30,
    r.jawaban->>'G01Q31'  AS g01q31,
    r.jawaban->>'G01Q32'  AS g01q32,
    r.jawaban->>'G01Q33'  AS g01q33,
    r.jawaban->>'G01Q34'  AS g01q34,
    r.jawaban->>'G01Q35'  AS g01q35,

    -- ── Section G: S1 khusus (NULL untuk strata lain) ─────────
    CASE (r.jawaban->>'S101')::SMALLINT
        WHEN 1 THEN 'Ya' WHEN 2 THEN 'Tidak'
    END AS s101,
    CASE (r.jawaban->>'S102')::SMALLINT
        WHEN 1 THEN 'ITB'
        WHEN 2 THEN 'Perguruan tinggi dalam negeri selain ITB'
        WHEN 3 THEN 'Di luar negeri'
        WHEN 4 THEN 'Tidak ada rencana studi lanjut'
    END AS s102,
    CASE (r.jawaban->>'S103')::SMALLINT
        WHEN 1 THEN 'Ya, bidang studi tersebut merupakan kelanjutan dari bidang studi yang baru saya selesaikan di ITB'
        WHEN 2 THEN 'Tidak, tetapi bidang studi tersebut masih serumpun dengan bidang studi yang baru saya selesaikan di ITB'
        WHEN 3 THEN 'Tidak, tetapi bidang studi tersebut masih membutuhkan pengetahuan dari bidang studi yang baru saya selesaikan di ITB'
        WHEN 4 THEN 'Tidak, bidang studi tersebut sangat berbeda dari bidang studi yang baru saya selesaikan di ITB'
        WHEN 5 THEN 'Tidak ada rencana studi lanjut'
    END AS s103,
    CASE (r.jawaban->>'S104_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS s104_sq001,
    CASE (r.jawaban->>'S104_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS s104_sq002,
    CASE (r.jawaban->>'S104_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS s104_sq003,
    CASE (r.jawaban->>'S104_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS s104_sq004,

    -- ── Section H: S2 khusus (NULL untuk strata lain) ─────────
    CASE (r.jawaban->>'M01')::SMALLINT
        WHEN 1 THEN 'Ya' WHEN 2 THEN 'Tidak'
    END AS m01,
    CASE (r.jawaban->>'M02')::SMALLINT
        WHEN 1 THEN 'ITB'
        WHEN 2 THEN 'Perguruan tinggi dalam negeri selain ITB'
        WHEN 3 THEN 'Di luar negeri'
        WHEN 4 THEN 'Tidak ada rencana studi lanjut'
    END AS m02,
    CASE (r.jawaban->>'M03')::SMALLINT
        WHEN 1 THEN 'Ya, bidang studi tersebut merupakan kelanjutan dari bidang studi yang baru saya selesaikan di ITB'
        WHEN 2 THEN 'Tidak, tetapi bidang studi tersebut masih serumpun dengan bidang studi yang baru saya selesaikan di ITB'
        WHEN 3 THEN 'Tidak, tetapi bidang studi tersebut masih membutuhkan pengetahuan dari bidang studi yang baru saya selesaikan di ITB'
        WHEN 4 THEN 'Tidak, bidang studi tersebut sangat berbeda dari bidang studi yang baru saya selesaikan di ITB'
        WHEN 5 THEN 'Tidak ada rencana studi lanjut'
    END AS m03,

    -- ── Section I: S3 khusus (NULL untuk strata lain) ─────────
    CASE (r.jawaban->>'D01_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS d01_sq001,
    CASE (r.jawaban->>'D01_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS d01_sq002,
    CASE (r.jawaban->>'D01_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS d01_sq003,
    CASE (r.jawaban->>'D01_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju' WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju' WHEN 4 THEN 'Setuju'
    END AS d01_sq004,

    -- ── Section J: FSRD khusus (NULL untuk fak lain) ──────────
    -- FSRD01: Tahap Persiapan Bersama (HARAPAN_FSRD, nilai=4→'Memenuhi harapan')
    CASE (r.jawaban->>'FSRD01_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd01_sq001,
    CASE (r.jawaban->>'FSRD01_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd01_sq002,
    CASE (r.jawaban->>'FSRD01_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd01_sq003,
    CASE (r.jawaban->>'FSRD01_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd01_sq004,
    CASE (r.jawaban->>'FSRD01_SQ005')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd01_sq005,
    -- FSRD02: Perwalian (HARAPAN_FSRD)
    CASE (r.jawaban->>'FSRD02_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd02_sq001,
    CASE (r.jawaban->>'FSRD02_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd02_sq002,
    CASE (r.jawaban->>'FSRD02_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd02_sq003,
    -- FSRD03: Mata Kuliah Teori (HARAPAN_FSRD)
    CASE (r.jawaban->>'FSRD03_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd03_sq001,
    CASE (r.jawaban->>'FSRD03_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd03_sq002,
    CASE (r.jawaban->>'FSRD03_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd03_sq003,
    CASE (r.jawaban->>'FSRD03_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd03_sq004,
    CASE (r.jawaban->>'FSRD03_SQ005')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd03_sq005,
    CASE (r.jawaban->>'FSRD03_SQ006')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd03_sq006,
    -- FSRD04: Mata Kuliah Praktika/Studio (HARAPAN_FSRD)
    CASE (r.jawaban->>'FSRD04_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd04_sq001,
    CASE (r.jawaban->>'FSRD04_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd04_sq002,
    CASE (r.jawaban->>'FSRD04_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd04_sq003,
    CASE (r.jawaban->>'FSRD04_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd04_sq004,
    CASE (r.jawaban->>'FSRD04_SQ005')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd04_sq005,
    CASE (r.jawaban->>'FSRD04_SQ006')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd04_sq006,
    -- FSRD05: Tugas Akhir (HARAPAN_FSRD)
    CASE (r.jawaban->>'FSRD05_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd05_sq001,
    CASE (r.jawaban->>'FSRD05_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd05_sq002,
    CASE (r.jawaban->>'FSRD05_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd05_sq003,
    CASE (r.jawaban->>'FSRD05_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan' WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan' WHEN 5 THEN 'Melampaui harapan'
    END AS fsrd05_sq004,

    -- ── Section K: SBM khusus (NULL untuk fak lain) ───────────
    -- PERKEMBANGAN_SBM: 5-poin bilingual (id – en)
    CASE (r.jawaban->>'SBM01_SQ001')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq001,
    CASE (r.jawaban->>'SBM01_SQ002')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq002,
    CASE (r.jawaban->>'SBM01_SQ003')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq003,
    CASE (r.jawaban->>'SBM01_SQ004')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq004,
    CASE (r.jawaban->>'SBM01_SQ005')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq005,
    CASE (r.jawaban->>'SBM01_SQ006')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq006,
    CASE (r.jawaban->>'SBM01_SQ007')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq007,
    CASE (r.jawaban->>'SBM01_SQ008')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq008,
    CASE (r.jawaban->>'SBM01_SQ009')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq009,
    CASE (r.jawaban->>'SBM01_SQ010')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq010,
    CASE (r.jawaban->>'SBM01_SQ011')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq011,
    CASE (r.jawaban->>'SBM01_SQ012')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq012,
    CASE (r.jawaban->>'SBM01_SQ013')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq013,
    CASE (r.jawaban->>'SBM01_SQ014')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq014,
    CASE (r.jawaban->>'SBM01_SQ015')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq015,
    CASE (r.jawaban->>'SBM01_SQ016')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq016,
    CASE (r.jawaban->>'SBM01_SQ017')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq017,
    CASE (r.jawaban->>'SBM01_SQ018')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq018,
    CASE (r.jawaban->>'SBM01_SQ019')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq019,
    CASE (r.jawaban->>'SBM01_SQ020')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq020,
    CASE (r.jawaban->>'SBM01_SQ021')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq021,
    CASE (r.jawaban->>'SBM01_SQ022')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq022,
    CASE (r.jawaban->>'SBM01_SQ023')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq023,
    CASE (r.jawaban->>'SBM01_SQ024')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq024,
    CASE (r.jawaban->>'SBM01_SQ025')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq025,
    CASE (r.jawaban->>'SBM01_SQ026')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq026,
    CASE (r.jawaban->>'SBM01_SQ027')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq027,
    CASE (r.jawaban->>'SBM01_SQ028')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq028,
    CASE (r.jawaban->>'SBM01_SQ029')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq029,
    CASE (r.jawaban->>'SBM01_SQ030')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq030,
    CASE (r.jawaban->>'SBM01_SQ031')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
    END AS sbm01_sq031

FROM evaluasi_wisudawan.respons r
JOIN utama.program_studi ps ON ps.no_ps = r.no_ps
JOIN utama.fakultas      f  ON f.kd_fak = r.kd_fak
LEFT JOIN evaluasi_wisudawan.ijazah_to_seremoni its
    ON its.periode_ijazah_id_final = r.periode_ijazah_id_final
LEFT JOIN evaluasi_wisudawan.periode_seremoni_sementara ser
    ON ser.periode_seremoni_id = its.periode_seremoni_id
WITH DATA;

CREATE UNIQUE INDEX ON analitik.mv_wisudawan_jawaban_responden (response_id);
-- UNIQUE INDEX pada response_id (SERIAL, tidak pernah NULL)
-- → aman untuk REFRESH CONCURRENTLY

CREATE INDEX ON analitik.mv_wisudawan_jawaban_responden (kd_strata);
CREATE INDEX ON analitik.mv_wisudawan_jawaban_responden (kd_fak);
CREATE INDEX ON analitik.mv_wisudawan_jawaban_responden (no_ps);
CREATE INDEX ON analitik.mv_wisudawan_jawaban_responden (periode_ijazah_id);
CREATE INDEX ON analitik.mv_wisudawan_jawaban_responden (periode_ijazah_id_final);
CREATE INDEX ON analitik.mv_wisudawan_jawaban_responden (tahun_ijazah);
CREATE INDEX ON analitik.mv_wisudawan_jawaban_responden (periode_seremoni_id);
CREATE INDEX ON analitik.mv_wisudawan_jawaban_responden (kd_strata, kd_fak);
CREATE INDEX ON analitik.mv_wisudawan_jawaban_responden (kd_strata, kd_fak, no_ps);


-- ============================================================
-- COMMENTS: mv_wisudawan_jawaban_responden
-- Format angka=label dipertahankan sebagai referensi mapping
-- walaupun kolom menyimpan TEXT (decoded label).
-- ============================================================

COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.response_id IS 'Surrogate primary key internal database';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.survey_platform_response_id IS 'ID response asli dari LimeSurvey (bisa NULL jika tidak tercatat)';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.periode_ijazah_id IS 'Periode wisuda format YYYYMM asli dari data sumber, contoh: 202502=Februari 2025. Nullable (66% terisi). FK ke wisuda.periode_ijazah';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.periode_ijazah_id_final IS 'periode_ijazah_id siap pakai: asli jika not null, diimputasi dari submit_date jika null. Gunakan kolom ini untuk filtering per periode';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.tahun_ijazah IS 'Tahun wisuda diturunkan dari periode_ijazah_id_final (YYYYMM / 100). Contoh: 202502 → 2025';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.periode_seremoni_id IS 'ID seremoni wisuda dari ijazah_to_seremoni (LEFT JOIN). Format YYYYMM, contoh: 202504=Seremoni April 2025. NULL jika periode belum dipetakan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.tahun_seremoni IS 'Tahun pelaksanaan seremoni wisuda, diekstrak dari lower(tgl_seremoni). NULL jika mapping belum ada atau tgl_seremoni belum diisi';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.bulan_seremoni IS 'Bulan pelaksanaan seremoni wisuda (1–12), diekstrak dari lower(tgl_seremoni). NULL jika mapping belum ada atau tgl_seremoni belum diisi';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.nama_seremoni IS 'Nama seremoni wisuda dalam Bahasa Indonesia dari periode_seremoni_sementara.nama->>''id''. NULL jika mapping belum ada';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.kd_strata IS 'Jenjang pendidikan kode: S1=Sarjana, S2=Magister, S3=Doktor, PR=Profesi';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.kd_fak IS 'Kode fakultas/sekolah singkat, contoh: STEI, SBM, FSRD. FK ke utama.fakultas';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.no_ps IS 'Kode numerik program studi, contoh: 135=Teknik Informatika S1. FK ke utama.program_studi';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.submit_date IS 'Timestamp pengisian kuesioner oleh wisudawan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.kode_prodi IS 'no_ps dari utama.program_studi (identik dengan no_ps, disediakan untuk konsistensi penamaan lintas MV)';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.singkatan_prodi IS 'Kode singkat program studi, contoh: IF, EL, MA. Dari utama.program_studi.kd_ps';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.nama_prodi_id IS 'Nama lengkap program studi dalam Bahasa Indonesia. Dari utama.program_studi.nama->>id';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.nama_prodi_en IS 'Nama lengkap program studi dalam Bahasa Inggris. Dari utama.program_studi.nama->>en';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.jenjang IS 'Jenjang program studi: S1, S2, S3, PR. Dari utama.program_studi.kd_strata';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.kode_fakultas IS 'Kode fakultas/sekolah. Dari utama.fakultas.kd_fak';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.nama_fakultas_id IS 'Nama lengkap fakultas dalam Bahasa Indonesia. Dari utama.fakultas.nama->>id';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.nama_fakultas_en IS 'Nama lengkap fakultas dalam Bahasa Inggris. Dari utama.fakultas.nama->>en';

-- Section A: Fasilitas & Kepuasan ITB (U03)
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u03_sq001 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Tersedia cukup ruang kelas';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u03_sq002 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Ruang kelas kondusif untuk pembelajaran';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u03_sq003 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Laboratorium kondusif untuk pembelajaran';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u03_sq004 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Akses internet memadai';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u03_sq005 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Fasilitas keprofesian memadai';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u03_sq006 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Akses perpustakaan memadai';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u03_sq007 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Perangkat pembelajaran up-to-date';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u03_sq008 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Fasilitas toilet memadai';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u03_sq009 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Fasilitas kantin memadai';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u03_sq010 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Fasilitas rekreasi/olahraga memadai';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u03_sq011 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Fasilitas kesehatan memadai';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u03_sq012 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Secara keseluruhan saya puas dengan fasilitas ITB';

-- Section B: Pendidikan di Prodi (U01 + U02)
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u01_sq001 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Wali akademik selalu tersedia saat dibutuhkan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u01_sq002 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Wali akademik membantu memenuhi persyaratan akademik';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u01_sq003 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Dosen berinteraksi secara informal dengan mahasiswa';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u01_sq004 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Dosen memperhatikan proses pembelajaran mahasiswa';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u01_sq005 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Dosen memiliki kemampuan profesional yang baik';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u01_sq006 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Matakuliah wajib memberikan dasar yang baik';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u01_sq007 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Matakuliah pilihan memberikan keleluasaan eksplorasi';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u01_sq008 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Praktikum sejalan dengan teori di kelas';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u01_sq009 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Sarana program studi memadai';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u01_sq010 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Program studi memberikan gambaran dunia kerja';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u01_sq011 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Saya menikmati bidang studi saya';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u01_sq012 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Saya akan memilih program studi yang sama lagi';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u02 IS 'Section B (U02) | Rekomendasi prodi | Populasi: semua | Nominal (REKOMENDASI_PRODI): 1=Kualitas dosen · 2=Suasana akademik · 3=Jejaring alumni · 4=Lapangan pekerjaan · 5=Fasilitas akademik · 6=Tidak merekomendasikan · 7=Other';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u02_other IS 'Section B (U02) | Teks bebas jika u02=Other. NULL jika u02 bukan Other';

-- Section C1: Softskills (U04)
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u04_sq001 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan komunikasi lisan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u04_sq002 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan komunikasi tertulis';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u04_sq003 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan berbahasa asing';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u04_sq004 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan penyelesaian masalah';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u04_sq005 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan berpikir kritis';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u04_sq006 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan introspeksi diri';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u04_sq007 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan menyampaikan pendapat';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u04_sq008 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan kerja tim';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u04_sq009 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan kerja mandiri';

-- Section C2: Karakter (U05)
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u05_sq001 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kejujuran';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u05_sq002 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Komitmen';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u05_sq003 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kecerdasan emosi';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u05_sq004 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kepedulian terhadap sesama';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u05_sq005 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Objektivitas';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u05_sq006 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Ketidakmudahan menyerah (Perseverance)';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u05_sq007 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kepatuhan terhadap aturan';

-- Section D1: Permasalahan Studi (U06)
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u06_sq001 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah atau sama sekali tidak · 2=Jarang atau kecil · 3=Sering atau cukup · 4=Selalu atau besar | Pertanyaan: Permasalahan akademis';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u06_sq002 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah atau sama sekali tidak · 2=Jarang atau kecil · 3=Sering atau cukup · 4=Selalu atau besar | Pertanyaan: Permasalahan keuangan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u06_sq003 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah atau sama sekali tidak · 2=Jarang atau kecil · 3=Sering atau cukup · 4=Selalu atau besar | Pertanyaan: Pengaruh keuangan terhadap akademis';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u06_sq004 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah atau sama sekali tidak · 2=Jarang atau kecil · 3=Sering atau cukup · 4=Selalu atau besar | Pertanyaan: Permasalahan psikologis';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u06_sq005 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah atau sama sekali tidak · 2=Jarang atau kecil · 3=Sering atau cukup · 4=Selalu atau besar | Pertanyaan: Pengaruh psikologis terhadap studi';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u06_sq006 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah atau sama sekali tidak · 2=Jarang atau kecil · 3=Sering atau cukup · 4=Selalu atau besar | Pertanyaan: Permasalahan sosial budaya';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u06_sq007 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah atau sama sekali tidak · 2=Jarang atau kecil · 3=Sering atau cukup · 4=Selalu atau besar | Pertanyaan: Pengaruh sosial budaya terhadap studi';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u06_sq008 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah atau sama sekali tidak · 2=Jarang atau kecil · 3=Sering atau cukup · 4=Selalu atau besar | Pertanyaan: Permasalahan kesehatan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u06_sq009 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah atau sama sekali tidak · 2=Jarang atau kecil · 3=Sering atau cukup · 4=Selalu atau besar | Pertanyaan: Pengaruh kesehatan terhadap studi';

-- Section D2: Ketersediaan Dukungan (U07)
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u07_sq001 IS 'Section D2 (U07) | Ketersediaan Dukungan | Populasi: semua strata & fakultas | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Sepenuhnya memenuhi harapan · 5=Melampaui harapan | Pertanyaan: Ketersediaan beasiswa atau pinjaman';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u07_sq002 IS 'Section D2 (U07) | Ketersediaan Dukungan | Populasi: semua strata & fakultas | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Sepenuhnya memenuhi harapan · 5=Melampaui harapan | Pertanyaan: Bimbingan konseling';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u07_sq003 IS 'Section D2 (U07) | Ketersediaan Dukungan | Populasi: semua strata & fakultas | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Sepenuhnya memenuhi harapan · 5=Melampaui harapan | Pertanyaan: Nasehat dari wali akademik';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.u07_sq004 IS 'Section D2 (U07) | Ketersediaan Dukungan | Populasi: semua strata & fakultas | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Sepenuhnya memenuhi harapan · 5=Melampaui harapan | Pertanyaan: Nasehat dari dosen matakuliah';

-- Section E: Free-text Pengalaman Belajar
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.g10q22 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Kebiasaan belajar (cara belajar, waktu, hal-hal yang mendorong belajar)';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.g01q23 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Kesan-kesan dan prestasi dalam belajar';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.g01q24 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Pengalaman lain yang sangat berkesan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.g01q25 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Aktivitas kemahasiswaan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.g01q26 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Cita-cita dalam karier';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.g01q27 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Cita-cita dalam hidup';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.g01q28 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Motto untuk sukses studi di ITB';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.g01q29 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Sifat khas diri sendiri';

-- Section F: Free-text Pandangan ITB
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.g11q30 IS 'Section F | Pandangan tentang ITB | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Suka duka menempuh studi di ITB';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.g01q31 IS 'Section F | Pandangan tentang ITB | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Segi positif studi di ITB';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.g01q32 IS 'Section F | Pandangan tentang ITB | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Segi negatif studi di ITB';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.g01q33 IS 'Section F | Pandangan tentang ITB | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Saran untuk perbaikan proses dan sarana pendidikan di ITB';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.g01q34 IS 'Section F | Pandangan tentang ITB | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Saran untuk mahasiswa lain dalam menempuh studi di ITB';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.g01q35 IS 'Section F | Pandangan tentang ITB | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Catatan atau komentar lain';

-- Section G: S1 Khusus
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.s101 IS 'Section G (S101) | Rencana melanjutkan ke pendidikan lebih tinggi | Hanya S1, NULL untuk strata lain | Nominal (YA_TIDAK): 1=Ya · 2=Tidak';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.s102 IS 'Section G (S102) | Lokasi rencana studi lanjut | Hanya S1, NULL untuk strata lain | Nominal (LOKASI_STUDI_LANJUT): 1=ITB · 2=Perguruan tinggi dalam negeri selain ITB · 3=Di luar negeri · 4=Tidak ada rencana studi lanjut';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.s103 IS 'Section G (S103) | Kelanjutan bidang studi | Hanya S1, NULL untuk strata lain | Nominal (BIDANG_STUDI_LANJUT): 1=Ya kelanjutan · 2=Tidak tapi serumpun · 3=Tidak tapi butuh pengetahuan ITB · 4=Tidak sangat berbeda · 5=Tidak ada rencana';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.s104_sq001 IS 'Section G (S104) | Penilaian Matakuliah Wajib ITB | Hanya S1, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Agama dan etika — pengaruh terhadap sikap';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.s104_sq002 IS 'Section G (S104) | Penilaian Matakuliah Wajib ITB | Hanya S1, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Pancasila dan kewarganegaraan — pengaruh terhadap sikap';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.s104_sq003 IS 'Section G (S104) | Penilaian Matakuliah Wajib ITB | Hanya S1, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Manajemen — wawasan pentingnya peranan manajemen';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.s104_sq004 IS 'Section G (S104) | Penilaian Matakuliah Wajib ITB | Hanya S1, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Lingkungan — wawasan dan perilaku ramah lingkungan';

-- Section H: S2 Khusus
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.m01 IS 'Section H (M01) | Rencana melanjutkan ke pendidikan lebih tinggi | Hanya S2, NULL untuk strata lain | Nominal (YA_TIDAK): 1=Ya · 2=Tidak';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.m02 IS 'Section H (M02) | Lokasi rencana studi lanjut | Hanya S2, NULL untuk strata lain | Nominal (LOKASI_STUDI_LANJUT): 1=ITB · 2=Perguruan tinggi dalam negeri selain ITB · 3=Di luar negeri · 4=Tidak ada rencana studi lanjut';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.m03 IS 'Section H (M03) | Kelanjutan bidang studi | Hanya S2, NULL untuk strata lain | Nominal (BIDANG_STUDI_LANJUT): 1=Ya kelanjutan · 2=Tidak tapi serumpun · 3=Tidak tapi butuh pengetahuan ITB · 4=Tidak sangat berbeda · 5=Tidak ada rencana';

-- Section I: S3 Khusus
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.d01_sq001 IS 'Section I (D01) | Penilaian Matakuliah Wajib ITB Doktor | Hanya S3, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Filsafat ilmu — wawasan pengembangan ilmu pengetahuan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.d01_sq002 IS 'Section I (D01) | Penilaian Matakuliah Wajib ITB Doktor | Hanya S3, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Metodologi penelitian — manfaat dalam penelitian';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.d01_sq003 IS 'Section I (D01) | Penilaian Matakuliah Wajib ITB Doktor | Hanya S3, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kesulitan mengambil filsafat ilmu';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.d01_sq004 IS 'Section I (D01) | Penilaian Matakuliah Wajib ITB Doktor | Hanya S3, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kesulitan mengambil metodologi penelitian';

-- Section J: FSRD Khusus
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd01_sq001 IS 'Section J FSRD01 (TPB) | Pemahaman Prinsip Estetik | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd01_sq002 IS 'Section J FSRD01 (TPB) | Penguasaan Proses Kreatif | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd01_sq003 IS 'Section J FSRD01 (TPB) | Penguasaan menggambar dan membentuk | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd01_sq004 IS 'Section J FSRD01 (TPB) | Pengetahuan tentang program studi FSRD | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd01_sq005 IS 'Section J FSRD01 (TPB) | Kemampuan menulis secara ilmiah | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd02_sq001 IS 'Section J FSRD02 (Perwalian) | Perwalian tatap muka | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd02_sq002 IS 'Section J FSRD02 (Perwalian) | Perwalian online | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd02_sq003 IS 'Section J FSRD02 (Perwalian) | Bantuan dan respon dosen wali | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd03_sq001 IS 'Section J FSRD03 (MK Teori) | Sejarah Seni/Kria/Desain | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd03_sq002 IS 'Section J FSRD03 (MK Teori) | Perkembangan Seni/Kria/Desain di Indonesia | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd03_sq003 IS 'Section J FSRD03 (MK Teori) | Perkembangan Seni/Kria/Desain di Dunia | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd03_sq004 IS 'Section J FSRD03 (MK Teori) | Metoda dan prosedur penciptaan/perancangan | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd03_sq005 IS 'Section J FSRD03 (MK Teori) | Kemampuan analisis-kritis karya | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd03_sq006 IS 'Section J FSRD03 (MK Teori) | Kesesuaian SKS dengan jumlah dan materi tugas | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd04_sq001 IS 'Section J FSRD04 (MK Studio) | Teknik penciptaan/perancangan | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd04_sq002 IS 'Section J FSRD04 (MK Studio) | Wawasan estetik dan proses perancangan | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd04_sq003 IS 'Section J FSRD04 (MK Studio) | Kesesuaian SKS dengan tugas studio | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd04_sq004 IS 'Section J FSRD04 (MK Studio) | Proses asistensi/pembimbingan | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd04_sq005 IS 'Section J FSRD04 (MK Studio) | Kesesuaian penilaian kualitas karya | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd04_sq006 IS 'Section J FSRD04 (MK Studio) | Kesesuaian pengetahuan dengan kerja profesi/pemagangan | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd05_sq001 IS 'Section J FSRD05 (Tugas Akhir) | Pengetahuan menunjang TA | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd05_sq002 IS 'Section J FSRD05 (Tugas Akhir) | Proses pembimbingan TA | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd05_sq003 IS 'Section J FSRD05 (Tugas Akhir) | Sarana dan prasarana TA | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.fsrd05_sq004 IS 'Section J FSRD05 (Tugas Akhir) | Buku dan literatur perpustakaan untuk TA | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';

-- Section K: SBM Khusus
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq001 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan berkomunikasi secara lisan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq002 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan berkomunikasi dalam tulisan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq003 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menggunakan pengetahuan marketing';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq004 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menggunakan pengetahuan manajemen operasi';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq005 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menggunakan pengetahuan manajemen sumber daya manusia';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq006 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menggunakan pengetahuan keuangan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq007 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan Pengambilan Keputusan dan Negosiasi';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq008 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan kewirausahaan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq009 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan tampil di depan publik';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq010 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Pengetahuan mendalam pada sekurangnya satu konsentrasi';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq011 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Pengetahuan probabilitas dan statistik termasuk analisis data';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq012 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menginterpretasi data';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq013 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan mengidentifikasi masalah';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq014 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menyelesaikan masalah';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq015 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan melakukan riset bisnis';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq016 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menggunakan internet untuk informasi dan berbagi pengetahuan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq017 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan membangun jejaring';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq018 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan mendirikan usaha baru';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq019 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan bekerjasama dalam tim';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq020 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan mengidentifikasi peluang bisnis';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq021 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan mengidentifikasi peluang peningkatan kondisi komunitas';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq022 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan merancang dan menciptakan produk baru';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq023 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan beradaptasi dalam kendala sosial';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq024 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan bekerja/belajar dalam kendala sumberdaya';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq025 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan bekerja/belajar dalam kendala etika';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq026 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan bekerja/belajar dalam kendala kesehatan dan keamanan';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq027 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Memahami tanggung jawab profesional';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq028 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Memahami tanggung jawab etis';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq029 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Pengakuan perlunya belajar seumur hidup';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq030 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan terlibat dalam pembelajaran seumur hidup';
COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.sbm01_sq031 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Pengetahuan pendukung untuk studi pasca sarjana';


-- ============================================================
-- REFRESH
--
--   mv_wisudawan_distribusi_jawaban dan mv_wisudawan_statistik_pertanyaan:
--   JANGAN gunakan CONCURRENTLY — periode_ijazah_id nullable
--   (NULL ≠ NULL dalam UNIQUE INDEX PostgreSQL).
--   Data diimport secara batch sehingga downtime singkat acceptable.
--
--   mv_wisudawan_jawaban_responden aman pakai CONCURRENTLY karena UNIQUE INDEX
--   hanya pada response_id (SERIAL, tidak pernah NULL).
-- ============================================================

-- REFRESH MATERIALIZED VIEW analitik.mv_wisudawan_distribusi_jawaban;
-- REFRESH MATERIALIZED VIEW analitik.mv_wisudawan_statistik_pertanyaan;
-- REFRESH MATERIALIZED VIEW CONCURRENTLY analitik.mv_wisudawan_jawaban_responden;