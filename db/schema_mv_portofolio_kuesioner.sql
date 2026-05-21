-- ================================================================
-- MATERIALIZED VIEWS : Data Portofolio & Kuesioner Akademik ITB
-- File   : mv_portofolio_kuesioner.sql
-- Urutan : Jalankan SETELAH schema_portofolio_kuesioner.sql
--          dan SETELAH seed data terisi
-- ================================================================
--
-- HIERARKI REFRESH (urutan wajib):
--   1. REFRESH MATERIALIZED VIEW CONCURRENTLY mv_kelas;
--   2. REFRESH MATERIALIZED VIEW CONCURRENTLY mv_statistik_prodi;
--   3. REFRESH MATERIALIZED VIEW CONCURRENTLY mv_statistik_dosen;
--
-- mv_statistik_prodi dan mv_statistik_dosen membaca dari mv_kelas,
-- bukan langsung dari tabel base. Refresh mv_kelas dulu sebelum keduanya.
--
-- PERBEDAAN UTAMA DARI SCHEMA LAMA:
--
--   [1] kelas.tahun (SMALLINT) + kelas.semester → computed tahun_ajaran VARCHAR
--       Semester 1 (Ganjil)  → 'tahun/tahun+1', e.g. 2024 → '2024/2025'
--       Semester 2 (Genap)   → 'tahun-1/tahun', e.g. 2025 → '2024/2025'
--       Semester 3 (Pendek)  → 'tahun/tahun+1' (ikuti ganjil)
--
--   [2] sks kini di mata_kuliah, bukan di kelas.
--
--   [3] Statistik kelas (kehadiran, IP) kini di statistik_kelas (shared PK),
--       bukan di kelas. Tidak ada nilai_portofolio atau is_synthetic di schema baru.
--
--   [4] Skor kuesioner terbagi dua tabel:
--       skor_kuesioner_kelas  → Q21,22,23,24,28,29,30,35,37 (level kelas)
--       skor_kuesioner_dosen  → Q25,26,27 (per dosen, berbeda antar dosen)
--       skor_agregat_kuesioner_dosen → dimensi key 1,2,3 per dosen
--       Di MV, skor Q25-27 dan dimensi pelaksanaan di-AVG antar dosen.
--
--   [5] Dimensi kuesioner aktual dari data SIX ITB:
--       Capaian      = avg(Q21, Q22, Q23)           → key 1
--       Pelaksanaan  = avg(Q24, Q25, Q26, Q27, Q28) → key 2 (Q25-27 per dosen)
--       Sarana       = avg(Q29, Q30)                → tidak ada key, hitung manual
--       Perilaku     = avg(Q35, Q37)                → key 3
--
--   [6] JOIN prodi dari kelas.prodi_id (bukan mk.prodi_id) agar MK lintas-prodi
--       (prefix WI) tetap tersedia di prodi penyelenggara.
--       Kelas MK WI tetap dapat kode/nama prodi dari kelas.prodi_id.
--
--   [7] mv_statistik_dosen menggunakan skor_agregat_kuesioner_dosen langsung
--       (bukan avg dari mv_kelas), sehingga skor per dosen lebih akurat.
-- ================================================================


-- ============================================================
-- MV 1: mv_kelas
-- 1 baris = 1 kelas. Semua dimensi ter-flatten.
-- Digunakan oleh view "Detail Kelas" dan sebagai base MV 2 & 3.
-- ============================================================

CREATE MATERIALIZED VIEW mv_kelas AS
WITH

-- ── CTE 1: Array dosen per kelas ─────────────────────────────────────────────
-- Pre-aggregate sebelum JOIN utama untuk menghindari row explosion.
dosen_per_kelas AS (
    SELECT
        pk.kelas_id,
        array_agg(d.dosen_id   ORDER BY d.dosen_id) AS semua_dosen_id,
        array_agg(d.nama_dosen ORDER BY d.dosen_id) AS semua_dosen_nama
    FROM pengajar_kelas pk
    JOIN dosen d ON d.dosen_id = pk.dosen_id
    GROUP BY pk.kelas_id
),

