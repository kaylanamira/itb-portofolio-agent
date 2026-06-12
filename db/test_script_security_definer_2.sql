-- ================================================================
-- TEST SECURITY LAYER — BAGIAN 2: EKSEKUSI TEST
--
-- WAJIB: isi nilai di bawah berdasarkan hasil test_security_01_discovery.sql
-- sebelum menjalankan file ini.
--
-- psql "postgresql://user:pass@host:port/dev_six" -f test_security_02_run.sql
--
-- Semua test dibungkus BEGIN...ROLLBACK -> tidak mengubah data apa pun,
-- aman dijalankan berkali-kali di environment dev/staging.
-- ================================================================

\pset format aligned
\pset border 2
\set ON_ERROR_STOP off

-- ── ISI NILAI BERIKUT (dari hasil discovery) ────────────────────
\set prodi_a_no       179
\set prodi_a_kdfak    'NONFS'
\set prodi_b_no       131
\set prodi_b_kdfak    'FTMD'
\set dosen_a          1
\set wisuda_prodi_no  135
\set wisuda_kdfak     'STEI'
\set komentar_prodi_no 102
\set komentar_kdfak    'FMIPA'
\set komentar_dosen    1
-- ─────────────────────────────────────────────────────────────


-- ================================================================
-- 0. BASELINE: jumlah baris mentah di analitik_mv (acuan ADMIN/DIREKTORAT)
-- ================================================================
\echo ''
\echo '================================================================'
\echo '0. BASELINE jumlah baris mentah (analitik_mv) — acuan ADMIN/DIREKTORAT'
\echo '================================================================'
SELECT
    (SELECT COUNT(*) FROM analitik_mv.mv_akademik_kelas)                  AS total_kelas,
    (SELECT COUNT(*) FROM analitik_mv.mv_akademik_komentar_mahasiswa)     AS total_komentar,
    (SELECT COUNT(*) FROM analitik_mv.mv_akademik_portofolio)             AS total_portofolio,
    (SELECT COUNT(*) FROM analitik_mv.mv_akademik_statistik_prodi)        AS total_stat_prodi,
    (SELECT COUNT(*) FROM analitik_mv.mv_akademik_statistik_dosen)        AS total_stat_dosen,
    (SELECT COUNT(*) FROM analitik_mv.mv_wisudawan_distribusi_jawaban)    AS total_wisuda_dist,
    (SELECT COUNT(*) FROM analitik_mv.mv_wisudawan_statistik_pertanyaan)  AS total_wisuda_stat,
    (SELECT COUNT(*) FROM analitik_mv.mv_wisudawan_jawaban_responden)     AS total_wisuda_jwb;


-- ================================================================
-- 1. TANPA SESSION VARIABLE — semua view security harus 0 baris
-- ================================================================
\echo ''
\echo '================================================================'
\echo '1. TANPA SESSION VARIABLE -> semua harus 0 (kecuali view publik A1-A5)'
\echo '================================================================'
BEGIN;
SELECT 'v_akademik_kelas'                  AS view_name, COUNT(*) AS rows, 0 AS expected FROM analitik.v_akademik_kelas
UNION ALL
SELECT 'v_akademik_komentar_mahasiswa',     COUNT(*), 0 FROM analitik.v_akademik_komentar_mahasiswa
UNION ALL
SELECT 'v_akademik_portofolio',            COUNT(*), 0 FROM analitik.v_akademik_portofolio
UNION ALL
SELECT 'v_akademik_statistik_prodi',       COUNT(*), 0 FROM analitik.v_akademik_statistik_prodi
UNION ALL
SELECT 'v_akademik_statistik_dosen',       COUNT(*), 0 FROM analitik.v_akademik_statistik_dosen
UNION ALL
SELECT 'v_wisudawan_distribusi_jawaban',   COUNT(*), 0 FROM analitik.v_wisudawan_distribusi_jawaban
UNION ALL
SELECT 'v_wisudawan_statistik_pertanyaan', COUNT(*), 0 FROM analitik.v_wisudawan_statistik_pertanyaan
UNION ALL
SELECT 'v_wisudawan_jawaban_responden',    COUNT(*), 0 FROM analitik.v_wisudawan_jawaban_responden;
ROLLBACK;

