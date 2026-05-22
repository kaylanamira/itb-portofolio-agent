-- ================================================================
-- MATERIALIZED VIEWS : Portofolio & Kuesioner Akademik ITB
-- File   : schema_mv_six_direct.sql
-- Versi  : Opsi B — Query langsung ke schema SIX (tanpa ETL)
--
-- CARA APPLY:
--   -- 1. Drop MV lama jika ada:
--   DROP MATERIALIZED VIEW IF EXISTS mv_statistik_dosen CASCADE;
--   DROP MATERIALIZED VIEW IF EXISTS mv_statistik_prodi  CASCADE;
--   DROP MATERIALIZED VIEW IF EXISTS mv_kelas            CASCADE;
--
--   -- 2. Apply file ini:
--   psql "postgresql://six:...@localhost:15432/dev_six" -f schema_mv_six_direct.sql
--
--   -- 3. Refresh berurutan (wajib):
--   REFRESH MATERIALIZED VIEW mv_kelas;
--   REFRESH MATERIALIZED VIEW mv_statistik_prodi;
--   REFRESH MATERIALIZED VIEW mv_statistik_dosen;
--
-- PERBEDAAN DARI schema_mv_portofolio_kuesioner.sql (versi lama):
--   [1] Query langsung ke utama.*, kelas.*, evaluasi.*, mahasiswa.*
--       Tidak ada tabel public.* — tidak perlu ETL
--   [2] Skor kuesioner diekstrak dari JSONB:
--       nilai_kelas.kuesioner  → skor_q21..q37 (level kelas)
--       nilai_dosen.kuesioner  → skor_q25/26/27 (per dosen, data baru)
--       nilai_dosen.skor_kues  → dimensi key "1","2","3" (data baru)
--       Data lama pakai key "4"-"9" → NULL. Bisa diterima.
--   [3] Distribusi nilai dihitung dari mahasiswa.kuliah (data nyata!)
--       Filter: sah_nilai=true AND ts_hapus IS NULL AND kelas_id NOT NULL
--   [4] jumlah_mahasiswa dari mahasiswa.kuliah (lebih akurat dari jwb_kuesioner)
--   [5] semua_dosen_id bertipe INTEGER[] (bukan UUID[])
--   [6] Kolom nama multilingual: ->>'id' untuk Bahasa Indonesia
--   [7] jenis_nilai: kd_penilaian 'A'→'ABCDE', 'P'→'PassFail'
--   [8] kode_fakultas = kd_fak (VARCHAR), bukan UUID
--
-- HIERARKI REFRESH (urutan wajib):
--   1. mv_kelas
--   2. mv_statistik_prodi
--   3. mv_statistik_dosen
-- ================================================================


-- ============================================================
-- MV 1: mv_kelas
-- 1 baris = 1 kelas. Semua dimensi ter-flatten.
-- ============================================================

CREATE MATERIALIZED VIEW mv_kelas AS
WITH

-- ── CTE 1: Array dosen per kelas ─────────────────────────────────────────────
dosen_per_kelas AS (
    SELECT
        pk.kelas_id,
        array_agg(d.dosen_id   ORDER BY d.dosen_id) AS semua_dosen_id,
        array_agg(d.nama_gelar ORDER BY d.dosen_id) AS semua_dosen_nama_gelar
    FROM kelas.pengajar pk
    JOIN utama.dosen d ON d.dosen_id = pk.dosen_id
    GROUP BY pk.kelas_id
),

-- ── CTE 2: Distribusi nilai per kelas dari mahasiswa.kuliah ──────────────────
-- Sumber: mahasiswa.kuliah, filter sah_nilai=true dan tidak dihapus.
-- Nilai: A, AB, B, BC, C, D, E (sistem ABCDE) | P, F (sistem PassFail)
-- T = belum selesai/incomplete, tidak dihitung sebagai lulus/tidak lulus.
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
        COUNT(*) FILTER (WHERE nilai = 'P')  AS dist_jumlah_pass,
        COUNT(*) FILTER (WHERE nilai = 'F')  AS dist_jumlah_fail,
        COUNT(*) FILTER (WHERE nilai <> 'T' AND nilai IS NOT NULL) AS total_mahasiswa
    FROM mahasiswa.kuliah
    WHERE sah_nilai  = true
      AND ts_hapus   IS NULL
      AND kelas_id   IS NOT NULL
    GROUP BY kelas_id
),