-- ── CTE 2: Distribusi nilai per kelas (pivot ABCDE + Pass/Fail) ───────────────
-- Data belum ada di CSV SIX ITB saat ini. Kolom akan bernilai 0 sampai data tersedia.
distribusi_pivot AS (
    SELECT
        kelas_id,
        COALESCE(MAX(jumlah)     FILTER (WHERE grade = 'A'),    0)    AS dist_jumlah_a,
        COALESCE(MAX(jumlah)     FILTER (WHERE grade = 'AB'),   0)    AS dist_jumlah_ab,
        COALESCE(MAX(jumlah)     FILTER (WHERE grade = 'B'),    0)    AS dist_jumlah_b,
        COALESCE(MAX(jumlah)     FILTER (WHERE grade = 'BC'),   0)    AS dist_jumlah_bc,
        COALESCE(MAX(jumlah)     FILTER (WHERE grade = 'C'),    0)    AS dist_jumlah_c,
        COALESCE(MAX(jumlah)     FILTER (WHERE grade = 'D'),    0)    AS dist_jumlah_d,
        COALESCE(MAX(jumlah)     FILTER (WHERE grade = 'E'),    0)    AS dist_jumlah_e,
        COALESCE(MAX(jumlah)     FILTER (WHERE grade = 'Pass'), 0)    AS dist_jumlah_pass,
        COALESCE(MAX(jumlah)     FILTER (WHERE grade = 'Fail'), 0)    AS dist_jumlah_fail,
        COALESCE(MAX(persentase) FILTER (WHERE grade = 'A'),    0)    AS dist_pct_a,
        COALESCE(MAX(persentase) FILTER (WHERE grade = 'AB'),   0)    AS dist_pct_ab,
        COALESCE(MAX(persentase) FILTER (WHERE grade = 'B'),    0)    AS dist_pct_b,
        COALESCE(MAX(persentase) FILTER (WHERE grade = 'BC'),   0)    AS dist_pct_bc,
        COALESCE(MAX(persentase) FILTER (WHERE grade = 'C'),    0)    AS dist_pct_c,
        COALESCE(MAX(persentase) FILTER (WHERE grade = 'D'),    0)    AS dist_pct_d,
        COALESCE(MAX(persentase) FILTER (WHERE grade = 'E'),    0)    AS dist_pct_e,
        COALESCE(MAX(persentase) FILTER (WHERE grade = 'Pass'), 0)    AS dist_pct_pass,
        COALESCE(MAX(persentase) FILTER (WHERE grade = 'Fail'), 0)    AS dist_pct_fail
    FROM distribusi_nilai
    GROUP BY kelas_id
),

-- ── CTE 3: Skor kuesioner level kelas (pivot per kd_pertanyaan) ───────────────
-- Berisi: Q21,Q22,Q23,Q24,Q28,Q29,Q30,Q35,Q37
-- Nilai identik untuk semua dosen dalam satu kelas (level kelas).
skor_kelas_pivot AS (
    SELECT
        skk.kelas_id,
        MAX(skk.rata_skor) FILTER (WHERE pq.kd_pertanyaan = 21) AS skor_q21,
        MAX(skk.rata_skor) FILTER (WHERE pq.kd_pertanyaan = 22) AS skor_q22,
        MAX(skk.rata_skor) FILTER (WHERE pq.kd_pertanyaan = 23) AS skor_q23,
        MAX(skk.rata_skor) FILTER (WHERE pq.kd_pertanyaan = 24) AS skor_q24,
        MAX(skk.rata_skor) FILTER (WHERE pq.kd_pertanyaan = 28) AS skor_q28,
        MAX(skk.rata_skor) FILTER (WHERE pq.kd_pertanyaan = 29) AS skor_q29,
        MAX(skk.rata_skor) FILTER (WHERE pq.kd_pertanyaan = 30) AS skor_q30,
        MAX(skk.rata_skor) FILTER (WHERE pq.kd_pertanyaan = 35) AS skor_q35,
        MAX(skk.rata_skor) FILTER (WHERE pq.kd_pertanyaan = 37) AS skor_q37
    FROM skor_kuesioner_kelas skk
    JOIN pertanyaan_kuesioner pq ON pq.pertanyaan_kuesioner_id = skk.pertanyaan_kuesioner_id
    GROUP BY skk.kelas_id
),

-- ── CTE 4: Skor Q25/Q26/Q27 dirata-rata antar dosen per kelas ────────────────
-- Q25,Q26,Q27 nilainya berbeda per dosen (TERVERIFIKASI). Di MV ini rata-rata
-- antar dosen mewakili skor kelas secara keseluruhan untuk ketiga pertanyaan itu.
skor_dosen_avg AS (
    SELECT
        skd.kelas_id,
        AVG(skd.rata_skor) FILTER (WHERE pq.kd_pertanyaan = 25) AS skor_q25_avg,
        AVG(skd.rata_skor) FILTER (WHERE pq.kd_pertanyaan = 26) AS skor_q26_avg,
        AVG(skd.rata_skor) FILTER (WHERE pq.kd_pertanyaan = 27) AS skor_q27_avg
    FROM skor_kuesioner_dosen skd
    JOIN pertanyaan_kuesioner pq ON pq.pertanyaan_kuesioner_id = skd.pertanyaan_kuesioner_id
    GROUP BY skd.kelas_id
),

