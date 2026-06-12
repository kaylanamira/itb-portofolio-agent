-- ================================================================
-- IMPLEMENTASI SECURITY LAYER
-- Schema: analitik (access layer) ← analitik_mv (raw data)
--
-- Session variables yang di-set backend sebelum setiap query (via scope.py get_rls_vars()):
--   app.role      → 'admin'|'direktorat'|'dekan'|'jajaran_dekanat'|'kaprodi'|'jajaran_prodi'|'dosen'
--   app.dosen_id  → integer (kosong string jika bukan dosen)
--   app.no_ps     → integer, no_ps prodi scope (kosong string jika tidak relevan)
--   app.kd_fak    → varchar, kd_fak scope (kosong string jika tidak relevan)
--   app.kk_id     → integer (tidak dipakai di fungsi ini)
--   app.user_id   → integer (tidak dipakai di fungsi ini)
--
-- Tidak ada tabel app_context — semua scope dari session variable
-- yang di-set backend dari session Redis (ScopeEntry.model_dump()).
-- ================================================================

CREATE SCHEMA IF NOT EXISTS analitik;

-- ================================================================
-- SNIPPET DECLARE + BEGIN yang sama di semua Security Definer Function
-- (disalin ke tiap function — tidak bisa di-share sebagai macro)
-- ================================================================
--
-- DECLARE
--     v_role     text;
--     v_dosen_id integer;
--     v_no_prodi integer;
--     v_kd_fak   character varying;
-- BEGIN
--     v_role     := NULLIF(current_setting('app.role',     true), '');
--     v_dosen_id := NULLIF(current_setting('app.dosen_id', true), '')::integer;
--     v_no_prodi := NULLIF(current_setting('app.no_ps', true), '')::integer;
--     v_kd_fak   := NULLIF(current_setting('app.kd_fak',   true), '');
--     IF v_role IS NULL THEN RETURN; END IF;
-- ================================================================


-- ================================================================
-- A. VIEW PUBLIK (tanpa Security Definer, semua role bisa akses)
-- ================================================================

-- ── A1. Jenis dan sifat mata kuliah ──────────────────────────────
CREATE VIEW analitik.v_akademik_jenis_dan_sifat_matkul AS
SELECT * FROM analitik_mv.mv_akademik_jenis_dan_sifat_matkul;

-- ── A2. Info umum mata kuliah (non-sensitif, dari mv_akademik_kelas) ─
CREATE VIEW analitik.v_info_umum_kelas_matkul AS
SELECT DISTINCT
    kelas_id,
    mata_kuliah_id,
    no_kelas,
    semester,
    tahun,
    tahun_ajaran,
    kode_matkul,
    nama_matkul_id,
    nama_matkul_en,
    sks,
    tahun_kurikulum,
    jenis_nilai,
    no_prodi,
    kode_prodi,
    nama_prodi_id,
    nama_prodi_en,
    jenjang,
    kode_fakultas,
    nama_fakultas_id,
    nama_fakultas_en,
    semua_dosen_id,
    semua_dosen_nama_gelar,
    kode_jenis_list,
    nama_jenis_list,
    nama_paket_list,
    kode_sifat_list,
    is_wajib_itb
FROM analitik_mv.mv_akademik_kelas;

-- ── A3. Info umum institusi (jumlah kelas/dosen/mhs — non-sensitif) ─
CREATE VIEW analitik.v_info_umum_institusi AS
SELECT
    no_prodi,
    kode_prodi,
    nama_prodi_id,
    nama_prodi_en,
    jenjang,
    kode_fakultas,
    nama_fakultas_id,
    nama_fakultas_en,
    semester,
    tahun,
    tahun_ajaran,
    jumlah_kelas,
    jumlah_matkul_aktif,
    jumlah_dosen_aktif,
    jumlah_mahasiswa_aktif
FROM analitik_mv.mv_akademik_statistik_prodi;

-- ── A4. Info umum dosen (jumlah mengajar — non-sensitif) ─────────
CREATE VIEW analitik.v_info_umum_dosen AS
SELECT
    dosen_id,
    nama_dosen_gelar,
    nip,
    kk_id,
    kode_fakultas_dosen,
    no_prodi,
    kode_prodi,
    semester,
    tahun,
    tahun_ajaran,
    jumlah_kelas,
    jumlah_matkul,
    total_sks_diajar,
    kode_matkul_list,
    no_prodi_diajar,
    kode_prodi_diajar
