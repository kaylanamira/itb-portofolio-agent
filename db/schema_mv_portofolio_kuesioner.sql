-- ================================================================
-- SCHEMA: analitik_mv
-- Tujuan: Memisahkan materialized view (raw data) dari schema
--         analitik yang berisi security layer (views + functions).
--
-- TAHAPAN PERANCANGAN:
--   1. Buat schema analitik_mv
--   2. Buat mv_jenis_dan_sifat_matkul (tidak ada dependensi ke MV lain)
--   3. Buat mv_akademik_kelas (bergantung pada mv_jenis_dan_sifat_matkul)
--   4. Buat mv_komentar_mahasiswa (bergantung pada mv_akademik_kelas)
--   5. Buat mv_portofolio (bergantung pada mv_akademik_kelas)
--   6. Buat mv_statistik_prodi (bergantung pada mv_akademik_kelas)
--   7. Buat mv_statistik_dosen (bergantung pada mv_akademik_kelas)
--   8. Buat mv_wisudawan_* (tidak bergantung pada mv_akademik_kelas)
--
-- URUTAN REFRESH (wajib diikuti untuk yang punya dependensi):
--
--   TAHAP 1 — tidak ada dependensi ke MV lain:
--   REFRESH MATERIALIZED VIEW CONCURRENTLY analitik_mv.mv_akademik_jenis_dan_sifat_matkul;
--   REFRESH MATERIALIZED VIEW CONCURRENTLY analitik_mv.mv_akademik_komentar_mahasiswa;
--   REFRESH MATERIALIZED VIEW CONCURRENTLY analitik_mv.mv_akademik_wisudawan_distribusi_jawaban;
--   REFRESH MATERIALIZED VIEW CONCURRENTLY analitik_mv.mv_akademik_wisudawan_jawaban_responden;
--   REFRESH MATERIALIZED VIEW CONCURRENTLY analitik_mv.mv_akademik_wisudawan_statistik_pertanyaan;
--
--   TAHAP 2 — bergantung pada mv_jenis_dan_sifat_matkul (harus setelah tahap 1):
--   REFRESH MATERIALIZED VIEW CONCURRENTLY analitik_mv.mv_akademik_kelas;
--
--   TAHAP 3 — bergantung pada mv_akademik_kelas (harus setelah tahap 2):
--   REFRESH MATERIALIZED VIEW CONCURRENTLY analitik_mv.mv_akademik_portofolio;
--   REFRESH MATERIALIZED VIEW CONCURRENTLY analitik_mv.mv_akademik_statistik_prodi;
--   REFRESH MATERIALIZED VIEW CONCURRENTLY analitik_mv.mv_akademik_statistik_dosen;
--
-- CATATAN:
--   - strip_html() tetap di schema analitik (utility function untuk views juga)
--   - Security Definer Functions dan view wrappers tetap di schema analitik
--   - mv_wisudawan_* menggunakan template — sesuaikan dengan query asli jika ada
-- ================================================================


-- ================================================================
-- STEP 0: Buat schema baru
-- ================================================================

CREATE SCHEMA IF NOT EXISTS analitik_mv;

COMMENT ON SCHEMA analitik_mv IS
    'Materialized view raw — pre-computed aggregations dari schema evaluasi.* (Data Portofolio & Kuesioner Akademik) dan evaluasi_wisudawan.* (Data Ulasan Wisudawan)'
    'dan sumber lainnya. Gunakan view/function di schema analitik sebagai access layer.';


-- ================================================================
-- STEP 1: mv_jenis_dan_sifat_matkul
-- Tidak ada dependensi ke MV lain.
-- Grain: 1 baris = 1 (mata_kuliah_id, no_prodi, paket/struktur)
-- ================================================================

CREATE MATERIALIZED VIEW analitik_mv.mv_akademik_jenis_dan_sifat_matkul AS

-- ── Bagian 1: kurikulum baru (kur24) ─────────────────────────────
SELECT
    pm.mata_kuliah_id,
    p.no_ps                         AS no_prodi,
    ps.kd_ps                        AS kode_prodi,
    ps.kd_strata                    AS jenjang,
    ps.nama->>'id'                  AS nama_prodi_id,
    ps.nama->>'en'                  AS nama_prodi_en,
    ps.kd_fak                       AS kode_fakultas,
    f.nama->>'id'                   AS nama_fakultas_id,
    f.nama->>'en'                   AS nama_fakultas_en,
    p.th_kur                        AS tahun_kurikulum,
    'kurikulum_2024'::TEXT          AS sumber,
    pm.paket_id                     AS paket_id,
    NULL::INTEGER                   AS struktur_id,
    p.kd_jenis                      AS kode_jenis,
    rjp.nama->>'id'                 AS nama_jenis,
    p.nama->>'id'                   AS nama_paket,
    pm.kd_sifat                     AS kode_sifat,
    FALSE                           AS is_wajib_itb
FROM kur24.paket_mk             pm
JOIN kur24.paket                 p   ON p.paket_id    = pm.paket_id
JOIN kur24.ref_jenis_paket       rjp ON rjp.kd_jenis  = p.kd_jenis
JOIN utama.program_studi         ps  ON ps.no_ps       = p.no_ps
JOIN utama.fakultas              f   ON f.kd_fak       = ps.kd_fak

UNION ALL

-- ── Bagian 2: kurikulum lama (kurikulum.*) ───────────────────────
SELECT
    ks.mata_kuliah_id,
    ks.no_ps                        AS no_prodi,
    ps.kd_ps                        AS kode_prodi,
    ps.kd_strata                    AS jenjang,
    ps.nama->>'id'                  AS nama_prodi_id,
    ps.nama->>'en'                  AS nama_prodi_en,
    ps.kd_fak                       AS kode_fakultas,
    f.nama->>'id'                   AS nama_fakultas_id,
    f.nama->>'en'                   AS nama_fakultas_en,
    ks.th_kur                       AS tahun_kurikulum,
    'kurikulum_lama'::TEXT          AS sumber,
    NULL::INTEGER                   AS paket_id,
    ks.struktur_id                  AS struktur_id,
    NULL::CHAR(1)                   AS kode_jenis,
    NULL::TEXT                      AS nama_jenis,
    NULL::TEXT                      AS nama_paket,
    CASE ks.kd_sifat
        WHEN 'W' THEN 'C'
        WHEN 'P' THEN 'E'
        ELSE ks.kd_sifat
    END                             AS kode_sifat,
    (EXISTS (
        SELECT 1 FROM kurikulum.struktur_wajib_itb swi
        WHERE swi.mata_kuliah_id = ks.mata_kuliah_id
          AND swi.no_ps          = ks.no_ps
    ))                              AS is_wajib_itb
FROM kurikulum.struktur          ks
JOIN utama.program_studi         ps  ON ps.no_ps  = ks.no_ps
JOIN utama.fakultas              f   ON f.kd_fak  = ps.kd_fak;

-- Index
CREATE UNIQUE INDEX idx_mv_akademik_jsm_pk
    ON analitik_mv.mv_akademik_jenis_dan_sifat_matkul
    (sumber, mata_kuliah_id, no_prodi, COALESCE(paket_id, struktur_id));
CREATE INDEX idx_mv_akademik_jsm_mk_prodi
    ON analitik_mv.mv_akademik_jenis_dan_sifat_matkul (mata_kuliah_id, no_prodi);
CREATE INDEX idx_mv_akademik_jsm_kode_jenis
    ON analitik_mv.mv_akademik_jenis_dan_sifat_matkul (kode_jenis)
    WHERE kode_jenis IS NOT NULL;
CREATE INDEX idx_mv_akademik_jsm_wajib_itb
    ON analitik_mv.mv_akademik_jenis_dan_sifat_matkul (is_wajib_itb, no_prodi)
    WHERE is_wajib_itb = TRUE;
CREATE INDEX idx_mv_akademik_jsm_th_kur
    ON analitik_mv.mv_akademik_jenis_dan_sifat_matkul (tahun_kurikulum, sumber);
CREATE INDEX idx_mv_akademik_jsm_fak
    ON analitik_mv.mv_akademik_jenis_dan_sifat_matkul (kode_fakultas, kode_jenis);
CREATE INDEX idx_mv_akademik_jsm_fak_jenjang
    ON analitik_mv.mv_akademik_jenis_dan_sifat_matkul (kode_fakultas, jenjang);
CREATE INDEX idx_mv_akademik_jsm_jenjang
    ON analitik_mv.mv_akademik_jenis_dan_sifat_matkul (jenjang, no_prodi);