-- ── CTE 5: Skor dimensi agregat dirata-rata antar dosen per kelas ─────────────
-- key 1 = avg(Q21,22,23) = capaian pembelajaran
-- key 2 = avg(Q24,25,26,27,28) = pelaksanaan perkuliahan  (termasuk Q25-27 per dosen)
-- key 3 = avg(Q35,37) = perilaku mahasiswa
-- Untuk kelas dengan >1 dosen, rata-rata antar dosen digunakan.
-- Sarana (Q29,Q30) tidak punya key di skor_agregat — dihitung dari skor_kelas_pivot.
skor_dimensi_avg AS (
    SELECT
        kelas_id,
        ROUND(AVG(rata_skor) FILTER (WHERE agregat_kuesioner_key = 1)::NUMERIC, 4)
            AS skor_avg_capaian,
        ROUND(AVG(rata_skor) FILTER (WHERE agregat_kuesioner_key = 2)::NUMERIC, 4)
            AS skor_avg_pelaksanaan,
        ROUND(AVG(rata_skor) FILTER (WHERE agregat_kuesioner_key = 3)::NUMERIC, 4)
            AS skor_avg_perilaku
    FROM skor_agregat_kuesioner_dosen
    GROUP BY kelas_id
)

SELECT
    -- ── Identitas kelas ──────────────────────────────────────────────────────
    k.kelas_id,
    k.matkul_id,
    k.no_kelas,
    k.semester,
    k.tahun,
    -- tahun_ajaran dikomputasi dari tahun + semester.
    -- Ganjil (1): 2024 → '2024/2025'. Genap (2): 2025 → '2024/2025'. Pendek (3): ikut ganjil.
    CASE k.semester
        WHEN 2 THEN (k.tahun - 1)::TEXT || '/' || k.tahun::TEXT
        ELSE          k.tahun::TEXT       || '/' || (k.tahun + 1)::TEXT
    END                                              AS tahun_ajaran,
    k.prodi_id,
    k.no_ps,

    -- ── Mata kuliah ───────────────────────────────────────────────────────────
    mk.kode_mk,
    mk.nama_mk,
    mk.sks,
    -- sks dari mata_kuliah (bukan kelas). Sesuai struktur CSV dan schema baru.
    mk.tahun_kurikulum,
    mk.jenis_nilai,

    -- ── Prodi & Fakultas ──────────────────────────────────────────────────────
    -- JOIN dari k.prodi_id (bukan mk.prodi_id) agar kelas MK lintas-prodi (WI)
    -- tetap mendapat data prodi penyelenggara. mk.prodi_id untuk MK WI = NULL.
    ps.kode_prodi,
    ps.singkatan_prodi,
    ps.nama_prodi,
    ps.jenjang,
    f.fakultas_id,
    f.kode_fakultas,
    f.nama_fakultas,

    -- ── Dosen ─────────────────────────────────────────────────────────────────
    COALESCE(dpk.semua_dosen_id,   '{}'::UUID[]) AS semua_dosen_id,
    COALESCE(dpk.semua_dosen_nama, '{}'::TEXT[]) AS semua_dosen_nama,

    -- ── Statistik kelas ───────────────────────────────────────────────────────
    -- Dari tabel statistik_kelas (shared PK 1:1 dengan kelas).
    -- NULLABLE: data mungkin belum tersedia saat kelas pertama kali di-insert.
    sk.pct_kehadiran_mahasiswa,
    sk.pct_kehadiran_dosen,
    sk.ip_mhs,
    -- ip_mhs = rata-rata IP mahasiswa (0.00-4.00). Setara rata_rata_nilai di schema lama.
    sk.jumlah_mahasiswa,
    sk.skor_dna,
    sk.ts_dna,
    sk.ip_mhs_dna,

    -- ── Distribusi nilai (pivot) ───────────────────────────────────────────────
    -- Semua 0 jika distribusi_nilai belum ada untuk kelas ini.
    COALESCE(dp.dist_jumlah_a,    0) AS dist_jumlah_a,
    COALESCE(dp.dist_jumlah_ab,   0) AS dist_jumlah_ab,
    COALESCE(dp.dist_jumlah_b,    0) AS dist_jumlah_b,
    COALESCE(dp.dist_jumlah_bc,   0) AS dist_jumlah_bc,
    COALESCE(dp.dist_jumlah_c,    0) AS dist_jumlah_c,
    COALESCE(dp.dist_jumlah_d,    0) AS dist_jumlah_d,
    COALESCE(dp.dist_jumlah_e,    0) AS dist_jumlah_e,
    COALESCE(dp.dist_jumlah_pass, 0) AS dist_jumlah_pass,
    COALESCE(dp.dist_jumlah_fail, 0) AS dist_jumlah_fail,
    COALESCE(dp.dist_pct_a,    0)    AS dist_pct_a,
    COALESCE(dp.dist_pct_ab,   0)    AS dist_pct_ab,
    COALESCE(dp.dist_pct_b,    0)    AS dist_pct_b,
    COALESCE(dp.dist_pct_bc,   0)    AS dist_pct_bc,
    COALESCE(dp.dist_pct_c,    0)    AS dist_pct_c,
    COALESCE(dp.dist_pct_d,    0)    AS dist_pct_d,
    COALESCE(dp.dist_pct_e,    0)    AS dist_pct_e,
    COALESCE(dp.dist_pct_pass, 0)    AS dist_pct_pass,
    COALESCE(dp.dist_pct_fail, 0)    AS dist_pct_fail,
    -- Persentase lulus: >=C untuk ABCDE, Pass untuk PassFail.
    -- NULL jika jenis_nilai belum diisi di mata_kuliah.
    CASE mk.jenis_nilai
        WHEN 'ABCDE' THEN
            COALESCE(dp.dist_pct_a,  0) + COALESCE(dp.dist_pct_ab, 0) +
            COALESCE(dp.dist_pct_b,  0) + COALESCE(dp.dist_pct_bc, 0) +
            COALESCE(dp.dist_pct_c,  0)
        WHEN 'PassFail' THEN
            COALESCE(dp.dist_pct_pass, 0)
        ELSE NULL
    END                                          AS dist_pct_lulus,

    -- ── Skor kuesioner individual (level kelas) ───────────────────────────────
    -- Sumber: skor_kuesioner_kelas. Nilai sudah merupakan rata-rata mahasiswa.
    -- NULL jika kelas belum punya data kuesioner.
    skp.skor_q21,   -- capaian: beban tugas sesuai
    skp.skor_q22,   -- capaian: kejelasan tujuan pembelajaran
    skp.skor_q23,   -- capaian: pencapaian tujuan pembelajaran
    skp.skor_q24,   -- pelaksanaan: kejelasan materi
    skp.skor_q28,   -- pelaksanaan: ketepatan waktu dosen
    skp.skor_q29,   -- sarana: kualitas ruang kelas
    skp.skor_q30,   -- sarana: ketersediaan media pembelajaran
    skp.skor_q35,   -- perilaku: kehadiran mahasiswa
    skp.skor_q37,   -- perilaku: partisipasi mahasiswa

    -- ── Skor Q25/Q26/Q27 (rata-rata antar dosen, untuk kelas) ─────────────────
    -- Nilai aslinya berbeda per dosen; nilai di sini adalah avg lintas dosen.
    -- NULL jika data Q25-27 belum ada.
    ROUND(sda.skor_q25_avg::NUMERIC, 4) AS skor_q25_avg,  -- pelaksanaan: penguasaan materi dosen
    ROUND(sda.skor_q26_avg::NUMERIC, 4) AS skor_q26_avg,  -- pelaksanaan: interaksi dosen-mahasiswa
    ROUND(sda.skor_q27_avg::NUMERIC, 4) AS skor_q27_avg,  -- pelaksanaan: kejujuran/objektivitas dosen

    -- ── Skor rata-rata per dimensi ────────────────────────────────────────────
    -- Capaian pembelajaran = avg(Q21, Q22, Q23)
    -- Sumber: skor_kelas_pivot (level kelas). NULL jika kuesioner belum ada.
    ROUND(
        (COALESCE(skp.skor_q21, 0) + COALESCE(skp.skor_q22, 0) + COALESCE(skp.skor_q23, 0))
        / NULLIF(
            (CASE WHEN skp.skor_q21 IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN skp.skor_q22 IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN skp.skor_q23 IS NOT NULL THEN 1 ELSE 0 END), 0
          )::NUMERIC, 2
    )                                                        AS skor_avg_capaian,

    -- Pelaksanaan perkuliahan = avg(Q24, Q25, Q26, Q27, Q28)
    -- Sumber: skor_dimensi_avg key 2 (sudah memperhitungkan Q25-27 per dosen).
    -- Lebih akurat daripada menghitung manual dari pivot + avg_dosen.
    ROUND(sda2.skor_avg_pelaksanaan::NUMERIC, 2)             AS skor_avg_pelaksanaan,

    -- Sarana prasarana = avg(Q29, Q30)
    -- Tidak ada agregat key di skor_agregat_kuesioner_dosen — hitung dari pivot.
    ROUND(
        (COALESCE(skp.skor_q29, 0) + COALESCE(skp.skor_q30, 0))
        / NULLIF(
            (CASE WHEN skp.skor_q29 IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN skp.skor_q30 IS NOT NULL THEN 1 ELSE 0 END), 0
          )::NUMERIC, 2
    )                                                        AS skor_avg_sarana,

    -- Perilaku mahasiswa = avg(Q35, Q37)
    -- Sumber: skor_dimensi_avg key 3.
    ROUND(sda2.skor_avg_perilaku::NUMERIC, 2)                AS skor_avg_perilaku,

    -- Overall = avg(capaian, pelaksanaan, sarana, perilaku)
    -- Dihitung dari 4 dimensi. NULL jika semua dimensi NULL.
    ROUND(
        (COALESCE(sda2.skor_avg_capaian, 0) + COALESCE(sda2.skor_avg_pelaksanaan, 0) +
         COALESCE(
             (COALESCE(skp.skor_q29, 0) + COALESCE(skp.skor_q30, 0))
             / NULLIF(
                 (CASE WHEN skp.skor_q29 IS NOT NULL THEN 1 ELSE 0 END +
                  CASE WHEN skp.skor_q30 IS NOT NULL THEN 1 ELSE 0 END), 0
               ), 0
         ) +
         COALESCE(sda2.skor_avg_perilaku, 0))
        / NULLIF(
            (CASE WHEN sda2.skor_avg_capaian    IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN sda2.skor_avg_pelaksanaan IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN skp.skor_q29              IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN sda2.skor_avg_perilaku    IS NOT NULL THEN 1 ELSE 0 END), 0
          )::NUMERIC, 2
    )                                                        AS skor_avg_overall