FROM analitik_mv.mv_akademik_statistik_dosen;

-- ── A5. Info umum wisuda (jumlah responden per prodi & periode) ──
CREATE VIEW analitik.v_info_umum_wisuda AS
SELECT
    no_prodi,
    kode_prodi,
    nama_prodi_id,
    nama_prodi_en,
    jenjang,
    kode_fakultas,
    nama_fakultas_id,
    nama_fakultas_en,
    periode_ijazah_id_final,
    tahun_ijazah,
    bulan_ijazah,
    periode_seremoni_id,
    tahun_seremoni,
    bulan_seremoni,
    nama_seremoni,
    is_seremoni_asumtif,
    COUNT(DISTINCT response_id) AS jumlah_responden
FROM analitik_mv.mv_wisudawan_jawaban_responden
GROUP BY
    no_prodi, kode_prodi, nama_prodi_id, nama_prodi_en,
    jenjang, kode_fakultas, nama_fakultas_id, nama_fakultas_en,
    periode_ijazah_id_final, tahun_ijazah, bulan_ijazah,
    periode_seremoni_id, tahun_seremoni, bulan_seremoni,
    nama_seremoni, is_seremoni_asumtif;


-- ================================================================
-- B. SECURITY DEFINER FUNCTIONS + VIEW WRAPPERS
-- ================================================================

-- ── B1. mv_akademik_kelas ─────────────────────────────────────────
-- DOSEN: row filter = no_prodi (setara KAPRODI)
-- DOSEN: skor_dosen_q25/26/27 di-mask → hanya entry miliknya
-- Semua role lain: semua kolom tampil penuh

CREATE OR REPLACE FUNCTION analitik.fn_get_akademik_kelas()
RETURNS TABLE (
    kelas_id                    integer,
    mata_kuliah_id              integer,
    no_kelas                    integer,
    semester                    smallint,
    tahun                       smallint,
    tahun_ajaran                text,
    kode_matkul                 character(6),
    nama_matkul_id              text,
    nama_matkul_en              text,
    sks                         integer,
    tahun_kurikulum             integer,
    jenis_nilai                 text,
    no_prodi                    integer,
    kode_prodi                  character(2),
    nama_prodi_id               text,
    nama_prodi_en               text,
    jenjang                     character(2),
    kode_fakultas               character varying,
    nama_fakultas_id            text,
    nama_fakultas_en            text,
    semua_dosen_id              integer[],
    semua_dosen_nama_gelar      character varying[],
    kode_jenis_list             character(1)[],
    nama_jenis_list             text[],
    nama_paket_list             text[],
    kode_sifat_list             character(1)[],
    is_wajib_itb                boolean,
    pct_kehadiran_mahasiswa     numeric,
    pct_kehadiran_dosen         numeric,
    avg_ip_akhir_mahasiswa      numeric,
    skor_dna                    numeric,
    ts_dna                      timestamp with time zone,
    ip_mhs_dna                  numeric,
    is_distribusi_nilai_sah     boolean,
    jumlah_mahasiswa            integer,
    dist_jumlah_a               bigint,
    dist_jumlah_ab              bigint,
    dist_jumlah_b               bigint,
    dist_jumlah_bc              bigint,
    dist_jumlah_c               bigint,
    dist_jumlah_d               bigint,
    dist_jumlah_e               bigint,
    dist_jumlah_pass            bigint,
    dist_jumlah_fail            bigint,
    dist_pct_a                  numeric,
    dist_pct_ab                 numeric,
    dist_pct_b                  numeric,
    dist_pct_bc                 numeric,
    dist_pct_c                  numeric,
    dist_pct_d                  numeric,
    dist_pct_e                  numeric,
    dist_pct_pass               numeric,
    dist_pct_fail               numeric,
    dist_pct_lulus_a_c          numeric,
    dist_pct_lulus_a_d          numeric,
    skor_q21                    numeric,
    skor_q22                    numeric,
    skor_q23                    numeric,
    skor_q24                    numeric,
    skor_q25                    numeric,
    skor_q26                    numeric,
    skor_q27                    numeric,
    skor_q28                    numeric,
    skor_q29                    numeric,
    skor_q30                    numeric,
    skor_q35                    numeric,
    skor_q37                    numeric,
    -- Kolom JSONB ini di-mask untuk DOSEN: hanya entry miliknya sendiri
    skor_dosen_q25         jsonb,
    skor_dosen_q26         jsonb,
    skor_dosen_q27         jsonb,
    avg_skor_capaian            numeric,
    avg_skor_pelaksanaan        numeric,
    avg_skor_sarana_prasarana   numeric,
    avg_skor_perilaku_mahasiswa numeric,
    avg_skor_overall            numeric
) AS $$
DECLARE
    v_role     text;
    v_dosen_id integer;
    v_no_prodi integer;
    v_kd_fak   character varying;