\echo ''
\echo '-- View PUBLIK (A1-A5) -> harus tetap return data walau tanpa session var --'
BEGIN;
SELECT 'v_akademik_jenis_dan_sifat_matkul' AS view_name, COUNT(*) AS rows FROM analitik.v_akademik_jenis_dan_sifat_matkul
UNION ALL
SELECT 'v_info_umum_kelas_matkul',     COUNT(*) FROM analitik.v_info_umum_kelas_matkul
UNION ALL
SELECT 'v_info_umum_institusi',  COUNT(*) FROM analitik.v_info_umum_institusi
UNION ALL
SELECT 'v_info_umum_dosen',      COUNT(*) FROM analitik.v_info_umum_dosen
UNION ALL
SELECT 'v_info_umum_wisuda',     COUNT(*) FROM analitik.v_info_umum_wisuda;
ROLLBACK;


-- ================================================================
-- 2. ROLE TIDAK DIKENAL (typo) — harus 0 baris (ELSE false)
-- ================================================================
\echo ''
\echo '================================================================'
\echo '2. ROLE TIDAK DIKENAL -> harus 0 baris'
\echo '================================================================'
BEGIN;
SELECT set_config('app.current_role', 'SUPERADMIN_TYPO', true);
SELECT set_config('app.current_no_prodi', :'prodi_a_no', true);
SELECT set_config('app.current_kd_fak', :'prodi_a_kdfak', true);
SELECT set_config('app.current_dosen_id', :'dosen_a', true);

SELECT 'v_akademik_kelas' AS view_name, COUNT(*) AS rows, 0 AS expected FROM analitik.v_akademik_kelas;
ROLLBACK;


-- ================================================================
-- 3. ADMIN & DIREKTORAT — harus lihat SEMUA baris (= baseline bagian 0)
-- ================================================================
\echo ''
\echo '================================================================'
\echo '3. ADMIN -> harus sama dengan baseline (semua baris, semua prodi)'
\echo '================================================================'
BEGIN;
SELECT set_config('app.current_role', 'ADMIN', true);
SELECT set_config('app.current_no_prodi', '', true);
SELECT set_config('app.current_kd_fak', '', true);
SELECT set_config('app.current_dosen_id', '', true);

SELECT 'v_akademik_kelas' AS view_name, COUNT(*) AS rows FROM analitik.v_akademik_kelas
UNION ALL
SELECT 'v_akademik_komentar_mahasiswa', COUNT(*) FROM analitik.v_akademik_komentar_mahasiswa
UNION ALL
SELECT 'v_akademik_portofolio', COUNT(*) FROM analitik.v_akademik_portofolio
UNION ALL
SELECT 'v_akademik_statistik_prodi', COUNT(*) FROM analitik.v_akademik_statistik_prodi
UNION ALL
SELECT 'v_akademik_statistik_dosen', COUNT(*) FROM analitik.v_akademik_statistik_dosen
UNION ALL
SELECT 'v_wisudawan_distribusi_jawaban', COUNT(*) FROM analitik.v_wisudawan_distribusi_jawaban
UNION ALL
SELECT 'v_wisudawan_statistik_pertanyaan', COUNT(*) FROM analitik.v_wisudawan_statistik_pertanyaan
UNION ALL
SELECT 'v_wisudawan_jawaban_responden', COUNT(*) FROM analitik.v_wisudawan_jawaban_responden;
ROLLBACK;

\echo ''
\echo '-- DIREKTORAT (harus identik dengan ADMIN di atas) --'
BEGIN;
SELECT set_config('app.current_role', 'DIREKTORAT', true);
SELECT set_config('app.current_no_prodi', '', true);
SELECT set_config('app.current_kd_fak', '', true);
SELECT set_config('app.current_dosen_id', '', true);

SELECT COUNT(*) AS v_akademik_kelas FROM analitik.v_akademik_kelas;
ROLLBACK;


-- ================================================================
-- 4. DEKAN / JAJARAN_DEKANAT — filter kode_fakultas = prodi_a_kdfak
-- ================================================================
\echo ''
\echo '================================================================'
\echo '4. DEKAN -> hanya kode_fakultas = :prodi_a_kdfak, leaked_rows harus 0'
\echo '================================================================'
BEGIN;
SELECT set_config('app.current_role', 'DEKAN', true);
SELECT set_config('app.current_kd_fak', :'prodi_a_kdfak', true);
SELECT set_config('app.current_no_prodi', '', true);
SELECT set_config('app.current_dosen_id', '', true);

SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE kode_fakultas = :'prodi_a_kdfak') AS own_rows,
    COUNT(*) FILTER (WHERE kode_fakultas <> :'prodi_a_kdfak') AS leaked_rows