FROM kelas k
JOIN mata_kuliah    mk  ON mk.matkul_id  = k.matkul_id
JOIN program_studi  ps  ON ps.prodi_id   = k.prodi_id
-- Gunakan k.prodi_id (bukan mk.prodi_id) agar MK WI (lintas-prodi) tetap
-- dapat data prodi penyelenggara dari kelas.
JOIN fakultas       f   ON f.fakultas_id = ps.fakultas_id
LEFT JOIN statistik_kelas           sk   ON sk.kelas_id  = k.kelas_id
-- statistik_kelas: shared PK 1:1 dengan kelas. LEFT JOIN karena bisa belum ada.
LEFT JOIN dosen_per_kelas           dpk  ON dpk.kelas_id  = k.kelas_id
LEFT JOIN distribusi_pivot          dp   ON dp.kelas_id   = k.kelas_id
LEFT JOIN skor_kelas_pivot          skp  ON skp.kelas_id  = k.kelas_id
LEFT JOIN skor_dosen_avg            sda  ON sda.kelas_id  = k.kelas_id
LEFT JOIN skor_dimensi_avg          sda2 ON sda2.kelas_id = k.kelas_id;

-- Index wajib untuk REFRESH CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_kelas_pk         ON mv_kelas (kelas_id);
-- Index operasional
CREATE INDEX idx_mv_kelas_prodi_sem         ON mv_kelas (prodi_id, semester, tahun);
CREATE INDEX idx_mv_kelas_fak_sem           ON mv_kelas (fakultas_id, semester, tahun);
CREATE INDEX idx_mv_kelas_matkul_sem        ON mv_kelas (kode_mk, semester, tahun);
CREATE INDEX idx_mv_kelas_tahun_ajaran      ON mv_kelas (tahun_ajaran, prodi_id);
CREATE INDEX idx_mv_kelas_dosen_arr         ON mv_kelas USING GIN (semua_dosen_id);