-- ── CTE 3: Skor kuesioner level kelas (dari nilai_kelas.kuesioner JSONB) ─────
-- Format: {"21": 3.74, "22": 3.69, ...} — key = kd_pertanyaan sebagai string.
-- Q21,Q22,Q23 = capaian | Q24,Q28 = pelaksanaan | Q29,Q30 = sarana | Q35,Q37 = perilaku
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

-- ── CTE 4: Skor Q25/Q26/Q27 dirata-rata antar dosen per kelas ────────────────
-- Q25/Q26/Q27 nilainya berbeda per dosen — dirata-rata untuk level kelas.
-- Sumber: nilai_dosen.kuesioner JSONB. Key "25","26","27" = format baru.
-- Data lama berisi {} → dilewati.
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

-- ── CTE 5: Skor dimensi agregat dari nilai_dosen.skor_kues JSONB ──────────────
-- key "1" = capaian pembelajaran    avg(Q21,22,23)
-- key "2" = pelaksanaan perkuliahan avg(Q24,25,26,27,28)
-- key "3" = perilaku mahasiswa      avg(Q35,37)
-- Data lama pakai key "4"-"9" → dilewati (NULL di output).
skor_dimensi_avg AS (
    SELECT
        nd.kelas_id,
        ROUND(AVG((nd.skor_kues->>'1')::NUMERIC)::NUMERIC, 4) AS skor_avg_capaian,
        ROUND(AVG((nd.skor_kues->>'2')::NUMERIC)::NUMERIC, 4) AS skor_avg_pelaksanaan,
        ROUND(AVG((nd.skor_kues->>'3')::NUMERIC)::NUMERIC, 4) AS skor_avg_perilaku
    FROM evaluasi.nilai_dosen nd
    WHERE nd.skor_kues IS NOT NULL
      AND nd.skor_kues <> '{}'::jsonb
      AND nd.skor_kues ? '1'
    GROUP BY nd.kelas_id
)

