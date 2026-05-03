# Schema Reference for SQL Agent

## Query Type Routing

**Global/Institutional Fact Queries** (e.g., "berapa banyak fakultas di ITB?", "ada berapa prodi?", "siapa saja dosen di IT?") MUST use the LOOKUP TABLES below — NOT the materialized views.
- Lookup tables have NO row-level security and return institution-wide data.
- Use `{SCOPE_FILTER}` as `WHERE TRUE` for lookup table queries (no user restriction needed).

**Portfolio Analytics Queries** (scores, evaluations, classes) MUST use the Materialized Views.

---

## Lookup / Reference Tables (Global, No RLS)

### fakultas (list of all faculties — no scope filter needed)
```
fakultas_id UUID PK
kode_fakultas VARCHAR(20) UNIQUE  -- e.g. "STEI", "FITB", "SBM"
nama_fakultas VARCHAR(100)
is_active BOOLEAN
```
Example: `SELECT COUNT(*) FROM fakultas WHERE is_active = TRUE AND {SCOPE_FILTER}` → total faculties at ITB

### program_studi (list of all study programs — no scope filter needed)
```
prodi_id UUID PK
fakultas_id UUID FK→fakultas
kode_prodi VARCHAR(10) UNIQUE
singkatan_prodi VARCHAR(10)  -- e.g. "IF", "STI"
nama_prodi VARCHAR(150)
jenjang VARCHAR(10)  -- S1|S2|S3|Profesi
is_active BOOLEAN
```

### dosen (list of all lecturers — no scope filter needed)
```
dosen_id UUID PK
kk_id UUID FK→kelompok_keahlian
nama_dosen VARCHAR(150)
is_active BOOLEAN
```
⚠️ IMPORTANT: dosen does NOT have a fakultas_id column!
To filter dosen by faculty, you MUST JOIN through kelompok_keahlian:
```sql
SELECT d.nama_dosen FROM dosen d
JOIN kelompok_keahlian kk ON kk.kk_id = d.kk_id
JOIN fakultas f ON f.fakultas_id = kk.fakultas_id
WHERE f.kode_fakultas = 'STEI' AND d.is_active = TRUE AND {SCOPE_FILTER}
ORDER BY d.nama_dosen LIMIT 5;
```

### kelompok_keahlian (research groups)
```
kk_id UUID PK
fakultas_id UUID FK→fakultas
nama_kk VARCHAR(200)
```

### mata_kuliah (course catalog — no scope filter needed)
```
matkul_id UUID PK
prodi_id UUID FK→program_studi
kode_mk VARCHAR(20)
nama_mk VARCHAR(200)
nama_mk_en VARCHAR(200)
jenis_nilai VARCHAR(10)  -- ABCDE | Pass/Fail
is_active BOOLEAN
```

---

## Primary Query Surface — USE THESE FIRST FOR PORTFOLIO ANALYTICS

### mv_kelas (materialized view — use this for per-class queries)
1 row per kelas (portfolio document). Everything denormalized.