COMMENT ON MATERIALIZED VIEW mv_kelas IS
'1 baris = 1 kelas portofolio, semua dimensi ter-flatten. '
'Base MV untuk mv_statistik_prodi dan mv_statistik_dosen. '
'Refresh dulu sebelum kedua MV lainnya. '
'Skor dimensi: capaian=avg(Q21-23), pelaksanaan=avg(Q24-28, termasuk avg dosen), '
'sarana=avg(Q29-30), perilaku=avg(Q35,37). '
'JOIN prodi dari kelas.prodi_id (bukan mk.prodi_id) agar MK WI tetap punya prodi.';

COMMENT ON COLUMN mv_kelas.tahun_ajaran IS
'Computed dari tahun + semester. Ganjil→tahun/tahun+1, Genap→tahun-1/tahun. '
'e.g. tahun=2024, semester=1 → ''2024/2025''; tahun=2025, semester=2 → ''2024/2025''.';

COMMENT ON COLUMN mv_kelas.sks IS
'SKS dari mata_kuliah (bukan kelas). Schema baru memindahkan sks ke mata_kuliah '
'sesuai struktur mata_kuliah.csv SIX ITB.';

COMMENT ON COLUMN mv_kelas.ip_mhs IS
'Rata-rata IP mahasiswa kelas (0.00–4.00). Setara rata_rata_nilai di schema lama. '
'Dari statistik_kelas.ip_mhs. NULLABLE: belum tentu tersedia.';

COMMENT ON COLUMN mv_kelas.semua_dosen_id IS
'Array UUID dosen pengampu. Filter: WHERE dosen_id_target = ANY(semua_dosen_id). '
'Untuk unnest: JOIN LATERAL unnest(semua_dosen_id) AS u(dosen_id) ON TRUE.';

COMMENT ON COLUMN mv_kelas.skor_q25_avg IS
'Rata-rata skor Q25 (penguasaan materi dosen) lintas dosen dalam kelas ini. '
'Q25 nilainya berbeda per dosen (TERVERIFIKASI). Nilai ini adalah estimasi level kelas.';

COMMENT ON COLUMN mv_kelas.skor_avg_pelaksanaan IS
'avg(Q24,Q25,Q26,Q27,Q28) → dari skor_agregat_kuesioner_dosen key 2, '
'dirata-rata lintas dosen. Lebih akurat karena sudah memperhitungkan Q25-27 per dosen.';

COMMENT ON COLUMN mv_kelas.dist_pct_lulus IS
'Persentase lulus: >=C untuk jenis_nilai=ABCDE, Pass untuk jenis_nilai=PassFail. '
'NULL jika jenis_nilai di mata_kuliah belum diisi (kolom NULLABLE).';


