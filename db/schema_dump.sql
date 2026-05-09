--
-- PostgreSQL database dump
--

\restrict TLgEkNtEeIJ2d9TIcgWiLKl0OucdSEByRW9ZQ3MDyMIpLmOWTD9VWIbAYfxddfP

-- Dumped from database version 16.13 (Debian 16.13-1.pgdg12+1)
-- Dumped by pg_dump version 16.13 (Debian 16.13-1.pgdg12+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: fuzzystrmatch; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS fuzzystrmatch WITH SCHEMA public;


--
-- Name: EXTENSION fuzzystrmatch; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION fuzzystrmatch IS 'determine similarities and distance between strings';


--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: tipe_konten_enum; Type: TYPE; Schema: public; Owner: itb_admin
--

CREATE TYPE public.tipe_konten_enum AS ENUM (
    'metode_perkuliahan',
    'sistem_penilaian',
    'analisis_capaian_kelas',
    'tambahan_info_statistik',
    'refleksi_pelaksanaan',
    'usulan_perbaikan_dosen',
    'usulan_perbaikan_itb'
);


ALTER TYPE public.tipe_konten_enum OWNER TO itb_admin;

--
-- Name: user_role_enum; Type: TYPE; Schema: public; Owner: itb_admin
--

CREATE TYPE public.user_role_enum AS ENUM (
    'admin',
    'wram',
    'dekan',
    'jajaran_dekanat',
    'kaprodi',
    'jajaran_prodi',
    'dosen'
);


ALTER TYPE public.user_role_enum OWNER TO itb_admin;

--
-- Name: fn_komentar_reset_embedding(); Type: FUNCTION; Schema: public; Owner: itb_admin
--

CREATE FUNCTION public.fn_komentar_reset_embedding() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.teks_komentar IS DISTINCT FROM OLD.teks_komentar THEN
        NEW.is_embedded := FALSE;
        NEW.embedded_at := NULL;
    END IF;
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.fn_komentar_reset_embedding() OWNER TO itb_admin;

--
-- Name: fn_teks_reset_embedding(); Type: FUNCTION; Schema: public; Owner: itb_admin
--

CREATE FUNCTION public.fn_teks_reset_embedding() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.konten IS DISTINCT FROM OLD.konten THEN
        NEW.is_embedded := FALSE;
        NEW.embedded_at := NULL;
    END IF;
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.fn_teks_reset_embedding() OWNER TO itb_admin;

--
-- Name: user_can_see_kelas(uuid); Type: FUNCTION; Schema: public; Owner: itb_admin
--

CREATE FUNCTION public.user_can_see_kelas(p_kelas_id uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    AS $$
    SELECT EXISTS (
        SELECT 1 FROM pengguna p
        WHERE p.user_id = current_setting('app.user_id', TRUE)::uuid
          AND p.role IN ('admin', 'wram')
    )
    OR EXISTS (
        SELECT 1 FROM kelas k
        JOIN mata_kuliah mk ON mk.matkul_id = k.matkul_id
        WHERE k.kelas_id = p_kelas_id AND (
            EXISTS (
                SELECT 1 FROM pengajar_kelas pk
                JOIN user_scope us ON us.dosen_id = pk.dosen_id
                WHERE pk.kelas_id = p_kelas_id
                  AND us.user_id = current_setting('app.user_id',TRUE)::uuid
            )
            OR EXISTS (
                SELECT 1 FROM user_scope us
                WHERE us.prodi_id = mk.prodi_id
                  AND us.user_id = current_setting('app.user_id',TRUE)::uuid
            )
            OR EXISTS (
                SELECT 1 FROM program_studi ps
                JOIN user_scope us ON us.fakultas_id = ps.fakultas_id
                WHERE ps.prodi_id = mk.prodi_id
                  AND us.user_id = current_setting('app.user_id',TRUE)::uuid
            )
        )
    );
$$;


ALTER FUNCTION public.user_can_see_kelas(p_kelas_id uuid) OWNER TO itb_admin;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: distribusi_nilai; Type: TABLE; Schema: public; Owner: itb_admin
--

CREATE TABLE public.distribusi_nilai (
    distribusi_id uuid DEFAULT gen_random_uuid() NOT NULL,
    kelas_id uuid NOT NULL,
    grade character varying(5) NOT NULL,
    jumlah smallint DEFAULT 0 NOT NULL,
    persentase numeric(5,2),
    CONSTRAINT distribusi_nilai_grade_check CHECK (((grade)::text = ANY ((ARRAY['A'::character varying, 'AB'::character varying, 'B'::character varying, 'BC'::character varying, 'C'::character varying, 'D'::character varying, 'E'::character varying, 'Pass'::character varying, 'Fail'::character varying])::text[]))),
    CONSTRAINT distribusi_nilai_jumlah_check CHECK ((jumlah >= 0)),
    CONSTRAINT distribusi_nilai_persentase_check CHECK (((persentase >= (0)::numeric) AND (persentase <= (100)::numeric)))
);


ALTER TABLE public.distribusi_nilai OWNER TO itb_admin;

--
-- Name: dosen; Type: TABLE; Schema: public; Owner: itb_admin
--

CREATE TABLE public.dosen (
    dosen_id uuid DEFAULT gen_random_uuid() NOT NULL,
    kk_id uuid,
    nama_dosen character varying(150) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.dosen OWNER TO itb_admin;

--
-- Name: fakultas; Type: TABLE; Schema: public; Owner: itb_admin
--

CREATE TABLE public.fakultas (
    fakultas_id uuid DEFAULT gen_random_uuid() NOT NULL,
    kode_fakultas character varying(20) NOT NULL,
    nama_fakultas character varying(100) NOT NULL,
    parent_fakultas_id uuid,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.fakultas OWNER TO itb_admin;

--
-- Name: TABLE fakultas; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON TABLE public.fakultas IS 'Hierarki fakultas/sekolah ITB. Self-referencing via parent_fakultas_id untuk struktur sub-kampus.';


--
-- Name: COLUMN fakultas.kode_fakultas; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.fakultas.kode_fakultas IS 'Kode singkat sesuai SIX ITB, e.g. STEI, FITB, SBM.';


--
-- Name: COLUMN fakultas.parent_fakultas_id; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.fakultas.parent_fakultas_id IS 'NULL untuk fakultas induk. Diisi untuk sub-sekolah/kampus.';


--
-- Name: ingestion_log; Type: TABLE; Schema: public; Owner: itb_admin
--

CREATE TABLE public.ingestion_log (
    log_id uuid DEFAULT gen_random_uuid() NOT NULL,
    kelas_id uuid,
    sumber_file character varying(500) NOT NULL,
    status character varying(20) NOT NULL,
    rows_inserted jsonb,
    error_message text,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    CONSTRAINT ingestion_log_status_check CHECK (((status)::text = ANY ((ARRAY['success'::character varying, 'partial'::character varying, 'failed'::character varying, 'skipped'::character varying])::text[])))
);


ALTER TABLE public.ingestion_log OWNER TO itb_admin;

--
-- Name: TABLE ingestion_log; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON TABLE public.ingestion_log IS 'Audit trail setiap proses ingestion CSV. kelas_id NULL jika gagal sebelum kelas terbuat. rows_inserted JSONB untuk breakdown per tabel.';


--
-- Name: kelas; Type: TABLE; Schema: public; Owner: itb_admin
--

CREATE TABLE public.kelas (
    kelas_id uuid DEFAULT gen_random_uuid() NOT NULL,
    matkul_id uuid NOT NULL,
    no_kelas character varying(5) NOT NULL,
    semester smallint NOT NULL,
    tahun_ajaran character varying(9) NOT NULL,
    sks smallint NOT NULL,
    pct_kehadiran_dosen numeric(5,2),
    pct_kehadiran_mahasiswa numeric(5,2),
    rata_rata_nilai numeric(4,2),
    jumlah_mahasiswa smallint DEFAULT 0,
    nilai_portofolio smallint,
    sumber_file character varying(500),
    is_synthetic boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT kelas_jumlah_mahasiswa_check CHECK ((jumlah_mahasiswa >= 0)),
    CONSTRAINT kelas_nilai_portofolio_check CHECK (((nilai_portofolio >= 1) AND (nilai_portofolio <= 4))),
    CONSTRAINT kelas_pct_kehadiran_dosen_check CHECK (((pct_kehadiran_dosen >= (0)::numeric) AND (pct_kehadiran_dosen <= (100)::numeric))),
    CONSTRAINT kelas_pct_kehadiran_mahasiswa_check CHECK (((pct_kehadiran_mahasiswa >= (0)::numeric) AND (pct_kehadiran_mahasiswa <= (100)::numeric))),
    CONSTRAINT kelas_rata_rata_nilai_check CHECK (((rata_rata_nilai >= (0)::numeric) AND (rata_rata_nilai <= (4)::numeric))),
    CONSTRAINT kelas_semester_check CHECK ((semester = ANY (ARRAY[1, 2, 3]))),
    CONSTRAINT kelas_sks_check CHECK (((sks >= 1) AND (sks <= 6))),
    CONSTRAINT kelas_tahun_ajaran_check CHECK (((tahun_ajaran)::text ~ '^\d{4}/\d{4}$'::text))
);


ALTER TABLE public.kelas OWNER TO itb_admin;

--
-- Name: TABLE kelas; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON TABLE public.kelas IS '1 row = 1 dokumen portofolio unik';


--
-- Name: COLUMN kelas.no_kelas; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.kelas.no_kelas IS 'Nomor kelas, e.g. 1, 2, 3.';


--
-- Name: COLUMN kelas.semester; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.kelas.semester IS '1=Ganjil, 2=Genap, 3=Semester Pendek (SBM/khusus ITB).';


--
-- Name: COLUMN kelas.sks; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.kelas.sks IS 'Snapshot SKS saat kelas ini berjalan. CHECK 1..6 .';


--
-- Name: COLUMN kelas.rata_rata_nilai; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.kelas.rata_rata_nilai IS 'Skala 0.00–4.00.';


--
-- Name: COLUMN kelas.nilai_portofolio; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.kelas.nilai_portofolio IS 'Skor verifikator 1–4. NULL jika belum diverifikasi.';


--
-- Name: kelompok_keahlian; Type: TABLE; Schema: public; Owner: itb_admin
--

CREATE TABLE public.kelompok_keahlian (
    kk_id uuid DEFAULT gen_random_uuid() NOT NULL,
    fakultas_id uuid NOT NULL,
    nama_kk character varying(200) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.kelompok_keahlian OWNER TO itb_admin;

--
-- Name: TABLE kelompok_keahlian; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON TABLE public.kelompok_keahlian IS 'KK berada di level fakultas. Dosen berafiliasi ke KK, bukan langsung ke prodi.';


--
-- Name: komentar_mahasiswa; Type: TABLE; Schema: public; Owner: itb_admin
--

CREATE TABLE public.komentar_mahasiswa (
    komentar_id uuid DEFAULT gen_random_uuid() NOT NULL,
    kelas_id uuid NOT NULL,
    no_komentar smallint NOT NULL,
    teks_komentar text NOT NULL,
    is_embedded boolean DEFAULT false NOT NULL,
    embedded_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT komentar_mahasiswa_no_komentar_check CHECK ((no_komentar > 0)),
    CONSTRAINT komentar_mahasiswa_teks_komentar_check CHECK ((length(TRIM(BOTH FROM teks_komentar)) > 0))
);


ALTER TABLE public.komentar_mahasiswa OWNER TO itb_admin;

--
-- Name: TABLE komentar_mahasiswa; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON TABLE public.komentar_mahasiswa IS 'Komentar bebas mahasiswa. 1 row = 1 komentar = 1 chunk di vector store. Di-split dari delimiter || saat ingestion CSV.';


--
-- Name: COLUMN komentar_mahasiswa.no_komentar; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.komentar_mahasiswa.no_komentar IS 'Urutan dalam kelas. Dipakai sebagai dedup key saat re-ingest (ON CONFLICT DO UPDATE).';


--
-- Name: llm_analysis_cache; Type: TABLE; Schema: public; Owner: itb_admin
--

CREATE TABLE public.llm_analysis_cache (
    cache_id character varying(64) NOT NULL,
    analysis_type character varying(50) NOT NULL,
    kelas_ids uuid[] NOT NULL,
    result_json jsonb NOT NULL,
    model_used character varying(100),
    prompt_tokens integer,
    completion_tokens integer,
    generated_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone
);


ALTER TABLE public.llm_analysis_cache OWNER TO itb_admin;

--
-- Name: TABLE llm_analysis_cache; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON TABLE public.llm_analysis_cache IS 'Cache hasil LLM call. cache_id = SHA256(sorted kelas_ids + analysis_type). TTL 180 hari via expires_at. result_json JSONB agar bisa query field tertentu.';


--
-- Name: COLUMN llm_analysis_cache.kelas_ids; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.llm_analysis_cache.kelas_ids IS 'Array UUID kelas yang menjadi input analisis.';


--
-- Name: mata_kuliah; Type: TABLE; Schema: public; Owner: itb_admin
--

CREATE TABLE public.mata_kuliah (
    matkul_id uuid DEFAULT gen_random_uuid() NOT NULL,
    prodi_id uuid NOT NULL,
    kode_mk character varying(20) NOT NULL,
    nama_mk character varying(200) NOT NULL,
    kategori character varying(100) DEFAULT 'Kuliah'::character varying NOT NULL,
    jenis_nilai character varying(10) DEFAULT 'ABCDE'::character varying NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    nama_mk_en character varying(200),
    CONSTRAINT mata_kuliah_jenis_nilai_check CHECK (((jenis_nilai)::text = ANY ((ARRAY['ABCDE'::character varying, 'Pass/Fail'::character varying])::text[])))
);


ALTER TABLE public.mata_kuliah OWNER TO itb_admin;

--
-- Name: COLUMN mata_kuliah.kode_mk; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.mata_kuliah.kode_mk IS 'e.g. IF4044. Unik per prodi (UNIQUE + prodi_id). NOT NULL.';


--
-- Name: pengajar_kelas; Type: TABLE; Schema: public; Owner: itb_admin
--

CREATE TABLE public.pengajar_kelas (
    kelas_id uuid NOT NULL,
    dosen_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.pengajar_kelas OWNER TO itb_admin;

--
-- Name: program_studi; Type: TABLE; Schema: public; Owner: itb_admin
--

CREATE TABLE public.program_studi (
    prodi_id uuid DEFAULT gen_random_uuid() NOT NULL,
    fakultas_id uuid NOT NULL,
    kode_prodi character varying(10) NOT NULL,
    singkatan_prodi character varying(10),
    nama_prodi character varying(150) NOT NULL,
    jenjang character varying(10) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT program_studi_jenjang_check CHECK (((jenjang)::text = ANY ((ARRAY['S1'::character varying, 'S2'::character varying, 'S3'::character varying, 'Profesi'::character varying])::text[])))
);


ALTER TABLE public.program_studi OWNER TO itb_admin;

--
-- Name: TABLE program_studi; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON TABLE public.program_studi IS '1 prodi hanya dimiliki 1 fakultas (no sharing). Relasi N:1 ke fakultas.';


--
-- Name: COLUMN program_studi.kode_prodi; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.program_studi.kode_prodi IS 'Kode PDDikti, e.g. 135 untuk Informatika.';


--
-- Name: COLUMN program_studi.singkatan_prodi; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.program_studi.singkatan_prodi IS 'Singkatan lazim, e.g. IF, STI — dipakai di label UI.';


--
-- Name: COLUMN program_studi.jenjang; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.program_studi.jenjang IS 'S1, S2, S3, atau Profesi.';


--
-- Name: skor_kuesioner; Type: TABLE; Schema: public; Owner: itb_admin
--

CREATE TABLE public.skor_kuesioner (
    skor_id uuid DEFAULT gen_random_uuid() NOT NULL,
    kelas_id uuid NOT NULL,
    no_pertanyaan smallint NOT NULL,
    rata_skor numeric(4,2) NOT NULL,
    CONSTRAINT skor_kuesioner_no_pertanyaan_check CHECK (((no_pertanyaan >= 1) AND (no_pertanyaan <= 12))),
    CONSTRAINT skor_kuesioner_rata_skor_check CHECK (((rata_skor >= (1)::numeric) AND (rata_skor <= (4)::numeric)))
);


ALTER TABLE public.skor_kuesioner OWNER TO itb_admin;

--
-- Name: TABLE skor_kuesioner; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON TABLE public.skor_kuesioner IS '12 rows per kelas (Q1–Q12). Mapping dimensi: Q1-3=capaian, Q4-8=pelaksanaan, Q9-10=sarana, Q11-12=perilaku.';


--
-- Name: COLUMN skor_kuesioner.no_pertanyaan; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.skor_kuesioner.no_pertanyaan IS 'Q1-Q3: capaian pembelajaran. Q4-Q8: pelaksanaan & fairness. Q9-Q10: sarana prasarana. Q11-Q12: perilaku & pengalaman mahasiswa.';


--
-- Name: COLUMN skor_kuesioner.rata_skor; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.skor_kuesioner.rata_skor IS 'Skala Likert 1.00–4.00. CHECK 1..4';


--
-- Name: mv_kelas; Type: MATERIALIZED VIEW; Schema: public; Owner: itb_admin
--

CREATE MATERIALIZED VIEW public.mv_kelas AS
 SELECT k.kelas_id,
    k.matkul_id,
    k.no_kelas,
    k.semester,
    k.tahun_ajaran,
    k.sks,
    mk.kode_mk,
    mk.nama_mk,
    ps.prodi_id,
    ps.kode_prodi,
    ps.singkatan_prodi,
    ps.nama_prodi,
    ps.jenjang,
    f.fakultas_id,
    f.kode_fakultas,
    f.nama_fakultas,
    array_agg(d.dosen_id ORDER BY d.dosen_id) AS semua_dosen_id,
    array_agg(d.nama_dosen ORDER BY d.dosen_id) AS semua_dosen_nama,
    k.pct_kehadiran_dosen,
    k.pct_kehadiran_mahasiswa,
    k.rata_rata_nilai,
    k.jumlah_mahasiswa,
    k.nilai_portofolio,
    k.is_synthetic,
    COALESCE((max(dn.jumlah) FILTER (WHERE ((dn.grade)::text = 'A'::text)))::integer, 0) AS dist_jumlah_a,
    COALESCE((max(dn.jumlah) FILTER (WHERE ((dn.grade)::text = 'AB'::text)))::integer, 0) AS dist_jumlah_ab,
    COALESCE((max(dn.jumlah) FILTER (WHERE ((dn.grade)::text = 'B'::text)))::integer, 0) AS dist_jumlah_b,
    COALESCE((max(dn.jumlah) FILTER (WHERE ((dn.grade)::text = 'BC'::text)))::integer, 0) AS dist_jumlah_bc,
    COALESCE((max(dn.jumlah) FILTER (WHERE ((dn.grade)::text = 'C'::text)))::integer, 0) AS dist_jumlah_c,
    COALESCE((max(dn.jumlah) FILTER (WHERE ((dn.grade)::text = 'D'::text)))::integer, 0) AS dist_jumlah_d,
    COALESCE((max(dn.jumlah) FILTER (WHERE ((dn.grade)::text = 'E'::text)))::integer, 0) AS dist_jumlah_e,
    COALESCE((max(dn.jumlah) FILTER (WHERE ((dn.grade)::text = 'Pass'::text)))::integer, 0) AS dist_jumlah_pass,
    COALESCE((max(dn.jumlah) FILTER (WHERE ((dn.grade)::text = 'Fail'::text)))::integer, 0) AS dist_jumlah_fail,
    COALESCE(max(dn.persentase) FILTER (WHERE ((dn.grade)::text = 'A'::text)), (0)::numeric) AS dist_pct_a,
    COALESCE(max(dn.persentase) FILTER (WHERE ((dn.grade)::text = 'AB'::text)), (0)::numeric) AS dist_pct_ab,
    COALESCE(max(dn.persentase) FILTER (WHERE ((dn.grade)::text = 'B'::text)), (0)::numeric) AS dist_pct_b,
    COALESCE(max(dn.persentase) FILTER (WHERE ((dn.grade)::text = 'BC'::text)), (0)::numeric) AS dist_pct_bc,
    COALESCE(max(dn.persentase) FILTER (WHERE ((dn.grade)::text = 'C'::text)), (0)::numeric) AS dist_pct_c,
    COALESCE(max(dn.persentase) FILTER (WHERE ((dn.grade)::text = 'D'::text)), (0)::numeric) AS dist_pct_d,
    COALESCE(max(dn.persentase) FILTER (WHERE ((dn.grade)::text = 'E'::text)), (0)::numeric) AS dist_pct_e,
    COALESCE(max(dn.persentase) FILTER (WHERE ((dn.grade)::text = 'Pass'::text)), (0)::numeric) AS dist_pct_pass,
    COALESCE(max(dn.persentase) FILTER (WHERE ((dn.grade)::text = 'Fail'::text)), (0)::numeric) AS dist_pct_fail,
        CASE mk.jenis_nilai
            WHEN 'ABCDE'::text THEN ((((COALESCE(max(dn.persentase) FILTER (WHERE ((dn.grade)::text = 'A'::text)), (0)::numeric) + COALESCE(max(dn.persentase) FILTER (WHERE ((dn.grade)::text = 'AB'::text)), (0)::numeric)) + COALESCE(max(dn.persentase) FILTER (WHERE ((dn.grade)::text = 'B'::text)), (0)::numeric)) + COALESCE(max(dn.persentase) FILTER (WHERE ((dn.grade)::text = 'BC'::text)), (0)::numeric)) + COALESCE(max(dn.persentase) FILTER (WHERE ((dn.grade)::text = 'C'::text)), (0)::numeric))
            WHEN 'Pass/Fail'::text THEN COALESCE(max(dn.persentase) FILTER (WHERE ((dn.grade)::text = 'Pass'::text)), (0)::numeric)
            ELSE NULL::numeric
        END AS dist_pct_lulus,
    round(max(sk.rata_skor) FILTER (WHERE (sk.no_pertanyaan = 1)), 2) AS skor_q1,
    round(max(sk.rata_skor) FILTER (WHERE (sk.no_pertanyaan = 2)), 2) AS skor_q2,
    round(max(sk.rata_skor) FILTER (WHERE (sk.no_pertanyaan = 3)), 2) AS skor_q3,
    round(max(sk.rata_skor) FILTER (WHERE (sk.no_pertanyaan = 4)), 2) AS skor_q4,
    round(max(sk.rata_skor) FILTER (WHERE (sk.no_pertanyaan = 5)), 2) AS skor_q5,
    round(max(sk.rata_skor) FILTER (WHERE (sk.no_pertanyaan = 6)), 2) AS skor_q6,
    round(max(sk.rata_skor) FILTER (WHERE (sk.no_pertanyaan = 7)), 2) AS skor_q7,
    round(max(sk.rata_skor) FILTER (WHERE (sk.no_pertanyaan = 8)), 2) AS skor_q8,
    round(max(sk.rata_skor) FILTER (WHERE (sk.no_pertanyaan = 9)), 2) AS skor_q9,
    round(max(sk.rata_skor) FILTER (WHERE (sk.no_pertanyaan = 10)), 2) AS skor_q10,
    round(max(sk.rata_skor) FILTER (WHERE (sk.no_pertanyaan = 11)), 2) AS skor_q11,
    round(max(sk.rata_skor) FILTER (WHERE (sk.no_pertanyaan = 12)), 2) AS skor_q12,
    round(avg(sk.rata_skor) FILTER (WHERE ((sk.no_pertanyaan >= 1) AND (sk.no_pertanyaan <= 3))), 2) AS skor_avg_capaian,
    round(avg(sk.rata_skor) FILTER (WHERE ((sk.no_pertanyaan >= 4) AND (sk.no_pertanyaan <= 8))), 2) AS skor_avg_pelaksanaan,
    round(avg(sk.rata_skor) FILTER (WHERE ((sk.no_pertanyaan >= 9) AND (sk.no_pertanyaan <= 10))), 2) AS skor_avg_sarana,
    round(avg(sk.rata_skor) FILTER (WHERE ((sk.no_pertanyaan >= 11) AND (sk.no_pertanyaan <= 12))), 2) AS skor_avg_perilaku,
    round(avg(sk.rata_skor), 2) AS skor_avg_overall
   FROM (((((((public.kelas k
     JOIN public.mata_kuliah mk ON ((mk.matkul_id = k.matkul_id)))
     JOIN public.program_studi ps ON ((ps.prodi_id = mk.prodi_id)))
     JOIN public.fakultas f ON ((f.fakultas_id = ps.fakultas_id)))
     LEFT JOIN public.pengajar_kelas pk ON ((pk.kelas_id = k.kelas_id)))
     LEFT JOIN public.dosen d ON ((d.dosen_id = pk.dosen_id)))
     LEFT JOIN public.distribusi_nilai dn ON ((dn.kelas_id = k.kelas_id)))
     LEFT JOIN public.skor_kuesioner sk ON ((sk.kelas_id = k.kelas_id)))
  GROUP BY k.kelas_id, k.matkul_id, k.no_kelas, k.semester, k.tahun_ajaran, k.sks, mk.kode_mk, mk.nama_mk, mk.jenis_nilai, ps.prodi_id, ps.kode_prodi, ps.singkatan_prodi, ps.nama_prodi, ps.jenjang, f.fakultas_id, f.kode_fakultas, f.nama_fakultas, k.pct_kehadiran_dosen, k.pct_kehadiran_mahasiswa, k.rata_rata_nilai, k.jumlah_mahasiswa, k.nilai_portofolio, k.is_synthetic
  WITH NO DATA;


ALTER MATERIALIZED VIEW public.mv_kelas OWNER TO itb_admin;

--
-- Name: MATERIALIZED VIEW mv_kelas; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON MATERIALIZED VIEW public.mv_kelas IS '1 row = 1 kelas portofolio, semua dimensi ter-flatten';


--
-- Name: COLUMN mv_kelas.semua_dosen_id; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.mv_kelas.semua_dosen_id IS 'Array UUID dosen pengampu. Filter: WHERE dosen_id_target = ANY(semua_dosen_id). 
 Untuk join ke dosen: LEFT JOIN LATERAL unnest(semua_dosen_id) AS d(id) ON TRUE.';


--
-- Name: mv_statistik_dosen; Type: MATERIALIZED VIEW; Schema: public; Owner: itb_admin
--

CREATE MATERIALIZED VIEW public.mv_statistik_dosen AS
 SELECT d_unnest.dosen_id,
    d.nama_dosen,
    d.kk_id AS kk_id_dosen,
    kk.nama_kk,
    kk.fakultas_id AS fakultas_id_dosen,
    f.semester,
    f.tahun_ajaran,
    count(DISTINCT f.kelas_id) AS jumlah_kelas,
    count(DISTINCT f.matkul_id) AS jumlah_matkul,
    sum(f.sks) AS total_sks_diajar,
    round(avg(f.pct_kehadiran_dosen), 2) AS avg_kehadiran_dosen,
    round(avg(f.pct_kehadiran_mahasiswa), 2) AS avg_kehadiran_mahasiswa,
    round(avg(f.rata_rata_nilai), 3) AS avg_nilai,
    round(avg(f.skor_avg_capaian), 2) AS avg_skor_capaian,
    round(avg(f.skor_avg_pelaksanaan), 2) AS avg_skor_pelaksanaan,
    round(avg(f.skor_avg_sarana), 2) AS avg_skor_sarana,
    round(avg(f.skor_avg_perilaku), 2) AS avg_skor_perilaku,
    round(avg(f.skor_avg_overall), 2) AS avg_skor_overall,
    array_agg(f.kelas_id ORDER BY f.matkul_id, f.no_kelas) AS kelas_ids,
    array_agg(f.kode_mk ORDER BY f.matkul_id, f.no_kelas) AS kode_mk_list
   FROM (((public.mv_kelas f
     JOIN LATERAL unnest(f.semua_dosen_id) d_unnest(dosen_id) ON (true))
     JOIN public.dosen d ON ((d.dosen_id = d_unnest.dosen_id)))
     JOIN public.kelompok_keahlian kk ON ((kk.kk_id = d.kk_id)))
  GROUP BY d_unnest.dosen_id, d.nama_dosen, d.kk_id, kk.nama_kk, kk.fakultas_id, f.semester, f.tahun_ajaran
  WITH NO DATA;


ALTER MATERIALIZED VIEW public.mv_statistik_dosen OWNER TO itb_admin;

--
-- Name: MATERIALIZED VIEW mv_statistik_dosen; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON MATERIALIZED VIEW public.mv_statistik_dosen IS 'Agregasi performa dosen per semester+periode.
 Digunakan oleh View Dosen (overview lintas kelas) dan View Prodi (profil dosen tab).
 REFRESH: jalankan setelah refresh mv_kelas.';


--
-- Name: mv_statistik_prodi; Type: MATERIALIZED VIEW; Schema: public; Owner: itb_admin
--

CREATE MATERIALIZED VIEW public.mv_statistik_prodi AS
 SELECT f.prodi_id,
    f.singkatan_prodi,
    f.nama_prodi,
    f.jenjang,
    f.fakultas_id,
    f.kode_fakultas,
    f.nama_fakultas,
    f.semester,
    f.tahun_ajaran,
    count(DISTINCT f.kelas_id) AS jumlah_kelas,
    count(DISTINCT f.matkul_id) AS jumlah_matkul_aktif,
    count(DISTINCT d_unnest.dosen_id) AS jumlah_dosen_aktif,
    round(avg(f.pct_kehadiran_dosen), 2) AS avg_kehadiran_dosen,
    round(avg(f.pct_kehadiran_mahasiswa), 2) AS avg_kehadiran_mahasiswa,
    round(avg(f.rata_rata_nilai), 3) AS avg_nilai,
    sum(f.dist_jumlah_a) AS total_mhs_a,
    sum(f.dist_jumlah_ab) AS total_mhs_ab,
    sum(f.dist_jumlah_b) AS total_mhs_b,
    sum(f.dist_jumlah_bc) AS total_mhs_bc,
    sum(f.dist_jumlah_c) AS total_mhs_c,
    sum(f.dist_jumlah_d) AS total_mhs_d,
    sum(f.dist_jumlah_e) AS total_mhs_e,
    round(avg(f.dist_pct_lulus), 2) AS avg_pct_lulus,
    round(avg(f.skor_avg_capaian), 2) AS avg_skor_capaian,
    round(avg(f.skor_avg_pelaksanaan), 2) AS avg_skor_pelaksanaan,
    round(avg(f.skor_avg_sarana), 2) AS avg_skor_sarana,
    round(avg(f.skor_avg_perilaku), 2) AS avg_skor_perilaku,
    round(avg(f.skor_avg_overall), 2) AS avg_skor_overall
   FROM (public.mv_kelas f
     LEFT JOIN LATERAL unnest(f.semua_dosen_id) d_unnest(dosen_id) ON (true))
  GROUP BY f.prodi_id, f.singkatan_prodi, f.nama_prodi, f.jenjang, f.fakultas_id, f.kode_fakultas, f.nama_fakultas, f.semester, f.tahun_ajaran
  WITH NO DATA;


ALTER MATERIALIZED VIEW public.mv_statistik_prodi OWNER TO itb_admin;

--
-- Name: MATERIALIZED VIEW mv_statistik_prodi; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON MATERIALIZED VIEW public.mv_statistik_prodi IS 'Agregasi statistik per prodi per semester+periode. 
 Digunakan oleh View Prodi (overview) dan View Fakultas (perbandingan antar prodi).
 REFRESH: jalankan setelah refresh mv_kelas.';


--
-- Name: pengguna; Type: TABLE; Schema: public; Owner: itb_admin
--

CREATE TABLE public.pengguna (
    user_id uuid DEFAULT gen_random_uuid() NOT NULL,
    username character varying(100) NOT NULL,
    email character varying(200) NOT NULL,
    nama_lengkap character varying(200) NOT NULL,
    role public.user_role_enum NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    last_login timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.pengguna OWNER TO itb_admin;

--
-- Name: TABLE pengguna; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON TABLE public.pengguna IS 'Akun pengguna sistem. 1 user = 1 role. Scope data ditentukan oleh user_scope.';


--
-- Name: teks_portofolio; Type: TABLE; Schema: public; Owner: itb_admin
--

CREATE TABLE public.teks_portofolio (
    teks_id uuid DEFAULT gen_random_uuid() NOT NULL,
    kelas_id uuid NOT NULL,
    tipe_konten public.tipe_konten_enum NOT NULL,
    konten text,
    is_embedded boolean DEFAULT false NOT NULL,
    embedded_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.teks_portofolio OWNER TO itb_admin;

--
-- Name: TABLE teks_portofolio; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON TABLE public.teks_portofolio IS 'Semua free-text dari portofolio, max 7 tipe per kelas. konten NULL valid (dosen tidak wajib isi semua field, terutama sistem_penilaian).';


--
-- Name: COLUMN teks_portofolio.tipe_konten; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.teks_portofolio.tipe_konten IS 'Section portfolio: metode_perkuliahan, analisis_capaian_kelas, refleksi_pelaksanaan, usulan_perbaikan_dosen, usulan_perbaikan_itb, tambahan_info_statistik, sistem_penilaian.';


--
-- Name: COLUMN teks_portofolio.embedded_at; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.teks_portofolio.embedded_at IS 'NULL jika belum pernah di-embed. Diisi pipeline setelah sukses upsert ke vector store.';


--
-- Name: user_scope; Type: TABLE; Schema: public; Owner: itb_admin
--

CREATE TABLE public.user_scope (
    scope_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    dosen_id uuid,
    kk_id uuid,
    prodi_id uuid,
    fakultas_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.user_scope OWNER TO itb_admin;

--
-- Name: TABLE user_scope; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON TABLE public.user_scope IS 'Scope akses data per user. Satu user = satu row. Kolom dosen_id/prodi_id/fakultas_id menentukan batas data yang bisa dilihat. Validasi "setidaknya satu diisi sesuai role" dilakukan di application layer (bukan CHECK constraint — subquery di CHECK anti-pattern di PostgreSQL).';


--
-- Name: COLUMN user_scope.dosen_id; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.user_scope.dosen_id IS 'Diisi untuk role=dosen. User hanya lihat kelas yang ia ampu via pengajar_kelas.';


--
-- Name: COLUMN user_scope.prodi_id; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.user_scope.prodi_id IS 'Diisi untuk role=kaprodi/jajaran_prodi. Akses semua kelas di prodi ini.';


--
-- Name: COLUMN user_scope.fakultas_id; Type: COMMENT; Schema: public; Owner: itb_admin
--

COMMENT ON COLUMN public.user_scope.fakultas_id IS 'Diisi untuk role=dekan/jajaran_dekanat. Akses semua kelas di semua prodi fakultas ini.';


--
-- Name: vector_chunks; Type: TABLE; Schema: public; Owner: itb_admin
--

CREATE TABLE public.vector_chunks (
    chunk_id uuid DEFAULT gen_random_uuid() NOT NULL,
    source_type character varying(20) NOT NULL,
    source_id uuid NOT NULL,
    kelas_id uuid NOT NULL,
    tipe_konten public.tipe_konten_enum,
    chunk_index smallint DEFAULT 0 NOT NULL,
    chunk_text text NOT NULL,
    embedding public.vector(1536),
    model_used character varying(100),
    embedded_at timestamp with time zone,
    kode_mk character varying(20) NOT NULL,
    kode_prodi character varying(10) NOT NULL,
    kode_fakultas character varying(20) NOT NULL,
    no_kelas character varying(5) NOT NULL,
    semester smallint NOT NULL,
    tahun_ajaran character varying(9) NOT NULL,
    nama_mk character varying(200) NOT NULL,
    nama_prodi character varying(150) NOT NULL,
    nama_fakultas character varying(100) NOT NULL,
    jenjang character varying(10) NOT NULL,
    semua_dosen_id uuid[] NOT NULL,
    semua_dosen_nama text[] DEFAULT '{}'::text[] NOT NULL,
    kelas_label text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT vector_chunks_jenjang_check CHECK (((jenjang)::text = ANY ((ARRAY['S1'::character varying, 'S2'::character varying, 'S3'::character varying, 'Profesi'::character varying])::text[]))),
    CONSTRAINT vector_chunks_source_type_check CHECK (((source_type)::text = ANY ((ARRAY['teks_portofolio'::character varying, 'komentar_mahasiswa'::character varying])::text[])))
);


ALTER TABLE public.vector_chunks OWNER TO itb_admin;

--
-- Name: distribusi_nilai distribusi_nilai_pkey; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.distribusi_nilai
    ADD CONSTRAINT distribusi_nilai_pkey PRIMARY KEY (distribusi_id);


--
-- Name: dosen dosen_pkey; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.dosen
    ADD CONSTRAINT dosen_pkey PRIMARY KEY (dosen_id);


--
-- Name: fakultas fakultas_kode_fakultas_key; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.fakultas
    ADD CONSTRAINT fakultas_kode_fakultas_key UNIQUE (kode_fakultas);


--
-- Name: fakultas fakultas_pkey; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.fakultas
    ADD CONSTRAINT fakultas_pkey PRIMARY KEY (fakultas_id);


--
-- Name: ingestion_log ingestion_log_pkey; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.ingestion_log
    ADD CONSTRAINT ingestion_log_pkey PRIMARY KEY (log_id);


--
-- Name: kelas kelas_pkey; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.kelas
    ADD CONSTRAINT kelas_pkey PRIMARY KEY (kelas_id);


--
-- Name: kelompok_keahlian kelompok_keahlian_pkey; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.kelompok_keahlian
    ADD CONSTRAINT kelompok_keahlian_pkey PRIMARY KEY (kk_id);


--
-- Name: komentar_mahasiswa komentar_mahasiswa_pkey; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.komentar_mahasiswa
    ADD CONSTRAINT komentar_mahasiswa_pkey PRIMARY KEY (komentar_id);


--
-- Name: llm_analysis_cache llm_analysis_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.llm_analysis_cache
    ADD CONSTRAINT llm_analysis_cache_pkey PRIMARY KEY (cache_id);


--
-- Name: mata_kuliah mata_kuliah_pkey; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.mata_kuliah
    ADD CONSTRAINT mata_kuliah_pkey PRIMARY KEY (matkul_id);


--
-- Name: pengajar_kelas pengajar_kelas_pkey; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.pengajar_kelas
    ADD CONSTRAINT pengajar_kelas_pkey PRIMARY KEY (kelas_id, dosen_id);


--
-- Name: pengguna pengguna_email_key; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.pengguna
    ADD CONSTRAINT pengguna_email_key UNIQUE (email);


--
-- Name: pengguna pengguna_pkey; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.pengguna
    ADD CONSTRAINT pengguna_pkey PRIMARY KEY (user_id);


--
-- Name: pengguna pengguna_username_key; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.pengguna
    ADD CONSTRAINT pengguna_username_key UNIQUE (username);


--
-- Name: program_studi program_studi_kode_prodi_key; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.program_studi
    ADD CONSTRAINT program_studi_kode_prodi_key UNIQUE (kode_prodi);


--
-- Name: program_studi program_studi_pkey; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.program_studi
    ADD CONSTRAINT program_studi_pkey PRIMARY KEY (prodi_id);


--
-- Name: skor_kuesioner skor_kuesioner_pkey; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.skor_kuesioner
    ADD CONSTRAINT skor_kuesioner_pkey PRIMARY KEY (skor_id);


--
-- Name: teks_portofolio teks_portofolio_pkey; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.teks_portofolio
    ADD CONSTRAINT teks_portofolio_pkey PRIMARY KEY (teks_id);


--
-- Name: vector_chunks uq_chunk_source_idx; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.vector_chunks
    ADD CONSTRAINT uq_chunk_source_idx UNIQUE (source_id, chunk_index);


--
-- Name: distribusi_nilai uq_distribusi_kelas_grade; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.distribusi_nilai
    ADD CONSTRAINT uq_distribusi_kelas_grade UNIQUE (kelas_id, grade);


--
-- Name: kelas uq_kelas_periode; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.kelas
    ADD CONSTRAINT uq_kelas_periode UNIQUE (matkul_id, no_kelas, semester, tahun_ajaran);


--
-- Name: mata_kuliah uq_kode_mk_prodi; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.mata_kuliah
    ADD CONSTRAINT uq_kode_mk_prodi UNIQUE (kode_mk, prodi_id);


--
-- Name: komentar_mahasiswa uq_komentar_kelas_no; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.komentar_mahasiswa
    ADD CONSTRAINT uq_komentar_kelas_no UNIQUE (kelas_id, no_komentar);


--
-- Name: skor_kuesioner uq_skor_kelas_pertanyaan; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.skor_kuesioner
    ADD CONSTRAINT uq_skor_kelas_pertanyaan UNIQUE (kelas_id, no_pertanyaan);


--
-- Name: teks_portofolio uq_teks_kelas_tipe; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.teks_portofolio
    ADD CONSTRAINT uq_teks_kelas_tipe UNIQUE (kelas_id, tipe_konten);


--
-- Name: user_scope user_scope_pkey; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.user_scope
    ADD CONSTRAINT user_scope_pkey PRIMARY KEY (scope_id);


--
-- Name: user_scope user_scope_user_id_key; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.user_scope
    ADD CONSTRAINT user_scope_user_id_key UNIQUE (user_id);


--
-- Name: vector_chunks vector_chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.vector_chunks
    ADD CONSTRAINT vector_chunks_pkey PRIMARY KEY (chunk_id);


--
-- Name: idx_cache_expires; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_cache_expires ON public.llm_analysis_cache USING btree (expires_at) WHERE (expires_at IS NOT NULL);


--
-- Name: idx_cache_kelas_ids; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_cache_kelas_ids ON public.llm_analysis_cache USING gin (kelas_ids);


--
-- Name: idx_distribusi_kelas; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_distribusi_kelas ON public.distribusi_nilai USING btree (kelas_id);


--
-- Name: idx_dosen_kk; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_dosen_kk ON public.dosen USING btree (kk_id);


--
-- Name: idx_ingestion_status; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_ingestion_status ON public.ingestion_log USING btree (status, started_at DESC);


--
-- Name: idx_kelas_matkul; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_kelas_matkul ON public.kelas USING btree (matkul_id);


--
-- Name: idx_kelas_matkul_sem; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_kelas_matkul_sem ON public.kelas USING btree (matkul_id, tahun_ajaran, semester);


--
-- Name: idx_kelas_tahun_sem; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_kelas_tahun_sem ON public.kelas USING btree (tahun_ajaran, semester);


--
-- Name: idx_kk_fakultas; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_kk_fakultas ON public.kelompok_keahlian USING btree (fakultas_id);


--
-- Name: idx_komentar_kelas; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_komentar_kelas ON public.komentar_mahasiswa USING btree (kelas_id);


--
-- Name: idx_komentar_unembedded; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_komentar_unembedded ON public.komentar_mahasiswa USING btree (is_embedded) WHERE (is_embedded = false);


--
-- Name: idx_matkul_prodi; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_matkul_prodi ON public.mata_kuliah USING btree (prodi_id);


--
-- Name: idx_mv_dosen_arr; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_mv_dosen_arr ON public.mv_kelas USING gin (semua_dosen_id);


--
-- Name: idx_mv_dosen_fak; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_mv_dosen_fak ON public.mv_statistik_dosen USING btree (fakultas_id_dosen, semester, tahun_ajaran);


--
-- Name: idx_mv_dosen_kk; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_mv_dosen_kk ON public.mv_statistik_dosen USING btree (kk_id_dosen, semester, tahun_ajaran);


--
-- Name: idx_mv_dosen_pk; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE UNIQUE INDEX idx_mv_dosen_pk ON public.mv_statistik_dosen USING btree (dosen_id, semester, tahun_ajaran);


--
-- Name: idx_mv_fak_sem; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_mv_fak_sem ON public.mv_kelas USING btree (fakultas_id, semester, tahun_ajaran);


--
-- Name: idx_mv_matkul_sem; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_mv_matkul_sem ON public.mv_kelas USING btree (kode_mk, semester, tahun_ajaran);


--
-- Name: idx_mv_pk; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE UNIQUE INDEX idx_mv_pk ON public.mv_kelas USING btree (kelas_id);


--
-- Name: idx_mv_prodi_fak; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_mv_prodi_fak ON public.mv_statistik_prodi USING btree (fakultas_id, semester, tahun_ajaran);


--
-- Name: idx_mv_prodi_pk; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE UNIQUE INDEX idx_mv_prodi_pk ON public.mv_statistik_prodi USING btree (prodi_id, semester, tahun_ajaran);


--
-- Name: idx_mv_prodi_sem; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_mv_prodi_sem ON public.mv_kelas USING btree (prodi_id, semester, tahun_ajaran);


--
-- Name: idx_pengajar_dosen; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_pengajar_dosen ON public.pengajar_kelas USING btree (dosen_id);


--
-- Name: idx_pengguna_role; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_pengguna_role ON public.pengguna USING btree (role);


--
-- Name: idx_prodi_fakultas; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_prodi_fakultas ON public.program_studi USING btree (fakultas_id);


--
-- Name: idx_scope_dosen; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_scope_dosen ON public.user_scope USING btree (dosen_id) WHERE (dosen_id IS NOT NULL);


--
-- Name: idx_scope_fakultas; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_scope_fakultas ON public.user_scope USING btree (fakultas_id) WHERE (fakultas_id IS NOT NULL);


--
-- Name: idx_scope_prodi; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_scope_prodi ON public.user_scope USING btree (prodi_id) WHERE (prodi_id IS NOT NULL);


--
-- Name: idx_skor_kelas; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_skor_kelas ON public.skor_kuesioner USING btree (kelas_id);


--
-- Name: idx_teks_kelas; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_teks_kelas ON public.teks_portofolio USING btree (kelas_id);


--
-- Name: idx_teks_unembedded; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_teks_unembedded ON public.teks_portofolio USING btree (is_embedded) WHERE (is_embedded = false);


--
-- Name: idx_vc_dosen; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_vc_dosen ON public.vector_chunks USING gin (semua_dosen_id);


--
-- Name: idx_vc_kelas_id; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_vc_kelas_id ON public.vector_chunks USING btree (kelas_id);


--
-- Name: idx_vc_kode_fak; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_vc_kode_fak ON public.vector_chunks USING btree (kode_fakultas, semester, tahun_ajaran) WHERE (embedding IS NOT NULL);


--
-- Name: idx_vc_kode_mk; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_vc_kode_mk ON public.vector_chunks USING btree (kode_mk, semester, tahun_ajaran) WHERE (embedding IS NOT NULL);


--
-- Name: idx_vc_kode_prodi; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_vc_kode_prodi ON public.vector_chunks USING btree (kode_prodi, semester, tahun_ajaran) WHERE (embedding IS NOT NULL);


--
-- Name: idx_vc_source; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_vc_source ON public.vector_chunks USING btree (source_type, source_id);


--
-- Name: idx_vc_tipe; Type: INDEX; Schema: public; Owner: itb_admin
--

CREATE INDEX idx_vc_tipe ON public.vector_chunks USING btree (tipe_konten) WHERE ((tipe_konten IS NOT NULL) AND (embedding IS NOT NULL));


--
-- Name: komentar_mahasiswa trg_komentar_reset_embedding; Type: TRIGGER; Schema: public; Owner: itb_admin
--

CREATE TRIGGER trg_komentar_reset_embedding BEFORE UPDATE ON public.komentar_mahasiswa FOR EACH ROW EXECUTE FUNCTION public.fn_komentar_reset_embedding();


--
-- Name: teks_portofolio trg_teks_reset_embedding; Type: TRIGGER; Schema: public; Owner: itb_admin
--

CREATE TRIGGER trg_teks_reset_embedding BEFORE UPDATE ON public.teks_portofolio FOR EACH ROW EXECUTE FUNCTION public.fn_teks_reset_embedding();


--
-- Name: distribusi_nilai distribusi_nilai_kelas_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.distribusi_nilai
    ADD CONSTRAINT distribusi_nilai_kelas_id_fkey FOREIGN KEY (kelas_id) REFERENCES public.kelas(kelas_id) ON DELETE CASCADE;


--
-- Name: dosen dosen_kk_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.dosen
    ADD CONSTRAINT dosen_kk_id_fkey FOREIGN KEY (kk_id) REFERENCES public.kelompok_keahlian(kk_id) ON UPDATE CASCADE;


--
-- Name: fakultas fakultas_parent_fakultas_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.fakultas
    ADD CONSTRAINT fakultas_parent_fakultas_id_fkey FOREIGN KEY (parent_fakultas_id) REFERENCES public.fakultas(fakultas_id);


--
-- Name: ingestion_log ingestion_log_kelas_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.ingestion_log
    ADD CONSTRAINT ingestion_log_kelas_id_fkey FOREIGN KEY (kelas_id) REFERENCES public.kelas(kelas_id) ON DELETE SET NULL;


--
-- Name: kelas kelas_matkul_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.kelas
    ADD CONSTRAINT kelas_matkul_id_fkey FOREIGN KEY (matkul_id) REFERENCES public.mata_kuliah(matkul_id) ON UPDATE CASCADE;


--
-- Name: kelompok_keahlian kelompok_keahlian_fakultas_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.kelompok_keahlian
    ADD CONSTRAINT kelompok_keahlian_fakultas_id_fkey FOREIGN KEY (fakultas_id) REFERENCES public.fakultas(fakultas_id) ON UPDATE CASCADE;


--
-- Name: komentar_mahasiswa komentar_mahasiswa_kelas_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.komentar_mahasiswa
    ADD CONSTRAINT komentar_mahasiswa_kelas_id_fkey FOREIGN KEY (kelas_id) REFERENCES public.kelas(kelas_id) ON DELETE CASCADE;


--
-- Name: mata_kuliah mata_kuliah_prodi_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.mata_kuliah
    ADD CONSTRAINT mata_kuliah_prodi_id_fkey FOREIGN KEY (prodi_id) REFERENCES public.program_studi(prodi_id) ON UPDATE CASCADE;


--
-- Name: pengajar_kelas pengajar_kelas_dosen_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.pengajar_kelas
    ADD CONSTRAINT pengajar_kelas_dosen_id_fkey FOREIGN KEY (dosen_id) REFERENCES public.dosen(dosen_id);


--
-- Name: pengajar_kelas pengajar_kelas_kelas_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.pengajar_kelas
    ADD CONSTRAINT pengajar_kelas_kelas_id_fkey FOREIGN KEY (kelas_id) REFERENCES public.kelas(kelas_id) ON DELETE CASCADE;


--
-- Name: program_studi program_studi_fakultas_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.program_studi
    ADD CONSTRAINT program_studi_fakultas_id_fkey FOREIGN KEY (fakultas_id) REFERENCES public.fakultas(fakultas_id) ON UPDATE CASCADE;


--
-- Name: skor_kuesioner skor_kuesioner_kelas_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.skor_kuesioner
    ADD CONSTRAINT skor_kuesioner_kelas_id_fkey FOREIGN KEY (kelas_id) REFERENCES public.kelas(kelas_id) ON DELETE CASCADE;


--
-- Name: teks_portofolio teks_portofolio_kelas_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.teks_portofolio
    ADD CONSTRAINT teks_portofolio_kelas_id_fkey FOREIGN KEY (kelas_id) REFERENCES public.kelas(kelas_id) ON DELETE CASCADE;


--
-- Name: user_scope user_scope_dosen_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.user_scope
    ADD CONSTRAINT user_scope_dosen_id_fkey FOREIGN KEY (dosen_id) REFERENCES public.dosen(dosen_id);


--
-- Name: user_scope user_scope_fakultas_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.user_scope
    ADD CONSTRAINT user_scope_fakultas_id_fkey FOREIGN KEY (fakultas_id) REFERENCES public.fakultas(fakultas_id) ON UPDATE CASCADE;


--
-- Name: user_scope user_scope_kk_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.user_scope
    ADD CONSTRAINT user_scope_kk_id_fkey FOREIGN KEY (kk_id) REFERENCES public.kelompok_keahlian(kk_id);


--
-- Name: user_scope user_scope_prodi_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.user_scope
    ADD CONSTRAINT user_scope_prodi_id_fkey FOREIGN KEY (prodi_id) REFERENCES public.program_studi(prodi_id) ON UPDATE CASCADE;


--
-- Name: user_scope user_scope_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.user_scope
    ADD CONSTRAINT user_scope_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.pengguna(user_id) ON DELETE CASCADE;


--
-- Name: vector_chunks vector_chunks_kelas_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: itb_admin
--

ALTER TABLE ONLY public.vector_chunks
    ADD CONSTRAINT vector_chunks_kelas_id_fkey FOREIGN KEY (kelas_id) REFERENCES public.kelas(kelas_id) ON DELETE CASCADE;


--
-- Name: kelas; Type: ROW SECURITY; Schema: public; Owner: itb_admin
--

ALTER TABLE public.kelas ENABLE ROW LEVEL SECURITY;

--
-- Name: komentar_mahasiswa; Type: ROW SECURITY; Schema: public; Owner: itb_admin
--

ALTER TABLE public.komentar_mahasiswa ENABLE ROW LEVEL SECURITY;

--
-- Name: kelas rls_kelas_all_roles; Type: POLICY; Schema: public; Owner: itb_admin
--

CREATE POLICY rls_kelas_all_roles ON public.kelas FOR SELECT USING (((EXISTS ( SELECT 1
   FROM public.pengguna p
  WHERE ((p.user_id = (current_setting('app.user_id'::text, true))::uuid) AND (p.role = ANY (ARRAY['admin'::public.user_role_enum, 'wram'::public.user_role_enum]))))) OR (EXISTS ( SELECT 1
   FROM (public.pengajar_kelas pk
     JOIN public.user_scope us ON ((us.dosen_id = pk.dosen_id)))
  WHERE ((pk.kelas_id = kelas.kelas_id) AND (us.user_id = (current_setting('app.user_id'::text, true))::uuid)))) OR (EXISTS ( SELECT 1
   FROM (public.mata_kuliah mk
     JOIN public.user_scope us ON ((us.prodi_id = mk.prodi_id)))
  WHERE ((mk.matkul_id = kelas.matkul_id) AND (us.user_id = (current_setting('app.user_id'::text, true))::uuid)))) OR (EXISTS ( SELECT 1
   FROM ((public.mata_kuliah mk
     JOIN public.program_studi ps ON ((ps.prodi_id = mk.prodi_id)))
     JOIN public.user_scope us ON ((us.fakultas_id = ps.fakultas_id)))
  WHERE ((mk.matkul_id = kelas.matkul_id) AND (us.user_id = (current_setting('app.user_id'::text, true))::uuid))))));


--
-- Name: komentar_mahasiswa rls_komentar; Type: POLICY; Schema: public; Owner: itb_admin
--

CREATE POLICY rls_komentar ON public.komentar_mahasiswa FOR SELECT USING (public.user_can_see_kelas(kelas_id));


--
-- Name: teks_portofolio rls_teks; Type: POLICY; Schema: public; Owner: itb_admin
--

CREATE POLICY rls_teks ON public.teks_portofolio FOR SELECT USING (public.user_can_see_kelas(kelas_id));


--
-- Name: vector_chunks rls_vector_chunks; Type: POLICY; Schema: public; Owner: itb_admin
--

CREATE POLICY rls_vector_chunks ON public.vector_chunks FOR SELECT USING (public.user_can_see_kelas(kelas_id));


--
-- Name: teks_portofolio; Type: ROW SECURITY; Schema: public; Owner: itb_admin
--

ALTER TABLE public.teks_portofolio ENABLE ROW LEVEL SECURITY;

--
-- Name: vector_chunks; Type: ROW SECURITY; Schema: public; Owner: itb_admin
--

ALTER TABLE public.vector_chunks ENABLE ROW LEVEL SECURITY;

--
-- PostgreSQL database dump complete
--

\unrestrict TLgEkNtEeIJ2d9TIcgWiLKl0OucdSEByRW9ZQ3MDyMIpLmOWTD9VWIbAYfxddfP