BEGIN
    v_role     := NULLIF(current_setting('app.role',     true), '');
    v_dosen_id := NULLIF(current_setting('app.dosen_id', true), '')::integer;
    v_no_prodi := NULLIF(current_setting('app.no_ps', true), '')::integer;
    v_kd_fak   := NULLIF(current_setting('app.kd_fak',   true), '');
    IF v_role IS NULL THEN RETURN; END IF;

    RETURN QUERY
    SELECT
        k.kelas_id, k.mata_kuliah_id, k.no_kelas,
        k.semester, k.tahun, k.tahun_ajaran,
        k.kode_matkul, k.nama_matkul_id, k.nama_matkul_en,
        k.sks, k.tahun_kurikulum, k.jenis_nilai,
        k.no_prodi, k.kode_prodi, k.nama_prodi_id, k.nama_prodi_en,
        k.jenjang, k.kode_fakultas, k.nama_fakultas_id, k.nama_fakultas_en,
        k.semua_dosen_id, k.semua_dosen_nama_gelar,
        k.kode_jenis_list, k.nama_jenis_list, k.nama_paket_list,
        k.kode_sifat_list, k.is_wajib_itb,
        k.pct_kehadiran_mahasiswa, k.pct_kehadiran_dosen,
        k.avg_ip_akhir_mahasiswa,
        k.skor_dna, k.ts_dna, k.ip_mhs_dna,
        k.is_distribusi_nilai_sah, k.jumlah_mahasiswa,
        k.dist_jumlah_a, k.dist_jumlah_ab, k.dist_jumlah_b,
        k.dist_jumlah_bc, k.dist_jumlah_c, k.dist_jumlah_d,
        k.dist_jumlah_e, k.dist_jumlah_pass, k.dist_jumlah_fail,
        k.dist_pct_a, k.dist_pct_ab, k.dist_pct_b, k.dist_pct_bc,
        k.dist_pct_c, k.dist_pct_d, k.dist_pct_e,
        k.dist_pct_pass, k.dist_pct_fail,
        k.dist_pct_lulus_a_c, k.dist_pct_lulus_a_d,
        k.skor_q21, k.skor_q22, k.skor_q23, k.skor_q24,
        k.skor_q25, k.skor_q26, k.skor_q27,
        k.skor_q28, k.skor_q29, k.skor_q30, k.skor_q35, k.skor_q37,
        -- Masking skor_dosen_q* untuk DOSEN:
        -- Non-DOSEN → tampilkan JSONB penuh (semua dosen dalam kelas)
        -- DOSEN      → hanya entry dengan key = dosen_id miliknya
        CASE WHEN v_role = 'DOSEN' THEN
            CASE WHEN k.skor_dosen_q25 ? (v_dosen_id::TEXT)
                 THEN jsonb_build_object(v_dosen_id::TEXT,
                          k.skor_dosen_q25->>(v_dosen_id::TEXT))
                 ELSE NULL END
        ELSE k.skor_dosen_q25 END,
        CASE WHEN v_role = 'DOSEN' THEN
            CASE WHEN k.skor_dosen_q26 ? (v_dosen_id::TEXT)
                 THEN jsonb_build_object(v_dosen_id::TEXT,
                          k.skor_dosen_q26->>(v_dosen_id::TEXT))
                 ELSE NULL END
        ELSE k.skor_dosen_q26 END,
        CASE WHEN v_role = 'DOSEN' THEN
            CASE WHEN k.skor_dosen_q27 ? (v_dosen_id::TEXT)
                 THEN jsonb_build_object(v_dosen_id::TEXT,
                          k.skor_dosen_q27->>(v_dosen_id::TEXT))
                 ELSE NULL END
        ELSE k.skor_dosen_q27 END,
        k.avg_skor_capaian, k.avg_skor_pelaksanaan,
        k.avg_skor_sarana_prasarana, k.avg_skor_perilaku_mahasiswa,
        k.avg_skor_overall
    FROM analitik_mv.mv_akademik_kelas k
    WHERE CASE v_role
        WHEN 'ADMIN'           THEN true
        WHEN 'DIREKTORAT'      THEN true
        WHEN 'DEKAN'           THEN k.kode_fakultas = v_kd_fak
        WHEN 'JAJARAN_DEKANAT' THEN k.kode_fakultas = v_kd_fak
        WHEN 'KAPRODI'         THEN k.no_prodi = v_no_prodi
        WHEN 'JAJARAN_PRODI'   THEN k.no_prodi = v_no_prodi
        WHEN 'DOSEN'           THEN k.no_prodi = v_no_prodi
        ELSE false
    END;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

