-- ============================================================
-- ITB WISUDAWAN SURVEY — MATERIALIZED VIEWS
-- Jalankan SETELAH wisudawan_schema_table.sql
--
-- Urutan CREATE (dependency order):
--   1. mv_wisudawan_statistik_prodi   (agregat per prodi per periode)
--   2. mv_dashboard_kpi               (KPI card — pct + avg per prodi)
--   3. mv_dashboard_distribution      (distribusi Likert per item)
--   4. mv_dashboard_trend             (time-series per fakultas)
--   5. mv_dashboard_rekomendasi       (distribusi alasan rekomendasi)
--   6. mv_dashboard_masalah_studi     (analisis mendalam masalah mahasiswa)
--   7. mv_dashboard_softskill         (radar chart softskill per item)
--
-- Urutan REFRESH (sama dengan dependency order):
--   REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_wisudawan_statistik_prodi;
--   REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_dashboard_kpi;
--   REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_dashboard_distribution;
--   REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_dashboard_trend;
--   REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_dashboard_rekomendasi;
--   REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_dashboard_masalah_studi;
--   REFRESH MATERIALIZED VIEW CONCURRENTLY public.mv_dashboard_softskill;
--
-- ─── DEFINISI THRESHOLD ────────────────────────────────────────────────────
-- "Positif" / "Puas" per skala:
--   likert4_agree  : score >= 3  (Cenderung Setuju + Setuju)
--   likert4_freq   : score >= 2  (pernah mengalami = Jarang s/d Selalu)
--   likert4_freq dampak: score >= 3  (pengaruh cukup s/d besar)
--   likert5_expect : score >= 3  (Sebagian besar memenuhi s/d Melampaui)
--   likert5_dev    : score >= 3  (Moderately s/d Highly Developed)
-- ============================================================


-- ============================================================
-- 1. mv_wisudawan_statistik_prodi
-- ============================================================
-- Statistik ringkas per (prodi_id, kd_fak, strata, periode_wisuda).
-- Digunakan sebagai sumber data agregat internal.
-- REFRESH setelah setiap ingest.
-- ============================================================

CREATE MATERIALIZED VIEW public.mv_wisudawan_statistik_prodi AS
SELECT
    r.prodi_id,
    r.kd_fak,
    r.strata,
    r.periode_wisuda,
    COUNT(r.responden_id)                               AS jumlah_responden,

    -- Section A: Fasilitas ITB
    ROUND(AVG(a.skor_avg), 2)                           AS avg_skor_fasilitas_itb,
    ROUND(AVG(a.kepuasan_umum), 2)                      AS avg_kepuasan_umum_itb,

    -- Section B: Prodi
    ROUND(AVG(b.skor_avg), 2)                           AS avg_skor_prodi,
    ROUND(AVG(b.dosen_prodi_profesional), 2)                  AS avg_dosen_prodi_profesional,
    ROUND(AVG(b.senang_prodi), 2)                       AS avg_senang_prodi,
    ROUND(AVG(b.pilih_prodi_yang_sama), 2)                         AS avg_pilih_prodi_yang_sama,

    -- Section B2: Rekomendasi (distribusi)
    COUNT(*) FILTER (WHERE b.rekomendasi_aspek = 'Kualitas dosen')        AS rek_kualitas_dosen,
    COUNT(*) FILTER (WHERE b.rekomendasi_aspek = 'Suasana akademik')       AS rek_suasana,
    COUNT(*) FILTER (WHERE b.rekomendasi_aspek = 'Jejaring alumni')        AS rek_jejaring,
    COUNT(*) FILTER (WHERE b.rekomendasi_aspek = 'Fasilitas akademik')     AS rek_fasilitas,
    COUNT(*) FILTER (WHERE b.rekomendasi_aspek = 'Lapangan pekerjaan')     AS rek_lapangan_kerja,
    COUNT(*) FILTER (WHERE b.rekomendasi_aspek = 'Tidak merekomendasikan') AS tdk_rekomendasikan,

    -- Section C: Softskill
    ROUND(AVG(c.skor_avg_kemampuan), 2)                 AS avg_skor_kemampuan,
    ROUND(AVG(c.skor_avg_karakter), 2)                  AS avg_skor_karakter,
    ROUND(AVG(c.kerja_tim), 2)                          AS avg_kerja_tim,
    ROUND(AVG(c.problem_solving), 2)                    AS avg_problem_solving,

    -- Section D: Masalah
    ROUND(AVG(d.masalah_akademis), 2)                   AS avg_masalah_akademis,
    ROUND(AVG(d.masalah_psikologis), 2)                 AS avg_masalah_psikologis,
    ROUND(AVG(d.masalah_keuangan), 2)                   AS avg_masalah_keuangan,

    -- Rencana studi lanjut
    COUNT(*) FILTER (WHERE rl.punya_rencana = 'Ya')     AS jml_rencana_lanjut,

    -- Essay count (proxy engagement pengisian)
    COUNT(DISTINCT e.essay_id)                          AS jml_essay_diisi

FROM public.wisudawan_responden r
LEFT JOIN public.wisudawan_skor_itb       a  ON a.responden_id = r.responden_id
LEFT JOIN public.wisudawan_skor_prodi     b  ON b.responden_id = r.responden_id
LEFT JOIN public.wisudawan_skor_softskill c  ON c.responden_id = r.responden_id
LEFT JOIN public.wisudawan_masalah_studi  d  ON d.responden_id = r.responden_id
LEFT JOIN public.wisudawan_rencana_lanjut rl ON rl.responden_id = r.responden_id
LEFT JOIN public.wisudawan_essay          e  ON e.responden_id = r.responden_id
GROUP BY r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda
WITH NO DATA;

CREATE UNIQUE INDEX idx_mv_wisudawan_prodi_pk
    ON public.mv_wisudawan_statistik_prodi (prodi_id, strata, periode_wisuda);
CREATE INDEX idx_mv_wisudawan_prodi_fak
    ON public.mv_wisudawan_statistik_prodi (kd_fak, periode_wisuda);


