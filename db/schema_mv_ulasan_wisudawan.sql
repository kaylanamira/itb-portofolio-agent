-- ================================================================
-- MATERIALIZED VIEWS : Wisudawan (analitik_mv) — VERSI PERBAIKAN
--
-- Perubahan dari draft awal analitik_mv:
--
--   [FIX-1] is_asumtif:
--     Semua baris evaluasi_wisudawan.ijazah_to_seremoni saat ini
--     is_asumtif = TRUE (data seremoni masih "dipaksakan ada"
--     sebagai placeholder untuk keperluan Tugas Akhir, belum ada
--     data resmi). Filter "WHERE i.is_asumtif = FALSE" pada draft
--     awal akan membuat mv_wisudawan_distribusi_jawaban dan
--     mv_wisudawan_statistik_pertanyaan KOSONG TOTAL.
--
--     Solusi: ganti JOIN -> LEFT JOIN ke ijazah_to_seremoni (dan
--     turunannya: periode_ijazah_sementara, periode_seremoni_sementara),
--     hapus filter WHERE is_asumtif, dan expose kolom
--     is_seremoni_asumtif di ketiga MV sebagai dimensi transparan.
--     Konsumen (dashboard/laporan) yang nanti ingin menyembunyikan
--     data seremoni dummy bisa filter sendiri:
--         WHERE is_seremoni_asumtif = FALSE
--     tanpa MV ikut kosong saat semua data masih dummy.
--
--   [FIX-2] tipe='N' -> tipe='O' di mv_wisudawan_statistik_pertanyaan:
--     AVG/MEDIAN/STDDEV/MIN/MAX hanya valid untuk pertanyaan ORDINAL
--     (skala Likert, tipe='O'). tipe='N' = nominal/kategoris (mis.
--     U02 "alasan rekomendasi": 1=Kualitas dosen, 2=Suasana akademik,
--     dst — angka hanya label, rata-rata tidak bermakna).
--
--   [FIX-3] Penyelarasan alias kolom pertanyaan:
--     kd_pertanyaan       -> kode_pertanyaan
--     kd_grup_pertanyaan  -> kode_grup_pertanyaan
--     kd_grup_opsi        -> kode_grup_opsi
--     Konsisten dengan konvensi "kode_*" di seluruh analitik_mv
--     (kode_prodi, kode_fakultas, dst), dan memperbaiki bug index
--     yang sebelumnya mereferensikan "kode_pertanyaan" padahal
--     kolom hasil SELECT bernama "kd_pertanyaan" (CREATE UNIQUE INDEX
--     akan gagal: column "kode_pertanyaan" does not exist).
--
-- CATATAN OPERASIONAL (dipertahankan dari draft lama):
--   mv_wisudawan_distribusi_jawaban dan mv_wisudawan_statistik_pertanyaan:
--   JANGAN REFRESH ... CONCURRENTLY — periode_ijazah_id nullable
--   (NULL <> NULL dalam UNIQUE INDEX PostgreSQL, sehingga
--   REFRESH CONCURRENTLY bisa gagal/tidak konsisten untuk baris
--   dengan periode_ijazah_id NULL). Gunakan REFRESH biasa.
--
--   mv_wisudawan_jawaban_responden aman pakai CONCURRENTLY karena
--   UNIQUE INDEX hanya pada response_id (SERIAL, tidak pernah NULL).
-- ================================================================


-- ================================================================
-- MV 1: mv_wisudawan_distribusi_jawaban
-- Tidak bergantung pada mv_akademik_kelas.
-- Sumber: evaluasi_wisudawan.respons (jawaban JSONB) + periode + prodi
-- Grain: 1 baris = 1 (periode_ijazah_id_final, jenjang, kode_fakultas,
--                     no_prodi, kode_pertanyaan, nilai)
-- ================================================================

CREATE MATERIALIZED VIEW analitik_mv.mv_wisudawan_distribusi_jawaban AS
WITH

-- Unnest setiap jawaban per responden menjadi baris (kd_pertanyaan, nilai)
jawaban_unnest AS (
    SELECT
        r.response_id,
        r.kd_strata,
        r.kd_fak,
        r.no_ps,
        r.periode_ijazah_id,
        r.periode_ijazah_id_final,
        kv.key                      AS kd_pertanyaan,
        kv.value::TEXT              AS nilai_jawaban
    FROM evaluasi_wisudawan.respons r
    CROSS JOIN LATERAL jsonb_each_text(r.jawaban) kv
    WHERE r.jawaban IS NOT NULL
),

-- Join ke tabel pertanyaan untuk dapat grup dan opsi
jawaban_dengan_opsi AS (
    SELECT
        ju.response_id,
        ju.kd_strata,
        ju.kd_fak,
        ju.no_ps,
        ju.periode_ijazah_id,
        ju.periode_ijazah_id_final,
        p.kd_pertanyaan,
        p.kd_grup_pertanyaan,
        p.kd_grup_opsi,
        go.tipe                     AS tipe_opsi,
        ju.nilai_jawaban::SMALLINT  AS nilai
    FROM jawaban_unnest ju
    JOIN evaluasi_wisudawan.pertanyaan    p  ON p.kd_pertanyaan = ju.kd_pertanyaan
    JOIN evaluasi_wisudawan.ref_grup_opsi go ON go.kd_grup_opsi = p.kd_grup_opsi
    WHERE p.kd_grup_opsi IS NOT NULL
      AND ju.nilai_jawaban ~ '^[0-9]+$'  -- hanya nilai numerik
)