CREATE VIEW analitik.v_akademik_kelas AS
SELECT * FROM analitik.fn_get_akademik_kelas();


-- ── B2. mv_akademik_komentar_mahasiswa ───────────────────────────
-- DOSEN: row filter = no_prodi (setara KAPRODI)
-- Tidak ada masking kolom

CREATE OR REPLACE FUNCTION analitik.fn_get_akademik_komentar_mahasiswa()
RETURNS SETOF analitik_mv.mv_akademik_komentar_mahasiswa AS $$
DECLARE
    v_role     text;
    v_dosen_id integer;
    v_no_prodi integer;
    v_kd_fak   character varying;
BEGIN
    v_role     := NULLIF(current_setting('app.role',     true), '');
    v_dosen_id := NULLIF(current_setting('app.dosen_id', true), '')::integer;
    v_no_prodi := NULLIF(current_setting('app.no_ps', true), '')::integer;
    v_kd_fak   := NULLIF(current_setting('app.kd_fak',   true), '');
    IF v_role IS NULL THEN RETURN; END IF;

    RETURN QUERY
    SELECT * FROM analitik_mv.mv_akademik_komentar_mahasiswa k
    WHERE CASE v_role
        WHEN 'ADMIN'           THEN true
        WHEN 'DIREKTORAT'      THEN true
        WHEN 'DEKAN'           THEN k.kode_fakultas = v_kd_fak
        WHEN 'JAJARAN_DEKANAT' THEN k.kode_fakultas = v_kd_fak
        WHEN 'KAPRODI'         THEN k.no_prodi = v_no_prodi
        WHEN 'JAJARAN_PRODI'   THEN k.no_prodi = v_no_prodi
        WHEN 'DOSEN'           THEN v_dosen_id = ANY(k.semua_dosen_id)
        ELSE false
    END;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

CREATE VIEW analitik.v_akademik_komentar_mahasiswa AS
SELECT * FROM analitik.fn_get_akademik_komentar_mahasiswa();


-- ── B3. mv_akademik_portofolio ───────────────────────────────────
-- DOSEN: row filter = no_prodi (setara KAPRODI)
-- Tidak ada masking kolom

CREATE OR REPLACE FUNCTION analitik.fn_get_akademik_portofolio()
RETURNS SETOF analitik_mv.mv_akademik_portofolio AS $$
DECLARE
    v_role     text;
    v_no_prodi integer;
    v_kd_fak   character varying;