FROM analitik.v_akademik_kelas;

SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE kode_fakultas = :'prodi_a_kdfak') AS own_rows,
    COUNT(*) FILTER (WHERE kode_fakultas <> :'prodi_a_kdfak') AS leaked_rows
FROM analitik.v_akademik_statistik_prodi;
ROLLBACK;

\echo ''
\echo '-- JAJARAN_DEKANAT (perilaku harus sama dengan DEKAN) --'
BEGIN;
SELECT set_config('app.current_role', 'JAJARAN_DEKANAT', true);
SELECT set_config('app.current_kd_fak', :'prodi_a_kdfak', true);
SELECT set_config('app.current_no_prodi', '', true);
SELECT set_config('app.current_dosen_id', '', true);

SELECT
    COUNT(*) FILTER (WHERE kode_fakultas <> :'prodi_a_kdfak') AS leaked_rows
FROM analitik.v_akademik_kelas;
ROLLBACK;


-- ================================================================
-- 5. KAPRODI / JAJARAN_PRODI — filter no_prodi = prodi_a_no
-- ================================================================
\echo ''
\echo '================================================================'
\echo '5. KAPRODI -> hanya no_prodi = :prodi_a_no, leaked_rows harus 0'
\echo '================================================================'
BEGIN;
SELECT set_config('app.current_role', 'KAPRODI', true);
SELECT set_config('app.current_no_prodi', :'prodi_a_no', true);
SELECT set_config('app.current_kd_fak', '', true);
SELECT set_config('app.current_dosen_id', '', true);

SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE no_prodi = :prodi_a_no) AS own_rows,
    COUNT(*) FILTER (WHERE no_prodi <> :prodi_a_no) AS leaked_rows
FROM analitik.v_akademik_kelas;

SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE no_prodi <> :prodi_a_no) AS leaked_rows
FROM analitik.v_akademik_portofolio;

SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE no_prodi <> :prodi_a_no) AS leaked_rows
FROM analitik.v_akademik_statistik_prodi;

-- v_akademik_statistik_dosen: filter berbasis no_prodi_diajar (array)
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE NOT (:prodi_a_no = ANY(no_prodi_diajar))) AS leaked_rows
FROM analitik.v_akademik_statistik_dosen;
ROLLBACK;

\echo ''
\echo '-- JAJARAN_PRODI (perilaku harus sama dengan KAPRODI) --'
BEGIN;
SELECT set_config('app.current_role', 'JAJARAN_PRODI', true);
SELECT set_config('app.current_no_prodi', :'prodi_a_no', true);
SELECT set_config('app.current_kd_fak', '', true);
SELECT set_config('app.current_dosen_id', '', true);

SELECT COUNT(*) FILTER (WHERE no_prodi <> :prodi_a_no) AS leaked_rows
FROM analitik.v_akademik_kelas;
ROLLBACK;


-- ================================================================
-- 6. DOSEN — row filter no_prodi + MASKING JSONB skor_dosen_q25/26/27
-- ================================================================
\echo ''
\echo '================================================================'
\echo '6a. DOSEN -> row filter no_prodi = :prodi_a_no'
\echo '================================================================'
BEGIN;
SELECT set_config('app.current_role', 'DOSEN', true);
SELECT set_config('app.current_no_prodi', :'prodi_a_no', true);
SELECT set_config('app.current_dosen_id', :'dosen_a', true);
SELECT set_config('app.current_kd_fak', '', true);

SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE no_prodi <> :prodi_a_no) AS leaked_rows
FROM analitik.v_akademik_kelas;
ROLLBACK;

\echo ''
\echo '================================================================'
\echo '6b. DOSEN -> MASKING skor_dosen_q25/26/27 (B1)'
\echo '    Untuk baris dosen_a sendiri: key harus HANYA :dosen_a (atau NULL)'
\echo '    is_masked_ok harus TRUE di semua baris'
\echo '================================================================'
BEGIN;
SELECT set_config('app.current_role', 'DOSEN', true);
SELECT set_config('app.current_no_prodi', :'prodi_a_no', true);
SELECT set_config('app.current_dosen_id', :'dosen_a', true);
SELECT set_config('app.current_kd_fak', '', true);

SELECT
    kelas_id,
    skor_dosen_q25,
    skor_dosen_q26,
    skor_dosen_q27,
    -- valid jika: NULL, ATAU hanya berisi key = dosen_a
    (skor_dosen_q25 IS NULL
        OR (jsonb_object_keys_array(skor_dosen_q25) = ARRAY[:'dosen_a']))
        AS is_masked_ok_q25