SELECT
    -- ── Periode ijazah (selalu ada, dari respons) ────────────────
    jdo.periode_ijazah_id,
    jdo.periode_ijazah_id_final,
    EXTRACT(YEAR  FROM lower(pi.tgl_ijazah))::INTEGER  AS tahun_ijazah,
    EXTRACT(MONTH FROM lower(pi.tgl_ijazah))::INTEGER  AS bulan_ijazah,

    -- ── Dimensi seremoni (LEFT JOIN — bisa NULL / masih dummy) ──
    i.periode_seremoni_id,
    EXTRACT(YEAR  FROM lower(s.tgl_seremoni))::INTEGER AS tahun_seremoni,
    EXTRACT(MONTH FROM lower(s.tgl_seremoni))::INTEGER AS bulan_seremoni,
    s.nama->>'id'                   AS nama_seremoni,
    i.is_asumtif                    AS is_seremoni_asumtif,

    -- ── Prodi & Fakultas ──────────────────────────────────────────
    ps.no_ps                        AS no_prodi,
    ps.kd_ps                        AS kode_prodi,
    ps.nama->>'id'                  AS nama_prodi_id,
    ps.nama->>'en'                  AS nama_prodi_en,
    ps.kd_strata                    AS jenjang,
    f.kd_fak                        AS kode_fakultas,
    f.nama->>'id'                   AS nama_fakultas_id,
    f.nama->>'en'                   AS nama_fakultas_en,

    -- ── Pertanyaan & distribusi jawaban ───────────────────────────
    jdo.kd_pertanyaan               AS kode_pertanyaan,
    jdo.kd_grup_pertanyaan          AS kode_grup_pertanyaan,
    jdo.kd_grup_opsi                AS kode_grup_opsi,
    jdo.tipe_opsi,
    jdo.nilai,
    COUNT(*)                        AS jumlah_responden,
    ROUND(COUNT(*)::NUMERIC / NULLIF(
        SUM(COUNT(*)) OVER (
            PARTITION BY jdo.kd_pertanyaan, jdo.periode_ijazah_id_final,
                         jdo.no_ps, jdo.kd_strata
        ), 0
    ) * 100, 2)                     AS persentase

FROM jawaban_dengan_opsi jdo
LEFT JOIN evaluasi_wisudawan.ijazah_to_seremoni         i   ON i.periode_ijazah_id_final = jdo.periode_ijazah_id_final
LEFT JOIN evaluasi_wisudawan.periode_ijazah_sementara   pi  ON pi.periode_ijazah_id      = jdo.periode_ijazah_id_final
LEFT JOIN evaluasi_wisudawan.periode_seremoni_sementara s   ON s.periode_seremoni_id     = i.periode_seremoni_id
JOIN utama.program_studi                                ps  ON ps.no_ps = jdo.no_ps
JOIN utama.fakultas                                     f   ON f.kd_fak = ps.kd_fak
GROUP BY
    jdo.periode_ijazah_id, jdo.periode_ijazah_id_final,
    pi.tgl_ijazah,
    i.periode_seremoni_id, i.is_asumtif, s.tgl_seremoni, s.nama,
    ps.no_ps, ps.kd_ps, ps.nama, ps.kd_strata, ps.kd_fak,
    f.kd_fak, f.nama,
    jdo.kd_pertanyaan, jdo.kd_grup_pertanyaan, jdo.kd_grup_opsi,
    jdo.tipe_opsi, jdo.nilai, jdo.no_ps, jdo.kd_strata;

-- Index
-- CATATAN: periode_ijazah_id nullable -> REFRESH tanpa CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_wisuda_dist_pk
    ON analitik_mv.mv_wisudawan_distribusi_jawaban
    (periode_ijazah_id, jenjang, kode_fakultas, no_prodi, kode_pertanyaan, nilai);
CREATE INDEX idx_mv_wisuda_dist_fak
    ON analitik_mv.mv_wisudawan_distribusi_jawaban (jenjang, kode_fakultas, no_prodi);
CREATE INDEX idx_mv_wisuda_dist_prodi
    ON analitik_mv.mv_wisudawan_distribusi_jawaban (no_prodi);
CREATE INDEX idx_mv_wisuda_dist_tahun
    ON analitik_mv.mv_wisudawan_distribusi_jawaban (tahun_ijazah);
CREATE INDEX idx_mv_wisuda_dist_grup_opsi
    ON analitik_mv.mv_wisudawan_distribusi_jawaban (kode_grup_opsi, nilai);
CREATE INDEX idx_mv_wisuda_dist_asumtif
    ON analitik_mv.mv_wisudawan_distribusi_jawaban (is_seremoni_asumtif);

COMMENT ON MATERIALIZED VIEW analitik_mv.mv_wisudawan_distribusi_jawaban IS
    'Base granular MV — 1 baris = 1 (periode_ijazah_id_final, jenjang, kode_fakultas, '
    'no_prodi, kode_pertanyaan, nilai). Mencakup ordinal (tipe_opsi=O) dan nominal (tipe_opsi=N). ';