BEGIN
    v_role     := NULLIF(current_setting('app.role',     true), '');
    v_no_prodi := NULLIF(current_setting('app.no_ps', true), '')::integer;
    v_kd_fak   := NULLIF(current_setting('app.kd_fak',   true), '');
    IF v_role IS NULL THEN RETURN; END IF;

    RETURN QUERY
    SELECT * FROM analitik_mv.mv_akademik_portofolio p
    WHERE CASE v_role
        WHEN 'ADMIN'           THEN true
        WHEN 'DIREKTORAT'      THEN true
        WHEN 'DEKAN'           THEN p.kode_fakultas = v_kd_fak
        WHEN 'JAJARAN_DEKANAT' THEN p.kode_fakultas = v_kd_fak
        WHEN 'KAPRODI'         THEN p.no_prodi = v_no_prodi
        WHEN 'JAJARAN_PRODI'   THEN p.no_prodi = v_no_prodi
        WHEN 'DOSEN'           THEN p.no_prodi = v_no_prodi --dosen_id ada di p.semua_dosen_id
        ELSE false
    END;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

CREATE VIEW analitik.v_akademik_portofolio AS
SELECT * FROM analitik.fn_get_akademik_portofolio();


-- ── B4. mv_akademik_statistik_prodi ─────────────────────────────
-- DOSEN: row filter = no_prodi (setara KAPRODI) — BERBEDA dari rancangan lama
-- Tidak ada masking kolom

CREATE OR REPLACE FUNCTION analitik.fn_get_akademik_statistik_prodi()
RETURNS SETOF analitik_mv.mv_akademik_statistik_prodi AS $$
DECLARE
    v_role     text;
    v_no_prodi integer;
    v_kd_fak   character varying;
BEGIN
    v_role     := NULLIF(current_setting('app.role',     true), '');
    v_no_prodi := NULLIF(current_setting('app.no_ps', true), '')::integer;
    v_kd_fak   := NULLIF(current_setting('app.kd_fak',   true), '');
    IF v_role IS NULL THEN RETURN; END IF;

    RETURN QUERY
    SELECT * FROM analitik_mv.mv_akademik_statistik_prodi sp
    WHERE CASE v_role
        WHEN 'ADMIN'           THEN true
        WHEN 'DIREKTORAT'      THEN true
        WHEN 'DEKAN'           THEN sp.kode_fakultas = v_kd_fak
        WHEN 'JAJARAN_DEKANAT' THEN sp.kode_fakultas = v_kd_fak
        WHEN 'KAPRODI'         THEN sp.no_prodi = v_no_prodi
        WHEN 'JAJARAN_PRODI'   THEN sp.no_prodi = v_no_prodi
        WHEN 'DOSEN'           THEN sp.no_prodi = v_no_prodi
        ELSE false
    END;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

CREATE VIEW analitik.v_akademik_statistik_prodi AS
SELECT * FROM analitik.fn_get_akademik_statistik_prodi();


-- ── B5. mv_akademik_statistik_dosen ─────────────────────────────
-- PALING KOMPLEKS — dua level filtering:
--
-- Row filter:
--   DEKAN/JAJARAN_DEKANAT : kode_fakultas_dosen = v_kd_fak (homebase)
--   KAPRODI/JAJARAN_PRODI : v_no_prodi = ANY(no_prodi_diajar) (prodi diajar)
--   DOSEN                 : v_no_prodi = ANY(no_prodi_diajar) (prodi diajar)
--
-- Column masking untuk DOSEN (dosen lain di prodinya):
--   Tampil penuh   → dosen_id = v_dosen_id (data diri sendiri)
--   Di-mask (NULL) → dosen_id != v_dosen_id (dosen lain)
--   Kolom yang di-mask: avg_pct_kehadiran_dosen, avg_ip_mhs,
--     avg_skor_q25/q26/q27, avg_skor_capaian, avg_skor_pelaksanaan,
--     avg_skor_sarana_prasarana, avg_skor_perilaku_mahasiswa,
--     avg_skor_overall, jumlah_kelas_dengan_skor, avg_nilai_akhir