COMMENT ON MATERIALIZED VIEW analitik_mv.mv_akademik_jenis_dan_sifat_matkul IS
    'Jenis dan sifat MK dalam struktur kurikulum. '
    'Grain: 1 baris = 1 (mata_kuliah_id, no_ps, paket/struktur). '
    'Satu MK bisa >1 baris jika masuk ke >1 paket dalam prodi yang sama. '
    'Sumber: kur24.* (kode_sifat C/E) UNION kurikulum.* (W→C, P→E). '
    'Refresh pertama sebelum mv_akademik_kelas.';


-- ================================================================
-- STEP 2: mv_akademik_kelas
-- Bergantung pada: analitik_mv.mv_akademik_jenis_dan_sifat_matkul
-- Modifikasi dari versi lama:
--   [+] CTE jenis_sifat_agg — agregasi jenis/sifat per matkul+prodi
--   [+] CTE status_nilai    — flag validitas data distribusi nilai
--   [+] 5 kolom jenis/sifat (kode_jenis_list, nama_jenis_list, dll.)
--   [+] Kolom is_distribusi_nilai_sah — flag ETL (true = ada nilai sah)
--   [~] Distribusi nilai: COALESCE kondisional (NULL jika belum ada sah_nilai)
--   [~] jumlah_mahasiswa: tanpa COALESCE (NULL jika belum ada sah_nilai)
-- ================================================================

CREATE MATERIALIZED VIEW analitik_mv.mv_akademik_kelas AS
WITH

-- ── CTE 1: Array dosen per kelas ─────────────────────────────────
dosen_per_kelas AS (
    SELECT
        pk.kelas_id,
        array_agg(d.dosen_id   ORDER BY d.dosen_id) AS semua_dosen_id,
        array_agg(d.nama_gelar ORDER BY d.dosen_id) AS semua_dosen_nama_gelar
    FROM kelas.pengajar pk
    JOIN utama.dosen d ON d.dosen_id = pk.dosen_id
    GROUP BY pk.kelas_id
),

-- ── CTE 2: Distribusi nilai per kelas ────────────────────────────
-- Filter: sah_nilai=true, tidak dihapus, punya kelas_id.
-- Nilai: A,AB,B,BC,C,D,E (ABCDE) | P,F (PassFail) | T = incomplete
distribusi_pivot AS (
    SELECT
        kelas_id,
        COUNT(*) FILTER (WHERE nilai = 'A')  AS dist_jumlah_a,
        COUNT(*) FILTER (WHERE nilai = 'AB') AS dist_jumlah_ab,
        COUNT(*) FILTER (WHERE nilai = 'B')  AS dist_jumlah_b,
        COUNT(*) FILTER (WHERE nilai = 'BC') AS dist_jumlah_bc,
        COUNT(*) FILTER (WHERE nilai = 'C')  AS dist_jumlah_c,
        COUNT(*) FILTER (WHERE nilai = 'D')  AS dist_jumlah_d,
        COUNT(*) FILTER (WHERE nilai = 'E')  AS dist_jumlah_e,
        COUNT(*) FILTER (WHERE nilai = 'T')  AS dist_jumlah_t,
        COUNT(*) FILTER (WHERE nilai = 'P')  AS dist_jumlah_pass,
        COUNT(*) FILTER (WHERE nilai = 'F')  AS dist_jumlah_fail,
        COUNT(*) FILTER (WHERE nilai IS NOT NULL) AS total_mahasiswa
    FROM mahasiswa.kuliah
    WHERE sah_nilai = true
      AND ts_hapus  IS NULL
      AND kelas_id  IS NOT NULL
    GROUP BY kelas_id
),

-- ── CTE 3: Skor kuesioner level kelas ───────────────────────────
skor_kelas_pivot AS (
    SELECT
        nk.kelas_id,
        (nk.kuesioner->>'21')::NUMERIC AS skor_q21,
        (nk.kuesioner->>'22')::NUMERIC AS skor_q22,
        (nk.kuesioner->>'23')::NUMERIC AS skor_q23,
        (nk.kuesioner->>'24')::NUMERIC AS skor_q24,
        (nk.kuesioner->>'28')::NUMERIC AS skor_q28,
        (nk.kuesioner->>'29')::NUMERIC AS skor_q29,
        (nk.kuesioner->>'30')::NUMERIC AS skor_q30,
        (nk.kuesioner->>'35')::NUMERIC AS skor_q35,
        (nk.kuesioner->>'37')::NUMERIC AS skor_q37
    FROM evaluasi.nilai_kelas nk
    WHERE nk.kuesioner IS NOT NULL
      AND nk.kuesioner <> '{}'::jsonb
),

-- ── CTE 4: Skor Q25/Q26/Q27 rata-rata antar dosen per kelas ──────
skor_dosen_avg AS (
    SELECT
        nd.kelas_id,
        AVG((nd.kuesioner->>'25')::NUMERIC) AS skor_q25_avg,
        AVG((nd.kuesioner->>'26')::NUMERIC) AS skor_q26_avg,
        AVG((nd.kuesioner->>'27')::NUMERIC) AS skor_q27_avg
    FROM evaluasi.nilai_dosen nd
    WHERE nd.kuesioner IS NOT NULL
      AND nd.kuesioner <> '{}'::jsonb
      AND nd.kuesioner ? '25'
    GROUP BY nd.kelas_id
),

-- ── CTE 5: Skor dimensi agregat ──────────────────────────────────
skor_dimensi_avg AS (
    SELECT
        nd.kelas_id,
        ROUND(AVG((nd.skor_kues->>'1')::NUMERIC)::NUMERIC, 4) AS avg_skor_capaian,
        ROUND(AVG((nd.skor_kues->>'2')::NUMERIC)::NUMERIC, 4) AS avg_skor_pelaksanaan,
        ROUND(AVG((nd.skor_kues->>'3')::NUMERIC)::NUMERIC, 4) AS avg_skor_perilaku_mahasiswa
    FROM evaluasi.nilai_dosen nd
    WHERE nd.skor_kues IS NOT NULL
      AND nd.skor_kues <> '{}'::jsonb
      AND nd.skor_kues ? '1'
    GROUP BY nd.kelas_id
),

-- ── CTE 6: Skor Q25/Q26/Q27 per dosen (JSONB dict) ──────────────
skor_kues_per_dosen AS (
    SELECT
        nd.kelas_id,
        jsonb_object_agg(nd.dosen_id::TEXT,
            ROUND((nd.kuesioner->>'25')::NUMERIC, 4)
        ) FILTER (WHERE nd.kuesioner ? '25')  AS skor_dosen_q25,
        jsonb_object_agg(nd.dosen_id::TEXT,
            ROUND((nd.kuesioner->>'26')::NUMERIC, 4)
        ) FILTER (WHERE nd.kuesioner ? '26')  AS skor_dosen_q26,
        jsonb_object_agg(nd.dosen_id::TEXT,
            ROUND((nd.kuesioner->>'27')::NUMERIC, 4)
        ) FILTER (WHERE nd.kuesioner ? '27')  AS skor_dosen_q27
    FROM evaluasi.nilai_dosen nd
    WHERE nd.kuesioner IS NOT NULL
      AND nd.kuesioner <> '{}'::jsonb
      AND (nd.kuesioner ? '25' OR nd.kuesioner ? '26' OR nd.kuesioner ? '27')
    GROUP BY nd.kelas_id
),

-- ── CTE 7 : Agregasi jenis & sifat matkul per matkul+prodi ─
-- Pre-aggregate dari mv_jenis_dan_sifat_matkul agar tidak duplikasi
-- baris di main query. Satu matkul bisa masuk >1 paket → array.
jenis_sifat_agg AS (
    SELECT
        mata_kuliah_id,
        no_prodi,
        ARRAY_AGG(DISTINCT kode_jenis ORDER BY kode_jenis) AS kode_jenis_list,
        ARRAY_AGG(DISTINCT nama_jenis ORDER BY nama_jenis) AS nama_jenis_list,
        ARRAY_AGG(DISTINCT nama_paket ORDER BY nama_paket) AS nama_paket_list,
        ARRAY_AGG(DISTINCT kode_sifat ORDER BY kode_sifat) AS kode_sifat_list,
        BOOL_OR(is_wajib_itb)                              AS is_wajib_itb
    FROM analitik_mv.mv_akademik_jenis_dan_sifat_matkul
    GROUP BY mata_kuliah_id, no_prodi
)