SELECT
    -- ── Identitas kelas ──────────────────────────────────────────────────────
    k.kelas_id,
    k.mata_kuliah_id                                             AS matkul_id,
    k.no_kelas,
    k.semester,
    k.tahun,
    CASE
        WHEN k.semester IN (2, 3)
            THEN (k.tahun - 1)::TEXT || '/' || k.tahun::TEXT
        ELSE
            k.tahun::TEXT || '/' || (k.tahun + 1)::TEXT
    END                                                          AS tahun_ajaran,

    -- ── Mata kuliah ───────────────────────────────────────────────────────────
    mk.kd_kuliah                                                 AS kode_mk,
    mk.nama->>'id'                                               AS nama_mk_id,
    mk.nama->>'en'                                               AS nama_mk_en,
    mk.sks,
    mk.th_kur                                                    AS tahun_kurikulum,
    CASE mk.kd_penilaian
        WHEN 'A' THEN 'ABCDE'
        WHEN 'P' THEN 'PassFail'
        ELSE NULL
    END                                                          AS jenis_nilai,

    -- ── Prodi & Fakultas ──────────────────────────────────────────────────────
    -- JOIN dari k.no_ps agar kelas MK lintas-prodi (WI) tetap punya prodi.
    ps.no_ps                                                     AS kode_prodi,
    ps.kd_ps                                                     AS singkatan_prodi,
    ps.nama->>'id'                                               AS nama_kode_prodi,
    ps.nama->>'en'                                               AS nama_prodi_en,
    ps.kd_strata                                                 AS jenjang,
    f.kd_fak                                                     AS kode_fakultas,
    f.nama->>'id'                                                AS nama_kode_fakultas,
    f.nama->>'en'                                                AS nama_fakultas_en,

    -- ── Dosen ─────────────────────────────────────────────────────────────────
    COALESCE(dpk.semua_dosen_id,   '{}'::INTEGER[])              AS semua_dosen_id,
    COALESCE(dpk.semua_dosen_nama_gelar, '{}'::TEXT[])           AS semua_dosen_nama_gelar,

    -- ── Statistik kelas (dari evaluasi.nilai_kelas) ───────────────────────────
    nk.hadir_mhs                                                 AS pct_kehadiran_mahasiswa,
    nk.hadir_dosen                                               AS pct_kehadiran_dosen,
    nk.ip_mhs,                                                   AS rata_ip_akhir_mahasiswa,
    COALESCE(dp.total_mahasiswa, 0)::INTEGER                     AS jumlah_mahasiswa,
    nk.skor_dna,
    nk.ts_dna,
    nk.ip_mhs_dna,

    -- ── Distribusi nilai (dari mahasiswa.kuliah — data nyata) ─────────────────
    COALESCE(dp.dist_jumlah_a,    0) AS dist_jumlah_a,
    COALESCE(dp.dist_jumlah_ab,   0) AS dist_jumlah_ab,
    COALESCE(dp.dist_jumlah_b,    0) AS dist_jumlah_b,
    COALESCE(dp.dist_jumlah_bc,   0) AS dist_jumlah_bc,
    COALESCE(dp.dist_jumlah_c,    0) AS dist_jumlah_c,
    COALESCE(dp.dist_jumlah_d,    0) AS dist_jumlah_d,
    COALESCE(dp.dist_jumlah_e,    0) AS dist_jumlah_e,
    COALESCE(dp.dist_jumlah_pass, 0) AS dist_jumlah_pass,
    COALESCE(dp.dist_jumlah_fail, 0) AS dist_jumlah_fail,

    -- Persentase distribusi
    ROUND(COALESCE(dp.dist_jumlah_a,  0)::NUMERIC / NULLIF(dp.total_mahasiswa, 0) * 100, 2) AS dist_pct_a,
    ROUND(COALESCE(dp.dist_jumlah_ab, 0)::NUMERIC / NULLIF(dp.total_mahasiswa, 0) * 100, 2) AS dist_pct_ab,
    ROUND(COALESCE(dp.dist_jumlah_b,  0)::NUMERIC / NULLIF(dp.total_mahasiswa, 0) * 100, 2) AS dist_pct_b,
    ROUND(COALESCE(dp.dist_jumlah_bc, 0)::NUMERIC / NULLIF(dp.total_mahasiswa, 0) * 100, 2) AS dist_pct_bc,
    ROUND(COALESCE(dp.dist_jumlah_c,  0)::NUMERIC / NULLIF(dp.total_mahasiswa, 0) * 100, 2) AS dist_pct_c,
    ROUND(COALESCE(dp.dist_jumlah_d,  0)::NUMERIC / NULLIF(dp.total_mahasiswa, 0) * 100, 2) AS dist_pct_d,
    ROUND(COALESCE(dp.dist_jumlah_e,  0)::NUMERIC / NULLIF(dp.total_mahasiswa, 0) * 100, 2) AS dist_pct_e,
    ROUND(COALESCE(dp.dist_jumlah_pass,0)::NUMERIC / NULLIF(dp.total_mahasiswa, 0) * 100, 2) AS dist_pct_pass,
    ROUND(COALESCE(dp.dist_jumlah_fail,0)::NUMERIC / NULLIF(dp.total_mahasiswa, 0) * 100, 2) AS dist_pct_fail,

    -- Persentase lulus: >=C untuk ABCDE, Pass untuk PassFail
    CASE mk.kd_penilaian
        WHEN 'A' THEN
            ROUND(
                (COALESCE(dp.dist_jumlah_a,  0) + COALESCE(dp.dist_jumlah_ab, 0) +
                 COALESCE(dp.dist_jumlah_b,  0) + COALESCE(dp.dist_jumlah_bc, 0) +
                 COALESCE(dp.dist_jumlah_c,  0))::NUMERIC
                / NULLIF(dp.total_mahasiswa, 0) * 100, 2)
        WHEN 'P' THEN
            ROUND(COALESCE(dp.dist_jumlah_pass, 0)::NUMERIC
                / NULLIF(dp.total_mahasiswa, 0) * 100, 2)
        ELSE NULL
    END                                                          AS dist_pct_lulus_A_C,

    CASE mk.kd_penilaian
        WHEN 'A' THEN
            ROUND(
                (COALESCE(dp.dist_jumlah_a,  0) + COALESCE(dp.dist_jumlah_ab, 0) +
                 COALESCE(dp.dist_jumlah_b,  0) + COALESCE(dp.dist_jumlah_bc, 0) +
                 COALESCE(dp.dist_jumlah_c,  0) + COALESCE(dp.dist_jumlah_d, 0))::NUMERIC
                / NULLIF(dp.total_mahasiswa, 0) * 100, 2)
        WHEN 'P' THEN
            ROUND(COALESCE(dp.dist_jumlah_pass, 0)::NUMERIC
                / NULLIF(dp.total_mahasiswa, 0) * 100, 2)
        ELSE NULL
    END                                                          AS dist_pct_lulus_A_D,

    -- ── Skor kuesioner individual (level kelas) ───────────────────────────────
    skp.skor_q21,
    skp.skor_q22,
    skp.skor_q23,
    skp.skor_q24,
    skp.skor_q28,
    skp.skor_q29,
    skp.skor_q30,
    skp.skor_q35,
    skp.skor_q37,

    -- ── Skor Q25/Q26/Q27 (rata-rata antar dosen) ──────────────────────────────
    ROUND(sda.skor_q25_avg::NUMERIC, 4)                          AS skor_q25_avg,
    ROUND(sda.skor_q26_avg::NUMERIC, 4)                          AS skor_q26_avg,
    ROUND(sda.skor_q27_avg::NUMERIC, 4)                          AS skor_q27_avg,

    -- ── Skor rata-rata per dimensi ────────────────────────────────────────────
    ROUND(sda2.skor_avg_capaian::NUMERIC,    2)                  AS skor_avg_capaian,
    ROUND(sda2.skor_avg_pelaksanaan::NUMERIC, 2)                 AS skor_avg_pelaksanaan,
    ROUND(
        (COALESCE(skp.skor_q29, 0) + COALESCE(skp.skor_q30, 0))
        / NULLIF(
            (CASE WHEN skp.skor_q29 IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN skp.skor_q30 IS NOT NULL THEN 1 ELSE 0 END), 0
          )::NUMERIC, 2
    )                                                            AS skor_avg_sarana_prasarana,
    ROUND(sda2.skor_avg_perilaku::NUMERIC,   2)                  AS skor_avg_perilaku_mahasiswa,
    -- Overall = avg(capaian, pelaksanaan, sarana, perilaku)
    ROUND(
        (
            COALESCE(skp.skor_q21, 0) +
            COALESCE(skp.skor_q22, 0) +
            COALESCE(skp.skor_q23, 0) +
            COALESCE(skp.skor_q24, 0) +
            COALESCE(sda.skor_q25_avg, 0) +
            COALESCE(sda.skor_q26_avg, 0) +
            COALESCE(sda.skor_q27_avg, 0) +
            COALESCE(skp.skor_q28, 0) +
            COALESCE(skp.skor_q29, 0) +
            COALESCE(skp.skor_q30, 0) +
            COALESCE(skp.skor_q35, 0) +
            COALESCE(skp.skor_q37, 0)
        )
        /
        NULLIF(
            (
                CASE WHEN skp.skor_q21 IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN skp.skor_q22 IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN skp.skor_q23 IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN skp.skor_q24 IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN sda.skor_q25_avg IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN sda.skor_q26_avg IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN sda.skor_q27_avg IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN skp.skor_q28 IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN skp.skor_q29 IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN skp.skor_q30 IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN skp.skor_q35 IS NOT NULL THEN 1 ELSE 0 END +
                CASE WHEN skp.skor_q37 IS NOT NULL THEN 1 ELSE 0 END
            ),
            0
        )::NUMERIC, 2                               ) AS skor_avg_overall