-- ================================================================
-- MV 2: mv_wisudawan_statistik_pertanyaan
-- Grain: 1 baris = 1 (periode_ijazah_id_final, jenjang, kode_fakultas,
--                      no_prodi, kode_pertanyaan)
-- Hanya tipe_opsi='O' (ordinal/Likert) — nominal tidak boleh di-AVG.
-- ================================================================

CREATE MATERIALIZED VIEW analitik_mv.mv_wisudawan_statistik_pertanyaan AS
WITH

jawaban_numerik AS (
    SELECT
        r.response_id,
        r.kd_strata,
        r.kd_fak,
        r.no_ps,
        r.periode_ijazah_id,
        r.periode_ijazah_id_final,
        p.kd_pertanyaan,
        p.kd_grup_pertanyaan,
        p.kd_grup_opsi,
        (kv.value::TEXT)::NUMERIC   AS nilai
    FROM evaluasi_wisudawan.respons r
    CROSS JOIN LATERAL jsonb_each_text(r.jawaban) kv
    JOIN evaluasi_wisudawan.pertanyaan    p  ON p.kd_pertanyaan = kv.key
    JOIN evaluasi_wisudawan.ref_grup_opsi go ON go.kd_grup_opsi = p.kd_grup_opsi
    WHERE r.jawaban IS NOT NULL
      AND go.tipe = 'O'              -- [FIX-2] ordinal saja — N=nominal tidak boleh di-AVG
      AND kv.value ~ '^[0-9]+(\.[0-9]+)?$'
)

SELECT
    -- ── Periode ijazah (selalu ada, dari respons) ────────────────
    jn.periode_ijazah_id,
    jn.periode_ijazah_id_final,
    EXTRACT(YEAR  FROM lower(pi.tgl_ijazah))::INTEGER  AS tahun_ijazah,
    EXTRACT(MONTH FROM lower(pi.tgl_ijazah))::INTEGER  AS bulan_ijazah,

    -- ── Dimensi seremoni (LEFT JOIN — bisa NULL / masih dummy) ──
    i.periode_seremoni_id,
    EXTRACT(YEAR  FROM lower(s.tgl_seremoni))::INTEGER AS tahun_seremoni,
    EXTRACT(MONTH FROM lower(s.tgl_seremoni))::INTEGER AS bulan_seremoni,
    s.nama->>'id'                   AS nama_seremoni,
    i.is_asumtif                    AS is_seremoni_asumtif,

    -- ── Prodi & Fakultas ──────────────────────────────────────────
    ps.no_ps                        AS no_prodi,
    ps.kd_ps                        AS kode_prodi,
    ps.nama->>'id'                  AS nama_prodi_id,
    ps.nama->>'en'                  AS nama_prodi_en,
    ps.kd_strata                    AS jenjang,
    f.kd_fak                        AS kode_fakultas,
    f.nama->>'id'                   AS nama_fakultas_id,
    f.nama->>'en'                   AS nama_fakultas_en,

    -- ── Pertanyaan & statistik ────────────────────────────────────
    jn.kd_pertanyaan                AS kode_pertanyaan,
    jn.kd_grup_pertanyaan           AS kode_grup_pertanyaan,
    jn.kd_grup_opsi                 AS kode_grup_opsi,
    COUNT(*)                                    AS jumlah_responden,
    ROUND(AVG(jn.nilai)::NUMERIC, 4)            AS rata_rata,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY jn.nilai)::NUMERIC, 4) AS median,
    ROUND(STDDEV(jn.nilai)::NUMERIC, 4)         AS std_dev,
    MIN(jn.nilai)                               AS skor_min,
    MAX(jn.nilai)                               AS skor_max

FROM jawaban_numerik jn
LEFT JOIN evaluasi_wisudawan.ijazah_to_seremoni         i   ON i.periode_ijazah_id_final = jn.periode_ijazah_id_final
LEFT JOIN evaluasi_wisudawan.periode_ijazah_sementara   pi  ON pi.periode_ijazah_id      = jn.periode_ijazah_id_final
LEFT JOIN evaluasi_wisudawan.periode_seremoni_sementara s   ON s.periode_seremoni_id     = i.periode_seremoni_id
JOIN utama.program_studi                                ps  ON ps.no_ps = jn.no_ps
JOIN utama.fakultas                                     f   ON f.kd_fak = ps.kd_fak
GROUP BY
    jn.periode_ijazah_id, jn.periode_ijazah_id_final,
    pi.tgl_ijazah,
    i.periode_seremoni_id, i.is_asumtif, s.tgl_seremoni, s.nama,
    ps.no_ps, ps.kd_ps, ps.nama, ps.kd_strata, ps.kd_fak,
    f.kd_fak, f.nama,
    jn.kd_pertanyaan, jn.kd_grup_pertanyaan, jn.kd_grup_opsi;

-- Index
-- CATATAN: periode_ijazah_id nullable -> REFRESH tanpa CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_wisuda_stat_pk
    ON analitik_mv.mv_wisudawan_statistik_pertanyaan
    (periode_ijazah_id, jenjang, kode_fakultas, no_prodi, kode_pertanyaan);
CREATE INDEX idx_mv_wisuda_stat_fak
    ON analitik_mv.mv_wisudawan_statistik_pertanyaan (jenjang, kode_fakultas, no_prodi);