-- ============================================================
-- MV 2: mv_statistik_prodi
-- 1 baris = 1 prodi × 1 semester × 1 tahun.
-- Untuk View Prodi (overview) dan View Fakultas (perbandingan antar prodi).
-- ============================================================

CREATE MATERIALIZED VIEW mv_statistik_prodi AS
SELECT
    -- ── Identitas prodi & periode ─────────────────────────────────────────────
    mv.prodi_id,
    mv.kode_prodi,
    mv.singkatan_prodi,
    mv.nama_prodi,
    mv.jenjang,
    mv.fakultas_id,
    mv.kode_fakultas,
    mv.nama_fakultas,
    mv.semester,
    mv.tahun,
    mv.tahun_ajaran,

    -- ── Jumlah entitas ────────────────────────────────────────────────────────
    COUNT(DISTINCT mv.kelas_id)                                  AS jumlah_kelas,
    COUNT(DISTINCT mv.matkul_id)                                 AS jumlah_matkul_aktif,
    COUNT(DISTINCT u.dosen_id)                                   AS jumlah_dosen_aktif,
    -- jumlah_dosen_aktif: dihitung dari unnest semua_dosen_id agar tidak double-count
    -- dosen yang mengajar lebih dari 1 kelas.

    -- ── Statistik kehadiran & nilai ───────────────────────────────────────────
    ROUND(AVG(mv.pct_kehadiran_dosen)::NUMERIC,     2)           AS avg_pct_kehadiran_dosen,
    ROUND(AVG(mv.pct_kehadiran_mahasiswa)::NUMERIC, 2)           AS avg_pct_kehadiran_mahasiswa,
    ROUND(AVG(mv.ip_mhs)::NUMERIC,                  3)           AS avg_ip_mhs,
    -- avg_ip_mhs setara avg_nilai di MV lama. Nama berubah karena kolom
    -- di schema baru adalah ip_mhs (dari statistik_kelas), bukan rata_rata_nilai.

    -- ── Distribusi nilai agregat ───────────────────────────────────────────────
    SUM(mv.dist_jumlah_a)                                        AS total_mhs_a,
    SUM(mv.dist_jumlah_ab)                                       AS total_mhs_ab,
    SUM(mv.dist_jumlah_b)                                        AS total_mhs_b,
    SUM(mv.dist_jumlah_bc)                                       AS total_mhs_bc,
    SUM(mv.dist_jumlah_c)                                        AS total_mhs_c,
    SUM(mv.dist_jumlah_d)                                        AS total_mhs_d,
    SUM(mv.dist_jumlah_e)                                        AS total_mhs_e,
    SUM(mv.dist_jumlah_pass)                                     AS total_mhs_pass,
    SUM(mv.dist_jumlah_fail)                                     AS total_mhs_fail,
    ROUND(AVG(mv.dist_pct_lulus)::NUMERIC, 2)                    AS avg_pct_lulus,
    -- avg_pct_lulus: rata-rata persentase lulus per kelas di prodi ini.
    -- Hanya terisi jika jenis_nilai sudah diset di mata_kuliah.

    -- ── Skor kuesioner per dimensi ────────────────────────────────────────────
    ROUND(AVG(mv.skor_avg_capaian)::NUMERIC,     2)              AS avg_skor_capaian,
    ROUND(AVG(mv.skor_avg_pelaksanaan)::NUMERIC, 2)              AS avg_skor_pelaksanaan,
    ROUND(AVG(mv.skor_avg_sarana)::NUMERIC,      2)              AS avg_skor_sarana,
    ROUND(AVG(mv.skor_avg_perilaku)::NUMERIC,    2)              AS avg_skor_perilaku,
    ROUND(AVG(mv.skor_avg_overall)::NUMERIC,     2)              AS avg_skor_overall

FROM mv_kelas mv
LEFT JOIN LATERAL unnest(mv.semua_dosen_id) AS u(dosen_id) ON TRUE
GROUP BY
    mv.prodi_id, mv.kode_prodi, mv.singkatan_prodi, mv.nama_prodi, mv.jenjang,
    mv.fakultas_id, mv.kode_fakultas, mv.nama_fakultas,
    mv.semester, mv.tahun, mv.tahun_ajaran;

-- Index wajib untuk REFRESH CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_prodi_pk         ON mv_statistik_prodi (prodi_id, semester, tahun);
-- Index operasional
CREATE INDEX idx_mv_prodi_fak_sem           ON mv_statistik_prodi (fakultas_id, semester, tahun);
CREATE INDEX idx_mv_prodi_tahun_ajaran      ON mv_statistik_prodi (tahun_ajaran, prodi_id);