FROM kelas.kelas k
JOIN utama.mata_kuliah    mk   ON mk.mata_kuliah_id = k.mata_kuliah_id
JOIN utama.program_studi  ps   ON ps.no_ps          = k.no_ps
JOIN utama.fakultas       f    ON f.kd_fak          = ps.kd_fak
LEFT JOIN dosen_per_kelas           dpk  ON dpk.kelas_id  = k.kelas_id
LEFT JOIN evaluasi.nilai_kelas      nk   ON nk.kelas_id   = k.kelas_id
LEFT JOIN distribusi_pivot          dp   ON dp.kelas_id   = k.kelas_id
LEFT JOIN skor_kelas_pivot          skp  ON skp.kelas_id  = k.kelas_id
LEFT JOIN skor_dosen_avg            sda  ON sda.kelas_id  = k.kelas_id
LEFT JOIN skor_dimensi_avg          sda2 ON sda2.kelas_id = k.kelas_id;

-- Index wajib untuk REFRESH CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_kelas_pk         ON mv_kelas (kelas_id);
-- Index operasional
CREATE INDEX idx_mv_kelas_prodi_sem         ON mv_kelas (kode_prodi, semester, tahun);
CREATE INDEX idx_mv_kelas_fak_sem           ON mv_kelas (kode_fakultas, semester, tahun);
CREATE INDEX idx_mv_kelas_matkul_sem        ON mv_kelas (kode_mk, semester, tahun);
CREATE INDEX idx_mv_kelas_tahun_ajaran      ON mv_kelas (tahun_ajaran, kode_prodi);
CREATE INDEX idx_mv_kelas_dosen_arr         ON mv_kelas USING GIN (semua_dosen_id);


