-- ================================================================
-- MATERIALIZED VIEWS : Portofolio & Kuesioner Akademik ITB
-- Versi  : Opsi B — Query langsung ke schema SIX (tanpa ETL)
--
-- CARA APPLY:
--   DROP MATERIALIZED VIEW IF EXISTS mv_statistik_dosen CASCADE;
--   DROP MATERIALIZED VIEW IF EXISTS mv_statistik_prodi  CASCADE;
--   DROP MATERIALIZED VIEW IF EXISTS mv_kelas            CASCADE;
--   psql "postgresql://six:...@localhost:15432/dev_six" -f schema_mv_portofolio_kuesioner.sql
--   REFRESH MATERIALIZED VIEW mv_kelas;
--   REFRESH MATERIALIZED VIEW mv_statistik_prodi;
--   REFRESH MATERIALIZED VIEW mv_statistik_dosen;
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
-- Filter: sah_nilai=true, tidak dihapus, punya kelas_id.
-- Nilai: A,AB,B,BC,C,D,E (ABCDE) | P,F (PassFail) | T = incomplete (tidak dihitung)
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
    WHERE sah_nilai = true
      AND ts_hapus  IS NULL
      AND kelas_id  IS NOT NULL
    GROUP BY kelas_id
),

-- ── CTE 3: Skor kuesioner level kelas (dari nilai_kelas.kuesioner JSONB) ─────
-- Format: {"21": 3.74, "22": 3.69, ...} — key = kd_pertanyaan string
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

-- ── CTE 4: Skor Q25/Q26/Q27 rata-rata antar dosen per kelas ──────────────────
-- Q25/Q26/Q27 nilainya berbeda per dosen — dirata-rata untuk level kelas.
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
-- key "1" = capaian | "2" = pelaksanaan | "3" = perilaku mahasiswa
-- Data lama pakai key "4"-"9" → dilewati (NULL).
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

-- ── CTE 6: Skor Q25/Q26/Q27 per dosen sebagai JSONB dict ─────────────────────
-- Hasil: {"123": 3.6667, "456": 4.0000}
-- Key = dosen_id (string), Value = skor rata-rata (4 desimal).
-- NULL jika kelas tidak punya data per dosen (data lama).
skor_kues_per_dosen AS (
    SELECT
        nd.kelas_id,
        jsonb_object_agg(
            nd.dosen_id::TEXT,
            ROUND((nd.kuesioner->>'25')::NUMERIC, 4)
        ) FILTER (WHERE nd.kuesioner ? '25')  AS skor_kues_dosen_q25,
        jsonb_object_agg(
            nd.dosen_id::TEXT,
            ROUND((nd.kuesioner->>'26')::NUMERIC, 4)
        ) FILTER (WHERE nd.kuesioner ? '26')  AS skor_kues_dosen_q26,
        jsonb_object_agg(
            nd.dosen_id::TEXT,
            ROUND((nd.kuesioner->>'27')::NUMERIC, 4)
        ) FILTER (WHERE nd.kuesioner ? '27')  AS skor_kues_dosen_q27
    FROM evaluasi.nilai_dosen nd
    WHERE nd.kuesioner IS NOT NULL
      AND nd.kuesioner <> '{}'::jsonb
      AND (nd.kuesioner ? '25' OR nd.kuesioner ? '26' OR nd.kuesioner ? '27')
    GROUP BY nd.kelas_id
)