CREATE OR REPLACE FUNCTION analitik.fn_get_akademik_statistik_dosen()
RETURNS TABLE (
    dosen_id                    integer,
    nama_dosen_gelar            character varying,
    nip                         character varying,
    kk_id                       integer,
    nama_kk_id                  text,
    nama_kk_en                  text,
    kode_fakultas_dosen         character varying,
    no_prodi                    integer,
    kode_prodi                  character varying,
    semester                    smallint,
    tahun                       smallint,
    tahun_ajaran                text,
    jumlah_kelas                bigint,
    jumlah_matkul               bigint,
    total_sks_diajar            bigint,
    -- Kehadiran dosen: di-mask untuk dosen lain jika role DOSEN
    avg_pct_kehadiran_dosen     numeric,
    avg_pct_kehadiran_mahasiswa numeric,
    -- IP mhs di kelas dosen: di-mask untuk dosen lain
    avg_ip_mhs                  numeric,
    -- Skor kuesioner: di-mask untuk  dosen lain
    avg_skor_q25                numeric,
    avg_skor_q26                numeric,
    avg_skor_q27                numeric,
    avg_skor_capaian            numeric,
    avg_skor_pelaksanaan        numeric,
    avg_skor_sarana_prasarana   numeric,
    avg_skor_perilaku_mahasiswa numeric,
    avg_skor_overall            numeric,
    jumlah_kelas_dengan_skor    bigint,
    avg_nilai_akhir             numeric,
    -- Info mengajar: selalu tampil (info profesional umum)
    kelas_ids                   integer[],
    kode_matkul_list            character(6)[],
    no_prodi_diajar             integer[],
    kode_prodi_diajar           character varying[]
) AS $$
DECLARE
    v_role     text;
    v_dosen_id integer;
    v_no_prodi integer;
    v_kd_fak   character varying;
    -- Shorthand: apakah baris ini milik dosen sendiri?
    -- Dievaluasi per baris di SELECT via ekspresi inline
BEGIN
    v_role     := NULLIF(current_setting('app.role',     true), '');
    v_dosen_id := NULLIF(current_setting('app.dosen_id', true), '')::integer;
    v_no_prodi := NULLIF(current_setting('app.no_ps', true), '')::integer;
    v_kd_fak   := NULLIF(current_setting('app.kd_fak',   true), '');
    IF v_role IS NULL THEN RETURN; END IF;

    RETURN QUERY
    SELECT
        -- Identitas dosen (selalu tampil)
        sd.dosen_id,
        sd.nama_dosen_gelar,
        sd.nip,
        sd.kk_id,
        sd.nama_kk_id,
        sd.nama_kk_en,
        sd.kode_fakultas_dosen,
        sd.no_prodi,
        sd.kode_prodi::character varying,
        sd.semester,
        sd.tahun,
        sd.tahun_ajaran,
        -- Statistik mengajar umum (selalu tampil)
        sd.jumlah_kelas,
        sd.jumlah_matkul,
        sd.total_sks_diajar,
        -- ── Kolom sensitif — di-mask untuk dosen lain jika role DOSEN ──
        -- Rumus: tampil jika (bukan DOSEN) ATAU (DOSEN dan baris milik sendiri)
        CASE WHEN v_role != 'DOSEN' OR sd.dosen_id = v_dosen_id
             THEN sd.avg_pct_kehadiran_dosen     ELSE NULL END,
        -- avg_pct_kehadiran_mahasiswa: tidak di-mask (tentang mahasiswa, bukan dosen)
        sd.avg_pct_kehadiran_mahasiswa,
        CASE WHEN v_role != 'DOSEN' OR sd.dosen_id = v_dosen_id
             THEN sd.avg_ip_mhs                  ELSE NULL END,
        CASE WHEN v_role != 'DOSEN' OR sd.dosen_id = v_dosen_id
             THEN sd.avg_skor_q25                ELSE NULL END,
        CASE WHEN v_role != 'DOSEN' OR sd.dosen_id = v_dosen_id
             THEN sd.avg_skor_q26                ELSE NULL END,
        CASE WHEN v_role != 'DOSEN' OR sd.dosen_id = v_dosen_id
             THEN sd.avg_skor_q27                ELSE NULL END,
        CASE WHEN v_role != 'DOSEN' OR sd.dosen_id = v_dosen_id
             THEN sd.avg_skor_capaian            ELSE NULL END,
        CASE WHEN v_role != 'DOSEN' OR sd.dosen_id = v_dosen_id
             THEN sd.avg_skor_pelaksanaan        ELSE NULL END,
        CASE WHEN v_role != 'DOSEN' OR sd.dosen_id = v_dosen_id
             THEN sd.avg_skor_sarana_prasarana   ELSE NULL END,
        CASE WHEN v_role != 'DOSEN' OR sd.dosen_id = v_dosen_id
             THEN sd.avg_skor_perilaku_mahasiswa ELSE NULL END,
        CASE WHEN v_role != 'DOSEN' OR sd.dosen_id = v_dosen_id
             THEN sd.avg_skor_overall            ELSE NULL END,
        CASE WHEN v_role != 'DOSEN' OR sd.dosen_id = v_dosen_id
             THEN sd.jumlah_kelas_dengan_skor    ELSE NULL END,
        CASE WHEN v_role != 'DOSEN' OR sd.dosen_id = v_dosen_id
             THEN sd.avg_nilai_akhir             ELSE NULL END,
        -- Info prodi yang diajar (selalu tampil)
        sd.kelas_ids,
        sd.kode_matkul_list,
        sd.no_prodi_diajar,
        sd.kode_prodi_diajar::character varying[]
    FROM analitik_mv.mv_akademik_statistik_dosen sd
    WHERE CASE v_role
        WHEN 'ADMIN'           THEN true
        WHEN 'DIREKTORAT'      THEN true
        WHEN 'DEKAN'           THEN sd.kode_fakultas_dosen = v_kd_fak
        WHEN 'JAJARAN_DEKANAT' THEN sd.kode_fakultas_dosen = v_kd_fak
        -- KAPRODI/JAJARAN_PRODI/DOSEN: berdasarkan prodi yang sedang diajar
        WHEN 'KAPRODI'         THEN v_no_prodi = ANY(sd.no_prodi_diajar)
        WHEN 'JAJARAN_PRODI'   THEN v_no_prodi = ANY(sd.no_prodi_diajar)
        WHEN 'DOSEN'           THEN v_no_prodi = ANY(sd.no_prodi_diajar)
        ELSE false
    END;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