-- ============================================================
-- MV 2: mv_statistik_prodi
-- 1 baris = 1 prodi × 1 semester × 1 tahun.
-- Membaca dari mv_kelas — tidak perlu ubah logika, hanya agregasi.
-- ============================================================

CREATE MATERIALIZED VIEW mv_statistik_prodi AS
SELECT
    mv.kode_prodi,
    mv.singkatan_prodi,
    mv.nama_kode_prodi,
    mv.nama_prodi_en,
    mv.jenjang,
    mv.kode_fakultas,
    mv.nama_kode_fakultas,
    mv.nama_fakultas_en,
    mv.semester,
    mv.tahun,
    mv.tahun_ajaran,

    COUNT(DISTINCT mv.kelas_id)                                  AS jumlah_kelas,
    COUNT(DISTINCT mv.matkul_id)                                 AS jumlah_matkul_aktif,
    COUNT(DISTINCT u.dosen_id)                                   AS jumlah_dosen_aktif,
    SUM(mv.jumlah_mahasiswa)                                     AS total_mahasiswa,

    ROUND(AVG(mv.pct_kehadiran_dosen)::NUMERIC,     2)           AS avg_pct_kehadiran_dosen,
    ROUND(AVG(mv.pct_kehadiran_mahasiswa)::NUMERIC, 2)           AS avg_pct_kehadiran_mahasiswa,
    ROUND(AVG(mv.skor_avg_capaian)::NUMERIC,        2)           AS avg_skor_capaian,
    ROUND(AVG(mv.skor_avg_pelaksanaan)::NUMERIC,    2)           AS avg_skor_pelaksanaan,
    ROUND(AVG(mv.skor_avg_sarana)::NUMERIC,         2)           AS avg_skor_sarana,
    ROUND(AVG(mv.skor_avg_perilaku)::NUMERIC,       2)           AS avg_skor_perilaku,
    ROUND(AVG(mv.skor_avg_overall)::NUMERIC,        2)           AS avg_skor_overall,
    ROUND(AVG(mv.ip_mhs)::NUMERIC,                  3)           AS avg_ip_mhs,
    ROUND(AVG(mv.dist_pct_lulus)::NUMERIC,          2)           AS avg_pct_lulus

FROM mv_kelas mv
JOIN LATERAL unnest(mv.semua_dosen_id) AS u(dosen_id) ON TRUE
GROUP BY
    mv.kode_prodi, mv.singkatan_prodi, mv.nama_kode_prodi, mv.nama_prodi_en,
    mv.jenjang,  mv.kode_fakultas,  mv.nama_kode_fakultas, mv.nama_fakultas_en,
    mv.semester, mv.tahun,       mv.tahun_ajaran;

CREATE UNIQUE INDEX idx_mv_prodi_pk      ON mv_statistik_prodi (kode_prodi, semester, tahun);
CREATE INDEX idx_mv_prodi_fak_sem        ON mv_statistik_prodi (kode_fakultas, semester, tahun);
CREATE INDEX idx_mv_prodi_tahun_ajaran   ON mv_statistik_prodi (tahun_ajaran, kode_prodi);


-- ============================================================
-- MV 3: mv_statistik_dosen
-- 1 baris = 1 dosen × 1 semester × 1 tahun.
-- ============================================================

CREATE MATERIALIZED VIEW mv_statistik_dosen AS
WITH
-- Skor dimensi per dosen per periode (dari nilai_dosen.skor_kues, format baru)
skor_per_dosen AS (
    SELECT
        nd.dosen_id,
        k.semester,
        k.tahun,
        CASE k.semester
            WHEN 2 THEN (k.tahun - 1)::TEXT || '/' || k.tahun::TEXT
            ELSE         k.tahun::TEXT        || '/' || (k.tahun + 1)::TEXT
        END                                                          AS tahun_ajaran,
        ROUND(AVG((nd.skor_kues->>'1')::NUMERIC)::NUMERIC, 4)       AS avg_skor_capaian,
        ROUND(AVG((nd.skor_kues->>'2')::NUMERIC)::NUMERIC, 4)       AS avg_skor_pelaksanaan,
        ROUND(AVG((nd.skor_kues->>'3')::NUMERIC)::NUMERIC, 4)       AS avg_skor_perilaku,
        COUNT(DISTINCT nd.kelas_id)                                  AS jumlah_kelas_dengan_skor
    FROM evaluasi.nilai_dosen nd
    JOIN kelas.kelas k ON k.kelas_id = nd.kelas_id
    WHERE nd.skor_kues IS NOT NULL
      AND nd.skor_kues <> '{}'::jsonb
      AND nd.skor_kues ? '1'
    GROUP BY nd.dosen_id, k.semester, k.tahun
)