-- ============================================================
-- 2. mv_dashboard_kpi
-- ============================================================
-- Satu baris per (prodi_id, kd_fak, strata, periode_wisuda).
-- Semua metrik dalam bentuk PERSENTASE dan COUNT — siap render
-- langsung ke KPI card tanpa kalkulasi tambahan di backend.
--
-- Definisi persentase:
--   pct_* = (jumlah yang memenuhi threshold / total yang mengisi) * 100
--   Hanya menghitung responden yang mengisi pertanyaan tsb (IS NOT NULL).
-- ============================================================

CREATE MATERIALIZED VIEW public.mv_dashboard_kpi AS
SELECT
    r.prodi_id,
    r.kd_fak,
    r.strata,
    r.periode_wisuda,

    -- ── Ukuran sampel ───────────────────────────────────────────
    COUNT(r.responden_id)                               AS jumlah_responden,

    -- ── Section A: Kepuasan Fasilitas ITB ───────────────────────
    ROUND(
        COUNT(*) FILTER (WHERE a.skor_avg >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE a.skor_avg IS NOT NULL), 0)
    , 1)                                                AS pct_puas_fasilitas_itb,

    ROUND(
        COUNT(*) FILTER (WHERE a.ruang_kelas >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE a.ruang_kelas IS NOT NULL), 0)
    , 1)                                                AS pct_puas_ruang_kelas,

    ROUND(
        COUNT(*) FILTER (WHERE a.kepuasan_umum >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE a.kepuasan_umum IS NOT NULL), 0)
    , 1)                                                AS pct_puas_keseluruhan_itb,

    -- ── Section B: Kepuasan Program Studi ───────────────────────
    ROUND(
        COUNT(*) FILTER (WHERE b.skor_avg >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE b.skor_avg IS NOT NULL), 0)
    , 1)                                                AS pct_puas_prodi,

    ROUND(
        COUNT(*) FILTER (WHERE b.pilih_prodi_yang_sama >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE b.pilih_prodi_yang_sama IS NOT NULL), 0)
    , 1)                                                AS pct_pilih_prodi_lagi,

    ROUND(
        COUNT(*) FILTER (
            WHERE b.rekomendasi_aspek IS NOT NULL
              AND b.rekomendasi_aspek != 'Tidak merekomendasikan'
        )
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE b.rekomendasi_aspek IS NOT NULL), 0)
    , 1)                                                AS pct_rekomendasikan_prodi,

    -- ── Section C: Softskill & Karakter ─────────────────────────
    ROUND(
        COUNT(*) FILTER (WHERE c.skor_avg_kemampuan >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE c.skor_avg_kemampuan IS NOT NULL), 0)
    , 1)                                                AS pct_positif_softskill,

    ROUND(
        COUNT(*) FILTER (WHERE c.skor_avg_karakter >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE c.skor_avg_karakter IS NOT NULL), 0)
    , 1)                                                AS pct_positif_karakter,

    -- ── Section D: Masalah Studi ─────────────────────────────────
    -- Threshold "pernah": score >= 2 (Jarang s/d Selalu)
    ROUND(
        COUNT(*) FILTER (WHERE d.masalah_akademis >= 2)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.masalah_akademis IS NOT NULL), 0)
    , 1)                                                AS pct_pernah_masalah_akademis,

    ROUND(
        COUNT(*) FILTER (WHERE d.masalah_psikologis >= 2)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.masalah_psikologis IS NOT NULL), 0)
    , 1)                                                AS pct_pernah_masalah_psikologis,

    ROUND(
        COUNT(*) FILTER (WHERE d.masalah_keuangan >= 2)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.masalah_keuangan IS NOT NULL), 0)
    , 1)                                                AS pct_pernah_masalah_keuangan,

    ROUND(
        COUNT(*) FILTER (WHERE d.masalah_kesehatan >= 2)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.masalah_kesehatan IS NOT NULL), 0)
    , 1)                                                AS pct_pernah_masalah_kesehatan,

    ROUND(
        COUNT(*) FILTER (WHERE d.masalah_sosial_budaya >= 2)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.masalah_sosial_budaya IS NOT NULL), 0)
    , 1)                                                AS pct_pernah_masalah_sosial,

    -- Threshold "dampak signifikan": score >= 3 (Sering/cukup s/d Selalu/besar)
    ROUND(
        COUNT(*) FILTER (WHERE d.dampak_psikologis >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.dampak_psikologis IS NOT NULL), 0)
    , 1)                                                AS pct_dampak_signifikan_psikologis,

    ROUND(
        COUNT(*) FILTER (WHERE d.dampak_keuangan >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.dampak_keuangan IS NOT NULL), 0)
    , 1)                                                AS pct_dampak_signifikan_keuangan,

    -- Threshold "dukungan memadai": score >= 3 (Sebagian besar s/d Melampaui)
    ROUND(
        COUNT(*) FILTER (WHERE d.dukungan_konseling >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.dukungan_konseling IS NOT NULL), 0)
    , 1)                                                AS pct_puas_dukungan_konseling,

    ROUND(
        COUNT(*) FILTER (WHERE d.dukungan_beasiswa >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.dukungan_beasiswa IS NOT NULL), 0)
    , 1)                                                AS pct_puas_dukungan_beasiswa,

    -- ── Rencana Studi Lanjut ─────────────────────────────────────
    ROUND(
        COUNT(*) FILTER (WHERE rl.punya_rencana = 'Ya')
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE rl.punya_rencana IS NOT NULL), 0)
    , 1)                                                AS pct_rencana_studi_lanjut,

    -- ── Raw averages (untuk penggunaan internal/sorting) ─────────
    ROUND(AVG(a.skor_avg), 2)                           AS avg_skor_fasilitas_itb,
    ROUND(AVG(b.skor_avg), 2)                           AS avg_skor_prodi,
    ROUND(AVG(c.skor_avg_kemampuan), 2)                 AS avg_skor_kemampuan,
    ROUND(AVG(c.skor_avg_karakter), 2)                  AS avg_skor_karakter