```
kelas_id UUID (PK)
matkul_id UUID
kode_mk VARCHAR(20)        -- e.g. "IF2210"
nama_mk VARCHAR(200)
-- NOTE: nama_mk_en is NOT in mv_kelas — use mata_kuliah base table if needed
jenis_nilai VARCHAR(10)    -- ABCDE | Pass/Fail
no_kelas VARCHAR(5)        -- "1", "2", "K1"
semester SMALLINT           -- 1=Ganjil, 2=Genap, 3=SP
tahun_ajaran VARCHAR(9)    -- "2024/2025"

prodi_id UUID
kode_prodi VARCHAR(10)     -- e.g. "135"
singkatan_prodi VARCHAR(10) -- e.g. "IF"
nama_prodi VARCHAR(150)
jenjang VARCHAR(10)        -- S1|S2|S3|Profesi

fakultas_id UUID
kode_fakultas VARCHAR(20)  -- e.g. "STEI"
nama_fakultas VARCHAR(100)

semua_dosen_id UUID[]      -- ARRAY of dosen UUIDs
semua_dosen_nama TEXT[]    -- matching ARRAY of dosen names

-- Class statistics
pct_kehadiran_dosen NUMERIC(5,2)      -- 0-100
pct_kehadiran_mahasiswa NUMERIC(5,2)  -- 0-100
rata_rata_nilai NUMERIC(4,2)          -- 0.00-4.00
jumlah_mahasiswa SMALLINT
nilai_portofolio SMALLINT             -- 1-4, nullable

-- Grade distribution (flattened from distribusi_nilai)
dist_jumlah_A SMALLINT    dist_pct_A NUMERIC(5,2)
dist_jumlah_AB SMALLINT   dist_pct_AB NUMERIC(5,2)
dist_jumlah_B SMALLINT    dist_pct_B NUMERIC(5,2)
dist_jumlah_BC SMALLINT   dist_pct_BC NUMERIC(5,2)
dist_jumlah_C SMALLINT    dist_pct_C NUMERIC(5,2)
dist_jumlah_D SMALLINT    dist_pct_D NUMERIC(5,2)
dist_jumlah_E SMALLINT    dist_pct_E NUMERIC(5,2)
dist_jumlah_pass SMALLINT dist_pct_pass NUMERIC(5,2)
dist_jumlah_fail SMALLINT dist_pct_fail NUMERIC(5,2)
dist_pct_lulus NUMERIC(5,2) -- computed: ≥C for ABCDE, Pass for Pass/Fail

-- Questionnaire scores (Likert 1.00-4.00)
skor_q1..skor_q12 NUMERIC(4,2)
skor_avg_capaian NUMERIC(4,2)     -- avg(Q1-Q3): capaian pembelajaran
skor_avg_pelaksanaan NUMERIC(4,2) -- avg(Q4-Q8): pelaksanaan perkuliahan
skor_avg_sarana NUMERIC(4,2)      -- avg(Q9-Q10): sarana prasarana
skor_avg_perilaku NUMERIC(4,2)    -- avg(Q11-Q12): perilaku mahasiswa
skor_avg_overall NUMERIC(4,2)     -- avg(Q1-Q12)
```

HINTS:
- Filter by dosen: `WHERE '<dosen_uuid_from_entities>'::uuid = ANY(semua_dosen_id)`
- Filter by matkul name: `WHERE nama_mk ILIKE '%basis data%'`
- For bilingual search, join mata_kuliah: `JOIN mata_kuliah mk ON mk.matkul_id = mv.matkul_id WHERE (mk.nama_mk || ' ' || COALESCE(mk.nama_mk_en, '')) ILIKE '%%keyword%%'`
- semester: 1=Ganjil, 2=Genap, 3=Pendek
- For ABCDE grading: use dist_jumlah_A..dist_jumlah_E columns
- For Pass/Fail grading: use dist_jumlah_pass/dist_jumlah_fail columns
- dist_pct_lulus works for both grading systems
- Always use COALESCE for nullable score columns

### mv_statistik_prodi (aggregated per prodi per semester)
```
prodi_id UUID (PK with semester, tahun_ajaran)
singkatan_prodi VARCHAR(10)
nama_prodi VARCHAR(150)
jenjang VARCHAR(10)
fakultas_id UUID
kode_fakultas VARCHAR(20)
nama_fakultas VARCHAR(100)
semester SMALLINT
tahun_ajaran VARCHAR(9)

jumlah_kelas BIGINT
jumlah_matkul_aktif BIGINT
jumlah_dosen_aktif BIGINT
avg_kehadiran_dosen NUMERIC(5,2)
avg_kehadiran_mahasiswa NUMERIC(5,2)
avg_nilai NUMERIC(4,3)
total_mhs_A..total_mhs_E BIGINT
avg_pct_lulus NUMERIC(5,2)
avg_skor_capaian NUMERIC(4,2)
avg_skor_pelaksanaan NUMERIC(4,2)
avg_skor_sarana NUMERIC(4,2)
avg_skor_perilaku NUMERIC(4,2)
avg_skor_overall NUMERIC(4,2)
```

### mv_statistik_dosen (aggregated per dosen per semester)
```
dosen_id UUID (PK with semester, tahun_ajaran)
nama_dosen VARCHAR(150)
kk_id_dosen UUID
nama_kk VARCHAR(200)
fakultas_id_dosen UUID
semester SMALLINT
tahun_ajaran VARCHAR(9)

jumlah_kelas BIGINT
jumlah_matkul BIGINT
total_sks_diajar BIGINT
avg_kehadiran_dosen NUMERIC(5,2)
avg_kehadiran_mahasiswa NUMERIC(5,2)
avg_nilai NUMERIC(4,3)
avg_skor_capaian NUMERIC(4,2)
avg_skor_pelaksanaan NUMERIC(4,2)
avg_skor_sarana NUMERIC(4,2)
avg_skor_perilaku NUMERIC(4,2)
avg_skor_overall NUMERIC(4,2)
kelas_ids UUID[]
kode_mk_list VARCHAR(20)[]
```