CREATE INDEX idx_mv_wisuda_stat_grup
    ON analitik_mv.mv_wisudawan_statistik_pertanyaan (kode_grup_pertanyaan);
CREATE INDEX idx_mv_wisuda_stat_asumtif
    ON analitik_mv.mv_wisudawan_statistik_pertanyaan (is_seremoni_asumtif);

COMMENT ON MATERIALIZED VIEW analitik_mv.mv_wisudawan_statistik_pertanyaan IS
    'Aggregate MV — 1 baris = 1 (periode_ijazah_id_final, jenjang, kode_fakultas, '
    'no_prodi, kode_pertanyaan). AVG/MEDIAN/STDDEV/MIN/MAX hanya untuk pertanyaan '
    'ordinal (tipe=O di evaluasi_wisudawan.ref_grup_opsi) — pertanyaan nominal '
    '(tipe=N, mis. U02 alasan rekomendasi) tidak ikut, karena rata-rata kode '
    'kategori tidak bermakna. ';


-- ================================================================
-- MV 3: mv_wisudawan_jawaban_responden
-- Wide table: 1 baris = 1 responden dengan semua jawaban di-pivot
-- ke kolom TEXT (decoded label).
--
-- Perubahan dari draft awal analitik_mv:
--   [+] Tambah i.is_asumtif AS is_seremoni_asumtif
--       (LEFT JOIN ke ijazah_to_seremoni sudah benar di draft awal,
--        hanya kolom flag-nya belum di-expose — ditambahkan agar
--        konsisten dengan mv_wisudawan_distribusi_jawaban dan
--        mv_wisudawan_statistik_pertanyaan, dan agar ketiga MV
--        bisa cross-check menggunakan dimensi yang sama).
--   [=] Seluruh CASE expression (decode numeric -> label teks)
--       dan strip_html() pada kolom teks bebas dipertahankan
--       sesuai draft awal analitik_mv.
-- ================================================================