FROM public.wisudawan_responden r
LEFT JOIN public.wisudawan_skor_itb        a  ON a.responden_id = r.responden_id
LEFT JOIN public.wisudawan_skor_prodi      b  ON b.responden_id = r.responden_id
LEFT JOIN public.wisudawan_skor_softskill  c  ON c.responden_id = r.responden_id
LEFT JOIN public.wisudawan_masalah_studi   d  ON d.responden_id = r.responden_id
LEFT JOIN public.wisudawan_rencana_lanjut  rl ON rl.responden_id = r.responden_id
GROUP BY r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda
WITH NO DATA;

CREATE UNIQUE INDEX idx_mv_kpi_pk
    ON public.mv_dashboard_kpi (prodi_id, strata, periode_wisuda);
CREATE INDEX idx_mv_kpi_fak
    ON public.mv_dashboard_kpi (kd_fak, periode_wisuda);


-- ============================================================
-- 3. mv_dashboard_distribution
-- ============================================================
-- Satu baris per (question_code, prodi_id, strata, periode_wisuda, skor_value).
-- Berguna untuk:
--   - Stacked bar chart distribusi Likert
--   - Polarization analysis
--   - Menghindari misleading average
--
-- Hanya mencakup pertanyaan Likert (bukan essay/categorical).
-- FSRD dan SBM tidak dimasukkan karena populasi minority —
-- buat MV terpisah jika diperlukan.
-- ============================================================

