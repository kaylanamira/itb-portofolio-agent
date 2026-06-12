-- ================================================================
-- TEST SECURITY LAYER — BAGIAN 1: DISCOVERY
-- Jalankan dulu untuk dapat nilai konkret (no_prodi, kode_fakultas,
-- dosen_id, dll.) yang akan dipakai di test_security_02_run.sql.
--
-- psql "postgresql://user:pass@host:port/dev_six" -f test_security_01_discovery.sql
-- ================================================================

\pset format aligned
\pset border 2

\echo ''
\echo '================================================================'
\echo '0. CEK OBJEK: functions & views di schema analitik'
\echo '================================================================'
\echo 'Harus ada 8 function fn_get_* dan 13 view (4 publik A1-A4 + 1 baru'
\echo 'v_info_umum_wisuda [A5] + 8 wrapper B1-B8).'
\echo 'Jika fn_get_akademik_komentar_mahasiswa TIDAK muncul -> function'
\echo 'ini gagal dibuat (bug app.dosen_id / p.semua_dosen_id) - perbaiki'
\echo 'dulu sebelum lanjut ke test B2.'
\echo ''

SELECT routine_name
FROM information_schema.routines
WHERE routine_schema = 'analitik' AND routine_type = 'FUNCTION'
ORDER BY routine_name;

SELECT table_name AS view_name
FROM information_schema.views
WHERE table_schema = 'analitik'
ORDER BY table_name;


\echo ''
\echo '================================================================'
\echo '1. PRODI DENGAN DATA TERBANYAK (untuk role KAPRODI/JAJARAN_PRODI/DOSEN)'
\echo '================================================================'
SELECT no_prodi, kode_prodi, kode_fakultas, COUNT(*) AS jumlah_kelas
FROM analitik_mv.mv_akademik_kelas
GROUP BY no_prodi, kode_prodi, kode_fakultas
ORDER BY jumlah_kelas DESC
LIMIT 3;


\echo ''
\echo '================================================================'
\echo '2. PRODI LAIN (FAKULTAS BERBEDA) — untuk leakage check'
\echo '   Pilih salah satu yang kode_fakultas-nya BEDA dari hasil #1'
\echo '================================================================'
SELECT no_prodi, kode_fakultas, COUNT(*) AS jumlah_kelas
FROM analitik_mv.mv_akademik_kelas
GROUP BY no_prodi, kode_fakultas
ORDER BY jumlah_kelas DESC
LIMIT 5;


\echo ''
\echo '================================================================'
\echo '3. DOSEN_ID CONTOH DI PRODI HASIL #1 + skor_dosen_Q25'
\echo '   Pakai no_prodi dari #1 (ganti 999 di bawah)'
\echo '================================================================'
-- Ganti :prodi_pilihan dengan no_prodi hasil langkah 1
SELECT
    k.kelas_id,
    u.dosen_id,
    k.skor_dosen_q25,
    (k.skor_dosen_q25 IS NOT NULL AND k.skor_dosen_q25 ? u.dosen_id::TEXT) AS punya_skor_q25
FROM analitik_mv.mv_akademik_kelas k
JOIN LATERAL unnest(k.semua_dosen_id) AS u(dosen_id) ON TRUE
WHERE k.no_prodi = 999  -- <<< GANTI dengan no_prodi dari hasil #1
ORDER BY punya_skor_q25 DESC
LIMIT 5;


\echo ''
\echo '================================================================'
\echo '4. DOSEN YANG MENGAJAR DI >1 PRODI (untuk test no_prodi_diajar di v_akademik_statistik_dosen)'
\echo '================================================================'
SELECT dosen_id, no_prodi, no_prodi_diajar, kode_fakultas_dosen
FROM analitik_mv.mv_akademik_statistik_dosen
WHERE array_length(no_prodi_diajar, 1) > 1
LIMIT 3;

\echo ''
\echo 'Kalau hasil di atas kosong, ambil contoh dosen biasa saja:'
SELECT dosen_id, no_prodi, no_prodi_diajar, kode_fakultas_dosen
FROM analitik_mv.mv_akademik_statistik_dosen
LIMIT 3;


\echo ''
\echo '================================================================'
\echo '5. PRODI/FAKULTAS DENGAN DATA WISUDAWAN'
\echo '   (grain berbeda dari akademik — perlu discovery terpisah)'
\echo '================================================================'
SELECT no_prodi, kode_fakultas, COUNT(*) AS jumlah_baris
FROM analitik_mv.mv_wisudawan_distribusi_jawaban
GROUP BY no_prodi, kode_fakultas
ORDER BY jumlah_baris DESC
LIMIT 3;


\echo ''
\echo '================================================================'
\echo '6. KOMENTAR MAHASISWA — prodi & dosen contoh (untuk B2)'
\echo '================================================================'
SELECT
    c.no_prodi,
    c.kode_fakultas,
    u.dosen_id,
    COUNT(*) AS jumlah_komentar
FROM analitik_mv.mv_akademik_komentar_mahasiswa c
JOIN LATERAL unnest(c.semua_dosen_id) AS u(dosen_id) ON TRUE
GROUP BY c.no_prodi, c.kode_fakultas, u.dosen_id
ORDER BY jumlah_komentar DESC
LIMIT 3;


\echo ''
\echo '================================================================'
\echo 'CATAT NILAI-NILAI BERIKUT UNTUK DIISI KE test_security_02_run.sql:'
\echo ''
\echo '  :prodi_a_no       <- no_prodi dari #1'
\echo '  :prodi_a_kdfak    <- kode_fakultas dari #1'
\echo '  :prodi_b_no       <- no_prodi dari #2 (fakultas berbeda dari #1)'
\echo '  :prodi_b_kdfak    <- kode_fakultas dari #2'
\echo '  :dosen_a          <- dosen_id dari #3 (idealnya punya_skor_q25=true)'
\echo '  :dosen_lain       <- dosen_id lain di prodi_a_no (untuk cek masking)'
\echo '  :dosen_multiprodi <- dosen_id dari #4'
\echo '  :wisuda_prodi_no  <- no_prodi dari #5'
\echo '  :wisuda_kdfak     <- kode_fakultas dari #5'
\echo '  :komentar_prodi_no  <- no_prodi dari #6'
\echo '  :komentar_kdfak     <- kode_fakultas dari #6'
\echo '  :komentar_dosen     <- dosen_id dari #6'
\echo '================================================================'