COMMENT ON MATERIALIZED VIEW mv_statistik_prodi IS
'Agregasi statistik per prodi per semester dan tahun. '
'Digunakan oleh View Prodi (overview) dan View Fakultas (perbandingan antar prodi). '
'REFRESH: wajib refresh mv_kelas terlebih dahulu. '
'avg_ip_mhs menggantikan avg_nilai di schema lama (kolom berganti nama dari statistik_kelas).';

COMMENT ON COLUMN mv_statistik_prodi.jumlah_dosen_aktif IS
'Jumlah dosen unik yang mengajar di prodi ini pada periode yang bersangkutan. '
'Dihitung via unnest(semua_dosen_id) untuk menghindari double-count '
'dosen yang mengajar lebih dari 1 kelas.';

COMMENT ON COLUMN mv_statistik_prodi.avg_ip_mhs IS
'Rata-rata IP mahasiswa lintas semua kelas di prodi ini. '
'NULL jika semua kelas belum punya data statistik_kelas.';

COMMENT ON COLUMN mv_statistik_prodi.avg_pct_lulus IS
'Rata-rata persentase lulus (>=C untuk ABCDE, Pass untuk PassFail) lintas kelas. '
'NULL jika distribusi_nilai atau jenis_nilai belum tersedia.';


-- ============================================================
-- MV 3: mv_statistik_dosen
-- 1 baris = 1 dosen × 1 semester × 1 tahun.
-- Untuk View Dosen (overview performa lintas kelas).
-- ============================================================
--
-- Catatan desain: MV ini menggunakan skor_agregat_kuesioner_dosen langsung
-- (bukan avg dari mv_kelas) sehingga skor per dosen lebih akurat — setiap
-- dosen punya skor dimensi individual dari nilai_dosen.csv yang sudah
-- memperhitungkan Q25,26,27 milik dosen tersebut saja.
-- ============================================================

CREATE MATERIALIZED VIEW mv_statistik_dosen AS
WITH
-- Pre-aggregate skor dimensi per dosen per semester dari tabel base
-- (lebih akurat daripada mengambil dari mv_kelas yang sudah di-AVG lintas dosen)
skor_per_dosen AS (
    SELECT
        sad.dosen_id,
        mk.semester,
        mk.tahun,
        CASE mk.semester
            WHEN 2 THEN (mk.tahun - 1)::TEXT || '/' || mk.tahun::TEXT
            ELSE         mk.tahun::TEXT        || '/' || (mk.tahun + 1)::TEXT
        END                                                        AS tahun_ajaran,
        ROUND(AVG(sad.rata_skor) FILTER (WHERE sad.agregat_kuesioner_key = 1)::NUMERIC, 4)
            AS avg_skor_capaian,
        ROUND(AVG(sad.rata_skor) FILTER (WHERE sad.agregat_kuesioner_key = 2)::NUMERIC, 4)
            AS avg_skor_pelaksanaan,
        ROUND(AVG(sad.rata_skor) FILTER (WHERE sad.agregat_kuesioner_key = 3)::NUMERIC, 4)
            AS avg_skor_perilaku,
        -- Sarana (Q29,Q30) tidak ada di skor_agregat_kuesioner_dosen.
        -- Diambil dari mv_kelas via join berikutnya.
        COUNT(DISTINCT sad.kelas_id)                               AS jumlah_kelas_dengan_skor
    FROM skor_agregat_kuesioner_dosen sad
    JOIN kelas mk ON mk.kelas_id = sad.kelas_id
    GROUP BY sad.dosen_id, mk.semester, mk.tahun
)

SELECT
    -- ── Identitas dosen & periode ─────────────────────────────────────────────
    u.dosen_id                                          AS dosen_id,
    d.nama_dosen,
    d.kk_id,
    kk.nama_kk,
    kk.fakultas_id                                      AS fakultas_id_kk,
    -- fakultas_id_kk: fakultas KK dosen (bisa berbeda dari prodi kelas yang diajar)

    mv.semester,
    mv.tahun,
    mv.tahun_ajaran,

    -- ── Jumlah entitas yang diajar ────────────────────────────────────────────
    COUNT(DISTINCT mv.kelas_id)                         AS jumlah_kelas,
    COUNT(DISTINCT mv.matkul_id)                        AS jumlah_matkul,
    SUM(mv.sks)                                         AS total_sks_diajar,
    -- total_sks_diajar: total SKS semua kelas yang diajar dosen ini pada periode ini.
    -- sks dari mv_kelas (yang mengambil dari mata_kuliah, bukan kelas).

    -- ── Statistik rata-rata kelas yang diajar ─────────────────────────────────
    ROUND(AVG(mv.pct_kehadiran_dosen)::NUMERIC,     2)  AS avg_pct_kehadiran_dosen,
    ROUND(AVG(mv.pct_kehadiran_mahasiswa)::NUMERIC, 2)  AS avg_pct_kehadiran_mahasiswa,
    ROUND(AVG(mv.ip_mhs)::NUMERIC,                  3)  AS avg_ip_mhs,

    -- ── Skor kuesioner per dimensi (dari skor_agregat_kuesioner_dosen, akurat) ─
    -- Dari CTE skor_per_dosen — skor individual dosen, bukan avg lintas dosen.
    spd.avg_skor_capaian,
    spd.avg_skor_pelaksanaan,
    -- Sarana: avg dari kelas-kelas yang diajar dosen ini (dari mv_kelas)
    ROUND(AVG(mv.skor_avg_sarana)::NUMERIC,         2)  AS avg_skor_sarana,
    spd.avg_skor_perilaku,
    -- Overall: avg dari 4 dimensi (capaian, pelaksanaan, sarana, perilaku)
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
    )                                                    AS avg_skor_overall,

    -- ── Nilai akhir rata-rata (dari nilai_dosen) ───────────────────────────────
    ROUND(AVG(nd.nilai_akhir)::NUMERIC, 4)               AS avg_nilai_akhir,
    -- avg_nilai_akhir: rata-rata nilai_akhir komposit dosen ini lintas kelas.
    -- PRIVAT di base table; di MV ini hanya admin/kaprodi yang query via aplikasi.

    -- ── Referensi ke kelas yang diajar ────────────────────────────────────────
    array_agg(DISTINCT mv.kelas_id ORDER BY mv.kelas_id) AS kelas_ids,
    array_agg(DISTINCT mv.kode_mk  ORDER BY mv.kode_mk)  AS kode_mk_list,
    array_agg(DISTINCT mv.prodi_id ORDER BY mv.prodi_id) AS prodi_ids_diajar
    -- prodi_ids_diajar: dosen bisa mengajar di >1 prodi (MK WI / cross-prodi)