CREATE MATERIALIZED VIEW public.mv_dashboard_distribution AS
WITH raw_scores AS (

    -- ── Section A: Fasilitas ITB (U03, likert4_agree) ────────────
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U03[SQ001]'::TEXT AS question_code, 'U03'::TEXT AS question_group,
           'likert4_agree'::TEXT AS answer_type, a.ruang_kelas AS skor_value
    FROM public.wisudawan_skor_itb a
    JOIN public.wisudawan_responden r ON r.responden_id = a.responden_id
    WHERE a.ruang_kelas IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U03[SQ002]', 'U03', 'likert4_agree', a.kelas_kondusif
    FROM public.wisudawan_skor_itb a
    JOIN public.wisudawan_responden r ON r.responden_id = a.responden_id
    WHERE a.kelas_kondusif IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U03[SQ003]', 'U03', 'likert4_agree', a.lab_kondusif
    FROM public.wisudawan_skor_itb a
    JOIN public.wisudawan_responden r ON r.responden_id = a.responden_id
    WHERE a.lab_kondusif IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U03[SQ004]', 'U03', 'likert4_agree', a.internet
    FROM public.wisudawan_skor_itb a
    JOIN public.wisudawan_responden r ON r.responden_id = a.responden_id
    WHERE a.internet IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U03[SQ005]', 'U03', 'likert4_agree', a.fasil_keprofesian
    FROM public.wisudawan_skor_itb a
    JOIN public.wisudawan_responden r ON r.responden_id = a.responden_id
    WHERE a.fasil_keprofesian IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U03[SQ006]', 'U03', 'likert4_agree', a.pustaka
    FROM public.wisudawan_skor_itb a
    JOIN public.wisudawan_responden r ON r.responden_id = a.responden_id
    WHERE a.pustaka IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U03[SQ007]', 'U03', 'likert4_agree', a.perangkat_uptodate
    FROM public.wisudawan_skor_itb a
    JOIN public.wisudawan_responden r ON r.responden_id = a.responden_id
    WHERE a.perangkat_uptodate IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U03[SQ008]', 'U03', 'likert4_agree', a.toilet
    FROM public.wisudawan_skor_itb a
    JOIN public.wisudawan_responden r ON r.responden_id = a.responden_id
    WHERE a.toilet IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U03[SQ009]', 'U03', 'likert4_agree', a.kantin
    FROM public.wisudawan_skor_itb a
    JOIN public.wisudawan_responden r ON r.responden_id = a.responden_id
    WHERE a.kantin IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U03[SQ010]', 'U03', 'likert4_agree', a.rekreasi
    FROM public.wisudawan_skor_itb a
    JOIN public.wisudawan_responden r ON r.responden_id = a.responden_id
    WHERE a.rekreasi IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U03[SQ011]', 'U03', 'likert4_agree', a.kesehatan
    FROM public.wisudawan_skor_itb a
    JOIN public.wisudawan_responden r ON r.responden_id = a.responden_id
    WHERE a.kesehatan IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U03[SQ012]', 'U03', 'likert4_agree', a.kepuasan_umum
    FROM public.wisudawan_skor_itb a
    JOIN public.wisudawan_responden r ON r.responden_id = a.responden_id
    WHERE a.kepuasan_umum IS NOT NULL

    UNION ALL
    -- ── Section B: Kepuasan Prodi (U01, likert4_agree) ───────────
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U01[SQ001]', 'U01', 'likert4_agree', b.dosen_wali_tersedia
    FROM public.wisudawan_skor_prodi b
    JOIN public.wisudawan_responden r ON r.responden_id = b.responden_id
    WHERE b.dosen_wali_tersedia IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U01[SQ002]', 'U01', 'likert4_agree', b.dosen_wali_membantu
    FROM public.wisudawan_skor_prodi b
    JOIN public.wisudawan_responden r ON r.responden_id = b.responden_id
    WHERE b.dosen_wali_membantu IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U01[SQ003]', 'U01', 'likert4_agree', b.dosen_prodi_interaksi_informal
    FROM public.wisudawan_skor_prodi b
    JOIN public.wisudawan_responden r ON r.responden_id = b.responden_id
    WHERE b.dosen_prodi_interaksi_informal IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U01[SQ004]', 'U01', 'likert4_agree', b.dosen_prodi_perhatian
    FROM public.wisudawan_skor_prodi b
    JOIN public.wisudawan_responden r ON r.responden_id = b.responden_id
    WHERE b.dosen_prodi_perhatian IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U01[SQ005]', 'U01', 'likert4_agree', b.dosen_prodi_profesional
    FROM public.wisudawan_skor_prodi b
    JOIN public.wisudawan_responden r ON r.responden_id = b.responden_id
    WHERE b.dosen_prodi_profesional IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U01[SQ006]', 'U01', 'likert4_agree', b.mk_wajib_pengetahuan
    FROM public.wisudawan_skor_prodi b
    JOIN public.wisudawan_responden r ON r.responden_id = b.responden_id
    WHERE b.mk_wajib_pengetahuan IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U01[SQ007]', 'U01', 'likert4_agree', b.mk_pilihan_luas
    FROM public.wisudawan_skor_prodi b
    JOIN public.wisudawan_responden r ON r.responden_id = b.responden_id
    WHERE b.mk_pilihan_luas IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U01[SQ008]', 'U01', 'likert4_agree', b.lab_selaras
    FROM public.wisudawan_skor_prodi b
    JOIN public.wisudawan_responden r ON r.responden_id = b.responden_id
    WHERE b.lab_selaras IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U01[SQ009]', 'U01', 'likert4_agree', b.sarana_prodi
    FROM public.wisudawan_skor_prodi b
    JOIN public.wisudawan_responden r ON r.responden_id = b.responden_id
    WHERE b.sarana_prodi IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U01[SQ010]', 'U01', 'likert4_agree', b.gambaran_kerja
    FROM public.wisudawan_skor_prodi b
    JOIN public.wisudawan_responden r ON r.responden_id = b.responden_id
    WHERE b.gambaran_kerja IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U01[SQ011]', 'U01', 'likert4_agree', b.senang_prodi
    FROM public.wisudawan_skor_prodi b
    JOIN public.wisudawan_responden r ON r.responden_id = b.responden_id
    WHERE b.senang_prodi IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U01[SQ012]', 'U01', 'likert4_agree', b.pilih_prodi_yang_sama
    FROM public.wisudawan_skor_prodi b
    JOIN public.wisudawan_responden r ON r.responden_id = b.responden_id
    WHERE b.pilih_prodi_yang_sama IS NOT NULL

    UNION ALL
    -- ── Section C1: Softskill (U04, likert4_agree) ───────────────
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U04[SQ001]', 'U04', 'likert4_agree', c.komunikasi_lisan
    FROM public.wisudawan_skor_softskill c
    JOIN public.wisudawan_responden r ON r.responden_id = c.responden_id
    WHERE c.komunikasi_lisan IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U04[SQ002]', 'U04', 'likert4_agree', c.komunikasi_tertulis
    FROM public.wisudawan_skor_softskill c
    JOIN public.wisudawan_responden r ON r.responden_id = c.responden_id
    WHERE c.komunikasi_tertulis IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U04[SQ003]', 'U04', 'likert4_agree', c.bahasa_asing
    FROM public.wisudawan_skor_softskill c
    JOIN public.wisudawan_responden r ON r.responden_id = c.responden_id
    WHERE c.bahasa_asing IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U04[SQ004]', 'U04', 'likert4_agree', c.problem_solving
    FROM public.wisudawan_skor_softskill c
    JOIN public.wisudawan_responden r ON r.responden_id = c.responden_id
    WHERE c.problem_solving IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U04[SQ005]', 'U04', 'likert4_agree', c.kritisi_pendapat_orang_lain
    FROM public.wisudawan_skor_softskill c
    JOIN public.wisudawan_responden r ON r.responden_id = c.responden_id
    WHERE c.kritisi_pendapat_orang_lain IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U04[SQ006]', 'U04', 'likert4_agree', c.kritisi_diri
    FROM public.wisudawan_skor_softskill c
    JOIN public.wisudawan_responden r ON r.responden_id = c.responden_id
    WHERE c.kritisi_diri IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U04[SQ007]', 'U04', 'likert4_agree', c.cara_berpendapat
    FROM public.wisudawan_skor_softskill c
    JOIN public.wisudawan_responden r ON r.responden_id = c.responden_id
    WHERE c.cara_berpendapat IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U04[SQ008]', 'U04', 'likert4_agree', c.kerja_tim
    FROM public.wisudawan_skor_softskill c
    JOIN public.wisudawan_responden r ON r.responden_id = c.responden_id
    WHERE c.kerja_tim IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U04[SQ009]', 'U04', 'likert4_agree', c.kerja_mandiri
    FROM public.wisudawan_skor_softskill c
    JOIN public.wisudawan_responden r ON r.responden_id = c.responden_id
    WHERE c.kerja_mandiri IS NOT NULL

    UNION ALL
    -- ── Section C2: Karakter (U05, likert4_agree) ────────────────
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U05[SQ001]', 'U05', 'likert4_agree', c.kejujuran
    FROM public.wisudawan_skor_softskill c
    JOIN public.wisudawan_responden r ON r.responden_id = c.responden_id
    WHERE c.kejujuran IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U05[SQ002]', 'U05', 'likert4_agree', c.komitmen
    FROM public.wisudawan_skor_softskill c
    JOIN public.wisudawan_responden r ON r.responden_id = c.responden_id
    WHERE c.komitmen IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U05[SQ003]', 'U05', 'likert4_agree', c.jaga_emosi
    FROM public.wisudawan_skor_softskill c
    JOIN public.wisudawan_responden r ON r.responden_id = c.responden_id
    WHERE c.jaga_emosi IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U05[SQ004]', 'U05', 'likert4_agree', c.kepedulian
    FROM public.wisudawan_skor_softskill c
    JOIN public.wisudawan_responden r ON r.responden_id = c.responden_id
    WHERE c.kepedulian IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U05[SQ005]', 'U05', 'likert4_agree', c.objektif
    FROM public.wisudawan_skor_softskill c
    JOIN public.wisudawan_responden r ON r.responden_id = c.responden_id
    WHERE c.objektif IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U05[SQ006]', 'U05', 'likert4_agree', c.pantang_menyerah
    FROM public.wisudawan_skor_softskill c
    JOIN public.wisudawan_responden r ON r.responden_id = c.responden_id
    WHERE c.pantang_menyerah IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U05[SQ007]', 'U05', 'likert4_agree', c.kepatuhan_aturan
    FROM public.wisudawan_skor_softskill c
    JOIN public.wisudawan_responden r ON r.responden_id = c.responden_id
    WHERE c.kepatuhan_aturan IS NOT NULL

    UNION ALL
    -- ── Section D1: Masalah Studi (U06, likert4_freq) ────────────
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U06[SQ001]', 'U06', 'likert4_freq', d.masalah_akademis
    FROM public.wisudawan_masalah_studi d
    JOIN public.wisudawan_responden r ON r.responden_id = d.responden_id
    WHERE d.masalah_akademis IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U06[SQ002]', 'U06', 'likert4_freq', d.masalah_keuangan
    FROM public.wisudawan_masalah_studi d
    JOIN public.wisudawan_responden r ON r.responden_id = d.responden_id
    WHERE d.masalah_keuangan IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U06[SQ003]', 'U06', 'likert4_freq', d.dampak_keuangan
    FROM public.wisudawan_masalah_studi d
    JOIN public.wisudawan_responden r ON r.responden_id = d.responden_id
    WHERE d.dampak_keuangan IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U06[SQ004]', 'U06', 'likert4_freq', d.masalah_psikologis
    FROM public.wisudawan_masalah_studi d
    JOIN public.wisudawan_responden r ON r.responden_id = d.responden_id
    WHERE d.masalah_psikologis IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U06[SQ005]', 'U06', 'likert4_freq', d.dampak_psikologis
    FROM public.wisudawan_masalah_studi d
    JOIN public.wisudawan_responden r ON r.responden_id = d.responden_id
    WHERE d.dampak_psikologis IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U06[SQ006]', 'U06', 'likert4_freq', d.masalah_sosial_budaya
    FROM public.wisudawan_masalah_studi d
    JOIN public.wisudawan_responden r ON r.responden_id = d.responden_id
    WHERE d.masalah_sosial_budaya IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U06[SQ007]', 'U06', 'likert4_freq', d.dampak_sosial_budaya
    FROM public.wisudawan_masalah_studi d
    JOIN public.wisudawan_responden r ON r.responden_id = d.responden_id
    WHERE d.dampak_sosial_budaya IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U06[SQ008]', 'U06', 'likert4_freq', d.masalah_kesehatan
    FROM public.wisudawan_masalah_studi d
    JOIN public.wisudawan_responden r ON r.responden_id = d.responden_id
    WHERE d.masalah_kesehatan IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U06[SQ009]', 'U06', 'likert4_freq', d.dampak_kesehatan
    FROM public.wisudawan_masalah_studi d
    JOIN public.wisudawan_responden r ON r.responden_id = d.responden_id
    WHERE d.dampak_kesehatan IS NOT NULL

    UNION ALL
    -- ── Section D2: Dukungan ITB (U07, likert5_expect) ───────────
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U07[SQ001]', 'U07', 'likert5_expect', d.dukungan_beasiswa
    FROM public.wisudawan_masalah_studi d
    JOIN public.wisudawan_responden r ON r.responden_id = d.responden_id
    WHERE d.dukungan_beasiswa IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U07[SQ002]', 'U07', 'likert5_expect', d.dukungan_konseling
    FROM public.wisudawan_masalah_studi d
    JOIN public.wisudawan_responden r ON r.responden_id = d.responden_id
    WHERE d.dukungan_konseling IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U07[SQ003]', 'U07', 'likert5_expect', d.dukungan_dosen_wali
    FROM public.wisudawan_masalah_studi d
    JOIN public.wisudawan_responden r ON r.responden_id = d.responden_id
    WHERE d.dukungan_dosen_wali IS NOT NULL
    UNION ALL
    SELECT r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda,
           'U07[SQ004]', 'U07', 'likert5_expect', d.dukungan_dosen_mk
    FROM public.wisudawan_masalah_studi d
    JOIN public.wisudawan_responden r ON r.responden_id = d.responden_id
    WHERE d.dukungan_dosen_mk IS NOT NULL

),
counted AS (
    SELECT
        question_code,
        question_group,
        answer_type,
        prodi_id,
        kd_fak,
        strata,
        periode_wisuda,
        skor_value,
        COUNT(*)                                        AS jumlah,
        SUM(COUNT(*)) OVER (
            PARTITION BY question_code, prodi_id, strata, periode_wisuda
        )                                               AS total_responden
    FROM raw_scores
    GROUP BY question_code, question_group, answer_type,
             prodi_id, kd_fak, strata, periode_wisuda, skor_value
)
SELECT
    question_code,
    question_group,
    answer_type,
    prodi_id,
    kd_fak,
    strata,
    periode_wisuda,
    skor_value,
    jumlah,
    total_responden,
    ROUND(jumlah * 100.0 / total_responden, 1)          AS pct,

    -- Label human-readable per skala
    CASE answer_type
        WHEN 'likert4_agree' THEN
            CASE skor_value
                WHEN 1 THEN 'Tidak Setuju'
                WHEN 2 THEN 'Cenderung Tidak Setuju'
                WHEN 3 THEN 'Cenderung Setuju'
                WHEN 4 THEN 'Setuju'
            END
        WHEN 'likert4_freq' THEN
            CASE skor_value
                WHEN 1 THEN 'Tidak pernah'
                WHEN 2 THEN 'Jarang / kecil'
                WHEN 3 THEN 'Sering / cukup'
                WHEN 4 THEN 'Selalu / besar'
            END
        WHEN 'likert5_expect' THEN
            CASE skor_value
                WHEN 1 THEN 'Tidak sesuai harapan'
                WHEN 2 THEN 'Ada yang memenuhi'
                WHEN 3 THEN 'Sebagian besar memenuhi'
                WHEN 4 THEN 'Memenuhi harapan'
                WHEN 5 THEN 'Melampaui harapan'
            END
        WHEN 'likert5_dev' THEN
            CASE skor_value
                WHEN 1 THEN 'Tidak berkembang'
                WHEN 2 THEN 'Sedikit berkembang'
                WHEN 3 THEN 'Cukup berkembang'
                WHEN 4 THEN 'Berkembang substansial'
                WHEN 5 THEN 'Berkembang sangat tinggi'
            END
    END                                                 AS skor_label,

    -- Flag skor "positif" sesuai threshold per skala
    CASE answer_type
        WHEN 'likert4_agree'  THEN (skor_value >= 3)
        WHEN 'likert4_freq'   THEN (skor_value >= 2)   -- "pernah mengalami"
        WHEN 'likert5_expect' THEN (skor_value >= 3)
        WHEN 'likert5_dev'    THEN (skor_value >= 3)
        ELSE FALSE
    END                                                 AS is_positif