FROM analitik.v_akademik_kelas
WHERE no_prodi = :prodi_a_no
  AND (skor_dosen_q25 IS NOT NULL
       OR skor_dosen_q26 IS NOT NULL
       OR skor_dosen_q27 IS NOT NULL)
LIMIT 10;
ROLLBACK;

\echo ''
\echo '-- Catatan: jika error "function jsonb_object_keys_array does not exist",'
\echo '   ganti dengan versi di bawah ini (PostgreSQL standar):'
BEGIN;
SELECT set_config('app.current_role', 'DOSEN', true);
SELECT set_config('app.current_no_prodi', :'prodi_a_no', true);
SELECT set_config('app.current_dosen_id', :'dosen_a', true);
SELECT set_config('app.current_kd_fak', '', true);

SELECT
    kelas_id,
    skor_dosen_q25,
    (skor_dosen_q25 IS NULL
        OR (
            (SELECT COUNT(*) FROM jsonb_object_keys(skor_dosen_q25)) = 1
            AND skor_dosen_q25 ? :'dosen_a'
        )
    ) AS is_masked_ok_q25
FROM analitik.v_akademik_kelas
WHERE no_prodi = :prodi_a_no
  AND skor_dosen_q25 IS NOT NULL
LIMIT 10;
ROLLBACK;


-- ================================================================
-- 7. v_akademik_komentar_mahasiswa (B2) — DOSEN filter = ANY(semua_dosen_id)
-- ================================================================
\echo ''
\echo '================================================================'
\echo '7. v_akademik_komentar_mahasiswa — DOSEN filter semua_dosen_id'
\echo '   leaked_rows harus 0 (semua baris harus memuat :komentar_dosen)'
\echo '================================================================'
BEGIN;
SELECT set_config('app.current_role', 'DOSEN', true);
SELECT set_config('app.current_no_prodi', :'komentar_prodi_no', true);
SELECT set_config('app.current_dosen_id', :'komentar_dosen', true);
SELECT set_config('app.current_kd_fak', '', true);

SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE NOT (:komentar_dosen = ANY(semua_dosen_id))) AS leaked_rows
FROM analitik.v_akademik_komentar_mahasiswa;
ROLLBACK;

\echo ''
\echo '-- KAPRODI di prodi yang sama -> row filter no_prodi (boleh lebih banyak dari DOSEN di atas)'
BEGIN;
SELECT set_config('app.current_role', 'KAPRODI', true);
SELECT set_config('app.current_no_prodi', :'komentar_prodi_no', true);
SELECT set_config('app.current_dosen_id', '', true);
SELECT set_config('app.current_kd_fak', '', true);

SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE no_prodi <> :komentar_prodi_no) AS leaked_rows
FROM analitik.v_akademik_komentar_mahasiswa;
ROLLBACK;


-- ================================================================
-- 8. v_akademik_statistik_dosen (B5) — MASKING kolom dosen lain
-- ================================================================
\echo ''
\echo '================================================================'
\echo '8. v_akademik_statistik_dosen — DOSEN melihat dosen lain'
\echo '   Baris MILIK SENDIRI (dosen_id = :dosen_a): kolom sensitif harus TERISI'
\echo '   Baris DOSEN LAIN: avg_skor_overall, avg_pct_kehadiran_dosen, dst HARUS NULL'
\echo '   avg_pct_kehadiran_mahasiswa TIDAK di-mask (boleh terisi untuk semua)'
\echo '================================================================'
BEGIN;
SELECT set_config('app.current_role', 'DOSEN', true);
SELECT set_config('app.current_no_prodi', :'prodi_a_no', true);
SELECT set_config('app.current_dosen_id', :'dosen_a', true);
SELECT set_config('app.current_kd_fak', '', true);

\echo '-- Baris milik sendiri --'
SELECT
    dosen_id,
    avg_skor_overall,
    avg_pct_kehadiran_dosen,
    avg_pct_kehadiran_mahasiswa,
    avg_nilai_akhir
FROM analitik.v_akademik_statistik_dosen
WHERE dosen_id = :dosen_a
LIMIT 3;

\echo '-- Baris dosen lain (harus avg_skor_overall & avg_pct_kehadiran_dosen = NULL,'
\echo '   avg_pct_kehadiran_mahasiswa TETAP terisi) --'
SELECT
    dosen_id,
    avg_skor_overall,
    avg_pct_kehadiran_dosen,
    avg_pct_kehadiran_mahasiswa,
    avg_nilai_akhir