SELECT
    u.dosen_id,
    d.nama_gelar                                                 AS nama_dosen,
    d.kk_id,
    kk.nama->>'id'                                               AS nama_kk,
    kk.kd_fak                                                    AS kode_fakultas_kk,

    mv.semester,
    mv.tahun,
    mv.tahun_ajaran,

    COUNT(DISTINCT mv.kelas_id)                                  AS jumlah_kelas,
    COUNT(DISTINCT mv.matkul_id)                                 AS jumlah_matkul,
    SUM(mv.sks)                                                  AS total_sks_diajar,

    ROUND(AVG(mv.pct_kehadiran_dosen)::NUMERIC,     2)           AS avg_pct_kehadiran_dosen,
    ROUND(AVG(mv.pct_kehadiran_mahasiswa)::NUMERIC, 2)           AS avg_pct_kehadiran_mahasiswa,
    ROUND(AVG(mv.ip_mhs)::NUMERIC,                  3)           AS avg_ip_mhs,

    spd.avg_skor_capaian,
    spd.avg_skor_pelaksanaan,
    ROUND(AVG(mv.skor_avg_sarana)::NUMERIC,         2)           AS avg_skor_sarana,
    spd.avg_skor_perilaku,
    ROUND(
        (COALESCE(spd.avg_skor_capaian,    0) +
         COALESCE(spd.avg_skor_pelaksanaan, 0) +
         COALESCE(AVG(mv.skor_avg_sarana),  0) +
         COALESCE(spd.avg_skor_perilaku,    0))
        / NULLIF(
            (CASE WHEN spd.avg_skor_capaian    IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN spd.avg_skor_pelaksanaan IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN AVG(mv.skor_avg_sarana)  IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN spd.avg_skor_perilaku    IS NOT NULL THEN 1 ELSE 0 END), 0
          )::NUMERIC, 2
    )                                                            AS avg_skor_overall,

    ROUND(AVG(nd.nilai_akhir)::NUMERIC, 4)                       AS avg_nilai_akhir,

    array_agg(DISTINCT mv.kelas_id ORDER BY mv.kelas_id)         AS kelas_ids,
    array_agg(DISTINCT mv.kode_mk  ORDER BY mv.kode_mk)          AS kode_mk_list,
    array_agg(DISTINCT mv.kode_prodi ORDER BY mv.kode_prodi)         AS kode_prodis_diajar

FROM mv_kelas mv
JOIN LATERAL unnest(mv.semua_dosen_id) AS u(dosen_id) ON TRUE
JOIN utama.dosen             d   ON d.dosen_id  = u.dosen_id
JOIN utama.kk                kk  ON kk.kk_id    = d.kk_id
LEFT JOIN skor_per_dosen     spd ON spd.dosen_id = u.dosen_id
                                 AND spd.semester = mv.semester
                                 AND spd.tahun    = mv.tahun
LEFT JOIN evaluasi.nilai_dosen nd ON nd.kelas_id = mv.kelas_id
                                 AND nd.dosen_id  = u.dosen_id
GROUP BY
    u.dosen_id, d.nama_gelar, d.kk_id, kk.nama, kk.kd_fak,
    mv.semester, mv.tahun, mv.tahun_ajaran,
    spd.avg_skor_capaian, spd.avg_skor_pelaksanaan, spd.avg_skor_perilaku;

CREATE UNIQUE INDEX idx_mv_dosen_pk       ON mv_statistik_dosen (dosen_id, semester, tahun);
CREATE INDEX idx_mv_dosen_kk_sem          ON mv_statistik_dosen (kk_id, semester, tahun);
CREATE INDEX idx_mv_dosen_fak_sem         ON mv_statistik_dosen (kode_fakultas_kk, semester, tahun);
CREATE INDEX idx_mv_dosen_tahun_ajaran    ON mv_statistik_dosen (tahun_ajaran, dosen_id);