FROM counted
WITH NO DATA;

CREATE UNIQUE INDEX idx_mv_dist_pk
    ON public.mv_dashboard_distribution
    (question_code, prodi_id, strata, periode_wisuda, skor_value);
CREATE INDEX idx_mv_dist_group
    ON public.mv_dashboard_distribution (question_group, kd_fak, periode_wisuda);


-- ============================================================
-- 4. mv_dashboard_trend
-- ============================================================
-- Time-series per (kd_fak, strata, periode_wisuda).
-- Grain di fakultas bukan prodi — supaya ada cukup sampel per
-- titik waktu untuk membuat trend yang meaningful.
-- ============================================================

CREATE MATERIALIZED VIEW public.mv_dashboard_trend AS
SELECT
    r.kd_fak,
    r.strata,
    r.periode_wisuda,
    COUNT(r.responden_id)                               AS jumlah_responden,

    -- Kepuasan (average — untuk trend line)
    ROUND(AVG(a.skor_avg), 2)                           AS avg_skor_fasilitas_itb,
    ROUND(AVG(b.skor_avg), 2)                           AS avg_skor_prodi,
    ROUND(AVG(c.skor_avg_kemampuan), 2)                 AS avg_skor_kemampuan,
    ROUND(AVG(c.skor_avg_karakter), 2)                  AS avg_skor_karakter,

    -- Kepuasan (persentase — untuk area chart)
    ROUND(
        COUNT(*) FILTER (WHERE a.skor_avg >= 3) * 100.0
        / NULLIF(COUNT(*) FILTER (WHERE a.skor_avg IS NOT NULL), 0)
    , 1)                                                AS pct_puas_fasilitas,
    ROUND(
        COUNT(*) FILTER (WHERE b.skor_avg >= 3) * 100.0
        / NULLIF(COUNT(*) FILTER (WHERE b.skor_avg IS NOT NULL), 0)
    , 1)                                                AS pct_puas_prodi,
    ROUND(
        COUNT(*) FILTER (WHERE b.pilih_prodi_yang_sama >= 3) * 100.0
        / NULLIF(COUNT(*) FILTER (WHERE b.pilih_prodi_yang_sama IS NOT NULL), 0)
    , 1)                                                AS pct_pilih_prodi_lagi,

    -- Masalah studi trend
    ROUND(
        COUNT(*) FILTER (WHERE d.masalah_psikologis >= 2) * 100.0
        / NULLIF(COUNT(*) FILTER (WHERE d.masalah_psikologis IS NOT NULL), 0)
    , 1)                                                AS pct_masalah_psikologis,
    ROUND(
        COUNT(*) FILTER (WHERE d.masalah_keuangan >= 2) * 100.0
        / NULLIF(COUNT(*) FILTER (WHERE d.masalah_keuangan IS NOT NULL), 0)
    , 1)                                                AS pct_masalah_keuangan,
    ROUND(
        COUNT(*) FILTER (WHERE d.masalah_akademis >= 2) * 100.0
        / NULLIF(COUNT(*) FILTER (WHERE d.masalah_akademis IS NOT NULL), 0)
    , 1)                                                AS pct_masalah_akademis,
    ROUND(
        COUNT(*) FILTER (WHERE d.masalah_kesehatan >= 2) * 100.0
        / NULLIF(COUNT(*) FILTER (WHERE d.masalah_kesehatan IS NOT NULL), 0)
    , 1)                                                AS pct_masalah_kesehatan,

    -- Rencana lanjut trend
    ROUND(
        COUNT(*) FILTER (WHERE rl.punya_rencana = 'Ya') * 100.0
        / NULLIF(COUNT(*) FILTER (WHERE rl.punya_rencana IS NOT NULL), 0)
    , 1)                                                AS pct_rencana_studi_lanjut