CREATE VIEW analitik.v_akademik_statistik_dosen AS
SELECT * FROM analitik.fn_get_akademik_statistik_dosen();


-- ── B6. mv_wisudawan_distribusi_jawaban ──────────────────────────

CREATE OR REPLACE FUNCTION analitik.fn_get_wisudawan_distribusi_jawaban()
RETURNS SETOF analitik_mv.mv_wisudawan_distribusi_jawaban AS $$
DECLARE
    v_role     text;
    v_no_prodi integer;
    v_kd_fak   character varying;
BEGIN
    v_role     := NULLIF(current_setting('app.role',     true), '');
    v_no_prodi := NULLIF(current_setting('app.no_ps', true), '')::integer;
    v_kd_fak   := NULLIF(current_setting('app.kd_fak',   true), '');
    IF v_role IS NULL THEN RETURN; END IF;

    RETURN QUERY
    SELECT * FROM analitik_mv.mv_wisudawan_distribusi_jawaban w
    WHERE CASE v_role
        WHEN 'ADMIN'           THEN true
        WHEN 'DIREKTORAT'      THEN true
        WHEN 'DEKAN'           THEN w.kode_fakultas = v_kd_fak
        WHEN 'JAJARAN_DEKANAT' THEN w.kode_fakultas = v_kd_fak
        WHEN 'KAPRODI'         THEN w.no_prodi = v_no_prodi
        WHEN 'JAJARAN_PRODI'   THEN w.no_prodi = v_no_prodi
        WHEN 'DOSEN'           THEN w.no_prodi = v_no_prodi
        ELSE false
    END;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

CREATE VIEW analitik.v_wisudawan_distribusi_jawaban AS
SELECT * FROM analitik.fn_get_wisudawan_distribusi_jawaban();


-- ── B7. mv_wisudawan_statistik_pertanyaan ────────────────────────

CREATE OR REPLACE FUNCTION analitik.fn_get_wisudawan_statistik_pertanyaan()
RETURNS SETOF analitik_mv.mv_wisudawan_statistik_pertanyaan AS $$
DECLARE
    v_role     text;
    v_no_prodi integer;
    v_kd_fak   character varying;