SELECT
    -- ── Identitas kelas ──────────────────────────────────────────────────────
    k.kelas_id,
    k.mata_kuliah_id                                             AS mata_kuliah_id,
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
    mk.kd_kuliah                                                 AS kode_matkul,
    mk.nama->>'id'                                               AS nama_matkul_id,
    mk.nama->>'en'                                               AS nama_matkul_en,
    mk.sks,
    mk.th_kur                                                    AS tahun_kurikulum,
    CASE mk.kd_penilaian
        WHEN 'A' THEN 'ABCDE'
        WHEN 'P' THEN 'PassFail'
        ELSE NULL
    END                                                          AS jenis_nilai,

    -- ── Prodi & Fakultas ──────────────────────────────────────────────────────
    ps.no_ps                                                     AS kode_prodi,
    ps.kd_ps                                                     AS singkatan_prodi,
    ps.nama->>'id'                                               AS nama_prodi_id,
    ps.nama->>'en'                                               AS nama_prodi_en,
    ps.kd_strata                                                 AS jenjang,
    f.kd_fak                                                     AS kode_fakultas,
    f.nama->>'id'                                                AS nama_fakultas_id,
    f.nama->>'en'                                                AS nama_fakultas_en,

    -- ── Dosen ─────────────────────────────────────────────────────────────────
    COALESCE(dpk.semua_dosen_id,         '{}'::INTEGER[])        AS semua_dosen_id,
    COALESCE(dpk.semua_dosen_nama_gelar, '{}'::TEXT[])           AS semua_dosen_nama_gelar,

    -- ── Statistik kelas (dari evaluasi.nilai_kelas) ───────────────────────────
    nk.hadir_mhs                                                 AS pct_kehadiran_mahasiswa,
    nk.hadir_dosen                                               AS pct_kehadiran_dosen,
    nk.ip_mhs                                                    AS rata_ip_akhir_mahasiswa,
    COALESCE(dp.total_mahasiswa, 0)::INTEGER                     AS jumlah_mahasiswa,
    nk.skor_dna,
    nk.ts_dna,
    nk.ip_mhs_dna,

    -- ── Distribusi nilai (dari mahasiswa.kuliah) ──────────────────────────────
    COALESCE(dp.dist_jumlah_a,    0) AS dist_jumlah_a,
    COALESCE(dp.dist_jumlah_ab,   0) AS dist_jumlah_ab,
    COALESCE(dp.dist_jumlah_b,    0) AS dist_jumlah_b,
    COALESCE(dp.dist_jumlah_bc,   0) AS dist_jumlah_bc,
    COALESCE(dp.dist_jumlah_c,    0) AS dist_jumlah_c,
    COALESCE(dp.dist_jumlah_d,    0) AS dist_jumlah_d,
    COALESCE(dp.dist_jumlah_e,    0) AS dist_jumlah_e,
    COALESCE(dp.dist_jumlah_pass, 0) AS dist_jumlah_pass,
    COALESCE(dp.dist_jumlah_fail, 0) AS dist_jumlah_fail,

    ROUND(COALESCE(dp.dist_jumlah_a,   0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100, 2) AS dist_pct_a,
    ROUND(COALESCE(dp.dist_jumlah_ab,  0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100, 2) AS dist_pct_ab,
    ROUND(COALESCE(dp.dist_jumlah_b,   0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100, 2) AS dist_pct_b,
    ROUND(COALESCE(dp.dist_jumlah_bc,  0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100, 2) AS dist_pct_bc,
    ROUND(COALESCE(dp.dist_jumlah_c,   0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100, 2) AS dist_pct_c,
    ROUND(COALESCE(dp.dist_jumlah_d,   0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100, 2) AS dist_pct_d,
    ROUND(COALESCE(dp.dist_jumlah_e,   0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100, 2) AS dist_pct_e,
    ROUND(COALESCE(dp.dist_jumlah_pass,0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100, 2) AS dist_pct_pass,
    ROUND(COALESCE(dp.dist_jumlah_fail,0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100, 2) AS dist_pct_fail,

    CASE mk.kd_penilaian
        WHEN 'A' THEN ROUND(
            (COALESCE(dp.dist_jumlah_a,0) + COALESCE(dp.dist_jumlah_ab,0) +
             COALESCE(dp.dist_jumlah_b,0) + COALESCE(dp.dist_jumlah_bc,0) +
             COALESCE(dp.dist_jumlah_c,0))::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100, 2)
        WHEN 'P' THEN ROUND(
            COALESCE(dp.dist_jumlah_pass,0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100, 2)
        ELSE NULL
    END                                                          AS dist_pct_lulus_A_C,

    CASE mk.kd_penilaian
        WHEN 'A' THEN ROUND(
            (COALESCE(dp.dist_jumlah_a,0) + COALESCE(dp.dist_jumlah_ab,0) +
             COALESCE(dp.dist_jumlah_b,0) + COALESCE(dp.dist_jumlah_bc,0) +
             COALESCE(dp.dist_jumlah_c,0) + COALESCE(dp.dist_jumlah_d,0))::NUMERIC
             / NULLIF(dp.total_mahasiswa,0) * 100, 2)
        WHEN 'P' THEN ROUND(
            COALESCE(dp.dist_jumlah_pass,0)::NUMERIC / NULLIF(dp.total_mahasiswa,0) * 100, 2)
        ELSE NULL
    END                                                          AS dist_pct_lulus_A_D,

    -- ── Skor kuesioner per pertanyaan (level kelas) ───────────────────────────
    skp.skor_q21,
    skp.skor_q22,
    skp.skor_q23,
    skp.skor_q24,
    ROUND(sda.skor_q25_avg::NUMERIC, 4)                          AS skor_q25_avg,
    ROUND(sda.skor_q26_avg::NUMERIC, 4)                          AS skor_q26_avg,
    ROUND(sda.skor_q27_avg::NUMERIC, 4)                          AS skor_q27_avg,
    skp.skor_q28,
    skp.skor_q29,
    skp.skor_q30,
    skp.skor_q35,
    skp.skor_q37,

    -- ── Skor per dosen sebagai JSONB dict {"dosen_id": skor} ─────────────────
    skdp.skor_kues_dosen_q25,
    skdp.skor_kues_dosen_q26,
    skdp.skor_kues_dosen_q27,

    -- ── Skor rata-rata per dimensi ────────────────────────────────────────────
    ROUND(sda2.avg_skor_capaian::NUMERIC,    2)                  AS avg_skor_capaian,
    ROUND(sda2.avg_skor_pelaksanaan::NUMERIC, 2)                 AS avg_skor_pelaksanaan,
    ROUND(
        (COALESCE(skp.skor_q29, 0) + COALESCE(skp.skor_q30, 0))
        / NULLIF(
            (CASE WHEN skp.skor_q29 IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN skp.skor_q30 IS NOT NULL THEN 1 ELSE 0 END), 0
          )::NUMERIC, 2
    )                                                            AS avg_skor_sarana_prasarana,
    ROUND(sda2.avg_skor_perilaku_mahasiswa::NUMERIC,   2)                  AS avg_skor_perilaku_mahasiswa,
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
    )                                                            AS avg_skor_overall

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
LEFT JOIN skor_kues_per_dosen       skdp ON skdp.kelas_id = k.kelas_id;

CREATE UNIQUE INDEX idx_mv_kelas_pk          ON mv_kelas (kelas_id);
CREATE INDEX idx_mv_kelas_prodi_sem          ON mv_kelas (kode_prodi, semester, tahun);
CREATE INDEX idx_mv_kelas_fak_sem            ON mv_kelas (kode_fakultas, semester, tahun);
CREATE INDEX idx_mv_kelas_matkul_sem         ON mv_kelas (kode_matkul, semester, tahun);
CREATE INDEX idx_mv_kelas_tahun_ajaran       ON mv_kelas (tahun_ajaran, kode_prodi);
CREATE INDEX idx_mv_kelas_dosen_arr          ON mv_kelas USING GIN (semua_dosen_id);
CREATE INDEX idx_mv_kelas_skor_dosen_q25     ON mv_kelas USING GIN (skor_kues_dosen_q25);
CREATE INDEX idx_mv_kelas_skor_dosen_q26     ON mv_kelas USING GIN (skor_kues_dosen_q26);
CREATE INDEX idx_mv_kelas_skor_dosen_q27     ON mv_kelas USING GIN (skor_kues_dosen_q27);


-- ============================================================
-- CTE BERSAMA: dipakai oleh mv_statistik_prodi DAN mv_statistik_fakultas
-- Definisi mahasiswa aktif per (prodi/fakultas, tahun, semester):
--   - ts_daftar IS NOT NULL  → FRS selesai & disetujui wali
--   - NOT EXISTS nonaktif    → exclude cuti, skorsing, outbound resmi
--   - Grup by no_ps ASAL mahasiswa (bukan prodi penyelenggara kelas)
-- ============================================================


-- ============================================================
-- MV 2: mv_statistik_prodi
-- 1 baris = 1 prodi × 1 semester × 1 tahun.
-- Berisi: ringkasan kelas, dosen, mahasiswa aktif,
--         akumulasi distribusi nilai seluruh kelas prodi,
--         rata-rata skor tiap pertanyaan kuesioner,
--         rata-rata skor per dimensi.
-- ============================================================

CREATE MATERIALIZED VIEW mv_statistik_prodi AS
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
    GROUP BY mhs.no_ps, st.tahun, st.semester
)

SELECT
    -- ── Identitas prodi ───────────────────────────────────────────────────────
    mv.kode_prodi,
    mv.singkatan_prodi,
    mv.nama_prodi_id,
    mv.nama_prodi_en,
    mv.jenjang,
    mv.kode_fakultas,
    mv.nama_fakultas_id,
    mv.nama_fakultas_en,
    mv.semester,
    mv.tahun,
    mv.tahun_ajaran,

    -- ── Ringkasan aktivitas ───────────────────────────────────────────────────
    COUNT(DISTINCT mv.kelas_id)                                  AS jumlah_kelas,
    COUNT(DISTINCT mv.mata_kuliah_id)                                 AS jumlah_matkul_aktif,
    COUNT(DISTINCT u.dosen_id)                                   AS jumlah_dosen_aktif,
    COALESCE(map.jumlah_mahasiswa_aktif, 0)                      AS jumlah_mahasiswa_aktif,

    -- ── Kehadiran & IP ────────────────────────────────────────────────────────
    ROUND(AVG(mv.pct_kehadiran_dosen)::NUMERIC,           2)     AS avg_pct_kehadiran_dosen,
    ROUND(AVG(mv.pct_kehadiran_mahasiswa)::NUMERIC,       2)     AS avg_pct_kehadiran_mahasiswa,
    ROUND(AVG(mv.rata_ip_akhir_mahasiswa)::NUMERIC,       3)     AS avg_ip_akhir_mahasiswa,

    -- ── Akumulasi distribusi nilai (SUM seluruh kelas prodi) ─────────────────
    -- Pakai SUM jumlah absolut, bukan AVG persentase per kelas,
    -- agar total bisa digunakan sebagai penyebut yang akurat.
    SUM(mv.dist_jumlah_a)                                        AS total_jumlah_a,
    SUM(mv.dist_jumlah_ab)                                       AS total_jumlah_ab,
    SUM(mv.dist_jumlah_b)                                        AS total_jumlah_b,
    SUM(mv.dist_jumlah_bc)                                       AS total_jumlah_bc,
    SUM(mv.dist_jumlah_c)                                        AS total_jumlah_c,
    SUM(mv.dist_jumlah_d)                                        AS total_jumlah_d,
    SUM(mv.dist_jumlah_e)                                        AS total_jumlah_e,
    SUM(mv.dist_jumlah_pass)                                     AS total_jumlah_pass,
    SUM(mv.dist_jumlah_fail)                                     AS total_jumlah_fail,
    -- Total penilaian (exclude T/incomplete)
    SUM(mv.dist_jumlah_a + mv.dist_jumlah_ab + mv.dist_jumlah_b +
        mv.dist_jumlah_bc + mv.dist_jumlah_c + mv.dist_jumlah_d +
        mv.dist_jumlah_e + mv.dist_jumlah_pass + mv.dist_jumlah_fail)
                                                                 AS total_mahasiswa_dinilai,

    -- ── Persentase distribusi nilai tingkat prodi ─────────────────────────────
    -- Dihitung dari akumulasi absolut (bukan rata-rata persentase per kelas)
    -- sehingga kelas besar tidak disamakan bobotnya dengan kelas kecil.
    ROUND(SUM(mv.dist_jumlah_a)::NUMERIC    / NULLIF(SUM(
        mv.dist_jumlah_a + mv.dist_jumlah_ab + mv.dist_jumlah_b +
        mv.dist_jumlah_bc + mv.dist_jumlah_c + mv.dist_jumlah_d +
        mv.dist_jumlah_e + mv.dist_jumlah_pass + mv.dist_jumlah_fail), 0) * 100, 2)
                                                                 AS dist_pct_a,
    ROUND(SUM(mv.dist_jumlah_ab)::NUMERIC   / NULLIF(SUM(
        mv.dist_jumlah_a + mv.dist_jumlah_ab + mv.dist_jumlah_b +
        mv.dist_jumlah_bc + mv.dist_jumlah_c + mv.dist_jumlah_d +
        mv.dist_jumlah_e + mv.dist_jumlah_pass + mv.dist_jumlah_fail), 0) * 100, 2)
                                                                 AS dist_pct_ab,
    ROUND(SUM(mv.dist_jumlah_b)::NUMERIC    / NULLIF(SUM(
        mv.dist_jumlah_a + mv.dist_jumlah_ab + mv.dist_jumlah_b +
        mv.dist_jumlah_bc + mv.dist_jumlah_c + mv.dist_jumlah_d +
        mv.dist_jumlah_e + mv.dist_jumlah_pass + mv.dist_jumlah_fail), 0) * 100, 2)
                                                                 AS dist_pct_b,
    ROUND(SUM(mv.dist_jumlah_bc)::NUMERIC   / NULLIF(SUM(
        mv.dist_jumlah_a + mv.dist_jumlah_ab + mv.dist_jumlah_b +
        mv.dist_jumlah_bc + mv.dist_jumlah_c + mv.dist_jumlah_d +
        mv.dist_jumlah_e + mv.dist_jumlah_pass + mv.dist_jumlah_fail), 0) * 100, 2)
                                                                 AS dist_pct_bc,
    ROUND(SUM(mv.dist_jumlah_c)::NUMERIC    / NULLIF(SUM(
        mv.dist_jumlah_a + mv.dist_jumlah_ab + mv.dist_jumlah_b +
        mv.dist_jumlah_bc + mv.dist_jumlah_c + mv.dist_jumlah_d +
        mv.dist_jumlah_e + mv.dist_jumlah_pass + mv.dist_jumlah_fail), 0) * 100, 2)
                                                                 AS dist_pct_c,
    ROUND(SUM(mv.dist_jumlah_d)::NUMERIC    / NULLIF(SUM(
        mv.dist_jumlah_a + mv.dist_jumlah_ab + mv.dist_jumlah_b +
        mv.dist_jumlah_bc + mv.dist_jumlah_c + mv.dist_jumlah_d +
        mv.dist_jumlah_e + mv.dist_jumlah_pass + mv.dist_jumlah_fail), 0) * 100, 2)
                                                                 AS dist_pct_d,
    ROUND(SUM(mv.dist_jumlah_e)::NUMERIC    / NULLIF(SUM(
        mv.dist_jumlah_a + mv.dist_jumlah_ab + mv.dist_jumlah_b +
        mv.dist_jumlah_bc + mv.dist_jumlah_c + mv.dist_jumlah_d +
        mv.dist_jumlah_e + mv.dist_jumlah_pass + mv.dist_jumlah_fail), 0) * 100, 2)
                                                                 AS dist_pct_e,
    ROUND(SUM(mv.dist_jumlah_pass)::NUMERIC / NULLIF(SUM(
        mv.dist_jumlah_a + mv.dist_jumlah_ab + mv.dist_jumlah_b +
        mv.dist_jumlah_bc + mv.dist_jumlah_c + mv.dist_jumlah_d +
        mv.dist_jumlah_e + mv.dist_jumlah_pass + mv.dist_jumlah_fail), 0) * 100, 2)
                                                                 AS dist_pct_pass,
    ROUND(SUM(mv.dist_jumlah_fail)::NUMERIC / NULLIF(SUM(
        mv.dist_jumlah_a + mv.dist_jumlah_ab + mv.dist_jumlah_b +
        mv.dist_jumlah_bc + mv.dist_jumlah_c + mv.dist_jumlah_d +
        mv.dist_jumlah_e + mv.dist_jumlah_pass + mv.dist_jumlah_fail), 0) * 100, 2)
                                                                 AS dist_pct_fail,

    -- Pct lulus ≥ C (dari akumulasi)
    ROUND(
        SUM(mv.dist_jumlah_a + mv.dist_jumlah_ab + mv.dist_jumlah_b +
            mv.dist_jumlah_bc + mv.dist_jumlah_c)::NUMERIC
        / NULLIF(SUM(mv.dist_jumlah_a + mv.dist_jumlah_ab + mv.dist_jumlah_b +
            mv.dist_jumlah_bc + mv.dist_jumlah_c + mv.dist_jumlah_d +
            mv.dist_jumlah_e + mv.dist_jumlah_pass + mv.dist_jumlah_fail), 0) * 100, 2)
                                                                 AS dist_pct_lulus_A_C,
    -- Pct lulus ≥ D (dari akumulasi)
    ROUND(
        SUM(mv.dist_jumlah_a + mv.dist_jumlah_ab + mv.dist_jumlah_b +
            mv.dist_jumlah_bc + mv.dist_jumlah_c + mv.dist_jumlah_d)::NUMERIC
        / NULLIF(SUM(mv.dist_jumlah_a + mv.dist_jumlah_ab + mv.dist_jumlah_b +
            mv.dist_jumlah_bc + mv.dist_jumlah_c + mv.dist_jumlah_d +
            mv.dist_jumlah_e + mv.dist_jumlah_pass + mv.dist_jumlah_fail), 0) * 100, 2)
                                                                 AS dist_pct_lulus_A_D,

    -- ── Rata-rata skor tiap pertanyaan kuesioner (tingkat prodi) ─────────────
    -- Rata-rata dari rata-rata tiap kelas (weighted equal per kelas).
    -- Kelas tanpa data kuesioner (NULL) tidak ikut dihitung (AVG abaikan NULL).
    ROUND(AVG(mv.skor_q21)::NUMERIC,         4)                  AS avg_skor_q21,
    ROUND(AVG(mv.skor_q22)::NUMERIC,         4)                  AS avg_skor_q22,
    ROUND(AVG(mv.skor_q23)::NUMERIC,         4)                  AS avg_skor_q23,
    ROUND(AVG(mv.skor_q24)::NUMERIC,         4)                  AS avg_skor_q24,
    ROUND(AVG(mv.skor_q25_avg)::NUMERIC,     4)                  AS avg_skor_q25,
    ROUND(AVG(mv.skor_q26_avg)::NUMERIC,     4)                  AS avg_skor_q26,
    ROUND(AVG(mv.skor_q27_avg)::NUMERIC,     4)                  AS avg_skor_q27,
    ROUND(AVG(mv.skor_q28)::NUMERIC,         4)                  AS avg_skor_q28,
    ROUND(AVG(mv.skor_q29)::NUMERIC,         4)                  AS avg_skor_q29,
    ROUND(AVG(mv.skor_q30)::NUMERIC,         4)                  AS avg_skor_q30,
    ROUND(AVG(mv.skor_q35)::NUMERIC,         4)                  AS avg_skor_q35,
    ROUND(AVG(mv.skor_q37)::NUMERIC,         4)                  AS avg_skor_q37,

    -- ── Rata-rata skor per dimensi ────────────────────────────────────────────
    ROUND(AVG(mv.avg_skor_capaian)::NUMERIC,           2)        AS avg_skor_capaian,
    ROUND(AVG(mv.avg_skor_pelaksanaan)::NUMERIC,       2)        AS avg_skor_pelaksanaan,
    ROUND(AVG(mv.avg_skor_sarana_prasarana)::NUMERIC,  2)        AS avg_skor_sarana_prasarana,
    ROUND(AVG(mv.avg_skor_perilaku_mahasiswa)::NUMERIC,2)        AS avg_skor_perilaku_mahasiswa,
    ROUND(AVG(mv.avg_skor_overall)::NUMERIC,           2)        AS avg_skor_overall

FROM mv_kelas mv
JOIN LATERAL unnest(mv.semua_dosen_id) AS u(dosen_id) ON TRUE
LEFT JOIN mhs_aktif_per_prodi map
       ON map.no_ps    = mv.kode_prodi
      AND map.tahun    = mv.tahun
      AND map.semester = mv.semester
GROUP BY
    mv.kode_prodi,    mv.singkatan_prodi, mv.nama_prodi_id,   mv.nama_prodi_en,
    mv.jenjang,       mv.kode_fakultas,   mv.nama_fakultas_id, mv.nama_fakultas_en,
    mv.semester,      mv.tahun,           mv.tahun_ajaran,
    map.jumlah_mahasiswa_aktif;

CREATE UNIQUE INDEX idx_mv_prodi_pk      ON mv_statistik_prodi (kode_prodi, semester, tahun);
CREATE INDEX idx_mv_prodi_fak_sem        ON mv_statistik_prodi (kode_fakultas, semester, tahun);
CREATE INDEX idx_mv_prodi_tahun_ajaran   ON mv_statistik_prodi (tahun_ajaran, kode_prodi);

-- ============================================================
-- MV 3: mv_statistik_dosen
-- 1 baris = 1 dosen × 1 semester × 1 tahun.
--
-- Sumber data:
--   - mv_kelas        → kelas yang diajar, kehadiran, IP mahasiswa
--   - evaluasi.nilai_dosen.skor_kues  → skor dimensi (key "1","2","3")
--   - evaluasi.nilai_dosen.kuesioner  → skor Q25/26/27 per dosen
--   - evaluasi.nilai_dosen.nilai_akhir → nilai akhir dosen (mungkin NULL)
--   - utama.dosen     → identitas dosen, no_ps asal, kd_fak langsung
--   - utama.kk        → kelompok keahlian
-- ============================================================

CREATE MATERIALIZED VIEW mv_statistik_dosen AS
WITH

-- ── CTE 1: Skor dimensi per dosen per semester ────────────────────────────────
-- Sumber: evaluasi.nilai_dosen.skor_kues JSONB
-- key "1" = capaian, "2" = pelaksanaan, "3" = perilaku mahasiswa (format baru)
-- Data lama pakai key "4"-"9" → dilewati (NULL).
skor_dimensi_dosen AS (
    SELECT
        nd.dosen_id,
        k.semester,
        k.tahun,
        ROUND(AVG((nd.skor_kues->>'1')::NUMERIC)::NUMERIC, 4)  AS avg_skor_capaian,
        ROUND(AVG((nd.skor_kues->>'2')::NUMERIC)::NUMERIC, 4)  AS avg_skor_pelaksanaan,
        ROUND(AVG((nd.skor_kues->>'3')::NUMERIC)::NUMERIC, 4)  AS avg_skor_perilaku_mahasiswa,
        COUNT(DISTINCT nd.kelas_id)                             AS jumlah_kelas_dengan_skor
    FROM evaluasi.nilai_dosen nd
    JOIN kelas.kelas k ON k.kelas_id = nd.kelas_id
    WHERE nd.skor_kues IS NOT NULL
      AND nd.skor_kues <> '{}'::jsonb
      AND nd.skor_kues ? '1'
    GROUP BY nd.dosen_id, k.semester, k.tahun
),

-- ── CTE 2: Skor Q25/Q26/Q27 per dosen per semester ───────────────────────────
-- Q25 = penguasaan materi dosen
-- Q26 = kemampuan menjelaskan dosen
-- Q27 = interaksi dosen dengan mahasiswa
-- Sumber: evaluasi.nilai_dosen.kuesioner JSONB (rata-rata dari tiap kelas)
-- Ini adalah skor yang paling relevan untuk evaluasi individual dosen.
-- Data lama berisi {} → dilewati (NULL).
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
    GROUP BY nd.dosen_id, k.semester, k.tahun
)

SELECT
    -- ── Identitas dosen ───────────────────────────────────────────────────────
    u.dosen_id,
    d.nama_gelar                                                 AS nama_dosen_gelar,
    d.nip,

    -- Organisasi dosen: KK dan Fakultas
    d.kk_id,
    kk.nama->>'id'                                               AS nama_kk_id,
    kk.nama->>'en'                                               AS nama_kk_en,
    -- kd_fak langsung dari utama.dosen (lebih otoritatif untuk admin)
    d.kd_fak                                                     AS kode_fakultas_dosen,

    -- Home prodi dosen (dari utama.dosen.no_ps)
    d.no_ps                                                      AS kode_prodi,

    -- ── Periode ───────────────────────────────────────────────────────────────
    mv.semester,
    mv.tahun,
    mv.tahun_ajaran,

    -- ── Ringkasan beban mengajar ──────────────────────────────────────────────
    COUNT(DISTINCT mv.kelas_id)                                  AS jumlah_kelas,
    COUNT(DISTINCT mv.mata_kuliah_id)                                 AS jumlah_matkul,
    -- total_sks = SUM SKS seluruh kelas (termasuk paralel)
    -- = beban mengajar total, bukan SKS unik per MK
    SUM(mv.sks)                                                  AS total_sks_diajar,

    -- ── Kehadiran & IP mahasiswa ──────────────────────────────────────────────
    ROUND(AVG(mv.pct_kehadiran_dosen)::NUMERIC,           2)     AS avg_pct_kehadiran_dosen,
    ROUND(AVG(mv.pct_kehadiran_mahasiswa)::NUMERIC,       2)     AS avg_pct_kehadiran_mahasiswa,
    ROUND(AVG(mv.rata_ip_akhir_mahasiswa)::NUMERIC,       3)     AS avg_ip_akhir_mahasiswa,

    -- ── Skor kuesioner per pertanyaan (yang spesifik ke dosen) ───────────────
    -- Q25/26/27: dari evaluasi.nilai_dosen.kuesioner (rata-rata lintas kelas)
    -- NULL = tidak ada data kuesioner per dosen untuk semester ini (data lama)
    sqd.avg_skor_q25,
    sqd.avg_skor_q26,
    sqd.avg_skor_q27,

    -- ── Skor dimensi (dari nilai_dosen.skor_kues, format baru) ───────────────
    sdd.avg_skor_capaian,
    sdd.avg_skor_pelaksanaan,
    -- sarana prasarana (Q29/Q30) bukan evaluasi dosen, tapi diambil dari
    -- kelas yang diajar sebagai konteks
    ROUND(AVG(mv.avg_skor_sarana_prasarana)::NUMERIC,     2)     AS avg_skor_sarana_prasarana,
    sdd.avg_skor_perilaku_mahasiswa,
    -- overall dosen: rata-rata dari dimensi yang tersedia
    ROUND(
        (COALESCE(sdd.avg_skor_capaian,    0) +
         COALESCE(sdd.avg_skor_pelaksanaan, 0) +
         COALESCE(sdd.avg_skor_perilaku_mahasiswa,    0))
        / NULLIF(
            (CASE WHEN sdd.avg_skor_capaian    IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN sdd.avg_skor_pelaksanaan IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN sdd.avg_skor_perilaku_mahasiswa    IS NOT NULL THEN 1 ELSE 0 END), 0
          )::NUMERIC, 2
    )                                                            AS avg_skor_overall,
    sdd.jumlah_kelas_dengan_skor,

    -- ── Nilai akhir dosen ─────────────────────────────────────────────────────
    -- nilai_akhir di evaluasi.nilai_dosen mungkin NULL (tidak konsisten diisi)
    ROUND(AVG(nd.nilai_akhir)::NUMERIC, 4)                       AS avg_nilai_akhir,

    -- ── Daftar kelas, MK, dan prodi yang diajar ───────────────────────────────
    array_agg(DISTINCT mv.kelas_id    ORDER BY mv.kelas_id)      AS kelas_ids,
    array_agg(DISTINCT mv.kode_matkul     ORDER BY mv.kode_matkul)       AS kode_matkul_list,
    -- kode_prodi_diajar = prodi penyelenggara kelas (bisa beda dari kode_prodi)
    array_agg(DISTINCT mv.kode_prodi  ORDER BY mv.kode_prodi)    AS kode_prodi_diajar,
    array_agg(DISTINCT mv.singkatan_prodi ORDER BY mv.singkatan_prodi)
                                                                 AS singkatan_prodi_diajar

FROM mv_kelas mv
JOIN LATERAL unnest(mv.semua_dosen_id) AS u(dosen_id) ON TRUE
JOIN utama.dosen              d    ON d.dosen_id   = u.dosen_id
JOIN utama.kk                 kk   ON kk.kk_id     = d.kk_id
LEFT JOIN skor_dimensi_dosen  sdd  ON sdd.dosen_id  = u.dosen_id
                                  AND sdd.semester   = mv.semester
                                  AND sdd.tahun      = mv.tahun
LEFT JOIN skor_q25_q27_dosen  sqd  ON sqd.dosen_id  = u.dosen_id
                                  AND sqd.semester   = mv.semester
                                  AND sqd.tahun      = mv.tahun
LEFT JOIN evaluasi.nilai_dosen nd  ON nd.kelas_id   = mv.kelas_id
                                  AND nd.dosen_id    = u.dosen_id
GROUP BY
    u.dosen_id, d.nip, d.nama_gelar, d.kk_id, d.kd_fak, d.no_ps,
    kk.nama, kk.kd_fak,
    mv.semester, mv.tahun, mv.tahun_ajaran,
    sdd.avg_skor_capaian, sdd.avg_skor_pelaksanaan,
    sdd.avg_skor_perilaku_mahasiswa, sdd.jumlah_kelas_dengan_skor,
    sqd.avg_skor_q25, sqd.avg_skor_q26, sqd.avg_skor_q27;

CREATE UNIQUE INDEX idx_mv_dosen_pk          ON mv_statistik_dosen (dosen_id, semester, tahun);
CREATE INDEX idx_mv_dosen_kk_sem             ON mv_statistik_dosen (kk_id, semester, tahun);
CREATE INDEX idx_mv_dosen_fak_dosen_sem      ON mv_statistik_dosen (kode_fakultas_dosen, semester, tahun);
CREATE INDEX idx_mv_dosen_no_ps_sem          ON mv_statistik_dosen (kode_prodi, semester, tahun);
CREATE INDEX idx_mv_dosen_tahun_ajaran       ON mv_statistik_dosen (tahun_ajaran, dosen_id);


-- ============================================================
-- MATERIALIZED VIEW 4 : mv_jenis_dan_sifat_matkul
--
-- Tujuan: Menyimpan status/posisi setiap mata kuliah dalam
--         struktur kurikulum, sebagai referensi join untuk
--         mv_kelas dan query analitik lainnya.
--
-- Grain: 1 baris = 1 kombinasi (mata_kuliah_id, no_ps, paket/struktur)
--        Satu MK bisa punya >1 baris jika masuk ke >1 paket
--        dalam prodi yang sama (many-to-many by design).
--
-- Sumber data:
--   kur24.*       → th_kur 2024, 2026 (data kurikulum baru)
--   kurikulum.*   → th_kur 2003–2023  (data kurikulum lama)
--
-- Coverage berdasarkan analisis kelas.kelas:
--   kur24         : ~14.102 kelas (7%)
--   kurikulum.*   : ~181.661 kelas (89%)
--   tidak tercakup: ~7.734 kelas th_kur 2000 (3,8%) — dead zone historis
--
-- Kolom kode_sifat: normalisasi lintas era
--   kur24        : C (Core/Wajib dalam paket) | E (Elective/Pilihan)
--   kurikulum.*  : W→C | P→E
--   → gunakan kode_sifat untuk filter/compare lintas era
--
-- Kolom is_wajib_itb:
--   Hanya tersedia untuk data kurikulum lama via
--   kurikulum.struktur_wajib_itb. Untuk kur24, nilai selalu FALSE
--   karena tidak ada tabel equivalen (TPB = kode_jenis 'B').
-- ============================================================


CREATE MATERIALIZED VIEW analitik.mv_jenis_dan_sifat_matkul AS

-- ── Bagian 1: kurikulum baru (kur24) ─────────────────────────────
SELECT
    pm.mata_kuliah_id,
    p.no_ps                         AS kode_prodi,
    ps.kd_ps                        AS singkatan_prodi,
    ps.kd_fak                       AS kode_fakultas,
    p.th_kur                        AS tahun_kurikulum,
    'kurikulum_2024'::TEXT          AS sumber,
    pm.paket_id                     AS paket_id,
    NULL::INTEGER                   AS struktur_id,
    p.kd_jenis                    AS kode_jenis,
    rjp.nama->>'id'                 AS nama_jenis,
    p.nama->>'id'                   AS nama_paket,
    pm.kd_sifat                     AS kode_sifat,
    FALSE                           AS is_wajib_itb

FROM kur24.paket_mk             pm
JOIN kur24.paket                 p   ON p.paket_id    = pm.paket_id
JOIN kur24.ref_jenis_paket       rjp ON rjp.kd_jenis = p.kd_jenis
JOIN utama.program_studi         ps  ON ps.no_ps       = p.no_ps

UNION ALL

-- ── Bagian 2: kurikulum lama (kurikulum.*) ───────────────────────
SELECT
    ks.mata_kuliah_id,
    ks.no_ps                        AS kode_prodi,
    ps.kd_ps                        AS singkatan_prodi,
    ps.kd_fak                       AS kode_fakultas,
    ks.th_kur                       AS tahun_kurikulum,
    'kurikulum_lama'::TEXT          AS sumber,
    NULL::INTEGER                   AS paket_id,
    ks.struktur_id                  AS struktur_id,
    NULL::CHAR(1)                   AS kode_jenis,
    NULL::TEXT                      AS nama_jenis,
    NULL::TEXT                      AS nama_paket,
    CASE ks.kd_sifat                AS kode_sifat,
    (EXISTS (
        SELECT 1 FROM kurikulum.struktur_wajib_itb swi
        WHERE swi.mata_kuliah_id = ks.mata_kuliah_id
          AND swi.no_ps          = ks.no_ps
    ))                              AS is_wajib_itb

FROM kurikulum.struktur          ks
JOIN utama.program_studi         ps  ON ps.no_ps = ks.no_ps;


-- Index untuk mv_jenis_dan_sifat_matkul
CREATE UNIQUE INDEX idx_mv_jsm_pk
    ON analitik.mv_jenis_dan_sifat_matkul
    (sumber, mata_kuliah_id, kode_prodi, COALESCE(paket_id, struktur_id));

CREATE INDEX idx_mv_jsm_mk_prodi
    ON analitik.mv_jenis_dan_sifat_matkul (mata_kuliah_id, kode_prodi);

CREATE INDEX idx_mv_jsm_kode_jenis
    ON analitik.mv_jenis_dan_sifat_matkul (kode_jenis)
    WHERE kode_jenis IS NOT NULL;

CREATE INDEX idx_mv_jsm_wajib_itb
    ON analitik.mv_jenis_dan_sifat_matkul (is_wajib_itb, kode_prodi)
    WHERE is_wajib_itb = TRUE;

CREATE INDEX idx_mv_jsm_th_kur
    ON analitik.mv_jenis_dan_sifat_matkul (tahun_kurikulum, sumber);

CREATE INDEX idx_mv_jsm_fak
    ON analitik.mv_jenis_dan_sifat_matkul (kode_fakultas, kode_jenis);

COMMENT ON MATERIALIZED VIEW analitik.mv_jenis_dan_sifat_matkul IS
    'Jenis dan sifat MK dalam struktur kurikulum. '
    'Grain: 1 baris = 1 (mata_kuliah_id, no_ps, paket/struktur). '
    'Satu MK bisa >1 baris jika masuk ke >1 paket dalam prodi yang sama. '
    'Sumber: kur24.* (kode_sifat C/E) UNION kurikulum.* (kode_sifat W sama dengan C dan P sama dengan E).';


-- ================================================================
-- HELPER FUNCTION: analitik.strip_html
-- Strip HTML tags dan decode HTML entities dari teks portofolio.
-- IMMUTABLE + PARALLEL SAFE → aman di MV dan expression index.
-- ================================================================

CREATE OR REPLACE FUNCTION analitik.strip_html(raw text)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT NULLIF(
        trim(
            -- Langkah 4: collapse whitespace berlebih
            regexp_replace(
                -- Langkah 3: decode HTML entities umum
                regexp_replace(
                    -- Langkah 2: strip semua tag HTML → spasi
                    regexp_replace(
                        -- Langkah 1: <br> / <br/> → spasi
                        regexp_replace(raw, '<br\s*/?>', ' ', 'gi'),
                    '<[^>]+>', ' ', 'g'),
                '&amp;|&lt;|&gt;|&quot;|&apos;|&nbsp;|&#[0-9]+;|&[a-z]{2,6};',
                ' ', 'gi'),
            '\s+', ' ', 'g')
        ),
    '');
$$;

COMMENT ON FUNCTION analitik.strip_html(text) IS
    'Strip HTML tags (<tag>, </tag>, <br/>) dan decode entitas HTML '
    '(&amp;, &nbsp;, &#160;, dll.) menjadi teks plain. '
    'IMMUTABLE STRICT → aman di MV dan expression index. '
    'Return NULL jika input NULL atau hasil akhir string kosong.';

-- ================================================================
-- MATERIALIZED VIEW: analitik.mv_portofolio
-- ================================================================

CREATE MATERIALIZED VIEW analitik.mv_portofolio AS
WITH
raw AS (
    SELECT
        p.kelas_id,
        p.tgl_entri,
        p.lengkap,
        p.nilai                  AS nilai_portofolio,
        CASE
            WHEN p.isian ? '12'  THEN 'baru'
            WHEN p.isian ? '1'   THEN 'lama'
            ELSE                      'kosong'
        END                      AS skema_pertanyaan,
        p.isian->>'12' AS r12, p.isian->>'13' AS r13,
        p.isian->>'14' AS r14, p.isian->>'15' AS r15,
        p.isian->>'16' AS r16, p.isian->>'17' AS r17,
        p.isian->>'18' AS r18, p.isian->>'19' AS r19,
        p.isian->>'1'  AS r1,  p.isian->>'2'  AS r2,
        p.isian->>'3'  AS r3,  p.isian->>'4'  AS r4,
        p.isian->>'5'  AS r5,  p.isian->>'6'  AS r6,
        p.isian->>'7'  AS r7,  p.isian->>'8'  AS r8,
        p.isian->>'9'  AS r9,  p.isian->>'10' AS r10,
        p.isian->>'11' AS r11,
        p.komentar->>'6' AS k6, p.komentar->>'7' AS k7,
        p.komentar->>'8' AS k8, p.komentar->>'9' AS k9,
        p.komentar->>'1' AS kg1, p.komentar->>'2' AS kg2,
        p.komentar->>'3' AS kg3, p.komentar->>'4' AS kg4,
        p.komentar->>'5' AS kg5
    FROM evaluasi.portofolio p
    WHERE p.isian IS NOT NULL
      AND p.isian <> '{}'::jsonb
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
    mk.kode_prodi,
    mk.singkatan_prodi,
    mk.nama_prodi_id,
    mk.jenjang,
    mk.kode_fakultas,
    mk.nama_fakultas_id,
    mk.semua_dosen_id,
    mk.semua_dosen_nama_gelar,
    r.tgl_entri         AS tanggal_entri,
    r.lengkap,
    r.nilai_portofolio,
    r.skema_pertanyaan,
    -- ERA BARU
    analitik.strip_html(r.r12) AS metode_perkuliahan,
    analitik.strip_html(r.r13) AS komponen_penilaian,
    analitik.strip_html(r.r14) AS statistik_nilai_kelas,
    analitik.strip_html(r.r15) AS analisis_ketercapaian_outcomes,
    analitik.strip_html(r.r16) AS tanggapan_kuesioner_mahasiswa,
    analitik.strip_html(r.r17) AS refleksi_perkuliahan,
    analitik.strip_html(r.r18) AS usulan_perbaikan_dosen,
    analitik.strip_html(r.r19) AS rekomendasi_ke_itb,
    -- ERA LAMA
    analitik.strip_html(r.r1)  AS lama_metode_perkuliahan,
    analitik.strip_html(r.r7)  AS lama_statistik_kelas,
    analitik.strip_html(r.r2)  AS lama_outcomes_matakuliah,
    analitik.strip_html(r.r3)  AS lama_sistem_penilaian,
    analitik.strip_html(r.r8)  AS lama_analisis_statistik_ketercapaian,
    analitik.strip_html(r.r4)  AS lama_uraian_kuesioner_statistik,
    analitik.strip_html(r.r9)  AS lama_komentar_kuesioner_mahasiswa,
    analitik.strip_html(r.r5)  AS lama_refleksi_perkuliahan,
    analitik.strip_html(r.r6)  AS lama_rencana_tindak_lanjut,
    analitik.strip_html(r.r10) AS lama_rekomendasi_perbaikan_dosen,
    analitik.strip_html(r.r11) AS lama_rekomendasi_itb,
    -- KOMENTAR VERIFIKATOR ERA BARU
    analitik.strip_html(r.k6)  AS komentar_penyelenggaraan,
    analitik.strip_html(r.k7)  AS komentar_ketercapaian,
    analitik.strip_html(r.k8)  AS komentar_refleksi,
    analitik.strip_html(r.k9)  AS komentar_rekomendasi,
    -- KOMENTAR VERIFIKATOR ERA LAMA
    analitik.strip_html(r.kg1) AS lama_komentar_pencapaian_outcomes,
    analitik.strip_html(r.kg2) AS lama_komentar_pelaksanaan_kuliah,
    analitik.strip_html(r.kg3) AS lama_komentar_refleksi,
    analitik.strip_html(r.kg4) AS lama_komentar_rencana_tindak_lanjut,
    analitik.strip_html(r.kg5) AS lama_komentar_rekomendasi
FROM raw r
JOIN analitik.mv_kelas mk ON mk.kelas_id = r.kelas_id;

-- Index untuk mv_portofolio
CREATE UNIQUE INDEX idx_mv_portofolio_pk
    ON analitik.mv_portofolio (kelas_id);
CREATE INDEX idx_mv_portofolio_tahun_ajaran
    ON analitik.mv_portofolio (tahun_ajaran, kode_prodi);
CREATE INDEX idx_mv_portofolio_matkul
    ON analitik.mv_portofolio (kode_matkul, tahun_ajaran);
CREATE INDEX idx_mv_portofolio_dosen_arr
    ON analitik.mv_portofolio USING gin (semua_dosen_id);
CREATE INDEX idx_mv_portofolio_fak_semester
    ON analitik.mv_portofolio (kode_fakultas, semester, tahun);
CREATE INDEX idx_mv_portofolio_era_baru
    ON analitik.mv_portofolio (kelas_id)
    WHERE skema_pertanyaan = 'baru';

COMMENT ON MATERIALIZED VIEW analitik.mv_portofolio IS
    'Wide table portofolio dosen — grain: 1 baris = 1 kelas. '
    'Sumber: evaluasi.portofolio JOIN analitik.mv_kelas. '
    'Era baru (skema_pertanyaan=''baru''): kd_pertanyaan 12-19, [20181,∞), ~54K baris. '
    'Era lama (skema_pertanyaan=''lama''): kd_pertanyaan 1-11, ~27K baris. '
    'Semua teks sudah distrip HTML via analitik.strip_html(). '
    'Refresh setelah analitik.mv_kelas. '
-- ================================================================
-- COMMENT ON MATERIALIZED VIEW
-- ================================================================
COMMENT ON MATERIALIZED VIEW analitik.mv_portofolio IS
    'Wide table portofolio dosen — grain: 1 baris = 1 kelas. '
    'Sumber: evaluasi.portofolio JOIN analitik.mv_kelas. '
    'Era baru (skema_pertanyaan=''baru''): kd_pertanyaan 12-19, [20181,∞), ~54K baris. '
    'Era lama (skema_pertanyaan=''lama''): kd_pertanyaan 1-11, ~27K baris. '
    'Semua teks sudah distrip HTML via analitik.strip_html(). '
    'Refresh setelah analitik.mv_kelas. '
    '--- '
    'CATATAN HISTORIS — Phased rollout skema evaluasi: '
    'Kuesioner mahasiswa beralih ke q21-q37 mulai 2016/semester-1, '
    'sedangkan portofolio dosen baru beralih ke q12-19 mulai 2018/semester-1. '
    'Akibatnya ~11.618 kelas (2016/1, 2016/2, 2017/1, 2017/2) '
    'memiliki skema_pertanyaan=''lama'' meski kuesioner mahasiswanya sudah era baru. '
    'Untuk kelas-kelas ini, respons dosen terhadap kuesioner mahasiswa '
    'ada di kolom lama_uraian_kuesioner_statistik (kd_pertanyaan=4) '
    'dan lama_komentar_kuesioner_mahasiswa (kd_pertanyaan=9).';

-- ================================================================
-- COMMENT ON COLUMN — DIMENSI KELAS
-- ================================================================
COMMENT ON COLUMN analitik.mv_portofolio.kelas_id
    IS 'PK MV. Identitas kelas (FK ke kelas.kelas).';
COMMENT ON COLUMN analitik.mv_portofolio.kode_mk
    IS 'Kode mata kuliah (6 karakter), contoh: MA1101.';
COMMENT ON COLUMN analitik.mv_portofolio.nama_mk_id
    IS 'Nama mata kuliah Bahasa Indonesia.';
COMMENT ON COLUMN analitik.mv_portofolio.nama_mk_en
    IS 'Nama mata kuliah Bahasa Inggris.';
COMMENT ON COLUMN analitik.mv_portofolio.sks
    IS 'Jumlah SKS mata kuliah.';
COMMENT ON COLUMN analitik.mv_portofolio.no_kelas
    IS 'Nomor urut kelas dalam satu mata kuliah per semester.';
COMMENT ON COLUMN analitik.mv_portofolio.semester
    IS '1=ganjil, 2/3=genap/pendek.';
COMMENT ON COLUMN analitik.mv_portofolio.tahun
    IS 'Tahun akademik (4 digit).';
COMMENT ON COLUMN analitik.mv_portofolio.tahun_ajaran
    IS 'Format YYYY/YYYY, contoh: 2022/2023.';
COMMENT ON COLUMN analitik.mv_portofolio.tahun_kurikulum
    IS 'Tahun kurikulum yang berlaku untuk mata kuliah ini.';
COMMENT ON COLUMN analitik.mv_portofolio.jenis_nilai
    IS 'ABCDE atau PassFail.';
COMMENT ON COLUMN analitik.mv_portofolio.kode_prodi
    IS 'no_ps program studi penyelenggara.';
COMMENT ON COLUMN analitik.mv_portofolio.singkatan_prodi
    IS 'Singkatan prodi (2 karakter).';
COMMENT ON COLUMN analitik.mv_portofolio.nama_prodi_id
    IS 'Nama program studi Bahasa Indonesia.';
COMMENT ON COLUMN analitik.mv_portofolio.jenjang
    IS 'Jenjang studi: S1, S2, S3, D3, dst.';
COMMENT ON COLUMN analitik.mv_portofolio.kode_fakultas
    IS 'Kode fakultas/sekolah (FMIPA, STEI, FTI, dst.).';
COMMENT ON COLUMN analitik.mv_portofolio.nama_fakultas_id
    IS 'Nama fakultas/sekolah Bahasa Indonesia.';
COMMENT ON COLUMN analitik.mv_portofolio.semua_dosen_id
    IS 'Array dosen_id semua pengajar kelas (dari kelas.pengajar).';
COMMENT ON COLUMN analitik.mv_portofolio.semua_dosen_nama_gelar
    IS 'Array nama lengkap dengan gelar semua pengajar kelas.';

-- ================================================================
-- COMMENT ON COLUMN — METADATA PORTOFOLIO
-- ================================================================
COMMENT ON COLUMN analitik.mv_portofolio.tgl_entri
    IS 'Tanggal dosen menyelesaikan pengisian portofolio.';
COMMENT ON COLUMN analitik.mv_portofolio.lengkap
    IS 'TRUE jika portofolio sudah dinyatakan lengkap oleh verifikator.';
COMMENT ON COLUMN analitik.mv_portofolio.nilai_portofolio
    IS 'Nilai numerik portofolio hasil verifikasi.';
COMMENT ON COLUMN analitik.mv_portofolio.skema_pertanyaan
    IS '"baru" = kd_pertanyaan 12-19 [20181,∞) | '
       '"lama" = kd_pertanyaan 1-11 (sebelum 2018) | '
       '"kosong" = isian NULL atau {}.';

-- ================================================================
-- COMMENT ON COLUMN — ERA BARU (kd_pertanyaan 12–19)
-- ================================================================
COMMENT ON COLUMN analitik.mv_portofolio.metode_perkuliahan
    IS '[ACTIVE | kd_pertanyaan=12 | kd_grup=6 Penyelenggaraan Perkuliahan] '
       'Uraian metode yang digunakan dalam pembelajaran: diskusi, '
       'collaborative learning, kuliah tamu, project, dsb.';
COMMENT ON COLUMN analitik.mv_portofolio.komponen_penilaian
    IS '[ACTIVE | kd_pertanyaan=13 | kd_grup=6 Penyelenggaraan Perkuliahan] '
       'Komponen-komponen penilaian (UTS, UAS, kuis, tugas, praktikum, presentasi, dll.) '
       'beserta bobot dan standar konversi nilai ke indeks.';
COMMENT ON COLUMN analitik.mv_portofolio.statistik_nilai_kelas
    IS '[ACTIVE | kd_pertanyaan=14 | kd_grup=7 Ketercapaian Outcomes] '
       'Distribusi nilai ujian, PR, kuis, dan bentuk penilaian lainnya, '
       'serta data statistik penting kelas lainnya.';
COMMENT ON COLUMN analitik.mv_portofolio.analisis_ketercapaian_outcomes
    IS '[ACTIVE | kd_pertanyaan=15 | kd_grup=7 Ketercapaian Outcomes] '
       'Uraian tentang tingkat keberhasilan pembelajaran dan ketercapaian outcomes '
       'beserta faktor-faktor yang mempengaruhinya berdasarkan data terkumpul.';
COMMENT ON COLUMN analitik.mv_portofolio.tanggapan_kuesioner_mahasiswa
    IS '[ACTIVE | kd_pertanyaan=16 | kd_grup=8 Refleksi Dosen] '
       'Tanggapan dosen terhadap penilaian mahasiswa melalui kuesioner.';
COMMENT ON COLUMN analitik.mv_portofolio.refleksi_perkuliahan
    IS '[ACTIVE | kd_pertanyaan=17 | kd_grup=8 Refleksi Dosen] '
       'Uraian tentang pelaksanaan perkuliahan: keberhasilan dan kegagalan rencana, '
       'masalah belajar mahasiswa, persoalan yang dihadapi dosen, temuan penting.';
COMMENT ON COLUMN analitik.mv_portofolio.usulan_perbaikan_dosen
    IS '[ACTIVE | kd_pertanyaan=18 | kd_grup=9 Rekomendasi Tindak Lanjut] '
       'Hal-hal yang perlu dilakukan oleh dosen pengampu pada perkuliahan mendatang '
       'untuk meningkatkan kualitas dan keberhasilan pembelajaran.';
COMMENT ON COLUMN analitik.mv_portofolio.rekomendasi_ke_itb
    IS '[ACTIVE | kd_pertanyaan=19 | kd_grup=9 Rekomendasi Tindak Lanjut] '
       'Hal-hal yang perlu dilakukan oleh ITB (institut, fakultas/sekolah, prodi) '
       'untuk mendukung keberhasilan perkuliahan: kurikulum, sarpras, fasilitas.';
-- ================================================================
-- COMMENT ON COLUMN — ERA LAMA (kd_pertanyaan 1–11)
-- ================================================================
COMMENT ON COLUMN analitik.mv_portofolio.lama_metode_perkuliahan
    IS '[ARCHIVED | kd_pertanyaan=1 | kd_grup=2 Pelaksanaan Kuliah] '
       'Metode Perkuliahan.';
COMMENT ON COLUMN analitik.mv_portofolio.lama_statistik_kelas
    IS '[ARCHIVED | kd_pertanyaan=7 | kd_grup=2 Pelaksanaan Kuliah] '
       'Statistik Kelas.';
COMMENT ON COLUMN analitik.mv_portofolio.lama_outcomes_matakuliah
    IS '[ARCHIVED | kd_pertanyaan=2 | kd_grup=1 Pencapaian Tujuan/Outcomes] '
       'Outcomes Matakuliah.';
COMMENT ON COLUMN analitik.mv_portofolio.lama_sistem_penilaian
    IS '[ARCHIVED | kd_pertanyaan=3 | kd_grup=1 Pencapaian Tujuan/Outcomes] '
       'Sistem Penilaian.';
COMMENT ON COLUMN analitik.mv_portofolio.lama_analisis_statistik_ketercapaian
    IS '[ARCHIVED | kd_pertanyaan=8 | kd_grup=1 Pencapaian Tujuan/Outcomes] '
       'Analisis terhadap Statistik Kelas dan Ketercapaian Outcomes.';
COMMENT ON COLUMN analitik.mv_portofolio.lama_uraian_kuesioner_statistik
    IS '[ARCHIVED | kd_pertanyaan=4 | kd_grup=3 Refleksi] '
       'Uraian terhadap Hasil Kuesioner dan Statistik Kelas.';
COMMENT ON COLUMN analitik.mv_portofolio.lama_komentar_kuesioner_mahasiswa
    IS '[ARCHIVED | kd_pertanyaan=9 | kd_grup=3 Refleksi] '
       'Komentar terhadap Hasil Kuesioner Mahasiswa.';
COMMENT ON COLUMN analitik.mv_portofolio.lama_refleksi_perkuliahan
    IS '[ARCHIVED | kd_pertanyaan=5 | kd_grup=3 Refleksi] '
       'Refleksi Pelaksanaan Perkuliahan.';
COMMENT ON COLUMN analitik.mv_portofolio.lama_rencana_tindak_lanjut
    IS '[ARCHIVED | kd_pertanyaan=6 | kd_grup=4 Rencana Tindak Lanjut] '
       'Rencana Tindak Lanjut.';
COMMENT ON COLUMN analitik.mv_portofolio.lama_rekomendasi_perbaikan_dosen
    IS '[ARCHIVED | kd_pertanyaan=10 | kd_grup=5 Rekomendasi Tindak Lanjut] '
       'Rekomendasi Perbaikan oleh Dosen Berikutnya.';
COMMENT ON COLUMN analitik.mv_portofolio.lama_rekomendasi_itb
    IS '[ARCHIVED | kd_pertanyaan=11 | kd_grup=5 Rekomendasi Tindak Lanjut] '
       'Rekomendasi Perbaikan oleh ITB.';
-- ================================================================
-- COMMENT ON COLUMN — KOMENTAR VERIFIKATOR ERA BARU
-- ================================================================
COMMENT ON COLUMN analitik.mv_portofolio.komentar_penyelenggaraan
    IS '[ACTIVE | kd_grup=6] '
       'Komentar verifikator untuk grup Penyelenggaraan Perkuliahan.';
COMMENT ON COLUMN analitik.mv_portofolio.komentar_ketercapaian
    IS '[ACTIVE | kd_grup=7] '
       'Komentar verifikator untuk grup Ketercapaian Outcomes.';
COMMENT ON COLUMN analitik.mv_portofolio.komentar_refleksi
    IS '[ACTIVE | kd_grup=8] '
       'Komentar verifikator untuk grup Refleksi Dosen.';
COMMENT ON COLUMN analitik.mv_portofolio.komentar_rekomendasi
    IS '[ACTIVE | kd_grup=9] '
       'Komentar verifikator untuk grup Rekomendasi Tindak Lanjut.';
-- ================================================================
-- COMMENT ON COLUMN — KOMENTAR VERIFIKATOR ERA LAMA
-- ================================================================
COMMENT ON COLUMN analitik.mv_portofolio.lama_komentar_pencapaian_outcomes
    IS '[ARCHIVED | kd_grup=1] '
       'Komentar verifikator untuk grup Pencapaian Tujuan/Outcomes.';
COMMENT ON COLUMN analitik.mv_portofolio.lama_komentar_pelaksanaan_kuliah
    IS '[ARCHIVED | kd_grup=2] '
       'Komentar verifikator untuk grup Pelaksanaan Kuliah.';
COMMENT ON COLUMN analitik.mv_portofolio.lama_komentar_refleksi
    IS '[ARCHIVED | kd_grup=3] '
       'Komentar verifikator untuk grup Refleksi.';
COMMENT ON COLUMN analitik.mv_portofolio.lama_komentar_rencana_tindak_lanjut
    IS '[ARCHIVED | kd_grup=4] '
       'Komentar verifikator untuk grup Rencana Tindak Lanjut.';
COMMENT ON COLUMN analitik.mv_portofolio.lama_komentar_rekomendasi
    IS '[ARCHIVED | kd_grup=5] '
       'Komentar verifikator untuk grup Rekomendasi Tindak Lanjut.';