FROM public.wisudawan_responden r
LEFT JOIN public.wisudawan_skor_itb        a  ON a.responden_id = r.responden_id
LEFT JOIN public.wisudawan_skor_prodi      b  ON b.responden_id = r.responden_id
LEFT JOIN public.wisudawan_skor_softskill  c  ON c.responden_id = r.responden_id
LEFT JOIN public.wisudawan_masalah_studi   d  ON d.responden_id = r.responden_id
LEFT JOIN public.wisudawan_rencana_lanjut  rl ON rl.responden_id = r.responden_id
GROUP BY r.kd_fak, r.strata, r.periode_wisuda
WITH NO DATA;

CREATE UNIQUE INDEX idx_mv_trend_pk
    ON public.mv_dashboard_trend (kd_fak, strata, periode_wisuda);


-- ============================================================
-- 5. mv_dashboard_rekomendasi
-- ============================================================
-- Distribusi alasan rekomendasi prodi.
-- Satu baris per (rekomendasi_aspek, prodi_id, strata, periode_wisuda).
-- ============================================================

CREATE MATERIALIZED VIEW public.mv_dashboard_rekomendasi AS
WITH base AS (
    SELECT
        r.prodi_id,
        r.kd_fak,
        r.strata,
        r.periode_wisuda,
        COALESCE(b.rekomendasi_aspek::TEXT, 'Tidak mengisi') AS rekomendasi_aspek,
        COUNT(*)                                              AS jumlah,
        SUM(COUNT(*)) OVER (
            PARTITION BY r.prodi_id, r.strata, r.periode_wisuda
        )                                                     AS total_prodi
    FROM public.wisudawan_responden r
    LEFT JOIN public.wisudawan_skor_prodi b ON b.responden_id = r.responden_id
    GROUP BY r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda, b.rekomendasi_aspek
)
SELECT
    prodi_id,
    kd_fak,
    strata,
    periode_wisuda,
    rekomendasi_aspek,
    jumlah,
    total_prodi                                             AS total_responden,
    ROUND(jumlah * 100.0 / NULLIF(total_prodi, 0), 1)      AS pct,
    (rekomendasi_aspek != 'Tidak merekomendasikan'
     AND rekomendasi_aspek != 'Tidak mengisi')              AS is_rekomendasikan