BEGIN
    v_role     := NULLIF(current_setting('app.role',     true), '');
    v_no_prodi := NULLIF(current_setting('app.no_ps', true), '')::integer;
    v_kd_fak   := NULLIF(current_setting('app.kd_fak',   true), '');
    IF v_role IS NULL THEN RETURN; END IF;

    RETURN QUERY
    SELECT * FROM analitik_mv.mv_wisudawan_statistik_pertanyaan w
    WHERE CASE v_role
        WHEN 'ADMIN'           THEN true
        WHEN 'DIREKTORAT'      THEN true
        WHEN 'DEKAN'           THEN w.kode_fakultas = v_kd_fak
        WHEN 'JAJARAN_DEKANAT' THEN w.kode_fakultas = v_kd_fak
        WHEN 'KAPRODI'         THEN w.no_prodi = v_no_prodi
        WHEN 'JAJARAN_PRODI'   THEN w.no_prodi = v_no_prodi
        WHEN 'DOSEN'           THEN w.no_prodi = v_no_prodi
        ELSE false
    END;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

CREATE VIEW analitik.v_wisudawan_statistik_pertanyaan AS
SELECT * FROM analitik.fn_get_wisudawan_statistik_pertanyaan();


-- ── B8. mv_wisudawan_jawaban_responden ───────────────────────────
-- Wide table (138+ kolom) — gunakan SETOF karena tidak ada masking

CREATE OR REPLACE FUNCTION analitik.fn_get_wisudawan_jawaban_responden()
RETURNS SETOF analitik_mv.mv_wisudawan_jawaban_responden AS $$
DECLARE
    v_role     text;
    v_no_prodi integer;
    v_kd_fak   character varying;
BEGIN
    v_role     := NULLIF(current_setting('app.role',     true), '');
    v_no_prodi := NULLIF(current_setting('app.no_ps', true), '')::integer;
    v_kd_fak   := NULLIF(current_setting('app.kd_fak',   true), '');
    IF v_role IS NULL THEN RETURN; END IF;

    RETURN QUERY
    SELECT * FROM analitik_mv.mv_wisudawan_jawaban_responden w
    WHERE CASE v_role
        WHEN 'ADMIN'           THEN true
        WHEN 'DIREKTORAT'      THEN true
        WHEN 'DEKAN'           THEN w.kode_fakultas = v_kd_fak
        WHEN 'JAJARAN_DEKANAT' THEN w.kode_fakultas = v_kd_fak
        WHEN 'KAPRODI'         THEN w.no_prodi = v_no_prodi
        WHEN 'JAJARAN_PRODI'   THEN w.no_prodi = v_no_prodi
        WHEN 'DOSEN'           THEN w.no_prodi = v_no_prodi
        ELSE false
    END;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = '';

CREATE VIEW analitik.v_wisudawan_jawaban_responden AS
SELECT * FROM analitik.fn_get_wisudawan_jawaban_responden();

-- ================================================================
-- E. RINGKASAN OBJEK YANG DIBUAT
-- ================================================================
--
-- Schema analitik.*
-- ├── View publik (5):
-- │   ├── v_akademik_jenis_dan_sifat_matkul  [A1] semua role
-- │   ├── v_info_umum_matkul                  [A2] semua role
-- │   ├── v_info_umum_institusi               [A3] semua role
-- │   ├── v_info_umum_dosen                   [A4] semua role
-- │   └── v_info_umum_wisuda                  [A5] semua role
-- │
-- ├── Security Definer Functions (8):
-- │   ├── fn_get_akademik_kelas()             [B1] + masking JSONB DOSEN
-- │   ├── fn_get_akademik_komentar_mahasiswa() [B2]
-- │   ├── fn_get_akademik_portofolio()        [B3]
-- │   ├── fn_get_akademik_statistik_prodi()   [B4]
-- │   ├── fn_get_akademik_statistik_dosen()   [B5] + masking kolom DOSEN
-- │   ├── fn_get_wisudawan_distribusi_jawaban() [B6]
-- │   ├── fn_get_wisudawan_statistik_pertanyaan() [B7]
-- │   └── fn_get_wisudawan_jawaban_responden() [B8]
-- │
-- └── View wrappers (8):
--     ├── v_akademik_kelas
--     ├── v_akademik_komentar_mahasiswa
--     ├── v_akademik_portofolio
--     ├── v_akademik_statistik_prodi
--     ├── v_akademik_statistik_dosen
--     ├── v_wisudawan_distribusi_jawaban
--     ├── v_wisudawan_statistik_pertanyaan
--     └── v_wisudawan_jawaban_responden