## Text Tables (for portfolio text content — use for text_lookup/RAG)

### teks_portofolio (1 row per content section per kelas)
```
teks_id UUID PK
kelas_id UUID FK→kelas
tipe_konten ENUM: metode_perkuliahan | sistem_penilaian | analisis_capaian_kelas |
                  tambahan_info_statistik | refleksi_pelaksanaan |
                  usulan_perbaikan_dosen | usulan_perbaikan_itb
konten TEXT (nullable)
```

### komentar_mahasiswa (1 row per student comment)
```
komentar_id UUID PK
kelas_id UUID FK→kelas
no_komentar SMALLINT
teks_komentar TEXT NOT NULL
```

## Common SQL Patterns

### Institutional fact queries (use lookup tables, scope filter = TRUE)
```sql
-- Total faculties at ITB
SELECT COUNT(*) AS total_fakultas FROM fakultas WHERE is_active = TRUE AND {SCOPE_FILTER};

-- List all faculties
SELECT kode_fakultas, nama_fakultas FROM fakultas WHERE is_active = TRUE AND {SCOPE_FILTER};

-- Total active prodi
SELECT COUNT(*) AS total_prodi FROM program_studi WHERE is_active = TRUE AND {SCOPE_FILTER};

-- Total active dosen
SELECT COUNT(*) AS total_dosen FROM dosen WHERE is_active = TRUE AND {SCOPE_FILTER};

-- Dosen in a specific faculty
SELECT d.nama_dosen FROM dosen d
JOIN kelompok_keahlian kk ON kk.kk_id = d.kk_id
JOIN fakultas f ON f.fakultas_id = kk.fakultas_id
WHERE f.kode_fakultas = 'STEI' AND d.is_active = TRUE AND {SCOPE_FILTER}
ORDER BY d.nama_dosen;

-- Compare total dosen between faculties
SELECT f.kode_fakultas, COUNT(d.dosen_id) AS total_dosen
FROM dosen d
JOIN kelompok_keahlian kk ON kk.kk_id = d.kk_id
JOIN fakultas f ON f.fakultas_id = kk.fakultas_id
WHERE f.kode_fakultas IN ('FTTM', 'STEI') AND d.is_active = TRUE AND {SCOPE_FILTER}
GROUP BY f.kode_fakultas;
```


```sql
-- All classes for a specific matkul in a semester
SELECT * FROM mv_kelas
WHERE kode_mk = 'IF2210' AND semester = 1 AND tahun_ajaran = '2024/2025'
  AND {SCOPE_FILTER}
ORDER BY no_kelas;

-- Dosen's own classes
SELECT kode_mk, no_kelas, rata_rata_nilai, skor_avg_overall
FROM mv_kelas
WHERE '<dosen_uuid>'::uuid = ANY(semua_dosen_id)
  AND tahun_ajaran = '2024/2025' AND {SCOPE_FILTER}
ORDER BY kode_mk, no_kelas;

-- Compare prodi statistics
SELECT singkatan_prodi, avg_nilai, avg_skor_overall, avg_kehadiran_dosen
FROM mv_statistik_prodi
WHERE fakultas_id = 'xxx'::uuid
  AND semester = 1 AND tahun_ajaran = '2024/2025'
ORDER BY avg_skor_overall DESC;

-- Grade distribution for a class
SELECT kode_mk, no_kelas,
       dist_jumlah_A, dist_jumlah_AB, dist_jumlah_B, dist_jumlah_BC,
       dist_jumlah_C, dist_jumlah_D, dist_jumlah_E, dist_pct_lulus
FROM mv_kelas
WHERE kode_mk = 'IF2210' AND {SCOPE_FILTER};

-- Dosen performance trend
SELECT semester, tahun_ajaran, avg_skor_overall, avg_nilai
FROM mv_statistik_dosen
WHERE dosen_id = 'xxx'::uuid
ORDER BY tahun_ajaran, semester;
```