FROM base
WITH NO DATA;

CREATE UNIQUE INDEX idx_mv_rek_pk
    ON public.mv_dashboard_rekomendasi
    (prodi_id, strata, periode_wisuda, rekomendasi_aspek);
CREATE INDEX idx_mv_rek_fak
    ON public.mv_dashboard_rekomendasi (kd_fak, periode_wisuda, rekomendasi_aspek);


-- ============================================================
-- 6. mv_dashboard_masalah_studi
-- ============================================================
-- Analisis mendalam masalah mahasiswa — semua metrik dalam
-- bentuk pct siap render ke: bar chart, heatmap, alert card.
-- ============================================================

CREATE MATERIALIZED VIEW public.mv_dashboard_masalah_studi AS
SELECT
    r.prodi_id,
    r.kd_fak,
    r.strata,
    r.periode_wisuda,
    COUNT(r.responden_id)                                   AS jumlah_responden,

    -- ── Prevalensi masalah (% yang pernah mengalami) ─────────────
    ROUND(COUNT(*) FILTER (WHERE d.masalah_akademis >= 2)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.masalah_akademis IS NOT NULL), 0), 1)
                                                            AS pct_pernah_masalah_akademis,
    ROUND(COUNT(*) FILTER (WHERE d.masalah_psikologis >= 2)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.masalah_psikologis IS NOT NULL), 0), 1)
                                                            AS pct_pernah_masalah_psikologis,
    ROUND(COUNT(*) FILTER (WHERE d.masalah_keuangan >= 2)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.masalah_keuangan IS NOT NULL), 0), 1)
                                                            AS pct_pernah_masalah_keuangan,
    ROUND(COUNT(*) FILTER (WHERE d.masalah_sosial_budaya >= 2)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.masalah_sosial_budaya IS NOT NULL), 0), 1)
                                                            AS pct_pernah_masalah_sosial,
    ROUND(COUNT(*) FILTER (WHERE d.masalah_kesehatan >= 2)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.masalah_kesehatan IS NOT NULL), 0), 1)
                                                            AS pct_pernah_masalah_kesehatan,

    -- ── Frekuensi masalah (% yang "sering" atau "selalu", score >= 3) ──
    ROUND(COUNT(*) FILTER (WHERE d.masalah_psikologis >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.masalah_psikologis IS NOT NULL), 0), 1)
                                                            AS pct_sering_masalah_psikologis,
    ROUND(COUNT(*) FILTER (WHERE d.masalah_keuangan >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.masalah_keuangan IS NOT NULL), 0), 1)
                                                            AS pct_sering_masalah_keuangan,
    ROUND(COUNT(*) FILTER (WHERE d.masalah_akademis >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.masalah_akademis IS NOT NULL), 0), 1)
                                                            AS pct_sering_masalah_akademis,

    -- ── Dampak signifikan terhadap akademik (score >= 3) ─────────
    -- Denominator: yang mengisi pertanyaan dampak (conditional)
    ROUND(COUNT(*) FILTER (WHERE d.dampak_psikologis >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.dampak_psikologis IS NOT NULL), 0), 1)
                                                            AS pct_dampak_signifikan_psikologis,
    ROUND(COUNT(*) FILTER (WHERE d.dampak_keuangan >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.dampak_keuangan IS NOT NULL), 0), 1)
                                                            AS pct_dampak_signifikan_keuangan,
    ROUND(COUNT(*) FILTER (WHERE d.dampak_sosial_budaya >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.dampak_sosial_budaya IS NOT NULL), 0), 1)
                                                            AS pct_dampak_signifikan_sosial,
    ROUND(COUNT(*) FILTER (WHERE d.dampak_kesehatan >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.dampak_kesehatan IS NOT NULL), 0), 1)
                                                            AS pct_dampak_signifikan_kesehatan,

    -- ── Jumlah absolut (untuk tabel detail) ──────────────────────
    COUNT(*) FILTER (WHERE d.masalah_psikologis >= 2)       AS n_masalah_psikologis,
    COUNT(*) FILTER (WHERE d.masalah_keuangan >= 2)         AS n_masalah_keuangan,
    COUNT(*) FILTER (WHERE d.masalah_akademis >= 2)         AS n_masalah_akademis,
    COUNT(*) FILTER (WHERE d.masalah_kesehatan >= 2)        AS n_masalah_kesehatan,
    COUNT(*) FILTER (WHERE d.masalah_sosial_budaya >= 2)    AS n_masalah_sosial,

    -- ── Kepuasan dukungan ITB (% yang puas, score >= 3) ──────────
    ROUND(COUNT(*) FILTER (WHERE d.dukungan_beasiswa >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.dukungan_beasiswa IS NOT NULL), 0), 1)
                                                            AS pct_puas_dukungan_beasiswa,
    ROUND(COUNT(*) FILTER (WHERE d.dukungan_konseling >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.dukungan_konseling IS NOT NULL), 0), 1)
                                                            AS pct_puas_dukungan_konseling,
    ROUND(COUNT(*) FILTER (WHERE d.dukungan_dosen_wali >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.dukungan_dosen_wali IS NOT NULL), 0), 1)
                                                            AS pct_puas_dukungan_dosen_wali,
    ROUND(COUNT(*) FILTER (WHERE d.dukungan_dosen_mk >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE d.dukungan_dosen_mk IS NOT NULL), 0), 1)
                                                            AS pct_puas_dukungan_dosen_mk,

    -- ── Average skor (untuk sorting/ranking) ─────────────────────
    ROUND(AVG(d.masalah_psikologis), 2)                     AS avg_skor_masalah_psikologis,
    ROUND(AVG(d.dukungan_konseling), 2)                     AS avg_skor_dukungan_konseling

FROM public.wisudawan_responden r
LEFT JOIN public.wisudawan_masalah_studi d ON d.responden_id = r.responden_id
GROUP BY r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda
WITH NO DATA;

CREATE UNIQUE INDEX idx_mv_masalah_pk
    ON public.mv_dashboard_masalah_studi (prodi_id, strata, periode_wisuda);