SELECT
    -- ── Identitas kelas ──────────────────────────────────────────
    k.kelas_id,
    k.mata_kuliah_id,
    k.no_kelas,
    k.semester,
    k.tahun,
    CASE
        WHEN k.semester IN (2, 3)
            THEN (k.tahun - 1)::TEXT || '/' || k.tahun::TEXT
        ELSE
            k.tahun::TEXT || '/' || (k.tahun + 1)::TEXT
    END                                                     AS tahun_ajaran,

    -- ── Mata kuliah ──────────────────────────────────────────────
    mk.kd_kuliah                                            AS kode_matkul,
    mk.nama->>'id'                                          AS nama_matkul_id,
    mk.nama->>'en'                                          AS nama_matkul_en,
    mk.sks,
    mk.th_kur                                               AS tahun_kurikulum,
    CASE mk.kd_penilaian
        WHEN 'A' THEN 'ABCDE'
        WHEN 'P' THEN 'PassFail'
        ELSE NULL
    END                                                     AS jenis_nilai,

    -- ── Prodi & Fakultas ─────────────────────────────────────────
    ps.no_ps                                                AS no_prodi,
    ps.kd_ps                                                AS kode_prodi,
    ps.nama->>'id'                                          AS nama_prodi_id,
    ps.nama->>'en'                                          AS nama_prodi_en,
    ps.kd_strata                                            AS jenjang,
    f.kd_fak                                                AS kode_fakultas,
    f.nama->>'id'                                           AS nama_fakultas_id,
    f.nama->>'en'                                           AS nama_fakultas_en,

    -- ── Dosen ────────────────────────────────────────────────────
    COALESCE(dpk.semua_dosen_id,         '{}'::INTEGER[])   AS semua_dosen_id,
    COALESCE(dpk.semua_dosen_nama_gelar, '{}'::TEXT[])      AS semua_dosen_nama_gelar,

    -- ── Jenis & Sifat Matkul ──────────────────────────────
    -- Array: satu MK bisa masuk beberapa paket/jenis
    -- NULL jika MK tidak terdaftar di struktur kurikulum manapun
    js.kode_jenis_list,
    js.nama_jenis_list,
    js.nama_paket_list,
    js.kode_sifat_list,
    js.is_wajib_itb,

    -- ── Statistik kelas ──────────────────────────────────────────
    nk.hadir_mhs                                            AS pct_kehadiran_mahasiswa,
    nk.hadir_dosen                                          AS pct_kehadiran_dosen,
    nk.ip_mhs                                               AS avg_ip_akhir_mahasiswa,
    nk.skor_dna,
    nk.ts_dna,
    nk.ip_mhs_dna,

    -- ── Flag validitas distribusi nilai ───────
    -- TRUE  = ada nilai sah → dist_jumlah_* terpercaya (0 berarti memang 0)
    -- FALSE = belum ada nilai sah → dist_jumlah_* NULL (bukan berarti 0)
    (dp.kelas_id IS NOT NULL)                               AS is_distribusi_nilai_sah,

    -- ── Jumlah mahasiswa ─────────────────────────────────────────
    -- NULL jika belum ada nilai sah (bukan 0), sesuai semantik data
    dp.total_mahasiswa::INTEGER                             AS jumlah_mahasiswa,

    -- ── Distribusi nilai ──────────────────────
    -- COALESCE kondisional: 0 hanya jika ada nilai sah (bukan misleading 0)
    -- NULL jika belum ada nilai sah sama sekali
    CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_a,    0) END AS dist_jumlah_a,
    CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_ab,   0) END AS dist_jumlah_ab,
    CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_b,    0) END AS dist_jumlah_b,
    CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_bc,   0) END AS dist_jumlah_bc,
    CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_c,    0) END AS dist_jumlah_c,
    CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_d,    0) END AS dist_jumlah_d,
    CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_e,    0) END AS dist_jumlah_e,
    CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_t,    0) END AS dist_jumlah_t,
    CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_pass, 0) END AS dist_jumlah_pass,
    CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_fail, 0) END AS dist_jumlah_fail,

    -- Persentase distribusi: NULL jika belum ada nilai sah
    ROUND(CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_a,   0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100 END, 2) AS dist_pct_a,
    ROUND(CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_ab,  0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100 END, 2) AS dist_pct_ab,
    ROUND(CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_b,   0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100 END, 2) AS dist_pct_b,
    ROUND(CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_bc,  0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100 END, 2) AS dist_pct_bc,
    ROUND(CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_c,   0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100 END, 2) AS dist_pct_c,
    ROUND(CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_d,   0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100 END, 2) AS dist_pct_d,
    ROUND(CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_e,   0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100 END, 2) AS dist_pct_e,
    ROUND(CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_t,   0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100 END, 2) AS dist_pct_t,
    ROUND(CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_pass,0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100 END, 2) AS dist_pct_pass,
    ROUND(CASE WHEN dp.kelas_id IS NOT NULL THEN COALESCE(dp.dist_jumlah_fail,0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100 END, 2) AS dist_pct_fail,

    CASE mk.kd_penilaian
        WHEN 'A' THEN
            CASE WHEN dp.kelas_id IS NOT NULL THEN
                ROUND((COALESCE(dp.dist_jumlah_a,0) + COALESCE(dp.dist_jumlah_ab,0) +
                       COALESCE(dp.dist_jumlah_b,0) + COALESCE(dp.dist_jumlah_bc,0) +
                       COALESCE(dp.dist_jumlah_c,0))::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100, 2)
            END
        WHEN 'P' THEN
            CASE WHEN dp.kelas_id IS NOT NULL THEN
                ROUND(COALESCE(dp.dist_jumlah_pass,0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100, 2)
            END
        ELSE NULL
    END                                                     AS dist_pct_lulus_a_c,

    CASE mk.kd_penilaian
        WHEN 'A' THEN
            CASE WHEN dp.kelas_id IS NOT NULL THEN
                ROUND((COALESCE(dp.dist_jumlah_a,0) + COALESCE(dp.dist_jumlah_ab,0) +
                       COALESCE(dp.dist_jumlah_b,0) + COALESCE(dp.dist_jumlah_bc,0) +
                       COALESCE(dp.dist_jumlah_c,0) + COALESCE(dp.dist_jumlah_d,0))::NUMERIC
                     / NULLIF(dp.total_mahasiswa,0) * 100, 2)
            END
        WHEN 'P' THEN
            CASE WHEN dp.kelas_id IS NOT NULL THEN
                ROUND(COALESCE(dp.dist_jumlah_pass,0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100, 2)
            END
        ELSE NULL
    END                                                     AS dist_pct_lulus_a_d,

    -- ── Skor kuesioner per pertanyaan ────────────────────────────
    skp.skor_q21, skp.skor_q22, skp.skor_q23, skp.skor_q24,
    ROUND(sda.skor_q25_avg::NUMERIC, 4)                     AS skor_q25,
    ROUND(sda.skor_q26_avg::NUMERIC, 4)                     AS skor_q26,
    ROUND(sda.skor_q27_avg::NUMERIC, 4)                     AS skor_q27,
    skp.skor_q28, skp.skor_q29, skp.skor_q30,
    skp.skor_q35, skp.skor_q37,

    -- ── Skor per dosen (JSONB dict) ──────────────────────────────
    skdp.skor_dosen_q25,
    skdp.skor_dosen_q26,
    skdp.skor_dosen_q27,

    -- ── Skor rata-rata per dimensi ───────────────────────────────
    ROUND(sda2.avg_skor_capaian::NUMERIC,    2)             AS avg_skor_capaian,
    ROUND(sda2.avg_skor_pelaksanaan::NUMERIC, 2)            AS avg_skor_pelaksanaan,
    ROUND(
        (COALESCE(skp.skor_q29, 0) + COALESCE(skp.skor_q30, 0))
        / NULLIF(
            (CASE WHEN skp.skor_q29 IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN skp.skor_q30 IS NOT NULL THEN 1 ELSE 0 END), 0
          )::NUMERIC, 2
    )                                                       AS avg_skor_sarana_prasarana,
    ROUND(sda2.avg_skor_perilaku_mahasiswa::NUMERIC, 2)     AS avg_skor_perilaku_mahasiswa,
    ROUND(
        (COALESCE(skp.skor_q21,     0) + COALESCE(skp.skor_q22,     0) +
         COALESCE(skp.skor_q23,     0) + COALESCE(skp.skor_q24,     0) +
         COALESCE(sda.skor_q25_avg, 0) + COALESCE(sda.skor_q26_avg, 0) +
         COALESCE(sda.skor_q27_avg, 0) + COALESCE(skp.skor_q28,     0) +
         COALESCE(skp.skor_q29,     0) + COALESCE(skp.skor_q30,     0) +
         COALESCE(skp.skor_q35,     0) + COALESCE(skp.skor_q37,     0))
        / NULLIF(
            (CASE WHEN skp.skor_q21     IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN skp.skor_q22     IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN skp.skor_q23     IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN skp.skor_q24     IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN sda.skor_q25_avg IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN sda.skor_q26_avg IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN sda.skor_q27_avg IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN skp.skor_q28     IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN skp.skor_q29     IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN skp.skor_q30     IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN skp.skor_q35     IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN skp.skor_q37     IS NOT NULL THEN 1 ELSE 0 END), 0
          )::NUMERIC, 2
    )                                                       AS avg_skor_overall

FROM kelas.kelas k
JOIN utama.mata_kuliah    mk   ON mk.mata_kuliah_id = k.mata_kuliah_id
JOIN utama.program_studi  ps   ON ps.no_ps          = k.no_ps
JOIN utama.fakultas       f    ON f.kd_fak          = ps.kd_fak
LEFT JOIN dosen_per_kelas           dpk  ON dpk.kelas_id  = k.kelas_id
LEFT JOIN evaluasi.nilai_kelas      nk   ON nk.kelas_id   = k.kelas_id
LEFT JOIN distribusi_pivot          dp   ON dp.kelas_id   = k.kelas_id
LEFT JOIN skor_kelas_pivot          skp  ON skp.kelas_id  = k.kelas_id
LEFT JOIN skor_dosen_avg            sda  ON sda.kelas_id  = k.kelas_id
LEFT JOIN skor_dimensi_avg          sda2 ON sda2.kelas_id = k.kelas_id
LEFT JOIN skor_kues_per_dosen       skdp ON skdp.kelas_id = k.kelas_id
LEFT JOIN jenis_sifat_agg           js   ON js.mata_kuliah_id = k.mata_kuliah_id
                                        AND js.no_prodi     = ps.no_ps
WHERE (
    -- semester 1: tahun >= 2018 → tahun_ajaran >= '2018/2019'
    (k.semester = 1 AND k.tahun >= 2018)
    OR
    -- semester 2: tahun >= 2019 → tahun_ajaran >= '2018/2019'
    (k.semester = 2 AND k.tahun >= 2019)
    OR
    -- semester 3 (pendek): tahun >= 2019 → tahun_ajaran >= '2018/2019'
    (k.semester = 3 AND k.tahun >= 2019)
);

-- Index
CREATE UNIQUE INDEX idx_mv_akademik_kelas_pk
    ON analitik_mv.mv_akademik_kelas (kelas_id);
CREATE INDEX idx_mv_akademik_kelas_prodi_sem
    ON analitik_mv.mv_akademik_kelas (no_prodi, semester, tahun);
CREATE INDEX idx_mv_akademik_kelas_fak_sem
    ON analitik_mv.mv_akademik_kelas (kode_fakultas, semester, tahun);
CREATE INDEX idx_mv_akademik_kelas_matkul_sem
    ON analitik_mv.mv_akademik_kelas (kode_matkul, semester, tahun);
CREATE INDEX idx_mv_akademik_kelas_matkul_tahun_ajaran
    ON analitik_mv.mv_akademik_kelas (kode_matkul, tahun_ajaran);
CREATE INDEX idx_mv_akademik_kelas_tahun_ajaran
    ON analitik_mv.mv_akademik_kelas (tahun_ajaran, no_prodi);
CREATE INDEX idx_mv_akademik_kelas_dosen_arr
    ON analitik_mv.mv_akademik_kelas USING GIN (semua_dosen_id);
CREATE INDEX idx_mv_akademik_kelas_skor_dosen_q25
    ON analitik_mv.mv_akademik_kelas USING GIN (skor_dosen_q25);
CREATE INDEX idx_mv_akademik_kelas_skor_dosen_q26
    ON analitik_mv.mv_akademik_kelas USING GIN (skor_dosen_q26);
CREATE INDEX idx_mv_akademik_kelas_skor_dosen_q27
    ON analitik_mv.mv_akademik_kelas USING GIN (skor_dosen_q27);
CREATE INDEX idx_mv_akademik_kelas_jenis_list
    ON analitik_mv.mv_akademik_kelas USING GIN (kode_jenis_list);
CREATE INDEX idx_mv_akademik_kelas_distribusi_tersedia
    ON analitik_mv.mv_akademik_kelas (is_distribusi_nilai_sah)
    WHERE is_distribusi_nilai_sah = TRUE;

COMMENT ON MATERIALIZED VIEW analitik_mv.mv_akademik_kelas IS
    '1 baris = 1 kelas. Semua dimensi ter-flatten. '
    'Periode: 2018/2019 semester 1 s.d. terkini. '
    'Refresh setelah mv_jenis_dan_sifat_matkul.';

COMMENT ON COLUMN analitik_mv.mv_akademik_kelas.is_distribusi_nilai_sah IS
    'TRUE = ada mahasiswa.kuliah dengan sah_nilai=true untuk kelas ini. '
    'FALSE/NULL = belum ada nilai yang disahkan (late arriving fact). '
    'Jika FALSE, kolom dist_jumlah_* dan dist_pct_* bernilai NULL bukan berarti tidak ada yang dapat nilai A, melainkan data belum tersedia.';

-- ================================================================
-- STEP 3: mv_komentar_mahasiswa
-- TIDAK bergantung pada mv_akademik_kelas — query langsung ke tabel base.
-- Sumber: evaluasi.jwb_kuesioner, kelas.kelas, utama.*
-- Komentar diambil dari jawaban JSONB key '103'.
-- Filter: k.open = true (hanya kelas yang sudah terbuka evaluasinya)
-- Catatan nama kolom: kode_matkul (bukan kode_matkul), nama_matkul_id (bukan nama_matkul_id)
-- ================================================================

CREATE MATERIALIZED VIEW analitik_mv.mv_akademik_komentar_mahasiswa AS
SELECT
    jk.jawaban_id,
    jk.kelas_id,
    k.tahun,
    k.semester,
    CASE
        WHEN k.semester = ANY (ARRAY[2, 3])
            THEN ((k.tahun - 1)::TEXT || '/' || k.tahun::TEXT)
        ELSE
            (k.tahun::TEXT || '/' || (k.tahun + 1)::TEXT)
    END                                     AS tahun_ajaran,
    mk.kd_kuliah                            AS kode_matkul,
    mk.nama->>'id'                          AS nama_matkul_id,
    mk.nama->>'en'                          AS nama_matkul_en,
    mk.sks,
    k.no_kelas,
    ps.no_ps                                AS no_prodi,
    ps.kd_ps                                AS kode_prodi,
    ps.nama->>'id'                          AS nama_prodi_id,
    ps.kd_strata                            AS jenjang,
    f.kd_fak                                AS kode_fakultas,
    f.nama->>'id'                           AS nama_fakultas_id,
    d.semua_dosen_id,
    d.semua_dosen_nama_gelar,
    analitik_mv.strip_html(jk.jawaban->>'103')  AS komentar_teks,
    jk.ts_entry                             AS ts_jawaban
FROM evaluasi.jwb_kuesioner jk
JOIN kelas.kelas                k   ON k.kelas_id          = jk.kelas_id
JOIN utama.mata_kuliah          mk  ON mk.mata_kuliah_id    = k.mata_kuliah_id
JOIN utama.program_studi        ps  ON ps.no_ps             = k.no_ps
JOIN utama.fakultas             f   ON f.kd_fak::TEXT       = ps.kd_fak::TEXT
LEFT JOIN LATERAL (
    SELECT
        array_agg(kp.dosen_id  ORDER BY kp.utama DESC, kp.weight) AS semua_dosen_id,
        array_agg(d2.nama_gelar ORDER BY kp.utama DESC, kp.weight) AS semua_dosen_nama_gelar
    FROM kelas.pengajar kp
    JOIN utama.dosen d2 ON d2.dosen_id = kp.dosen_id
    WHERE kp.kelas_id = k.kelas_id
) d ON TRUE
WHERE (jk.jawaban->>'103') IS NOT NULL
  AND (jk.jawaban->>'103') <> ''
  AND (
      (k.semester = 1 AND k.tahun >= 2018)
      OR
      (k.semester IN (2, 3) AND k.tahun >= 2019)
  );

COMMENT ON MATERIALIZED VIEW analitik_mv.mv_akademik_komentar_mahasiswa IS
    '1 baris = 1 jawaban komentar teks mahasiswa per kelas. '
    'Komentar diambil dari evaluasi.jwb_kuesioner.jawaban key ''103''. '
    'Periode: 2018/2019 semester 1 s.d. terkini. ';

-- Index
CREATE INDEX idx_mv_komentar_kelas
    ON analitik_mv.mv_akademik_komentar_mahasiswa (kelas_id);
CREATE INDEX idx_mv_komentar_tahun_ajaran
    ON analitik_mv.mv_akademik_komentar_mahasiswa (tahun_ajaran, no_prodi);
CREATE INDEX idx_mv_komentar_dosen_arr
    ON analitik_mv.mv_akademik_komentar_mahasiswa USING GIN (semua_dosen_id);
CREATE INDEX idx_mv_komentar_prodi_semester
    ON analitik_mv.mv_akademik_komentar_mahasiswa (no_prodi, tahun, semester);
CREATE INDEX idx_mv_komentar_fak_semester
    ON analitik_mv.mv_akademik_komentar_mahasiswa (kode_fakultas, tahun, semester);


CREATE OR REPLACE FUNCTION analitik_mv.strip_html(raw text)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT NULLIF(
        trim(
            regexp_replace(
                regexp_replace(
                    regexp_replace(
                        regexp_replace(raw, '<br\s*/?>', ' ', 'gi'),
                    '<[^>]+>', ' ', 'g'),
                '&amp;|&lt;|&gt;|&quot;|&apos;|&nbsp;|&#[0-9]+;|&[a-z]{2,6};',
                ' ', 'gi'),
            '\s+', ' ', 'g')
        ),
    '');
$$;
 
COMMENT ON FUNCTION analitik_mv.strip_html(text) IS 'Strip HTML tags dan decode entitas HTML  menjadi teks plain. ';


-- ================================================================
-- STEP 4: mv_portofolio
-- Bergantung pada: analitik_mv.mv_akademik_kelas
-- Perubahan: referensi analitik.mv_akademik_kelas → analitik_mv.mv_akademik_kelas
-- strip_html() tetap di schema analitik
-- ================================================================

CREATE MATERIALIZED VIEW analitik_mv.mv_akademik_portofolio AS
WITH
raw AS (
    SELECT
        p.kelas_id,
        p.tgl_entri,
        p.lengkap,
        p.nilai                  AS nilai_portofolio,
        p.isian->>'12' AS r12, p.isian->>'13' AS r13,
        p.isian->>'14' AS r14, p.isian->>'15' AS r15,
        p.isian->>'16' AS r16, p.isian->>'17' AS r17,
        p.isian->>'18' AS r18, p.isian->>'19' AS r19,
        p.komentar->>'6' AS k6, p.komentar->>'7' AS k7,
        p.komentar->>'8' AS k8, p.komentar->>'9' AS k9
    FROM evaluasi.portofolio p
    WHERE p.isian IS NOT NULL
      AND p.isian <> '{}'::jsonb
      AND (
          p.isian ? '12' OR p.isian ? '13' OR p.isian ? '14' OR
          p.isian ? '15' OR p.isian ? '16' OR p.isian ? '17' OR
          p.isian ? '18' OR p.isian ? '19'
      )
)
SELECT
    mk.kelas_id,
    mk.kode_matkul,
    mk.nama_matkul_id,
    mk.nama_matkul_en,
    mk.sks,
    mk.no_kelas,
    mk.semester,
    mk.tahun,
    mk.tahun_ajaran,
    mk.tahun_kurikulum,
    mk.jenis_nilai,
    mk.no_prodi,
    mk.kode_prodi,
    mk.nama_prodi_id,
    mk.nama_prodi_en,
    mk.jenjang,
    mk.kode_fakultas,
    mk.nama_fakultas_id,
    mk.nama_fakultas_en,
    mk.semua_dosen_id,
    mk.semua_dosen_nama_gelar,
    r.tgl_entri                             AS tanggal_entri,
    r.lengkap,
    r.nilai_portofolio,
    analitik_mv.strip_html(r.r12)              AS metode_perkuliahan,
    analitik_mv.strip_html(r.r13)              AS sistem_penilaian,
    analitik_mv.strip_html(r.r14)              AS statistik_kelas,
    analitik_mv.strip_html(r.r15)              AS analisis_terhadap_statistik_kelas_dan_ketercapaian_outcomes,
    analitik_mv.strip_html(r.r16)              AS komentar_terhadap_hasil_kuesioner_mahasiswa,
    analitik_mv.strip_html(r.r17)              AS refleksi_pelaksanaan_perkuliahan,
    analitik_mv.strip_html(r.r18)              AS usulan_perbaikan_oleh_dosen_berikutnya,
    analitik_mv.strip_html(r.r19)              AS usulan_perbaikan_oleh_itb,
    analitik_mv.strip_html(r.k6)               AS verifikator_penyelenggaraan_perkuliahan,
    analitik_mv.strip_html(r.k7)               AS verifikator_ketercapaian_outcomes,
    analitik_mv.strip_html(r.k8)               AS verifikator_refleksi_dosen,
    analitik_mv.strip_html(r.k9)               AS verifikator_rekomendasi_tindak_lanjut
FROM raw r
JOIN analitik_mv.mv_akademik_kelas mk ON mk.kelas_id = r.kelas_id;

COMMENT ON MATERIALIZED VIEW analitik_mv.mv_akademik_portofolio IS
    'Portofolio dosen per kelas : refleksi, analisis, dan rekomendasi pengajaran. '
    'Grain        : 1 baris = 1 kelas (hanya kelas dengan portofolio terisi). '
    'Skema        : hanya pertanyaan baru (kd_pertanyaan 12–19). ';

-- Index
CREATE UNIQUE INDEX idx_mv_portofolio_pk
    ON analitik_mv.mv_akademik_portofolio (kelas_id);
CREATE INDEX idx_mv_portofolio_tahun_ajaran
    ON analitik_mv.mv_akademik_portofolio (tahun_ajaran, no_prodi);
CREATE INDEX idx_mv_portofolio_matkul
    ON analitik_mv.mv_akademik_portofolio (kode_matkul, tahun_ajaran);
CREATE INDEX idx_mv_portofolio_dosen_arr
    ON analitik_mv.mv_akademik_portofolio USING GIN (semua_dosen_id);
CREATE INDEX idx_mv_portofolio_fak_semester
    ON analitik_mv.mv_akademik_portofolio (kode_fakultas, semester, tahun);
CREATE INDEX idx_mv_portofolio_fak_jenjang
    ON analitik_mv.mv_akademik_portofolio (kode_fakultas, jenjang, tahun, semester);

-- ================================================================
-- STEP 5: mv_statistik_prodi
-- Bergantung pada: analitik_mv.mv_akademik_kelas
-- Catatan: SUM dari dist_jumlah_* sekarang mengabaikan NULL
-- (kelas tanpa nilai sah tidak ikut dihitung) — ini behavior yang lebih akurat
-- ================================================================

CREATE MATERIALIZED VIEW analitik_mv.mv_akademik_statistik_prodi AS
WITH

mhs_aktif_per_prodi AS (
    SELECT
        mhs.no_ps,
        st.tahun,
        st.semester,
        COUNT(DISTINCT st.mahasiswa_id) AS jumlah_mahasiswa_aktif
    FROM mahasiswa.status  st
    JOIN utama.mahasiswa   mhs ON mhs.mahasiswa_id = st.mahasiswa_id
    WHERE st.ts_daftar IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM mahasiswa.nonaktif na
          WHERE na.mahasiswa_id = st.mahasiswa_id
            AND na.tahun        = st.tahun
            AND na.semester     = st.semester
      )
      AND (
          (st.semester = 1 AND st.tahun >= 2018)
          OR
          (st.semester IN (2, 3) AND st.tahun >= 2019)
      )
    GROUP BY mhs.no_ps, st.tahun, st.semester
)

SELECT
    mv.no_prodi,
    mv.kode_prodi,
    mv.nama_prodi_id,
    mv.nama_prodi_en,
    mv.jenjang,
    mv.kode_fakultas,
    mv.nama_fakultas_id,
    mv.nama_fakultas_en,
    mv.semester,
    mv.tahun,
    mv.tahun_ajaran,

    COUNT(DISTINCT mv.kelas_id)                                 AS jumlah_kelas,
    COUNT(DISTINCT mv.mata_kuliah_id)                           AS jumlah_matkul_aktif,
    COUNT(DISTINCT u.dosen_id)                                  AS jumlah_dosen_aktif,
    COALESCE(map.jumlah_mahasiswa_aktif, 0)                     AS jumlah_mahasiswa_aktif,

    ROUND(AVG(mv.pct_kehadiran_dosen)::NUMERIC,           2)    AS avg_pct_kehadiran_dosen,
    ROUND(AVG(mv.pct_kehadiran_mahasiswa)::NUMERIC,       2)    AS avg_pct_kehadiran_mahasiswa,
    ROUND(AVG(mv.avg_ip_akhir_mahasiswa)::NUMERIC,       3)    AS avg_ip_akhir_mahasiswa,

    -- SUM mengabaikan NULL — kelas tanpa nilai sah tidak ikut dihitung
    SUM(mv.dist_jumlah_a)                                       AS total_jumlah_a,
    SUM(mv.dist_jumlah_ab)                                      AS total_jumlah_ab,
    SUM(mv.dist_jumlah_b)                                       AS total_jumlah_b,
    SUM(mv.dist_jumlah_bc)                                      AS total_jumlah_bc,
    SUM(mv.dist_jumlah_c)                                       AS total_jumlah_c,
    SUM(mv.dist_jumlah_d)                                       AS total_jumlah_d,
    SUM(mv.dist_jumlah_e)                                       AS total_jumlah_e,
    SUM(mv.dist_jumlah_t)                                       AS total_jumlah_t,
    SUM(mv.dist_jumlah_pass)                                    AS total_jumlah_pass,
    SUM(mv.dist_jumlah_fail)                                    AS total_jumlah_fail,
    SUM(COALESCE(mv.dist_jumlah_a,0) + COALESCE(mv.dist_jumlah_ab,0) +
        COALESCE(mv.dist_jumlah_b,0) + COALESCE(mv.dist_jumlah_bc,0) +
        COALESCE(mv.dist_jumlah_c,0) + COALESCE(mv.dist_jumlah_d,0) +
        COALESCE(mv.dist_jumlah_e,0) + COALESCE(mv.dist_jumlah_t,0) + COALESCE(mv.dist_jumlah_pass,0) +
        COALESCE(mv.dist_jumlah_fail,0))
        FILTER (WHERE mv.is_distribusi_nilai_sah)                AS total_mahasiswa_dinilai,

    ROUND(SUM(mv.dist_jumlah_a)::NUMERIC    / NULLIF(SUM(COALESCE(mv.dist_jumlah_a,0)+COALESCE(mv.dist_jumlah_ab,0)+COALESCE(mv.dist_jumlah_b,0)+COALESCE(mv.dist_jumlah_bc,0)+COALESCE(mv.dist_jumlah_c,0)+COALESCE(mv.dist_jumlah_d,0)+COALESCE(mv.dist_jumlah_e,0)+COALESCE(mv.dist_jumlah_t,0)+COALESCE(mv.dist_jumlah_pass,0)+COALESCE(mv.dist_jumlah_fail,0)) FILTER (WHERE mv.is_distribusi_nilai_sah),0)*100,2) AS dist_pct_a,
    ROUND(SUM(mv.dist_jumlah_ab)::NUMERIC   / NULLIF(SUM(COALESCE(mv.dist_jumlah_a,0)+COALESCE(mv.dist_jumlah_ab,0)+COALESCE(mv.dist_jumlah_b,0)+COALESCE(mv.dist_jumlah_bc,0)+COALESCE(mv.dist_jumlah_c,0)+COALESCE(mv.dist_jumlah_d,0)+COALESCE(mv.dist_jumlah_e,0)+COALESCE(mv.dist_jumlah_t,0)+COALESCE(mv.dist_jumlah_pass,0)+COALESCE(mv.dist_jumlah_fail,0)) FILTER (WHERE mv.is_distribusi_nilai_sah),0)*100,2) AS dist_pct_ab,
    ROUND(SUM(mv.dist_jumlah_b)::NUMERIC    / NULLIF(SUM(COALESCE(mv.dist_jumlah_a,0)+COALESCE(mv.dist_jumlah_ab,0)+COALESCE(mv.dist_jumlah_b,0)+COALESCE(mv.dist_jumlah_bc,0)+COALESCE(mv.dist_jumlah_c,0)+COALESCE(mv.dist_jumlah_d,0)+COALESCE(mv.dist_jumlah_e,0)+COALESCE(mv.dist_jumlah_t,0)+COALESCE(mv.dist_jumlah_pass,0)+COALESCE(mv.dist_jumlah_fail,0)) FILTER (WHERE mv.is_distribusi_nilai_sah),0)*100,2) AS dist_pct_b,
    ROUND(SUM(mv.dist_jumlah_bc)::NUMERIC   / NULLIF(SUM(COALESCE(mv.dist_jumlah_a,0)+COALESCE(mv.dist_jumlah_ab,0)+COALESCE(mv.dist_jumlah_b,0)+COALESCE(mv.dist_jumlah_bc,0)+COALESCE(mv.dist_jumlah_c,0)+COALESCE(mv.dist_jumlah_d,0)+COALESCE(mv.dist_jumlah_e,0)+COALESCE(mv.dist_jumlah_t,0)+COALESCE(mv.dist_jumlah_pass,0)+COALESCE(mv.dist_jumlah_fail,0)) FILTER (WHERE mv.is_distribusi_nilai_sah),0)*100,2) AS dist_pct_bc,
    ROUND(SUM(mv.dist_jumlah_c)::NUMERIC    / NULLIF(SUM(COALESCE(mv.dist_jumlah_a,0)+COALESCE(mv.dist_jumlah_ab,0)+COALESCE(mv.dist_jumlah_b,0)+COALESCE(mv.dist_jumlah_bc,0)+COALESCE(mv.dist_jumlah_c,0)+COALESCE(mv.dist_jumlah_d,0)+COALESCE(mv.dist_jumlah_e,0)+COALESCE(mv.dist_jumlah_t,0)+COALESCE(mv.dist_jumlah_pass,0)+COALESCE(mv.dist_jumlah_fail,0)) FILTER (WHERE mv.is_distribusi_nilai_sah),0)*100,2) AS dist_pct_c,
    ROUND(SUM(mv.dist_jumlah_d)::NUMERIC    / NULLIF(SUM(COALESCE(mv.dist_jumlah_a,0)+COALESCE(mv.dist_jumlah_ab,0)+COALESCE(mv.dist_jumlah_b,0)+COALESCE(mv.dist_jumlah_bc,0)+COALESCE(mv.dist_jumlah_c,0)+COALESCE(mv.dist_jumlah_d,0)+COALESCE(mv.dist_jumlah_e,0)+COALESCE(mv.dist_jumlah_t,0)+COALESCE(mv.dist_jumlah_pass,0)+COALESCE(mv.dist_jumlah_fail,0)) FILTER (WHERE mv.is_distribusi_nilai_sah),0)*100,2) AS dist_pct_d,
    ROUND(SUM(mv.dist_jumlah_e)::NUMERIC    / NULLIF(SUM(COALESCE(mv.dist_jumlah_a,0)+COALESCE(mv.dist_jumlah_ab,0)+COALESCE(mv.dist_jumlah_b,0)+COALESCE(mv.dist_jumlah_bc,0)+COALESCE(mv.dist_jumlah_c,0)+COALESCE(mv.dist_jumlah_d,0)+COALESCE(mv.dist_jumlah_e,0)+COALESCE(mv.dist_jumlah_t,0)+COALESCE(mv.dist_jumlah_pass,0)+COALESCE(mv.dist_jumlah_fail,0)) FILTER (WHERE mv.is_distribusi_nilai_sah),0)*100,2) AS dist_pct_e,
    ROUND(SUM(mv.dist_jumlah_t)::NUMERIC    / NULLIF(SUM(COALESCE(mv.dist_jumlah_a,0)+COALESCE(mv.dist_jumlah_ab,0)+COALESCE(mv.dist_jumlah_b,0)+COALESCE(mv.dist_jumlah_bc,0)+COALESCE(mv.dist_jumlah_c,0)+COALESCE(mv.dist_jumlah_d,0)+COALESCE(mv.dist_jumlah_e,0)+COALESCE(mv.dist_jumlah_t,0)+COALESCE(mv.dist_jumlah_pass,0)+COALESCE(mv.dist_jumlah_fail,0)) FILTER (WHERE mv.is_distribusi_nilai_sah),0)*100,2) AS dist_pct_t,
    ROUND(SUM(mv.dist_jumlah_pass)::NUMERIC / NULLIF(SUM(COALESCE(mv.dist_jumlah_a,0)+COALESCE(mv.dist_jumlah_ab,0)+COALESCE(mv.dist_jumlah_b,0)+COALESCE(mv.dist_jumlah_bc,0)+COALESCE(mv.dist_jumlah_c,0)+COALESCE(mv.dist_jumlah_d,0)+COALESCE(mv.dist_jumlah_e,0)+COALESCE(mv.dist_jumlah_t,0)+COALESCE(mv.dist_jumlah_pass,0)+COALESCE(mv.dist_jumlah_fail,0)) FILTER (WHERE mv.is_distribusi_nilai_sah),0)*100,2) AS dist_pct_pass,
    ROUND(SUM(mv.dist_jumlah_fail)::NUMERIC / NULLIF(SUM(COALESCE(mv.dist_jumlah_a,0)+COALESCE(mv.dist_jumlah_ab,0)+COALESCE(mv.dist_jumlah_b,0)+COALESCE(mv.dist_jumlah_bc,0)+COALESCE(mv.dist_jumlah_c,0)+COALESCE(mv.dist_jumlah_d,0)+COALESCE(mv.dist_jumlah_e,0)+COALESCE(mv.dist_jumlah_t,0)+COALESCE(mv.dist_jumlah_pass,0)+COALESCE(mv.dist_jumlah_fail,0)) FILTER (WHERE mv.is_distribusi_nilai_sah),0)*100,2) AS dist_pct_fail,

    ROUND((SUM(COALESCE(mv.dist_jumlah_a,0)+COALESCE(mv.dist_jumlah_ab,0)+COALESCE(mv.dist_jumlah_b,0)+COALESCE(mv.dist_jumlah_bc,0)+COALESCE(mv.dist_jumlah_c,0)) FILTER (WHERE mv.is_distribusi_nilai_sah))::NUMERIC
        / NULLIF(SUM(COALESCE(mv.dist_jumlah_a,0)+COALESCE(mv.dist_jumlah_ab,0)+COALESCE(mv.dist_jumlah_b,0)+COALESCE(mv.dist_jumlah_bc,0)+COALESCE(mv.dist_jumlah_c,0)+COALESCE(mv.dist_jumlah_d,0)+COALESCE(mv.dist_jumlah_e,0)+COALESCE(mv.dist_jumlah_t,0)+COALESCE(mv.dist_jumlah_pass,0)+COALESCE(mv.dist_jumlah_fail,0)) FILTER (WHERE mv.is_distribusi_nilai_sah),0)*100,2) AS dist_pct_lulus_a_c,

    ROUND((SUM(COALESCE(mv.dist_jumlah_a,0)+COALESCE(mv.dist_jumlah_ab,0)+COALESCE(mv.dist_jumlah_b,0)+COALESCE(mv.dist_jumlah_bc,0)+COALESCE(mv.dist_jumlah_c,0)+COALESCE(mv.dist_jumlah_d,0)) FILTER (WHERE mv.is_distribusi_nilai_sah))::NUMERIC
        / NULLIF(SUM(COALESCE(mv.dist_jumlah_a,0)+COALESCE(mv.dist_jumlah_ab,0)+COALESCE(mv.dist_jumlah_b,0)+COALESCE(mv.dist_jumlah_bc,0)+COALESCE(mv.dist_jumlah_c,0)+COALESCE(mv.dist_jumlah_d,0)+COALESCE(mv.dist_jumlah_e,0)+COALESCE(mv.dist_jumlah_t,0)+COALESCE(mv.dist_jumlah_pass,0)+COALESCE(mv.dist_jumlah_fail,0)) FILTER (WHERE mv.is_distribusi_nilai_sah),0)*100,2) AS dist_pct_lulus_a_d,

    ROUND(AVG(mv.skor_q21)::NUMERIC,     4) AS avg_skor_q21,
    ROUND(AVG(mv.skor_q22)::NUMERIC,     4) AS avg_skor_q22,
    ROUND(AVG(mv.skor_q23)::NUMERIC,     4) AS avg_skor_q23,
    ROUND(AVG(mv.skor_q24)::NUMERIC,     4) AS avg_skor_q24,
    ROUND(AVG(mv.skor_q25)::NUMERIC, 4) AS avg_skor_q25,
    ROUND(AVG(mv.skor_q26)::NUMERIC, 4) AS avg_skor_q26,
    ROUND(AVG(mv.skor_q27)::NUMERIC, 4) AS avg_skor_q27,
    ROUND(AVG(mv.skor_q28)::NUMERIC,     4) AS avg_skor_q28,
    ROUND(AVG(mv.skor_q29)::NUMERIC,     4) AS avg_skor_q29,
    ROUND(AVG(mv.skor_q30)::NUMERIC,     4) AS avg_skor_q30,
    ROUND(AVG(mv.skor_q35)::NUMERIC,     4) AS avg_skor_q35,
    ROUND(AVG(mv.skor_q37)::NUMERIC,     4) AS avg_skor_q37,

    ROUND(AVG(mv.avg_skor_capaian)::NUMERIC,            2) AS avg_skor_capaian,
    ROUND(AVG(mv.avg_skor_pelaksanaan)::NUMERIC,        2) AS avg_skor_pelaksanaan,
    ROUND(AVG(mv.avg_skor_sarana_prasarana)::NUMERIC,   2) AS avg_skor_sarana_prasarana,
    ROUND(AVG(mv.avg_skor_perilaku_mahasiswa)::NUMERIC, 2) AS avg_skor_perilaku_mahasiswa,
    ROUND(AVG(mv.avg_skor_overall)::NUMERIC,            2) AS avg_skor_overall

FROM analitik_mv.mv_akademik_kelas mv
JOIN LATERAL unnest(mv.semua_dosen_id) AS u(dosen_id) ON TRUE
LEFT JOIN mhs_aktif_per_prodi map
       ON map.no_ps    = mv.no_prodi
      AND map.tahun    = mv.tahun
      AND map.semester = mv.semester
GROUP BY
    mv.no_prodi,    mv.kode_prodi, mv.nama_prodi_id,   mv.nama_prodi_en,
    mv.jenjang,       mv.kode_fakultas,   mv.nama_fakultas_id, mv.nama_fakultas_en,
    mv.semester,      mv.tahun,           mv.tahun_ajaran,
    map.jumlah_mahasiswa_aktif;

COMMENT ON MATERIALIZED VIEW analitik_mv.mv_akademik_statistik_prodi IS
    'Statistik agregat seluruh kelas per prodi per semester. '
    'Periode: 2018/2019 semester 1 s.d. terkini';

-- Index
CREATE UNIQUE INDEX idx_mv_prodi_pk
    ON analitik_mv.mv_akademik_statistik_prodi (no_prodi, semester, tahun);
CREATE INDEX idx_mv_prodi_fak_sem
    ON analitik_mv.mv_akademik_statistik_prodi (kode_fakultas, semester, tahun);
CREATE INDEX idx_mv_prodi_tahun_ajaran
    ON analitik_mv.mv_akademik_statistik_prodi (tahun_ajaran, no_prodi);


-- ================================================================
-- STEP 6: mv_statistik_dosen
-- Bergantung pada: analitik_mv.mv_akademik_kelas
-- ================================================================

CREATE MATERIALIZED VIEW analitik_mv.mv_akademik_statistik_dosen AS
WITH

skor_dimensi_dosen AS (
    SELECT
        nd.dosen_id,
        k.semester,
        k.tahun,
        ROUND(AVG((nd.skor_kues->>'1')::NUMERIC)::NUMERIC, 4) AS avg_skor_capaian,
        ROUND(AVG((nd.skor_kues->>'2')::NUMERIC)::NUMERIC, 4) AS avg_skor_pelaksanaan,
        ROUND(AVG((nd.skor_kues->>'3')::NUMERIC)::NUMERIC, 4) AS avg_skor_perilaku_mahasiswa,
        COUNT(DISTINCT nd.kelas_id)                            AS jumlah_kelas_dengan_skor
    FROM evaluasi.nilai_dosen nd
    JOIN kelas.kelas k ON k.kelas_id = nd.kelas_id
    WHERE nd.skor_kues IS NOT NULL
      AND nd.skor_kues <> '{}'::jsonb
      AND nd.skor_kues ? '1'
      AND (
        (k.semester = 1 AND k.tahun >= 2018)
        OR
        (k.semester IN (2, 3) AND k.tahun >= 2019)
      )
    GROUP BY nd.dosen_id, k.semester, k.tahun
),

skor_q25_q27_dosen AS (
    SELECT
        nd.dosen_id,
        k.semester,
        k.tahun,
        ROUND(AVG((nd.kuesioner->>'25')::NUMERIC)::NUMERIC, 4) AS avg_skor_q25,
        ROUND(AVG((nd.kuesioner->>'26')::NUMERIC)::NUMERIC, 4) AS avg_skor_q26,
        ROUND(AVG((nd.kuesioner->>'27')::NUMERIC)::NUMERIC, 4) AS avg_skor_q27
    FROM evaluasi.nilai_dosen nd
    JOIN kelas.kelas k ON k.kelas_id = nd.kelas_id
    WHERE nd.kuesioner IS NOT NULL
      AND nd.kuesioner <> '{}'::jsonb
      AND nd.kuesioner ? '25'
      AND (
          (k.semester = 1 AND k.tahun >= 2018)
          OR
          (k.semester IN (2, 3) AND k.tahun >= 2019)
      )
    GROUP BY nd.dosen_id, k.semester, k.tahun
)

SELECT
    u.dosen_id,
    d.nama_gelar                                                 AS nama_dosen_gelar,
    d.nip,
    d.kk_id,
    kk.nama->>'id'                                               AS nama_kk_id,
    kk.nama->>'en'                                               AS nama_kk_en,
    d.kd_fak                                                     AS kode_fakultas_dosen,
    d.no_ps                                                      AS no_prodi,
    ps.kd_ps                                                      AS kode_prodi,
    mv.semester,
    mv.tahun,
    mv.tahun_ajaran,
    COUNT(DISTINCT mv.kelas_id)                                  AS jumlah_kelas,
    COUNT(DISTINCT mv.mata_kuliah_id)                            AS jumlah_matkul,
    SUM(mv.sks)                                                  AS total_sks_diajar,
    ROUND(AVG(mv.pct_kehadiran_dosen)::NUMERIC,           2)     AS avg_pct_kehadiran_dosen,
    ROUND(AVG(mv.pct_kehadiran_mahasiswa)::NUMERIC,       2)     AS avg_pct_kehadiran_mahasiswa,
    ROUND(AVG(mv.avg_ip_akhir_mahasiswa)::NUMERIC,       3)     AS avg_ip_mhs,
    sqd.avg_skor_q25,
    sqd.avg_skor_q26,
    sqd.avg_skor_q27,
    sdd.avg_skor_capaian,
    sdd.avg_skor_pelaksanaan,
    ROUND(AVG(mv.avg_skor_sarana_prasarana)::NUMERIC,     2)     AS avg_skor_sarana_prasarana,
    sdd.avg_skor_perilaku_mahasiswa,
    ROUND(
        (COALESCE(sdd.avg_skor_capaian,    0) +
         COALESCE(sdd.avg_skor_pelaksanaan, 0) +
         COALESCE(sdd.avg_skor_perilaku_mahasiswa, 0))
        / NULLIF(
            (CASE WHEN sdd.avg_skor_capaian    IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN sdd.avg_skor_pelaksanaan IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN sdd.avg_skor_perilaku_mahasiswa IS NOT NULL THEN 1 ELSE 0 END), 0
          )::NUMERIC, 2
    )                                                            AS avg_skor_overall,
    sdd.jumlah_kelas_dengan_skor,
    ROUND(AVG(nd.nilai_akhir)::NUMERIC, 4)                       AS avg_nilai_akhir,
    array_agg(DISTINCT mv.kelas_id    ORDER BY mv.kelas_id)      AS kelas_id_list,
    array_agg(DISTINCT mv.kode_matkul ORDER BY mv.kode_matkul)   AS kode_matkul_list,
    array_agg(DISTINCT mv.no_prodi  ORDER BY mv.no_prodi)    AS no_prodi_diajar,
    array_agg(DISTINCT mv.kode_prodi ORDER BY mv.kode_prodi) AS kode_prodi_diajar

FROM analitik_mv.mv_akademik_kelas mv
JOIN LATERAL unnest(mv.semua_dosen_id) AS u(dosen_id) ON TRUE
JOIN utama.dosen              d    ON d.dosen_id   = u.dosen_id
LEFT JOIN utama.program_studi ps   ON d.no_ps      = ps.no_ps   -- ← LEFT JOIN
LEFT JOIN utama.kk            kk   ON kk.kk_id     = d.kk_id 
LEFT JOIN skor_dimensi_dosen  sdd  ON sdd.dosen_id  = u.dosen_id
                                  AND sdd.semester   = mv.semester
                                  AND sdd.tahun      = mv.tahun
LEFT JOIN skor_q25_q27_dosen  sqd  ON sqd.dosen_id  = u.dosen_id
                                  AND sqd.semester   = mv.semester
                                  AND sqd.tahun      = mv.tahun
LEFT JOIN evaluasi.nilai_dosen nd  ON nd.kelas_id   = mv.kelas_id
                                  AND nd.dosen_id    = u.dosen_id
GROUP BY
    u.dosen_id, d.nip, d.nama_gelar, d.kk_id, d.kd_fak, d.no_ps, ps.kd_ps,
    kk.nama, kk.kd_fak,
    mv.semester, mv.tahun, mv.tahun_ajaran,
    sdd.avg_skor_capaian, sdd.avg_skor_pelaksanaan,
    sdd.avg_skor_perilaku_mahasiswa, sdd.jumlah_kelas_dengan_skor,
    sqd.avg_skor_q25, sqd.avg_skor_q26, sqd.avg_skor_q27;

COMMENT ON MATERIALIZED VIEW analitik_mv.mv_akademik_statistik_dosen IS
    'Statistik agregat per dosen per semester. '
    'Periode: 2018/2019 semester 1 s.d. terkini ';

-- Index
CREATE UNIQUE INDEX idx_mv_dosen_pk
    ON analitik_mv.mv_akademik_statistik_dosen (dosen_id, semester, tahun);
CREATE INDEX idx_mv_dosen_kk_sem
    ON analitik_mv.mv_akademik_statistik_dosen (kk_id, semester, tahun);
CREATE INDEX idx_mv_dosen_fak_dosen_sem
    ON analitik_mv.mv_akademik_statistik_dosen (kode_fakultas_dosen, semester, tahun);
CREATE INDEX idx_mv_dosen_no_ps_sem
    ON analitik_mv.mv_akademik_statistik_dosen (no_prodi, semester, tahun);
CREATE INDEX idx_mv_dosen_tahun_ajaran
    ON analitik_mv.mv_akademik_statistik_dosen (tahun_ajaran, dosen_id);
CREATE INDEX idx_mv_dosen_prodi_diajar_arr
    ON analitik_mv.mv_akademik_statistik_dosen USING gin (no_prodi_diajar);

-- ================================================================
-- STEP 7: mv_akademik_statistik_dosen
-- ================================================================
CREATE MATERIALIZED VIEW analitik_mv.mv_akademik_komponen_evaluasi_kelas AS

WITH komponen_per_kelas AS (
    -- SUM bobot per komponen per kelas.
    -- WHERE bobot > 0 memfilter placeholder sebelum SUM.
    -- Beberapa entri TGS per kelas (Tugas 1 + Tugas 2 + ...) di-SUM jadi satu angka.
    SELECT
        kelas_id,
        SUM(CASE WHEN kd_komponen_evaluasi_mk = 'UTS' THEN bobot ELSE 0 END) AS bobot_uts,
        SUM(CASE WHEN kd_komponen_evaluasi_mk = 'UAS' THEN bobot ELSE 0 END) AS bobot_uas,
        SUM(CASE WHEN kd_komponen_evaluasi_mk = 'TGS' THEN bobot ELSE 0 END) AS bobot_tugas,
        SUM(CASE WHEN kd_komponen_evaluasi_mk = 'QIZ' THEN bobot ELSE 0 END) AS bobot_kuis,
        SUM(CASE WHEN kd_komponen_evaluasi_mk = 'PRK' THEN bobot ELSE 0 END) AS bobot_praktikum,
        SUM(CASE WHEN kd_komponen_evaluasi_mk = 'PRO' THEN bobot ELSE 0 END) AS bobot_projek,
        SUM(CASE WHEN kd_komponen_evaluasi_mk = 'PAR' THEN bobot ELSE 0 END) AS bobot_partisipatif,
        SUM(bobot)                                                            AS total_bobot_kelas
    FROM evaluasi.komponen_evaluasi
    WHERE bobot > 0
    GROUP BY kelas_id
)
SELECT
    -- ── Identitas kelas ───────────────────────────────────────────────────────
    mk.kelas_id,
    mk.no_kelas,
    mk.kode_matkul,
    mk.nama_matkul_id,
    mk.nama_matkul_en,
    mk.sks,

    -- ── Dimensi prodi & fakultas ──────────────────────────────────────────────
    mk.no_prodi,
    mk.kode_prodi,
    mk.nama_prodi_id,
    mk.nama_prodi_en,
    mk.jenjang,
    mk.kode_fakultas,
    mk.nama_fakultas_id,
    mk.nama_fakultas_en,
    mk.semua_dosen_id,
    mk.semua_dosen_nama_gelar,

    -- ── Dimensi waktu ─────────────────────────────────────────────────────────
    mk.tahun,
    mk.semester,
    mk.tahun_ajaran,
    mk.tahun_kurikulum,

    -- ── Bobot komponen (sudah di-SUM, tanpa pre-aggregation ke prodi) ────────
    kpk.bobot_uts,
    kpk.bobot_uas,
    kpk.bobot_tugas,
    kpk.bobot_kuis,
    kpk.bobot_praktikum,
    kpk.bobot_projek,
    kpk.bobot_partisipatif,
    kpk.total_bobot_kelas   -- indikator kelengkapan data; idealnya mendekati 100

FROM komponen_per_kelas kpk
JOIN analitik_mv.mv_akademik_kelas mk ON kpk.kelas_id = mk.kelas_id;


-- ─── Index ────────────────────────────────────────────────────────────────────

-- Filter utama: spatial + temporal (pola query chart grading_comp)
CREATE INDEX ON analitik_mv.mv_akademik_komponen_evaluasi_kelas (no_prodi);
CREATE INDEX ON analitik_mv.mv_akademik_komponen_evaluasi_kelas (kode_fakultas);
CREATE INDEX ON analitik_mv.mv_akademik_komponen_evaluasi_kelas (tahun_ajaran, semester);
CREATE INDEX ON analitik_mv.mv_akademik_komponen_evaluasi_kelas (kode_fakultas, tahun_ajaran, semester);

-- Lookup per kelas (jika dipakai untuk drill-down)
CREATE UNIQUE INDEX ON analitik_mv.mv_akademik_komponen_evaluasi_kelas (kelas_id);