CREATE MATERIALIZED VIEW analitik_mv.mv_wisudawan_jawaban_responden AS
SELECT
    r.response_id,
    r.survey_platform_response_id,
    r.periode_ijazah_id,
    r.periode_ijazah_id_final,
    EXTRACT(YEAR  FROM lower(pij.tgl_ijazah))::INTEGER          AS tahun_ijazah,
    EXTRACT(MONTH FROM lower(pij.tgl_ijazah))::INTEGER          AS bulan_ijazah,
    its.periode_seremoni_id,
    EXTRACT(YEAR  FROM lower(ser.tgl_seremoni))::INTEGER        AS tahun_seremoni,
    EXTRACT(MONTH FROM lower(ser.tgl_seremoni))::INTEGER        AS bulan_seremoni,
    ser.nama->>'id'                                             AS nama_seremoni,
    its.is_asumtif                                              AS is_seremoni_asumtif,
    r.submit_date,
    ps.no_ps                                                    AS no_prodi,
    ps.kd_ps                                                    AS kode_prodi,
    ps.nama->>'id'                                              AS nama_prodi_id,
    ps.nama->>'en'                                              AS nama_prodi_en,
    r.kd_strata                                                 AS jenjang,
    r.kd_fak                                                    AS kode_fakultas,
    f.nama->>'id'                                               AS nama_fakultas_id,
    f.nama->>'en'                                               AS nama_fakultas_en,

    -- ── U03: Kepuasan terhadap layanan akademik (Tidak–Setuju) ───
    CASE (r.jawaban->>'U03_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u03_sq001,
    CASE (r.jawaban->>'U03_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u03_sq002,
    CASE (r.jawaban->>'U03_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u03_sq003,
    CASE (r.jawaban->>'U03_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u03_sq004,
    CASE (r.jawaban->>'U03_SQ005')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u03_sq005,
    CASE (r.jawaban->>'U03_SQ006')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u03_sq006,
    CASE (r.jawaban->>'U03_SQ007')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u03_sq007,
    CASE (r.jawaban->>'U03_SQ008')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u03_sq008,
    CASE (r.jawaban->>'U03_SQ009')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u03_sq009,
    CASE (r.jawaban->>'U03_SQ010')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u03_sq010,
    CASE (r.jawaban->>'U03_SQ011')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u03_sq011,
    CASE (r.jawaban->>'U03_SQ012')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u03_sq012,

    -- ── U01: Kepuasan terhadap proses pembelajaran (Tidak–Setuju) ─
    CASE (r.jawaban->>'U01_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u01_sq001,
    CASE (r.jawaban->>'U01_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u01_sq002,
    CASE (r.jawaban->>'U01_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u01_sq003,
    CASE (r.jawaban->>'U01_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u01_sq004,
    CASE (r.jawaban->>'U01_SQ005')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u01_sq005,
    CASE (r.jawaban->>'U01_SQ006')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u01_sq006,
    CASE (r.jawaban->>'U01_SQ007')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u01_sq007,
    CASE (r.jawaban->>'U01_SQ008')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u01_sq008,
    CASE (r.jawaban->>'U01_SQ009')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u01_sq009,
    CASE (r.jawaban->>'U01_SQ010')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u01_sq010,
    CASE (r.jawaban->>'U01_SQ011')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u01_sq011,
    CASE (r.jawaban->>'U01_SQ012')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u01_sq012,

    -- ── U02: Alasan merekomendasikan ITB ──────────────────────────
    CASE (r.jawaban->>'U02')::SMALLINT
        WHEN 1 THEN 'Kualitas dosen'
        WHEN 2 THEN 'Suasana akademik'
        WHEN 3 THEN 'Jejaring alumni'
        WHEN 4 THEN 'Lapangan pekerjaan'
        WHEN 5 THEN 'Fasilitas akademik'
        WHEN 6 THEN 'Tidak merekomendasikan'
        WHEN 7 THEN 'Other'
        ELSE NULL
    END AS u02,
    analitik_mv.strip_html(r.jawaban->>'U02_other')             AS u02_other,

    -- ── U04: Kepuasan fasilitas kampus (Tidak–Setuju) ─────────────
    CASE (r.jawaban->>'U04_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u04_sq001,
    CASE (r.jawaban->>'U04_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u04_sq002,
    CASE (r.jawaban->>'U04_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u04_sq003,
    CASE (r.jawaban->>'U04_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u04_sq004,
    CASE (r.jawaban->>'U04_SQ005')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u04_sq005,
    CASE (r.jawaban->>'U04_SQ006')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u04_sq006,
    CASE (r.jawaban->>'U04_SQ007')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u04_sq007,
    CASE (r.jawaban->>'U04_SQ008')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u04_sq008,
    CASE (r.jawaban->>'U04_SQ009')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u04_sq009,

    -- ── U05: Kepuasan pengembangan diri (Tidak–Setuju) ────────────
    CASE (r.jawaban->>'U05_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u05_sq001,
    CASE (r.jawaban->>'U05_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u05_sq002,
    CASE (r.jawaban->>'U05_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u05_sq003,
    CASE (r.jawaban->>'U05_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u05_sq004,
    CASE (r.jawaban->>'U05_SQ005')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u05_sq005,
    CASE (r.jawaban->>'U05_SQ006')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u05_sq006,
    CASE (r.jawaban->>'U05_SQ007')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS u05_sq007,

    -- ── U06: Frekuensi/intensitas kegiatan (Tidak pernah–Selalu) ──
    CASE (r.jawaban->>'U06_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak pernah atau sama sekali tidak'
        WHEN 2 THEN 'Jarang atau kecil'
        WHEN 3 THEN 'Sering atau cukup'
        WHEN 4 THEN 'Selalu atau besar'
        ELSE NULL
    END AS u06_sq001,
    CASE (r.jawaban->>'U06_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak pernah atau sama sekali tidak'
        WHEN 2 THEN 'Jarang atau kecil'
        WHEN 3 THEN 'Sering atau cukup'
        WHEN 4 THEN 'Selalu atau besar'
        ELSE NULL
    END AS u06_sq002,
    CASE (r.jawaban->>'U06_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak pernah atau sama sekali tidak'
        WHEN 2 THEN 'Jarang atau kecil'
        WHEN 3 THEN 'Sering atau cukup'
        WHEN 4 THEN 'Selalu atau besar'
        ELSE NULL
    END AS u06_sq003,
    CASE (r.jawaban->>'U06_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak pernah atau sama sekali tidak'
        WHEN 2 THEN 'Jarang atau kecil'
        WHEN 3 THEN 'Sering atau cukup'
        WHEN 4 THEN 'Selalu atau besar'
        ELSE NULL
    END AS u06_sq004,
    CASE (r.jawaban->>'U06_SQ005')::SMALLINT
        WHEN 1 THEN 'Tidak pernah atau sama sekali tidak'
        WHEN 2 THEN 'Jarang atau kecil'
        WHEN 3 THEN 'Sering atau cukup'
        WHEN 4 THEN 'Selalu atau besar'
        ELSE NULL
    END AS u06_sq005,
    CASE (r.jawaban->>'U06_SQ006')::SMALLINT
        WHEN 1 THEN 'Tidak pernah atau sama sekali tidak'
        WHEN 2 THEN 'Jarang atau kecil'
        WHEN 3 THEN 'Sering atau cukup'
        WHEN 4 THEN 'Selalu atau besar'
        ELSE NULL
    END AS u06_sq006,
    CASE (r.jawaban->>'U06_SQ007')::SMALLINT
        WHEN 1 THEN 'Tidak pernah atau sama sekali tidak'
        WHEN 2 THEN 'Jarang atau kecil'
        WHEN 3 THEN 'Sering atau cukup'
        WHEN 4 THEN 'Selalu atau besar'
        ELSE NULL
    END AS u06_sq007,
    CASE (r.jawaban->>'U06_SQ008')::SMALLINT
        WHEN 1 THEN 'Tidak pernah atau sama sekali tidak'
        WHEN 2 THEN 'Jarang atau kecil'
        WHEN 3 THEN 'Sering atau cukup'
        WHEN 4 THEN 'Selalu atau besar'
        ELSE NULL
    END AS u06_sq008,
    CASE (r.jawaban->>'U06_SQ009')::SMALLINT
        WHEN 1 THEN 'Tidak pernah atau sama sekali tidak'
        WHEN 2 THEN 'Jarang atau kecil'
        WHEN 3 THEN 'Sering atau cukup'
        WHEN 4 THEN 'Selalu atau besar'
        ELSE NULL
    END AS u06_sq009,

    -- ── U07: Kesesuaian dengan harapan ────────────────────────────
    CASE (r.jawaban->>'U07_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Sepenuhnya memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS u07_sq001,
    CASE (r.jawaban->>'U07_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Sepenuhnya memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS u07_sq002,
    CASE (r.jawaban->>'U07_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Sepenuhnya memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS u07_sq003,
    CASE (r.jawaban->>'U07_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Sepenuhnya memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS u07_sq004,

    -- ── G: Teks bebas — [strip_html] ─────────────────────────────
    analitik_mv.strip_html(r.jawaban->>'G10Q22')                AS g10q22,
    analitik_mv.strip_html(r.jawaban->>'G01Q23')                AS g01q23,
    analitik_mv.strip_html(r.jawaban->>'G01Q24')                AS g01q24,
    analitik_mv.strip_html(r.jawaban->>'G01Q25')                AS g01q25,
    analitik_mv.strip_html(r.jawaban->>'G01Q26')                AS g01q26,
    analitik_mv.strip_html(r.jawaban->>'G01Q27')                AS g01q27,
    analitik_mv.strip_html(r.jawaban->>'G01Q28')                AS g01q28,
    analitik_mv.strip_html(r.jawaban->>'G01Q29')                AS g01q29,
    analitik_mv.strip_html(r.jawaban->>'G11Q30')                AS g11q30,
    analitik_mv.strip_html(r.jawaban->>'G01Q31')                AS g01q31,
    analitik_mv.strip_html(r.jawaban->>'G01Q32')                AS g01q32,
    analitik_mv.strip_html(r.jawaban->>'G01Q33')                AS g01q33,
    analitik_mv.strip_html(r.jawaban->>'G01Q34')                AS g01q34,
    analitik_mv.strip_html(r.jawaban->>'G01Q35')                AS g01q35,

    -- ── S: Rencana studi lanjut (S1) ──────────────────────────────
    CASE (r.jawaban->>'S101')::SMALLINT
        WHEN 1 THEN 'Ya'
        WHEN 2 THEN 'Tidak'
        ELSE NULL
    END AS s101,
    CASE (r.jawaban->>'S102')::SMALLINT
        WHEN 1 THEN 'ITB'
        WHEN 2 THEN 'Perguruan tinggi dalam negeri selain ITB'
        WHEN 3 THEN 'Di luar negeri'
        WHEN 4 THEN 'Tidak ada rencana studi lanjut'
        ELSE NULL
    END AS s102,
    CASE (r.jawaban->>'S103')::SMALLINT
        WHEN 1 THEN 'Ya, bidang studi tersebut merupakan kelanjutan dari bidang studi yang baru saya selesaikan di ITB'
        WHEN 2 THEN 'Tidak, tetapi bidang studi tersebut masih serumpun dengan bidang studi yang baru saya selesaikan di ITB'
        WHEN 3 THEN 'Tidak, tetapi bidang studi tersebut masih membutuhkan pengetahuan dari bidang studi yang baru saya selesaikan di ITB'
        WHEN 4 THEN 'Tidak, bidang studi tersebut sangat berbeda dari bidang studi yang baru saya selesaikan di ITB'
        WHEN 5 THEN 'Tidak ada rencana studi lanjut'
        ELSE NULL
    END AS s103,
    CASE (r.jawaban->>'S104_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS s104_sq001,
    CASE (r.jawaban->>'S104_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS s104_sq002,
    CASE (r.jawaban->>'S104_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS s104_sq003,
    CASE (r.jawaban->>'S104_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS s104_sq004,

    -- ── M: Rencana studi lanjut (S2) ──────────────────────────────
    CASE (r.jawaban->>'M01')::SMALLINT
        WHEN 1 THEN 'Ya'
        WHEN 2 THEN 'Tidak'
        ELSE NULL
    END AS m01,
    CASE (r.jawaban->>'M02')::SMALLINT
        WHEN 1 THEN 'ITB'
        WHEN 2 THEN 'Perguruan tinggi dalam negeri selain ITB'
        WHEN 3 THEN 'Di luar negeri'
        WHEN 4 THEN 'Tidak ada rencana studi lanjut'
        ELSE NULL
    END AS m02,
    CASE (r.jawaban->>'M03')::SMALLINT
        WHEN 1 THEN 'Ya, bidang studi tersebut merupakan kelanjutan dari bidang studi yang baru saya selesaikan di ITB'
        WHEN 2 THEN 'Tidak, tetapi bidang studi tersebut masih serumpun dengan bidang studi yang baru saya selesaikan di ITB'
        WHEN 3 THEN 'Tidak, tetapi bidang studi tersebut masih membutuhkan pengetahuan dari bidang studi yang baru saya selesaikan di ITB'
        WHEN 4 THEN 'Tidak, bidang studi tersebut sangat berbeda dari bidang studi yang baru saya selesaikan di ITB'
        WHEN 5 THEN 'Tidak ada rencana studi lanjut'
        ELSE NULL
    END AS m03,

    -- ── D01: Spesifik prodi S3 (Tidak–Setuju) ─────────────────────
    CASE (r.jawaban->>'D01_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS d01_sq001,
    CASE (r.jawaban->>'D01_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS d01_sq002,
    CASE (r.jawaban->>'D01_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS d01_sq003,
    CASE (r.jawaban->>'D01_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak Setuju'
        WHEN 2 THEN 'Cenderung Tidak Setuju'
        WHEN 3 THEN 'Cenderung Setuju'
        WHEN 4 THEN 'Setuju'
        ELSE NULL
    END AS d01_sq004,

    -- ── FSRD01–FSRD05: Spesifik FSRD (Tidak sesuai–Melampaui) ─────
    CASE (r.jawaban->>'FSRD01_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd01_sq001,
    CASE (r.jawaban->>'FSRD01_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd01_sq002,
    CASE (r.jawaban->>'FSRD01_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd01_sq003,
    CASE (r.jawaban->>'FSRD01_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd01_sq004,
    CASE (r.jawaban->>'FSRD01_SQ005')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd01_sq005,
    CASE (r.jawaban->>'FSRD02_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd02_sq001,
    CASE (r.jawaban->>'FSRD02_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd02_sq002,
    CASE (r.jawaban->>'FSRD02_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd02_sq003,
    CASE (r.jawaban->>'FSRD03_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd03_sq001,
    CASE (r.jawaban->>'FSRD03_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd03_sq002,
    CASE (r.jawaban->>'FSRD03_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd03_sq003,
    CASE (r.jawaban->>'FSRD03_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd03_sq004,
    CASE (r.jawaban->>'FSRD03_SQ005')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd03_sq005,
    CASE (r.jawaban->>'FSRD03_SQ006')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd03_sq006,
    CASE (r.jawaban->>'FSRD04_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd04_sq001,
    CASE (r.jawaban->>'FSRD04_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd04_sq002,
    CASE (r.jawaban->>'FSRD04_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd04_sq003,
    CASE (r.jawaban->>'FSRD04_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd04_sq004,
    CASE (r.jawaban->>'FSRD04_SQ005')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd04_sq005,
    CASE (r.jawaban->>'FSRD04_SQ006')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd04_sq006,
    CASE (r.jawaban->>'FSRD05_SQ001')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd05_sq001,
    CASE (r.jawaban->>'FSRD05_SQ002')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd05_sq002,
    CASE (r.jawaban->>'FSRD05_SQ003')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd05_sq003,
    CASE (r.jawaban->>'FSRD05_SQ004')::SMALLINT
        WHEN 1 THEN 'Tidak sesuai harapan'
        WHEN 2 THEN 'Ada yang memenuhi harapan'
        WHEN 3 THEN 'Sebagian besar memenuhi harapan'
        WHEN 4 THEN 'Memenuhi harapan'
        WHEN 5 THEN 'Melampaui harapan'
        ELSE NULL
    END AS fsrd05_sq004,

    -- ── SBM01: Spesifik SBM (Undeveloped–Highly Developed) ────────
    CASE (r.jawaban->>'SBM01_SQ001')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq001,
    CASE (r.jawaban->>'SBM01_SQ002')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq002,
    CASE (r.jawaban->>'SBM01_SQ003')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq003,
    CASE (r.jawaban->>'SBM01_SQ004')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq004,
    CASE (r.jawaban->>'SBM01_SQ005')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq005,
    CASE (r.jawaban->>'SBM01_SQ006')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq006,
    CASE (r.jawaban->>'SBM01_SQ007')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq007,
    CASE (r.jawaban->>'SBM01_SQ008')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq008,
    CASE (r.jawaban->>'SBM01_SQ009')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq009,
    CASE (r.jawaban->>'SBM01_SQ010')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq010,
    CASE (r.jawaban->>'SBM01_SQ011')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq011,
    CASE (r.jawaban->>'SBM01_SQ012')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq012,
    CASE (r.jawaban->>'SBM01_SQ013')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq013,
    CASE (r.jawaban->>'SBM01_SQ014')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq014,
    CASE (r.jawaban->>'SBM01_SQ015')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq015,
    CASE (r.jawaban->>'SBM01_SQ016')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq016,
    CASE (r.jawaban->>'SBM01_SQ017')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq017,
    CASE (r.jawaban->>'SBM01_SQ018')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq018,
    CASE (r.jawaban->>'SBM01_SQ019')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq019,
    CASE (r.jawaban->>'SBM01_SQ020')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq020,
    CASE (r.jawaban->>'SBM01_SQ021')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq021,
    CASE (r.jawaban->>'SBM01_SQ022')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq022,
    CASE (r.jawaban->>'SBM01_SQ023')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq023,
    CASE (r.jawaban->>'SBM01_SQ024')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq024,
    CASE (r.jawaban->>'SBM01_SQ025')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq025,
    CASE (r.jawaban->>'SBM01_SQ026')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq026,
    CASE (r.jawaban->>'SBM01_SQ027')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq027,
    CASE (r.jawaban->>'SBM01_SQ028')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq028,
    CASE (r.jawaban->>'SBM01_SQ029')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq029,
    CASE (r.jawaban->>'SBM01_SQ030')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq030,
    CASE (r.jawaban->>'SBM01_SQ031')::SMALLINT
        WHEN 1 THEN 'Undeveloped – Tidak berkembang'
        WHEN 2 THEN 'Slightly Developed – Sedikit berkembang'
        WHEN 3 THEN 'Moderately Developed – Cukup berkembang'
        WHEN 4 THEN 'Substantially Developed – Berkembang secara substansial'
        WHEN 5 THEN 'Highly Developed – Berkembang dengan sangat tinggi'
        ELSE NULL
    END AS sbm01_sq031

FROM evaluasi_wisudawan.respons                         r
JOIN utama.program_studi                           ps   ON ps.no_ps      = r.no_ps
JOIN utama.fakultas                                f    ON f.kd_fak::TEXT = r.kd_fak::TEXT
LEFT JOIN evaluasi_wisudawan.ijazah_to_seremoni    its  ON its.periode_ijazah_id_final = r.periode_ijazah_id_final
LEFT JOIN evaluasi_wisudawan.periode_seremoni_sementara ser
                                                        ON ser.periode_seremoni_id = its.periode_seremoni_id
LEFT JOIN evaluasi_wisudawan.periode_ijazah_sementara pij
                                                        ON pij.periode_ijazah_id = r.periode_ijazah_id_final
WHERE r.jawaban IS NOT NULL;

-- Index
CREATE UNIQUE INDEX idx_mv_wisuda_jwb_pk
    ON analitik_mv.mv_wisudawan_jawaban_responden (response_id);
CREATE INDEX idx_mv_wisuda_jwb_prodi
    ON analitik_mv.mv_wisudawan_jawaban_responden (no_prodi);
CREATE INDEX idx_mv_wisuda_jwb_fak
    ON analitik_mv.mv_wisudawan_jawaban_responden (jenjang, kode_fakultas, no_prodi);
CREATE INDEX idx_mv_wisuda_jwb_tahun
    ON analitik_mv.mv_wisudawan_jawaban_responden (tahun_ijazah);
CREATE INDEX idx_mv_wisuda_jwb_periode
    ON analitik_mv.mv_wisudawan_jawaban_responden (periode_ijazah_id_final);
CREATE INDEX idx_mv_wisuda_jwb_asumtif
    ON analitik_mv.mv_wisudawan_jawaban_responden (is_seremoni_asumtif);

COMMENT ON MATERIALIZED VIEW analitik_mv.mv_wisudawan_jawaban_responden IS
    '1 baris = 1 responden wisudawan dengan semua jawaban survey di-pivot. ';

COMMENT ON COLUMN analitik_mv.mv_wisudawan_jawaban_responden.is_seremoni_asumtif IS
    'TRUE = pemetaan periode_ijazah_id_final -> periode_seremoni_id pada '
    'evaluasi_wisudawan.ijazah_to_seremoni masih bersifat asumtif/dummy '
    '(default kolom is_asumtif = TRUE). FALSE = pemetaan sudah dikonfirmasi '
    'dengan data seremoni resmi. NULL = belum ada pemetaan sama sekali '
    'untuk periode_ijazah_id_final ini.';


-- ================================================================
-- REFRESH ORDER SCRIPT
-- Simpan sebagai refresh_analitik_mv_wisudawan.sql untuk dijalankan
-- scheduler. Ketiga MV ini tidak saling bergantung (semua sumbernya
-- evaluasi_wisudawan.respons + tabel referensi), jadi urutan antar
-- MV ini bebas — tapi tetap setelah MV akademik lain jika dijalankan
-- dalam satu batch refresh_analitik_mv.sql.
--
-- mv_wisudawan_distribusi_jawaban dan mv_wisudawan_statistik_pertanyaan:
--   JANGAN CONCURRENTLY (periode_ijazah_id nullable).
-- mv_wisudawan_jawaban_responden:
--   Aman CONCURRENTLY (unique index pada response_id, SERIAL not null).
-- ================================================================

-- REFRESH MATERIALIZED VIEW analitik_mv.mv_wisudawan_distribusi_jawaban;
-- REFRESH MATERIALIZED VIEW analitik_mv.mv_wisudawan_statistik_pertanyaan;
-- REFRESH MATERIALIZED VIEW CONCURRENTLY analitik_mv.mv_wisudawan_jawaban_responden;


-- ================================================================
-- CATATAN TAMBAHAN — COMMENT ON COLUMN per pertanyaan (U03, U01, U02,
-- U04, U05, U06, U07, free-text G, S, M, D01, FSRD, SBM01)
--
-- Isi COMMENT ON COLUMN untuk kolom-kolom jawaban di atas IDENTIK
-- dengan dokumentasi pada schema_mv_wisudawan_lama (analitik), karena
-- mapping angka->label, populasi target (strata/fakultas), dan teks
-- pertanyaan tidak berubah pada migrasi ini — hanya nama schema/MV
-- yang berubah dari analitik.mv_wisudawan_jawaban_responden menjadi
-- analitik_mv.mv_wisudawan_jawaban_responden.
--
-- Untuk melengkapi dokumentasi, copy seluruh blok
--   COMMENT ON COLUMN analitik.mv_wisudawan_jawaban_responden.<kolom> IS ...
-- dari schema lama, lalu ganti prefix
--   analitik.mv_wisudawan_jawaban_responden
-- menjadi
--   analitik_mv.mv_wisudawan_jawaban_responden
-- (find & replace satu baris, aman karena nama kolom & isi comment
-- tidak berubah).
-- ================================================================