CREATE INDEX idx_mv_masalah_fak
    ON public.mv_dashboard_masalah_studi (kd_fak, periode_wisuda);


-- ============================================================
-- 7. mv_dashboard_softskill
-- ============================================================
-- Evaluasi outcome softskill per item — untuk radar chart
-- dan perbandingan antar prodi/fakultas.
-- ============================================================

CREATE MATERIALIZED VIEW public.mv_dashboard_softskill AS
SELECT
    r.prodi_id,
    r.kd_fak,
    r.strata,
    r.periode_wisuda,
    COUNT(r.responden_id)                                   AS jumlah_responden,

    -- ── Average skor per item (untuk radar chart) ────────────────
    ROUND(AVG(c.komunikasi_lisan), 2)                       AS avg_komunikasi_lisan,
    ROUND(AVG(c.komunikasi_tertulis), 2)                    AS avg_komunikasi_tertulis,
    ROUND(AVG(c.bahasa_asing), 2)                           AS avg_bahasa_asing,
    ROUND(AVG(c.problem_solving), 2)                        AS avg_problem_solving,
    ROUND(AVG(c.kritisi_pendapat_orang_lain), 2)                      AS avg_kritisi_pendapat_orang_lain,
    ROUND(AVG(c.kritisi_diri), 2)                            AS avg_kritisi_diri,
    ROUND(AVG(c.cara_berpendapat), 2)                       AS avg_cara_berpendapat,
    ROUND(AVG(c.kerja_tim), 2)                              AS avg_kerja_tim,
    ROUND(AVG(c.kerja_mandiri), 2)                          AS avg_kerja_mandiri,
    ROUND(AVG(c.kejujuran), 2)                              AS avg_kejujuran,
    ROUND(AVG(c.komitmen), 2)                               AS avg_komitmen,
    ROUND(AVG(c.jaga_emosi), 2)                                  AS avg_jaga_emosi,
    ROUND(AVG(c.kepedulian), 2)                             AS avg_kepedulian,
    ROUND(AVG(c.objektif), 2)                               AS avg_objektif,
    ROUND(AVG(c.pantang_menyerah), 2)                       AS avg_pantang_menyerah,
    ROUND(AVG(c.kepatuhan_aturan), 2)                       AS avg_kepatuhan_aturan,

    -- ── Persentase positif per item (score >= 3) ─────────────────
    ROUND(COUNT(*) FILTER (WHERE c.komunikasi_lisan >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE c.komunikasi_lisan IS NOT NULL), 0), 1)
                                                            AS pct_positif_komunikasi_lisan,
    ROUND(COUNT(*) FILTER (WHERE c.komunikasi_tertulis >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE c.komunikasi_tertulis IS NOT NULL), 0), 1)
                                                            AS pct_positif_komunikasi_tertulis,
    ROUND(COUNT(*) FILTER (WHERE c.bahasa_asing >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE c.bahasa_asing IS NOT NULL), 0), 1)
                                                            AS pct_positif_bahasa_asing,
    ROUND(COUNT(*) FILTER (WHERE c.problem_solving >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE c.problem_solving IS NOT NULL), 0), 1)
                                                            AS pct_positif_problem_solving,
    ROUND(COUNT(*) FILTER (WHERE c.kritisi_pendapat_orang_lain >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE c.kritisi_pendapat_orang_lain IS NOT NULL), 0), 1)
                                                            AS pct_positif_kritisi_pendapat_orang_lain,
    ROUND(COUNT(*) FILTER (WHERE c.kritisi_diri >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE c.kritisi_diri IS NOT NULL), 0), 1)
                                                            AS pct_positif_kritisi_diri,
    ROUND(COUNT(*) FILTER (WHERE c.cara_berpendapat >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE c.cara_berpendapat IS NOT NULL), 0), 1)
                                                            AS pct_positif_cara_berpendapat,
    ROUND(COUNT(*) FILTER (WHERE c.kerja_tim >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE c.kerja_tim IS NOT NULL), 0), 1)
                                                            AS pct_positif_kerja_tim,
    ROUND(COUNT(*) FILTER (WHERE c.kerja_mandiri >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE c.kerja_mandiri IS NOT NULL), 0), 1)
                                                            AS pct_positif_kerja_mandiri,
    ROUND(COUNT(*) FILTER (WHERE c.kejujuran >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE c.kejujuran IS NOT NULL), 0), 1)
                                                            AS pct_positif_kejujuran,
    ROUND(COUNT(*) FILTER (WHERE c.komitmen >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE c.komitmen IS NOT NULL), 0), 1)
                                                            AS pct_positif_komitmen,
    ROUND(COUNT(*) FILTER (WHERE c.pantang_menyerah >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE c.pantang_menyerah IS NOT NULL), 0), 1)
                                                            AS pct_positif_pantang_menyerah,

    -- ── Sub-score aggregate ───────────────────────────────────────
    ROUND(AVG(c.skor_avg_kemampuan), 2)                     AS avg_skor_kemampuan,
    ROUND(AVG(c.skor_avg_karakter), 2)                      AS avg_skor_karakter,
    ROUND(COUNT(*) FILTER (WHERE c.skor_avg_kemampuan >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE c.skor_avg_kemampuan IS NOT NULL), 0), 1)
                                                            AS pct_positif_kemampuan_overall,
    ROUND(COUNT(*) FILTER (WHERE c.skor_avg_karakter >= 3)
        * 100.0 / NULLIF(COUNT(*) FILTER (WHERE c.skor_avg_karakter IS NOT NULL), 0), 1)
                                                            AS pct_positif_karakter_overall

FROM public.wisudawan_responden r
LEFT JOIN public.wisudawan_skor_softskill c ON c.responden_id = r.responden_id
GROUP BY r.prodi_id, r.kd_fak, r.strata, r.periode_wisuda
WITH NO DATA;

CREATE UNIQUE INDEX idx_mv_softskill_pk
    ON public.mv_dashboard_softskill (prodi_id, strata, periode_wisuda);
CREATE INDEX idx_mv_softskill_fak
    ON public.mv_dashboard_softskill (kd_fak, periode_wisuda);