FROM analitik.v_akademik_statistik_dosen
WHERE dosen_id <> :dosen_a
LIMIT 5;

\echo '-- Ringkasan otomatis: harus 0 baris dosen lain yang punya avg_skor_overall terisi --'
SELECT COUNT(*) AS dosen_lain_dengan_skor_terisi_harus_0
FROM analitik.v_akademik_statistik_dosen
WHERE dosen_id <> :dosen_a
  AND avg_skor_overall IS NOT NULL;
ROLLBACK;


-- ================================================================
-- 9. WISUDAWAN VIEWS (B6, B7, B8) — pattern sama dengan akademik
-- ================================================================
\echo ''
\echo '================================================================'
\echo '9a. v_wisudawan_distribusi_jawaban — KAPRODI filter no_prodi'
\echo '================================================================'
BEGIN;
SELECT set_config('app.current_role', 'KAPRODI', true);
SELECT set_config('app.current_no_prodi', :'wisuda_prodi_no', true);
SELECT set_config('app.current_kd_fak', '', true);
SELECT set_config('app.current_dosen_id', '', true);

SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE no_prodi <> :wisuda_prodi_no) AS leaked_rows
FROM analitik.v_wisudawan_distribusi_jawaban;
ROLLBACK;

\echo ''
\echo '================================================================'
\echo '9b. v_wisudawan_statistik_pertanyaan — DEKAN filter kode_fakultas'
\echo '================================================================'
BEGIN;
SELECT set_config('app.current_role', 'DEKAN', true);
SELECT set_config('app.current_kd_fak', :'wisuda_kdfak', true);
SELECT set_config('app.current_no_prodi', '', true);
SELECT set_config('app.current_dosen_id', '', true);

SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE kode_fakultas <> :'wisuda_kdfak') AS leaked_rows
FROM analitik.v_wisudawan_statistik_pertanyaan;
ROLLBACK;

\echo ''
\echo '================================================================'
\echo '9c. v_wisudawan_jawaban_responden — DOSEN filter no_prodi'
\echo '================================================================'
BEGIN;
SELECT set_config('app.current_role', 'DOSEN', true);
SELECT set_config('app.current_no_prodi', :'wisuda_prodi_no', true);
SELECT set_config('app.current_kd_fak', '', true);
SELECT set_config('app.current_dosen_id', :'dosen_a', true);

SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE no_prodi <> :wisuda_prodi_no) AS leaked_rows
FROM analitik.v_wisudawan_jawaban_responden;
ROLLBACK;


-- ================================================================
-- 10. KONSISTENSI ANTAR-VIEW WISUDAWAN (cross-check is_seremoni_asumtif)
-- ================================================================
\echo ''
\echo '================================================================'
\echo '10. is_seremoni_asumtif konsisten -> harus semua TRUE (data dummy)'
\echo '================================================================'
BEGIN;
SELECT set_config('app.current_role', 'ADMIN', true);
SELECT set_config('app.current_no_prodi', '', true);
SELECT set_config('app.current_kd_fak', '', true);
SELECT set_config('app.current_dosen_id', '', true);

SELECT
    'v_wisudawan_distribusi_jawaban' AS view_name,
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE is_seremoni_asumtif IS TRUE)  AS asumtif_true,
    COUNT(*) FILTER (WHERE is_seremoni_asumtif IS FALSE) AS asumtif_false,
    COUNT(*) FILTER (WHERE is_seremoni_asumtif IS NULL)  AS asumtif_null
FROM analitik.v_wisudawan_distribusi_jawaban
UNION ALL
SELECT
    'v_wisudawan_jawaban_responden',
    COUNT(*),
    COUNT(*) FILTER (WHERE is_seremoni_asumtif IS TRUE),
    COUNT(*) FILTER (WHERE is_seremoni_asumtif IS FALSE),
    COUNT(*) FILTER (WHERE is_seremoni_asumtif IS NULL)
FROM analitik.v_wisudawan_jawaban_responden;
ROLLBACK;


\echo ''
\echo '================================================================'
\echo 'SELESAI. Periksa setiap "leaked_rows" / "*_harus_0" -> harus 0.'
\echo 'Periksa bagian 6b -> is_masked_ok_* harus TRUE di semua baris.'
\echo 'Periksa bagian 8  -> dosen_lain_dengan_skor_terisi_harus_0 = 0.'
\echo '================================================================'