FROM mv_kelas mv
JOIN LATERAL unnest(mv.semua_dosen_id) AS u(dosen_id) ON TRUE
JOIN dosen               d   ON d.dosen_id  = u.dosen_id
JOIN kelompok_keahlian   kk  ON kk.kk_id   = d.kk_id
LEFT JOIN skor_per_dosen spd ON spd.dosen_id = u.dosen_id
                             AND spd.semester = mv.semester
                             AND spd.tahun    = mv.tahun
LEFT JOIN nilai_dosen    nd  ON nd.kelas_id = mv.kelas_id
                             AND nd.dosen_id = u.dosen_id
GROUP BY
    u.dosen_id, d.nama_dosen, d.kk_id, kk.nama_kk, kk.fakultas_id,
    mv.semester, mv.tahun, mv.tahun_ajaran,
    spd.avg_skor_capaian, spd.avg_skor_pelaksanaan, spd.avg_skor_perilaku;

-- Index wajib untuk REFRESH CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_dosen_pk         ON mv_statistik_dosen (dosen_id, semester, tahun);
-- Index operasional
CREATE INDEX idx_mv_dosen_kk_sem            ON mv_statistik_dosen (kk_id, semester, tahun);
CREATE INDEX idx_mv_dosen_fak_sem           ON mv_statistik_dosen (fakultas_id_kk, semester, tahun);
CREATE INDEX idx_mv_dosen_tahun_ajaran      ON mv_statistik_dosen (tahun_ajaran, dosen_id);

COMMENT ON MATERIALIZED VIEW mv_statistik_dosen IS
'Agregasi performa dosen per semester dan tahun. '
'Digunakan oleh View Dosen (overview lintas kelas) dan View Prodi (tab profil dosen). '
'REFRESH: wajib refresh mv_kelas terlebih dahulu. '
'Skor dimensi capaian, pelaksanaan, perilaku diambil dari skor_agregat_kuesioner_dosen '
'langsung (bukan avg dari mv_kelas) sehingga lebih akurat per dosen individual.';

COMMENT ON COLUMN mv_statistik_dosen.avg_nilai_akhir IS
'Rata-rata nilai_akhir komposit dari nilai_dosen lintas kelas yang diajar dosen ini. '
'Nilai ini bersumber dari tabel PRIVAT (nilai_dosen). '
'Di MV ini tidak ada RLS — akses dikontrol di application layer. '
'Jangan expose langsung ke dosen yang bersangkutan via endpoint publik.';

COMMENT ON COLUMN mv_statistik_dosen.avg_skor_pelaksanaan IS
'avg(Q24,Q25,Q26,Q27,Q28) dari skor_agregat_kuesioner_dosen key 2. '
'Nilai ini adalah skor individual dosen, sudah memperhitungkan Q25,26,27 '
'yang nilainya spesifik untuk dosen ini. Lebih akurat dari avg lintas dosen.';

COMMENT ON COLUMN mv_statistik_dosen.prodi_ids_diajar IS
'Array prodi_id dari semua kelas yang diajar dosen ini pada periode yang bersangkutan. '
'Satu dosen bisa mengajar di beberapa prodi (MK WI atau cross-prodi).';

COMMENT ON COLUMN mv_statistik_dosen.total_sks_diajar IS
'Total SKS dari semua kelas yang diajar dosen ini. '
'Dihitung dari mk.sks (bukan kelas.sks) sesuai schema baru.';