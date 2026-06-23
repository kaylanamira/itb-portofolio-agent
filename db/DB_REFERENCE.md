# Database Reference — ITB Academic Portfolio Analytics
**Database:** `dev_six` (PostgreSQL, accessed via SSH tunnel)
**Last updated from:** `dev_six_schema.sql` + `mv_dokumentasi.md` + `schema_mv_portofolio_kuesioner.sql` + `schema_ulasan_wisudawan.sql` + `schema_mv_ulasan_wisudawan.sql` (2026-06-12)
**Scope:** This document covers every schema in `dev_six`. Schemas are classified by relevance to the portfolio analytics system.

---

## Schema Classification Index

| Schema | Relevance | Purpose |
|--------|-----------|---------|
| `analitik` | **YES** | Agent-facing analytics layer. 13 views (5 public + 8 row/column-secured via `SECURITY DEFINER`). See "Analytics Views" section. |
| `analitik_mv` | **NO (agent must not query)** | Raw materialized views backing `analitik.*`. Not RLS-enforced — owned by the application DB role, so GRANT/REVOKE does not block direct access. |
| `utama` | **YES** | Master data: dosen, mahasiswa, mata kuliah, prodi, fakultas, KK |
| `kelas` | **YES** | Class sessions, instructors, attendance meetings |
| `evaluasi` | **YES** | Questionnaire scores, portfolio free-text, class/dosen scores |
| `mahasiswa` | **PARTIAL YES** | Student enrollment, grades, active status, IP |
| `users` | **YES** | User accounts, SSO mapping, multi-role assignments |
| `kur24` | **YES** | New 2024 curriculum — CPL, CPMK, paket |
| `referensi` | **MAYBE** | kegiatan_kelas, jalur_seleksi, mata_kuliah_kategori (for mata_kuliah), ruang (really questionable) |
| `kurikulum` | **MAYBE** | Curriculum structure, syllabus, learning outcomes |
| `ivc` | **NO** | International Virtual Course activities |
| `kemahasiswaan` | **NO** | Student/dosen activities, competitions, achievements |
| `jadwal` | **NO** | db is empty |
| `presensi` | **NO** | Granular per-meeting attendance with timestamps |
| `wisuda` | **PARTIAL YES** | Graduation data — `periode_ijazah` and `periode_seremoni` are used by `analitik.v_wisudawan_*` for seremoni mapping. Direct queries out of scope per PRD. |
| `keuangan` | **NO** | Tuition billing, payment, UKT |
| `bpp` | **NO** | BPP tuition components |
| `pmb` | **NO** | Admissions (new student intake) |
| `penjurusan` | **NO** | Major placement for TPB students |
| `mobile` | **NO** | Laravel app for ITB mobile — separate system |
| `web_academic` | **NO** | ITB academic website CMS |
| `ms365` | **NO** | Microsoft Teams/365 integration |
| `ktm` | **NO** | Student ID card (KTM) data |
| `psikologi` | **NO** | Psychological assessment |
| `publikasi` | **NO** | Faculty publications |
| `ruang` | **NO** | Room booking |
| `notif` | **NO** | Notification broadcasts |
| `transfer` | **NO** | Credit transfer from other universities |
| `nonreguler` | **NO** | Non-regular program students |
| `dokumen` | **NO** | Document generation |
| `tmp` | **NO** | Temporary migration/work tables (do not query) |
| `logs` | **NO** | System audit logs |
| `kesehatan` | **NO** | Student health records |
| `mutu` | **NO** | Quality/accreditation records |
| `sistem` | **NO** | Legacy SIX application RBAC |
| `kuesioner` | **NO** | Generic questionnaire builder (not the evaluasi questionnaire) |
| `v_*` schemas | **NO** | Read-only views for external systems (ditkeu, ditpeg, etc.) |
| `x_*` schemas | **NO** | Sync tables for PDDikti, HRIS, SIBPP |
| `__*` schemas | **NO** | Legacy/backup snapshot schemas (double-underscore prefix) |

## Application Scope Statement
 
Aplikasi ini dibatasi pada domain portofolio perkuliahan dan evaluasi akademik program studi reguler di ITB. Secara spesifik, aplikasi menangani: penilaian kualitas pengajaran dosen, evaluasi capaian pembelajaran mahasiswa, analisis skor kuesioner evaluasi perkuliahan, distribusi nilai, statistik kehadiran, serta teks portofolio dosen per kelas.
 
Pengguna aplikasi adalah pemangku kepentingan divisi akademik — dosen, kaprodi, dan dekan — yang bertanggung jawab atas kualitas pembelajaran dalam program studi reguler. Aplikasi tidak menangani dan tidak mengakses data yang berada di luar mandat akademik tersebut:
 
- Keuangan mahasiswa (UKT, tagihan, cicilan, beasiswa)
- Kemahasiswaan (kegiatan ekstrakurikuler, prestasi, kompetisi) — dikelola Ditmawa, bukan divisi akademik
- Kesehatan mahasiswa
- Penerimaan mahasiswa baru (PMB/seleksi)
- Penjurusan mahasiswa TPB — dikelola unit layanan akademik TPB, bukan kaprodi/dekan program studi tujuan
- Kelas IVC (International Visiting Course) — dikelola kantor urusan internasional dengan kerangka evaluasi terpisah
- Presensi granular per pertemuan per mahasiswa (hanya agregat dari sistem evaluasi yang tersedia di `analitik.v_akademik_kelas`)
- Data kepegawaian dosen di luar identitas dan beban mengajar
- Sistem informasi eksternal (PDDikti, HRIS, MS365, mobile app)

---

## Schema: `utama` — Master Data

**Relevance: YES**
Core lookup tables for the entire SIX system. These tables are institution-wide and not scoped to a single prodi or semester. The SQL agent treats them as unrestricted reference tables.

---

### `utama.fakultas`

Faculty master table.

| Column | Type | Notes |
|--------|------|-------|
| `kd_fak` | `varchar` PK | e.g. `"STEI"`, `"FMIPA"`, `"SBM"` |
| `nama` | `jsonb` | `{"id": "Sekolah Teknik Elektro dan Informatika", "en": "..."}` |
| `nama_pendek` | `varchar` | Short label, same with kd_fak |
| `dosen_id_dekan` | `integer` | FK → `utama.dosen` (current dean) |
| `dosen_id_wda` | `integer` | FK → `utama.dosen` (vice dean academic) |
| `active` | `boolean` | Filter: `WHERE active = true` |
| `weight` | `integer` | Display order |

Access pattern: `SELECT kd_fak, nama->>'id' FROM utama.fakultas WHERE active = true`

---

### `utama.program_studi`

Program of study (prodi) master.

| Column | Type | Notes |
|--------|------|-------|
| `no_ps` | `integer` PK | 3-digit numeric code, e.g. `135` (IF S1) |
| `kd_ps` | `char(2)` | Short code, e.g. `"IF"`, `"EL"`, `"STI"` |
| `kd_fak` | `varchar` FK | → `utama.fakultas.kd_fak` , FK|
| `kd_strata` | `char(2)` | `"S1"`, `"S2"`, `"S3"`, `"PR"` (Profesi) |
| `kd_jenis` | `char(1)` | Program type code |
| `kd_kampus` | `char(2)` | Campus code, fk -> `utama.kampus.kd_kampus` |
| `nama` | `jsonb` | `{"id": "Teknik Informatika", "en": "Informatics Engineering"}` |
| `nama_pendek` | `varchar` | Abbreviated name |
| `dosen_id_kaprodi` | `integer` | FK → `utama.dosen` (current head of program) |
| `active` | `boolean` | |
| `th_kur` | `integer` | Active curriculum year |
| `no_ps_induk` | `integer` | Parent prodi (for sub-programs) |

Access pattern: `SELECT no_ps, kd_ps, kd_strata, nama->>'id' FROM utama.program_studi WHERE active = true`

---

### `utama.mata_kuliah`

Course (mata kuliah) master.

| Column | Type | Notes |
|--------|------|-------|
| `mata_kuliah_id` | `integer` PK | Internal numeric ID |
| `kd_kuliah` | `char(6)` | Course code, e.g. `"IF2210"`. UNIQUE per curriculum year. |
| `th_kur` | `integer` | Curriculum year, e.g. `2019` |
| `sks` | `integer` | Credit hours |
| `no_ps` | `integer` FK | → `utama.program_studi.no_ps` (owning prodi) |
| `nama` | `jsonb` | `{"id": "Pemrograman Berorientasi Objek", "en": "Object-Oriented Programming"}` |
| `kd_kategori` | `char(3)` | Course category code |
| `kd_penilaian` | `char(1)` | `'A'` = letter grade (ABCDE), `'P'` = Pass/Fail |
| `active` | `boolean` | |

Text search: `WHERE (nama->>'id' \|\| ' ' \|\| COALESCE(nama->>'en', '')) ILIKE '%basis data%'`

---

### `utama.dosen`

Lecturer master.

| Column | Type | Notes |
|--------|------|-------|
| `dosen_id` | `integer` PK | Internal numeric ID |
| `nip` | `varchar` | Employee number |
| `nama` | `varchar` | Name without title - anonymized |
| `nama_gelar` | `varchar` | **GENERATED**: full name with academic titles (use this for display) |
| `gelar_depan` | `varchar` | Prefix title, e.g. `"Dr."`, `"Prof. Dr."` |
| `gelar_belakang` | `varchar` | Suffix title, e.g. `"M.T."`, `"Ph.D."` |
| `kd_fak` | `varchar` FK | Home faculty (from `utama.dosen.kd_fak`, authoritative) |
| `kk_id` | `integer` FK | → `utama.kk` (research group) |
| `no_ps` | `integer` FK | Home prodi (may differ from prodi where they teach), majority null |
| `active` | `boolean` | |
| `nidn` | `varchar` | National lecturer ID |
| `tgl_valid` | `daterange` | Validity period of the lecturer record |
| `jenis_kepeg` | `varchar` | Employment type |
| `status_kepeg` | `varchar` | Employment status |

Name search: `WHERE nama_gelar ILIKE '%tricya%'` or `WHERE nama ILIKE '%budi%'`

---

### `utama.kk`

Research group (Kelompok Keahlian).

| Column | Type | Notes |
|--------|------|-------|
| `kk_id` | `integer` PK | |
| `kd_fak` | `varchar` FK | Faculty this KK belongs to |
| `nama` | `jsonb` | `{"id": "Rekayasa Perangkat Lunak dan Data", "en": "..."}` |
| `dosen_id_ketua` | `integer` FK | Head of KK |
| `active` | `boolean` | |

---

### `utama.kelas_prodi`

Subgroup of a prodi.

| Column | Type | Notes |
|--------|------|-------|
| `kelas_prodi_id` | `integer` PK | |
| `no_ps` | `integer` FK | → `utama.program_studi` |
| `kd_kampus` | `char(2)` | FK → `utama.kampus` |
| `nama` | `jsonb` | |

might involving mahasiswa, map cluster kelas prodi, wali
---

### `utama.kampus`

| Column | Type | Notes |
|--------|------|-------|
| `kd_kampus` | `char(2)` | PK |
| `nama` | `jsonb` | {"en": "Ganesha", "id": "Ganesha"} |
| `active` | `boolean` | |
| `kota` | `varchar` | |

---

### `utama.mahasiswa`

Student master record (identity, enrollment metadata).

| Column | Type | Notes |
|--------|------|-------|
| `mahasiswa_id` | `integer` PK | |
| `nim` | `char(8)` | Student ID number - caution: nim in this table is majority empty, dont rely on this, nim is more reliable in mahasiswa schema |
| `nama` | `varchar` | Name (no title) - caution: anonymized |
| `nama_lengkap` | `varchar` | Full legal name - caution: anonymized |
| `no_ps` | `integer` FK | REFERENCES utama.program_studi(no_ps) Home prodi: e.g 135 |
| `kd_fak` | `varchar` FK | REFERENCES utama.fakultas(kd_fak) Home faculty: e.g STEI |
| `kd_strata` | `char(2)` | `"S1"`, `"S2"`, `"S3"` |
| `kd_stat_aktif` | `char(1)` | Active status code, FK to reference.stat_aktif, 'W = 'Graduated' , 'A' = Active , 'N' = Dropped Out, 'C' = Applicant|
| `kd_stat_reguler` | `char(1)` | `'R'` = regular, 'C' = Credit Earning, etc, FK to reference.stat_reguler |
| `dosen_id_wali` | `integer` FK | REFERENCES utama.dosen(dosen_id), Academic advisor: caution: majorly null |
| `tahun_daftar` | `smallint` | Enrollment year: e.g 2023 |
| `semester_daftar` | `smallint` | Enrollment semester: e.g 1 or 2|

---

### `utama.pejabat`

Institutional officials (dekan, wakil dekan, etc.) with validity periods.

| Column | Type | Notes |
|--------|------|-------|
| `pejabat_id` | `integer` PK | |
| `kd_jabatan` | `varchar` | Position code: rektor, dir, wram, dekan   |
| `unit` | `varchar` | Organizational unit (e.g., faculty code) |
| `dosen_id` | `integer` FK | → `utama.dosen` |
| `tgl_aktif` | `daterange` | Active period |
| `jabatan` | `varchar` | Position label |

caution: im not sure if really reliable, more reliable by joining users.role role_name | nama : 111| kk |{"en": "Ketua Kelompok Keilmuan", "id": "Ketua Kelompok Keilmuan"} ;   14|prodi             |prodi     |true  |{"en": "Head of Study Program", "id": "Ketua Program Studi”}; 
13|fakultas          |fakultas  |true  |{"en": "Faculty (Dean or Vice Dean)", "id": "Fakultas (Dekan & Wakil Dekan)"}

---

### `utama.cluster_prodi` / `utama.map_cluster_prodi` / `utama.map_cluster_kelas_prodi`

Prodi cluster groupings. Likely used for administrative grouping of programs; low relevance for analytics queries, but we might do something just for fyi by joining cluster_prodi, map_cluster_prodi, mahasiswa etc.

---

## Schema: `kelas` — Class Sessions

**Relevance: YES**
The primary transactional schema for class data. `kelas.kelas` is the base table from which `analitik.v_akademik_kelas` is derived.

---

### `kelas.kelas`

One row per class offering (parallel section of a course in a semester).

this schema also has some views.

| Column | Type | Notes |
|--------|------|-------|
| `kelas_id` | `integer` PK | |
| `mata_kuliah_id` | `integer` FK | → `utama.mata_kuliah` |
| `tahun` | `smallint` | Calendar year, e.g. `2024` |
| `semester` | `smallint` | `1` = Ganjil, `2` = Genap, `3` = Short semester (SP) |
| `no_kelas` | `integer` | Parallel section number, e.g. `1`, `2`, `3` |
| `no_ps` | `integer` FK | → `utama.program_studi` (owning prodi) |
| `kuota` | `integer` | Enrollment cap, caution: might be null |
| `open` | `boolean` | Whether the class is open for registration |
| `ada_kuesioner` | `boolean` | Whether questionnaire is available |
| `batasan` | `jsonb` | Additional info |
| `kd_reguler` | `char(1)` | `'R'` = regular, other = special program |
| `kd_bahasa` | `char(2)` | Language code: `'id'` or `'en'` |
| `kd_kampus` | `char(2)` | Campus, FK -> `utama.kampus` |
| `dosen_id_verif_porto` | `integer` FK | Lecturer who verified the portfolio |
| `ts_ver_nilai` | `timestamp` | Grade verification timestamp |
| `ts_final_nilai` | `timestamp` | Grade finalization timestamp |
| `tag` | `varchar` | Free-form tag |

`tahun_ajaran` derivation: `CASE WHEN semester IN (2,3) THEN (tahun-1)||'/'||tahun ELSE tahun||'/'||(tahun+1) END`

---

### `kelas.pengajar`

Many-to-many between kelas and dosen (co-teaching).

| Column | Type | Notes |
|--------|------|-------|
| `kelas_id` | `integer` FK | → `kelas.kelas` |
| `dosen_id` | `integer` FK | → `utama.dosen` |
| `utama` | `boolean` | Whether this dosen is the primary instructor |
| `weight` | `integer` | Display order |
| `beban` | `numeric` | Teaching load fraction |
| `kd_status` | `char(1)` | Status code |

PK: `(kelas_id, dosen_id)`

---

### `kelas.pertemuan` - [OLD DATA]

Individual lecture/meeting records. Used to compute actual attendance, caution: mostly irrelevant

| Column | Type | Notes |
|--------|------|-------|
| `pertemuan_id` | `integer` PK | |
| `kelas_id` | `integer` FK | |
| `waktu` | `tstzrange` | Actual scheduled time range |
| `waktu_plan` | `tstzrange` | Planned time |
| `kd_kegiatan` | `char(1)` | Activity type (Lecture, Tutorial, etc.), FK to `kelas.ref_kegiatan` |
| `kd_metode` | `char(1)` | Delivery method (In-Person, Online, Hybrid), FK to `kelas.ref_metode` |
| `dosen` | `jsonb` | Dosen attendance JSON |
| `topik` | `varchar` | Meeting topic |

---

### `kelas.jadwal_kuliah` - [OLD DATA]

Scheduled lecture slots (recurring schedule entries).

| Column | Type | Notes |
|--------|------|-------|
| `jadwal_kuliah_id` | `integer` PK | |
| `kelas_id` | `integer` FK | |
| `kd_hari` | `smallint` | Day of week |
| `ruang_id` | `integer` | Room reference |
| `waktu` | `int4range` | Time slot range (minute offsets) : e.g [11,13) |

---

### `kelas.jadwal_ujian` - [OLD DATA]

Exam schedule entries.

| Column | Type | Notes |
|--------|------|-------|
| `mata_kuliah_id` | `integer` FK | |
| `kd_ujian` | `char(1)` | Exam type code (UTS, UAS, etc.) |
| `waktu` | `tstzrange` | Exam time |
| `tahun` | `integer` |  |
| `semester` | `integer` |  |
| `kelas_id` | `integer[]` | Array of class IDs covered |

---

### `kelas.distribusi, kelas.pola_*` - not relevant

Distribution policy assignment for a course in a semester.

---

### `kelas.ref_kegiatan`, `kelas.ref_metode`, `kelas.ref_reguler`

Reference/lookup tables for activity types, delivery methods, and regularity codes.

---

## Schema: `evaluasi` — Evaluation & Portfolio

**Relevance: YES**
Contains all questionnaire scores and portfolio free-text data. This is the most critical schema for the analytics system alongside `analitik.v_akademik_kelas`.

---

### `evaluasi.nilai_kelas`

Aggregated evaluation results per class (class-level questionnaire scores and attendance).

| Column | Type | Notes |
|--------|------|-------|
| `kelas_id` | `integer` FK PK | → `kelas.kelas` |
| `tahun` | `smallint` | |
| `semester` | `smallint` | |
| `kuesioner` | `jsonb` | Class-level question scores: `{"<evaluasi.pertanyaan_kuesioner.kd_pertanyaan>": 3.74, "22": 3.69, "28": 3.80, ...}` |
| `hadir_dosen` | `numeric` | Lecturer attendance percentage (0–100) |
| `hadir_mhs` | `numeric` | Student attendance percentage (0–100) |
| `ip_mhs` | `numeric` | Average student GPA in this class |
| `skor_dna` | `numeric` | DNA composite score |
| `ts_dna` | `timestamp` | DNA computation timestamp |
| `ip_mhs_dna` | `numeric` | Student GPA from DNA system - DONT USE |

`kuesioner` key mapping (class-level questions, same for all instructors):
- Q21, Q22, Q23 → Capaian pembelajaran
- Q24, Q28 → Pelaksanaan perkuliahan
- Q29, Q30 → Sarana & prasarana
- Q35, Q37 → Perilaku mahasiswa

---

### `evaluasi.nilai_dosen`

Per-lecturer evaluation scores within a class.

| Column | Type | Notes |
|--------|------|-------|
| `kelas_id` | `integer` FK | → `kelas.kelas` |
| `dosen_id` | `integer` FK | → `utama.dosen` |
| `tahun` | `smallint` | |
| `semester` | `smallint` | |
| `kuesioner` | `jsonb` | Per-dosen scores: `{"25": 3.67, "26": 3.44, "27": 3.11}` — older records may be `{}` |
| `skor_kues` | `jsonb` | Dimension aggregates: `{"1": 3.82, "2": 3.91, "3": 3.75}` — key "1"=capaian, "2"=pelaksanaan, EXCEPT SAPRAS, "3"=perilaku |
| `nilai_akhir` | `numeric` | Final composite score — frequently NULL, inconsistently populated |

PK: `(kelas_id, dosen_id)`

Q25 = penguasaan materi, Q26 = kemampuan menjelaskan, Q27 = interaksi dosen–mahasiswa. These three are the individual dosen evaluation questions; all others are class-level.

---

### `evaluasi.portofolio`

Portfolio free-text submissions per class. **This is the actual portfolio text storage** — the equivalent of `teks_portofolio`.

| Column | Type | Notes |
|--------|------|-------|
| `kelas_id` | `integer` FK PK | → `kelas.kelas` |
| `isian` | `jsonb` | Portfolio text sections keyed by question code. Structure: `{"<kd_pertanyaan>": "<text>", ...}` |
| `komentar` | `jsonb` | Verificator comments (NOT STUDENT) |
| `lengkap` | `boolean` | Whether portfolio submission is complete |
| `nilai` | `integer` | Verifier score (1–4), nullable |
| `tgl_entri` | `date` | Submission date |

The keys inside `isian` correspond to `evaluasi.pertanyaan_portofolio.kd_pertanyaan`. To map question codes to section names, join with `evaluasi.pertanyaan_portofolio` or `evaluasi.pertanyaan_grup_portofolio`.

---

### `evaluasi.pertanyaan_portofolio` - Sections in pdf

Portfolio question definitions. Maps question codes to human-readable section names.

| Column | Type | Notes |
|--------|------|-------|
| `kd_pertanyaan` | `integer` PK | Matches keys inside `evaluasi.portofolio.isian` |
| `pertanyaan` | `jsonb` | Question text: `{"id": "Metode Perkuliahan", "en": "..."}` |
| `deskripsi` | `jsonb` | Description |
| `kd_grup` | `integer` FK | → `evaluasi.pertanyaan_grup_portofolio` |
| `weight` | `integer` | Display order |
| `active` | `boolean` | |
| `semester_berlaku` | `int4range` | Semesters for which this question is valid |

---

### `evaluasi.pertanyaan_grup_portofolio`

Portfolio question group definitions - usually for verification purposes.

| Column | Type | Notes |
|--------|------|-------|
| `kd_grup` | `integer` PK | |
| `pertanyaan` | `jsonb` | Group name: `{"id": "Refleksi & Usulan", "en": "..."}` |
| `weight` | `integer` | |
| `active` | `boolean` | |

---

### `evaluasi.pertanyaan_kuesioner`

Questionnaire question definitions. Maps question numbers (Q21–Q37 etc.) to dimension groups.

| Column | Type | Notes |
|--------|------|-------|
| `kd_pertanyaan` | `integer` PK | e.g. `21`, `25`, `35` |
| `pertanyaan` | `jsonb` | Question text bilingual |
| `kd_kelompok` | `integer` FK | → `evaluasi.kelompok_kuesioner` (dimension group) |
| `kd_kategori` | `char(1)` | Category: `'K'` = class-level, `'D'` = dosen-specific |
| `active` | `boolean` | |
| `semester_berlaku` | `int4range` | Validity range |

---

### `evaluasi.kelompok_kuesioner`

Questionnaire dimension groups (capaian, pelaksanaan, sarana, perilaku).

| Column | Type | Notes |
|--------|------|-------|
| `kd_kelompok` | `integer` PK | |
| `kelompok` | `jsonb` | Group name bilingual, e.g: {"en": "Outcome (luaran) matakuliah", "id": "Outcome (luaran) matakuliah"} |
| `weight` | `integer` | |
| `active` | `boolean` | |

---

### `evaluasi.jwb_kuesioner`

Raw individual student questionnaire responses (one row per student per class). Used for computing aggregated scores in `nilai_kelas` — not directly queried by the analytics agent.

| Column | Type | Notes |
|--------|------|-------|
| `jawaban_id` | `integer` PK | |
| `mahasiswa_id` | `integer` FK | May be NULL (anonymous) |
| `kelas_id` | `integer` FK | |
| `tahun` | `smallint` | |
| `semester` | `smallint` | |
| `jawaban` | `jsonb` | Full response payload |

---

### `evaluasi.jwb_kuesioner_dosen`

Raw individual questionnaire responses about a specific dosen. Not directly queried.

---

### `evaluasi.komponen_evaluasi`

Grading component definitions per class (e.g., UTS 30%, UAS 40%, Tugas 30%).

| Column | Type | Notes |
|--------|------|-------|
| `komponen_id` | `integer` PK | |
| `kelas_id` | `integer` FK | |
| `nama` | `jsonb` | Component name |
| `bobot` | `numeric` | Weight percentage |

---

### `evaluasi.realisasi`

Weekly curriculum realization records (which topics were covered each week).

| Column | Type | Notes |
|--------|------|-------|
| `kelas_id` | `integer` FK | |
| `minggu` | `smallint` | Week number |
| `topik` | `varchar` | Topic covered |
| `keterangan` | `varchar` | Notes |

---

## Schema: `mahasiswa` — Student Records

**Relevance: PARTIAL YES**
Only a subset of tables are needed. The full schema handles student lifecycle: admissions through graduation. However the core mahasiswa data is in utama.mahasiswa.

---

### `mahasiswa.kuliah` — USED BY MV

Grade records per student per course. **Primary source for grade distribution data.**

| Column | Type | Notes |
|--------|------|-------|
| `mahasiswa_id` | `integer` FK | → `utama.mahasiswa` |
| `mata_kuliah_id` | `integer` FK | → `utama.mata_kuliah` |
| `tahun` | `smallint` | |
| `semester` | `smallint` | |
| `kelas_id` | `integer` FK | → `kelas.kelas` — may be NULL for non-regular |
| `nilai` | `varchar(2)` | Grade: `'A'`, `'AB'`, `'B'`, `'BC'`, `'C'`, `'D'`, `'E'`, `'P'`, `'F'`, `'T'` (incomplete) |
| `sah_nilai` | `boolean` | Whether the grade is finalized |
| `ts_hapus` | `timestamp` | If set, the record is soft-deleted |
| `lulus` | `boolean` | Pass flag |

Filter for valid grades: `WHERE sah_nilai = true AND ts_hapus IS NULL AND kelas_id IS NOT NULL`
Grade `'T'` (incomplete) must be excluded from distribution counts.


---

### `mahasiswa.nonaktif` — USE THIS

Records of inactive students (on leave, suspension, official outbound).

| Column | Type | Notes |
|--------|------|-------|
| `mahasiswa_id` | `integer` FK | |
| `tahun` | `smallint` | |
| `semester` | `smallint` | |
| `kd_stat_daftar` | `char(1)` | Status: cuti, skorsing, etc. |
| `kd_jenis` | `char(1)` | Type of non-active status |

Used to exclude from active student count.

---

### `mahasiswa.ip`

Cumulative GPA record per student (latest). Not per-semester.

| Column | Type | Notes |
|--------|------|-------|
| `mahasiswa_id` | `integer` PK | |
| `ipk` | `numeric` | Cumulative GPA |
| `ip` | `numeric` | Semester GPA (last semester) |
| `sks_total` | `integer` | Total credits attempted |
| `sks_lulus` | `integer` | Total credits passed |

---

### `mahasiswa.nr`

Per-semester GPA summary per student.

| Column | Type | Notes |
|--------|------|-------|
| `mahasiswa_id` | `integer` FK | |
| `tahun` | `smallint` | |
| `semester` | `smallint` | |
| `nr` | `numeric` | Semester GPA |
| `nr_beban` | `numeric` | Weighted GPA |
| `sks` | `integer` | Credits taken |
| `sks_lulus` | `integer` | Credits passed |

---

### `mahasiswa.cpmk`

the nilai cpmk achieved by mahasiswa

---
### Not relevant from `mahasiswa`

The following `mahasiswa.*` tables are not needed for portfolio analytics:

`alamat`, `beasiswa`, `catatan_wali`, `doktoral`, `ekonomi`, `fpn`, `inbound`, `ip_tahap`, `kasus`, `keluarga`, `kerjasama`, `kesehatan`, `kirim_paket`, `ktm`, `kuliah_ambil`, `kuliah_paksa`, `message`, `minor`, `nilai_cpmk`, `nilai_komponen_evaluasi`, `outbound`, `pembayaran`, `pembimbing`, `perpanjangan`, `pindah_prodi`, `riwayat_pendidikan`, `tahap`, `transkrip`, `tugas_akhir`, `wisuda`

---

## Schema: `users` — User Accounts and Roles

**Relevance: YES**
Authentication, SSO mapping, and multi-role RBAC. Do not expose in SQL generation — agent-layer only.

---

### `users.user`

Application user accounts.

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | `integer` PK | |
| `user_name` | `varchar` | Login username |
| `nama` | `varchar` | Display name |
| `active` | `boolean` | |
| `ina_id` | `varchar` | SSO identifier (IntelliGate / SSO ITB) |
| `ms365_id` | `uuid` | Microsoft 365 user ID |
| `ms365_upn` | `text` | MS365 User Principal Name (email) |
| `language` | `char(2)` | Preferred language: `'EN'` or `'ID'` |
| `ts_reg` | `timestamp` | Account creation time |

SSO mapping: match incoming SSO session by `ina_id` or `ms365_upn`.

---

### `users.role`

Role definitions.

| Column | Type | Notes |
|--------|------|-------|
| `role_id` | `integer` PK | |
| `role_name` | `varchar` | e.g. `"kk"`, `"fakultas"`, `"prodi"`, `"dosen"` |
| `scope_type` | `varchar` | What scope this role applies to: `"fakultas"`, `"prodi"`, `"dosen"`, `"kk"`, mahasiswa, sps, etc. |
| `nama` | `jsonb` | {"en": "Head of Study Program", "id": "Ketua Program Studi"}, {"en": "Faculty (Dean or Vice Dean)", "id": "Fakultas (Dekan & Wakil Dekan)"}, {"en": "Lecturer", "id": "Dosen"}, {"en": "Ketua Kelompok Keilmuan", "id": "Ketua Kelompok Keilmuan"}   |
| `active` | `boolean` | |

---

### `users.user_role`

Multi-role assignment per user. **One user can hold multiple roles simultaneously.**

| Column | Type | Notes |
|--------|------|-------|
| `user_role_id` | `integer` PK | |
| `user_id` | `integer` FK | → `users.user` |
| `role_id` | `integer` FK | → `users.role` |
| `ts_valid` | `tstzrange` | Validity period — must check `ts_valid @> now()` for active roles |
| `active` | `boolean` | Must also be `true` |
| `prime` | `boolean` | Primary role flag |
| `nama` | `jsonb` | Override label for this specific assignment |

A dekan of two faculties will have two rows in `user_role` with `role_name = 'dekan'` and different `scope` values. Both can be simultaneously valid. The application must handle this when building `UserScope`.


---

## Analytics Views (`analitik.*`)

**primary query surface for the analytics agent.**

The analytics layer is split into two schemas:

- `analitik_mv.*` — raw materialized views (defined in `schema_mv_portofolio_kuesioner.sql`, documented in `mv_dokumentasi.md`). **Agent must NEVER query this schema** — not RLS-enforced, and the application DB role owns it (GRANT/REVOKE does not block direct access).
- `analitik.*` — 13 views consumed by the agent. 5 public views (Group A, no row filtering) + 8 row/column-secured views (Group B), each backed by an `analitik.fn_get_*()` `SECURITY DEFINER` function.

Every generated query must reference `analitik.*` with the schema prefix. References to `analitik_mv.*`, other schemas, or unqualified table names must be rejected before execution.

### Row-Level Security (Group B)

Before querying any Group B view, the following session variables must be set via `SET LOCAL`, in the same transaction as the query:

| Variable | Type | Notes |
|----------|------|-------|
| `app.role` | text | **Lowercase, exact match.** `admin`, `direktorat`, `dekan`, `jajaran_dekanat`, `kaprodi`, `jajaran_prodi`, `dosen` |
| `app.user_id` | integer | App user ID |
| `app.dosen_id` | integer | Dosen ID, empty if N/A |
| `app.kk_id` | integer | KK ID, empty if N/A |
| `app.no_ps` | integer | = `no_prodi`, empty if N/A |
| `app.kd_fak` | varchar | Faculty code, empty if N/A |

| `app.role` | Effect on Group B views |
|---|---|
| `admin`, `direktorat` | All rows, all columns |
| `dekan`, `jajaran_dekanat` | Row filter: `kode_fakultas = app.kd_fak` |
| `kaprodi`, `jajaran_prodi` | Row filter: `no_prodi = app.no_ps` |
| `dosen` | Row filter: `no_prodi = app.no_ps`, plus column masking (see `skor_dosen_q25/26/27` below and `v_akademik_statistik_dosen`) |

Without these session variables, all 8 Group B views return **0 rows** (not an error). Group A views (the 5 `v_info_umum_*` / `v_akademik_jenis_dan_sifat_matkul` views) always return data regardless of session variables.

---

### `analitik.v_akademik_kelas`

**Granularity: 1 row = 1 class.**
The primary analytics view. All dimensions are pre-joined and flattened. Query this before any base table for numeric analytics.

**Row filter:** see RLS table above (`kode_fakultas` for dekan/jajaran_dekanat, `no_prodi` for kaprodi/jajaran_prodi/dosen).
**Column masking (role `dosen`):** `skor_dosen_q25/26/27` (JSONB) — restricted to the entry for `app.dosen_id` only.

#### Refresh dependency
Must be refreshed first before `analitik.v_akademik_statistik_prodi` and `analitik.v_akademik_statistik_dosen`.

#### Key columns

| Column | Type | Example |
|--------|------|---------|
| `kelas_id` | `integer` | `10342` |
| `mata_kuliah_id` | `integer` | `501` |
| `no_kelas` | `integer` | `1`, `2`, `3` |
| `semester` | `smallint` | `1` (Ganjil), `2` (Genap), `3` (SP) |
| `tahun` | `smallint` | `2024` |
| `tahun_ajaran` | `text` | `"2024/2025"` |
| `kode_matkul` | `varchar` | `"IF2210"` |
| `nama_matkul_id` | `text` | `"Pemrograman Berorientasi Objek"` |
| `nama_matkul_en` | `text` | `"Object-Oriented Programming"` |
| `sks` | `integer` | `3` |
| `jenis_nilai` | `text` | `"ABCDE"` or `"PassFail"` |
| `tahun_kurikulum` | `integer` | `2019` |
| `no_prodi` | `integer` | `135` (= `no_ps`) |
| `kode_prodi` | `varchar` | `"IF"` |
| `nama_prodi_id` | `text` | `"Teknik Informatika"` |
| `jenjang` | `varchar` | `"S1"`, `"S2"`, `"S3"` |
| `kode_fakultas` | `varchar` | `"STEI"` |
| `nama_fakultas_id` | `text` | `"Sekolah Teknik Elektro dan Informatika"` |
| `semua_dosen_id` | `integer[]` | `{123, 456}` |
| `semua_dosen_nama_gelar` | `text[]` | `{"Prof. Dr. Budi, M.T.", "Dr. Siti, Ph.D."}` |
| `kode_jenis_list` | `varchar[]` | Jenis MK dalam kurikulum (dari `v_akademik_jenis_dan_sifat_matkul`), bisa >1 entri |
| `nama_jenis_list` | `text[]` | Nama jenis MK, paralel dengan `kode_jenis_list` |
| `nama_paket_list` | `text[]` | Nama paket kurikulum yang memuat MK ini |
| `kode_sifat_list` | `varchar[]` | `C`=Core/Wajib, `E`=Elective, paralel dengan `kode_jenis_list` |
| `is_wajib_itb` | `boolean` | Dari kurikulum lama; selalu `FALSE` untuk kur24 (proxy: `kode_jenis_list` contains `'B'`) |
| `pct_kehadiran_dosen` | `numeric` | `92.50` |
| `pct_kehadiran_mahasiswa` | `numeric` | `88.00` |
| `avg_ip_akhir_mahasiswa` | `numeric` | `3.12` |
| `skor_dna` | `numeric` | `3.80` |
| `ts_dna` | `timestamptz` | DNA computation timestamp |
| `ip_mhs_dna` | `numeric` | `3.15` |
| `is_distribusi_nilai_sah` | `boolean` | **Gate column.** `TRUE` = nilai sudah sah. Jika `FALSE`/NULL, semua kolom `dist_*` di bawah bernilai NULL (bukan 0) — WAJIB `WHERE is_distribusi_nilai_sah = TRUE` sebelum agregasi `dist_*` |
| `jumlah_mahasiswa` | `integer` | `40` (jumlah dgn nilai sah) |
| `dist_jumlah_a` .. `dist_jumlah_e` | `integer` | `12`, `8`, `10`, `5`, `3`, `1`, `1` |
| `dist_jumlah_pass` / `dist_jumlah_fail` | `integer` | For PassFail courses only |
| `dist_pct_a` .. `dist_pct_fail` | `numeric` | `30.00`, `20.00`, ... |
| `dist_pct_lulus_a_c` | `numeric` | `95.00` — % with grade ≥ C (or Pass) |
| `dist_pct_lulus_a_d` | `numeric` | `97.50` — % with grade ≥ D (or Pass) |
| `skor_q21` .. `skor_q24`, `skor_q28` .. `skor_q30`, `skor_q35`, `skor_q37` | `numeric` | `3.74` (Likert 1–4, class-level) |
| `skor_q25`, `skor_q26`, `skor_q27` | `numeric` | `3.67` (averaged across dosen) |
| `skor_dosen_q25` | `jsonb` | `{"123": 3.6667, "456": 4.0000}`. **Role `dosen`**: hanya entry milik `app.dosen_id` (atau `NULL` jika tidak ada) |
| `skor_dosen_q26` | `jsonb` | Same structure, same masking |
| `skor_dosen_q27` | `jsonb` | Same structure, same masking |
| `avg_skor_capaian` | `numeric` | Avg(Q21, Q22, Q23) |
| `avg_skor_pelaksanaan` | `numeric` | Avg(Q24, Q25, Q26, Q27, Q28) |
| `avg_skor_sarana_prasarana` | `numeric` | Avg(Q29, Q30) |
| `avg_skor_perilaku_mahasiswa` | `numeric` | Avg(Q35, Q37) |
| `avg_skor_overall` | `numeric` | Avg of all Q with data |


#### Common query patterns

```sql
-- All classes for a course in a semester
SELECT * FROM analitik.v_akademik_kelas
WHERE kode_matkul = 'IF2210' AND semester = 1 AND tahun = 2024;

-- Filter by prodi (scoped user)
WHERE no_prodi = 135 AND semester = 1 AND tahun = 2024

-- Filter by fakultas (scoped user)
WHERE kode_fakultas = 'STEI' AND semester = 1 AND tahun = 2024

-- Text search for course name (bilingual)
WHERE (nama_matkul_id || ' ' || COALESCE(nama_matkul_en, '')) ILIKE '%basis data%'

-- Per-dosen Q25 score from JSONB
(skor_dosen_q25->>:dosen_id_str)::numeric
```

---

### `analitik.v_akademik_statistik_prodi`

**Granularity: 1 row = 1 prodi × 1 semester × 1 tahun.**
Pre-aggregated for prodi-level dashboard panels.

**Row filter:** `kode_fakultas` for dekan/jajaran_dekanat, `no_prodi` for kaprodi/jajaran_prodi/dosen. **Column masking:** none.

#### Key columns

| Column | Type | Notes |
|--------|------|-------|
| `no_prodi` | `integer` | PK component (= `no_ps`) |
| `kode_prodi` | `varchar` | `"IF"` |
| `nama_prodi_id` / `nama_prodi_en` | `text` | |
| `jenjang` | `varchar` | |
| `kode_fakultas` | `varchar` | |
| `nama_fakultas_id` / `nama_fakultas_en` | `text` | |
| `semester` | `smallint` | PK component |
| `tahun` | `smallint` | PK component |
| `tahun_ajaran` | `text` | Derived |
| `jumlah_kelas` | `bigint` | |
| `jumlah_matkul_aktif` | `bigint` | |
| `jumlah_dosen_aktif` | `bigint` | Unique dosen teaching this prodi this semester |
| `jumlah_mahasiswa_aktif` | `bigint` | From `mahasiswa.status` by home prodi |
| `avg_pct_kehadiran_dosen` | `numeric` | |
| `avg_pct_kehadiran_mahasiswa` | `numeric` | |
| `avg_ip_akhir_mahasiswa` | `numeric` | |
| `total_jumlah_a` .. `total_jumlah_fail` | `bigint` | SUM across all kelas |
| `total_mahasiswa_dinilai` | `bigint` | Total graded students (denominator) |
| `dist_pct_a` .. `dist_pct_fail` | `numeric` | Computed from absolute sums, not averaged percentages |
| `dist_pct_lulus_a_c` / `dist_pct_lulus_a_d` | `numeric` | |
| `avg_skor_q21` .. `avg_skor_q37` | `numeric` | Per-question averages across kelas |
| `avg_skor_capaian` / `avg_skor_pelaksanaan` / `avg_skor_sarana_prasarana` / `avg_skor_perilaku_mahasiswa` / `avg_skor_overall` | `numeric` | |

Faculty-level aggregation: `GROUP BY kode_fakultas, nama_fakultas_id, semester, tahun` on this view — no separate MV needed.

---

### `analitik.v_akademik_statistik_dosen`

**Granularity: 1 row = 1 dosen × 1 semester × 1 tahun.**
Pre-aggregated for dosen-level dashboard panels.

**Row filter:** `kode_fakultas_dosen` (homebase) for dekan/jajaran_dekanat; `app.no_ps = ANY(no_prodi_diajar)` for kaprodi/jajaran_prodi/dosen.
**Column masking (role `dosen`):** for rows of *other* dosen (`dosen_id != app.dosen_id`), the `[SENSITIF]` columns below (`avg_pct_kehadiran_dosen`, `avg_ip_mhs`, `avg_skor_q25/26/27`, `avg_skor_capaian/pelaksanaan/sarana_prasarana/perilaku_mahasiswa/overall`, `jumlah_kelas_dengan_skor`, `avg_nilai_akhir`) are set to `NULL`. Own rows (`dosen_id = app.dosen_id`) show full data. `avg_pct_kehadiran_mahasiswa` is never masked.

#### Key columns

| Column | Type | Notes |
|--------|------|-------|
| `dosen_id` | `integer` | PK component |
| `nama_dosen_gelar` | `varchar` | Full name with titles |
| `nip` | `varchar` | |
| `kk_id` | `integer` | |
| `nama_kk_id` / `nama_kk_en` | `text` | |
| `kode_fakultas_dosen` | `varchar` | Home faculty from `utama.dosen.kd_fak` |
| `no_prodi` | `integer` | Home prodi from `utama.dosen.no_ps` |
| `semester` | `smallint` | PK component |
| `tahun` | `smallint` | PK component |
| `tahun_ajaran` | `text` | |
| `jumlah_kelas` | `bigint` | |
| `jumlah_matkul` | `bigint` | |
| `total_sks_diajar` | `bigint` | Sum across all kelas (paralel kelas counted separately) |
| `avg_pct_kehadiran_dosen` | `numeric` | |
| `avg_pct_kehadiran_mahasiswa` | `numeric` | |
| `avg_ip_mhs` | `numeric` | |
| `avg_skor_q25` / `avg_skor_q26` / `avg_skor_q27` | `numeric` | Dosen-specific question averages; NULL for legacy data |
| `avg_skor_capaian` / `avg_skor_pelaksanaan` / `avg_skor_perilaku_mahasiswa` | `numeric` | From `skor_kues` dim-level |
| `avg_skor_sarana_prasarana` | `numeric` | Contextual only — not a dosen evaluation |
| `avg_skor_overall` | `numeric` | Avg of capaian + pelaksanaan + perilaku (sarana excluded) |
| `jumlah_kelas_dengan_skor` | `bigint` | Classes with questionnaire data |
| `avg_nilai_akhir` | `numeric` | Usually NULL — inconsistently populated |
| `kelas_ids` | `integer[]` | Array of taught kelas_id |
| `kode_matkul_list` | `varchar[]` | Unique course codes taught |
| `no_prodi_diajar` | `integer[]` | Prodi where this dosen taught (may differ from home prodi) |
| `kode_prodi_diajar` | `varchar[]` | |

### `analitik.v_akademik_komentar_mahasiswa` (under `analitik` schema)

**Granularity: 1 row = 1 student free-text comment per class.**
Contains pre-joined student evaluation comments for easy RAG ingestion and analysis. Excludes `mahasiswa_id` (comment content only).

**Row filter:** `kode_fakultas` for dekan/jajaran_dekanat; `no_prodi` for kaprodi/jajaran_prodi; for `dosen`, `app.dosen_id = ANY(semua_dosen_id)` (only classes they teach). **Column masking:** none.

#### Key columns

| Column | Type | Notes |
|--------|------|-------|
| `jawaban_id` | `integer` | PK component |
| `kelas_id` | `integer` | Class identifier |
| `tahun` | `smallint` | Year |
| `semester` | `smallint` | Semester code |
| `tahun_ajaran` | `text` | e.g. `"2024/2025"` |
| `kode_matkul` | `varchar` | Course code (e.g., `"IF2210"`) |
| `nama_matkul_id` | `text` | Indonesian course name |
| `nama_matkul_en` | `text` | English course name |
| `sks` | `integer` | Course credit weight |
| `no_kelas` | `integer` | Class number |
| `no_prodi` | `integer` | Prodi identifier |
| `kode_prodi` | `varchar` | Prodi code abbreviation (e.g., `"IF"`) |
| `nama_prodi_id` | `text` | Prodi name |
| `jenjang` | `varchar` | Degree level (e.g., `"S1"`) |
| `kode_fakultas` | `varchar` | Faculty abbreviation (e.g., `"STEI"`) |
| `nama_fakultas_id` | `text` | Faculty name |
| `semua_dosen_id` | `integer[]` | Array of dosen IDs teaching the class |
| `semua_dosen_nama_gelar` | `text[]` | Array of teaching dosen names with titles |
| `komentar_teks` | `text` | Raw comment text (question code 103) |
| `ts_jawaban` | `timestamp` | Entry timestamp |

---

### `analitik.v_akademik_portofolio` (under `analitik` schema)

> **✅ Status:** Fully queryable. Ini adalah **primary surface untuk semua query portfolio dosen** — query langsung ke `evaluasi.portofolio` (JSONB raw) tidak lagi diperlukan untuk analytics maupun RAG. Semua dimensi kelas dari `analitik.v_akademik_kelas` sudah ter-join, dan semua teks sudah clean dari HTML via `analitik.strip_html()`.

**Row filter:** `kode_fakultas` for dekan/jajaran_dekanat; `no_prodi` for kaprodi/jajaran_prodi/dosen. **Column masking:** none.

> **Refresh:** the underlying `analitik_mv.mv_akademik_portofolio` is refreshed via `REFRESH MATERIALIZED VIEW CONCURRENTLY analitik_mv.mv_akademik_portofolio` — jalankan setelah `analitik_mv.mv_akademik_kelas` selesai refresh. `analitik.v_akademik_portofolio` itself is a plain view (via `SECURITY DEFINER`), so it reflects the underlying MV immediately after refresh.

| Column | Type | Notes |
|--------|------|-------|
| `kelas_id` | `integer` | PK component |
| `kode_matkul` | `varchar` | Course code (e.g., `"IF2210"`) |
| `nama_matkul_id` | `text` | Indonesian course name |
| `nama_matkul_en` | `text` | English course name |
| `sks` | `integer` | Course credit weight |
| `no_kelas` | `integer` | Class number |
| `semester` | `smallint` | Semester code |
| `tahun` | `smallint` | Year |
| `tahun_ajaran` | `text` | e.g. `"2024/2025"` |
| `tahun_kurikulum` | `integer` | e.g. `2024` |
| `jenis_nilai` | `text` | e.g. `"ABCDE"` |
| `no_prodi` | `integer` | Prodi identifier |
| `kode_prodi` | `varchar` | Prodi code abbreviation (e.g., `"IF"`) |
| `nama_prodi_id` | `text` | Prodi name |
| `jenjang` | `varchar` | Degree level (e.g., `"S1"`) |
| `kode_fakultas` | `varchar` | Faculty abbreviation (e.g., `"STEI"`) |
| `nama_fakultas_id` | `text` | Faculty name |
| `semua_dosen_id` | `integer[]` | Array of dosen IDs teaching the class |
| `semua_dosen_nama_gelar` | `text[]` | Array of teaching dosen names with titles |
| `metode_perkuliahan` | `text` |  |
| `komponen_penilaian` | `text` |  |
| `statistik_nilai_kelas` | `text` |  |
| `analisis_ketercapaian_outcomes` | `text` |  |
| `tanggapan_kuesioner_mahasiswa` | `text` |  |
| `refleksi_perkuliahan` | `text` |  |
| `usulan_perbaikan_dosen` | `text` |  |
| `rekomendasi_ke_itb` | `text` |  |
| `lama_metode_perkuliahan` | `text` |  |
| `lama_statistik_kelas` | `text` |  |
| `lama_outcomes_matakuliah` | `text` |  |
| `lama_sistem_penilaian` | `text` |  |
| `lama_analisis_statistik_ketercapaian` | `text` |  |
| `lama_uraian_kuesioner_statistik` | `text` |  |
| `lama_komentar_kuesioner_mahasiswa` | `text` |  |
| `lama_refleksi_perkuliahan` | `text` |  |
| `lama_rencana_tindak_lanjut` | `text` |  |
| `lama_rekomendasi_perbaikan_dosen` | `text` |  |
| `lama_rekomendasi_itb` | `text` |  |
| `komentar_penyelenggaraan` | `text` |  |
| `komentar_ketercapaian` | `text` |  |
| `komentar_refleksi` | `text` |  |
| `komentar_rekomendasi` | `text` |  |
| `lama_komentar_pencapaian_outcomes` | `text` |  |
| `lama_komentar_pelaksanaan_kuliah` | `text` |  |
| `lama_komentar_refleksi` | `text` |  |
| `lama_komentar_rencana_tindak_lanjut` | `text` |  |
| `lama_komentar_rekomendasi` | `text` |  |

### `analitik.v_akademik_jenis_dan_sifat_matkul` (under `analitik` schema, **publik / Group A — no row filter**)

> **⚠️ Routing note:** `analitik.v_akademik_kelas` now carries summarized array columns (`kode_jenis_list`, `nama_jenis_list`, `nama_paket_list`, `kode_sifat_list`, `is_wajib_itb`) for jenis/sifat MK — for most queries those are sufficient and no join is needed. Join to `analitik.v_akademik_jenis_dan_sifat_matkul` via `mata_kuliah_id` and `no_prodi` only when the per-paket detail (`paket_id`, `struktur_id`, `sumber`) is required.

Jenis dan sifat MK dalam struktur kurikulum. Grain: 1 baris = 1 (mata_kuliah_id, no_ps, paket/struktur). Satu MK bisa >1 baris jika masuk ke >1 paket dalam prodi yang sama. Sumber: kur24.* (kode_sifat C=Wajib/E=Pilihan) UNION kurikulum.* (W=C, P=E). Kolom filter: jenjang, no_prodi, kode_fakultas, tahun_kurikulum. nama_prodi_id/en dan nama_fakultas_id/en tersedia untuk display/label.

| Column | Type | Notes |
|--------|------|-------|
| `mata_kuliah_id` | `integer` | PK component |
| `no_prodi` | `integer` | Prodi identifier |
| `kode_prodi` | `varchar` | Prodi code abbreviation |
| `jenjang` | `varchar` | Degree level |
| `nama_prodi_id` | `text` | Prodi name |
| `nama_prodi_en` | `text` | Prodi name |
| `kode_fakultas` | `varchar` | Faculty code |
| `nama_fakultas_id` | `text` | Faculty name |
| `nama_fakultas_en` | `text` | Faculty name |
| `tahun_kurikulum` | `integer` | Curriculum year |
| `sumber` | `varchar` | Source |
| `paket_id` | `integer` | PK component |
| `struktur_id` | `integer` | PK component |
| `kode_jenis` | `varchar` | PK component |
| `nama_jenis` | `text` | PK component |
| `nama_paket` | `text` | PK component |
| `kode_sifat` | `varchar` | PK component |
| `is_wajib_itb` | `boolean` | PK component |

---

### `analitik.v_info_umum_kelas_matkul` (**publik / Group A — no row filter**)

**Granularity: 1 row = 1 class.** Lookup kelas/MK/dosen/prodi tanpa nilai/kehadiran/skor (versi `v_akademik_kelas` tanpa kolom evaluasi & RLS).

| Column | Type | Notes |
|--------|------|-------|
| `kelas_id`, `mata_kuliah_id`, `no_kelas`, `semester`, `tahun`, `tahun_ajaran` | — | Identitas kelas |
| `kode_matkul`, `nama_matkul_id` / `nama_matkul_en`, `sks`, `tahun_kurikulum`, `jenis_nilai` | — | Info MK |
| `no_prodi`, `kode_prodi`, `nama_prodi_id` / `nama_prodi_en`, `jenjang` | — | Prodi |
| `kode_fakultas`, `nama_fakultas_id` / `nama_fakultas_en` | — | Fakultas |
| `semua_dosen_id`, `semua_dosen_nama_gelar` | `integer[]` / `text[]` | `[0]` = dosen utama |
| `kode_jenis_list`, `nama_jenis_list`, `nama_paket_list`, `kode_sifat_list` | array | `NULL` jika MK tidak terdaftar di kurikulum |
| `is_wajib_itb` | `boolean` | Dari kurikulum lama |

---

### `analitik.v_info_umum_institusi` (**publik / Group A — no row filter**)

**Granularity: 1 row = (no_prodi, semester, tahun).** Jumlah kelas/MK/dosen/mahasiswa aktif per prodi per semester.

| Column | Type | Notes |
|--------|------|-------|
| `no_prodi`, `kode_prodi`, `nama_prodi_id` / `nama_prodi_en`, `jenjang`, `kode_fakultas`, `nama_fakultas_id` / `nama_fakultas_en`, `semester`, `tahun`, `tahun_ajaran` | — | Dimensi |
| `jumlah_kelas` | `bigint` | |
| `jumlah_matkul_aktif` | `bigint` | |
| `jumlah_dosen_aktif` | `bigint` | |
| `jumlah_mahasiswa_aktif` | `bigint` | |

---

### `analitik.v_info_umum_dosen` (**publik / Group A — no row filter**)

**Granularity: 1 row = (dosen_id, semester, tahun).** Beban mengajar dosen + daftar prodi/MK diajar, tanpa skor evaluasi (skor evaluasi ada di `v_akademik_statistik_dosen`, filtered+masked).

| Column | Type | Notes |
|--------|------|-------|
| `dosen_id`, `semester`, `tahun` | — | PK |
| `nama_dosen_gelar`, `nip`, `kk_id`, `kode_fakultas_dosen`, `no_prodi`, `kode_prodi` | — | Identitas / homebase |
| `jumlah_kelas`, `jumlah_matkul`, `total_sks_diajar` | `bigint` | Beban mengajar |
| `kode_matkul_list`, `no_prodi_diajar`, `kode_prodi_diajar` | array | MK/prodi yang diajar |

---

### `analitik.v_info_umum_wisuda` (**publik / Group A — no row filter**)

**Granularity: 1 row = (no_prodi, periode_ijazah_id_final, periode_seremoni_id).** Jumlah responden survei wisudawan per prodi per periode.

| Column | Type | Notes |
|--------|------|-------|
| `no_prodi`, `kode_prodi`, `nama_prodi_id` / `nama_prodi_en`, `jenjang`, `kode_fakultas`, `nama_fakultas_id` / `nama_fakultas_en` | — | Prodi/fakultas |
| `periode_ijazah_id_final`, `tahun_ijazah`, `bulan_ijazah` | — | Periode ijazah |
| `periode_seremoni_id`, `tahun_seremoni`, `bulan_seremoni`, `nama_seremoni`, `is_seremoni_asumtif` | — | Periode seremoni (saat ini semua `is_seremoni_asumtif = TRUE`, data dummy) |
| `jumlah_responden` | `bigint` | `COUNT(DISTINCT response_id)` — jumlah pengisi survei, BUKAN jumlah lulusan riil |

---

## Schema: `referensi` — Lookup / Reference Data

**Relevance: MAYBE (context enrichment)**
Contains static reference tables used across the SIX system. Useful for resolving codes to human labels.

Relevant tables:

| Table | Purpose |
|-------|---------|
| `referensi.semester` | Semester label lookup |
| `referensi.tahun_semester` | Valid (tahun, semester) combinations |
| `referensi.bobot_nilai` | Grade weight mapping (A=4.0, AB=3.5, etc.) |
| `referensi.strata` | Jenjang code to label |
| `referensi.kehadiran` | Attendance status codes |

Not relevant: `agama`, `gol_darah`, `bank`, `kota`, `provinsi`, `negara`, `slta`, and most others.

---

## Schema: `kurikulum` — Curriculum Structure

**Relevance: MAYBE (context enrichment)**
Useful for querying which courses belong to which curriculum structure, prerequisite relationships, and learning outcomes. Not required for primary analytics but may support diagnostic queries.

| Table | Purpose |
|-------|---------|
| `kurikulum.struktur` | Curriculum structure (which courses are in which program) |
| `kurikulum.silabus` | Syllabus entries |
| `kurikulum.outcomes_prodi` | Program learning outcomes |
| `kurikulum.status` | Curriculum status per prodi |
| `kurikulum.akreditasi_prodi` | Accreditation records |

---

## Schema: `kur24` — 2024 Curriculum (New)

Schema baru untuk kurikulum berbasis OBE (Outcome-Based Education) yang berlaku mulai 2024. Menggunakan konsep PEO (Program Educational Objective), CPL (Capaian Pembelajaran Lulusan), Sub-CPL, CPMK, dan Paket Program.
 
### Relasi Antar Tabel `kur24`
 
```
kur24.kurikulum (per prodi per th_kur)
    ├── kur24.cpl          (CPL per kurikulum)
    │       └── kur24.sub_cpl   (Sub-CPL per CPL)
    │               └── kur24.cpmk_subcpl (mapping CPMK → Sub-CPL)
    ├── kur24.peo          (Program Educational Objectives)
    └── kur24.paket        (Paket program/track)
            └── kur24.paket_mk  (MK dalam paket)
                    └── kur24.relasi_mk (relasi antar MK)
 
kur24.cpmk  (per mata_kuliah_id, lintas kurikulum)
    └── kur24.cpmk_subcpl
 
kur24.rpmk  (Rencana Pembelajaran MK per mata_kuliah_id)
```
 
---
 
### `kur24.kurikulum`
Curriculum definition PER PRODI (anchor tabel `kur24`).
 
| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `kurikulum_id` | `integer` PK | ID kurikulum |
| `no_ps` | `integer` FK | FK → `utama.program_studi.no_ps` |
| `th_kur` | `integer` | Tahun kurikulum, mis. `2024` |
| `nama` | `jsonb` | Nama kurikulum dua bahasa |
| `tgl_aktif` | `date` | Tanggal mulai berlaku |
| `active` | `boolean` | `true` = kurikulum aktif |
 
---
 
### `kur24.cpl`
Capaian Pembelajaran Lulusan per kurikulum. 1 kurikulum can have multiple CPL.
 
| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `cpl_id` | `integer` PK | ID CPL |
| `kurikulum_id` | `integer` FK | FK → `kur24.kurikulum.kurikulum_id` |
| `nama` | `jsonb` | Deskripsi CPL dua bahasa |
| `weight` | `integer` | Urutan tampil |
| `active` | `boolean` | `true` = aktif |
 
---
 
### `kur24.sub_cpl`
Sub-CPL — derivative of CPL - only minor part of CPL has this.
 
| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `sub_cpl_id` | `integer` PK | ID Sub-CPL |
| `cpl_id` | `integer` FK | FK → `kur24.cpl.cpl_id` |
| `nama` | `jsonb` | Deskripsi Sub-CPL dua bahasa |
| `weight` | `integer` | Urutan tampil |
| `active` | `boolean` | `true` = aktif |
 
---
 
### `kur24.cpmk`
Capaian Pembelajaran Mata Kuliah — capaian spesifik yang harus dicapai mahasiswa per MK.
 
| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `cpmk_id` | `integer` PK | ID CPMK |
| `mata_kuliah_id` | `integer` FK | FK → `utama.mata_kuliah.mata_kuliah_id` |
| `nama` | `jsonb` | Deskripsi CPMK dua bahasa |
| `weight` | `integer` | Urutan |
| `active` | `boolean` | `true` = aktif |
 
Sample query to get cpmk for certain mk on a prodi, always order by weight and nama:
```sql
SELECT cpmk.*, mk.kd_kuliah, mk.nama->>'id' AS nama_mk
FROM kur24.cpmk cpmk
JOIN utama.mata_kuliah mk ON mk.mata_kuliah_id = cpmk.mata_kuliah_id
order by cpmk.mata_kuliah_id , cpmk.weight 
```
---
 
### `kur24.cpmk_subcpl`
Mapping CPMK ke Sub-CPL beserta bobot kontribusi but the result is minimal. It is better to query cpmk directly to mk.
 
| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `sub_cpl_id` | `integer` FK | FK → `kur24.sub_cpl.sub_cpl_id` |
| `cpmk_id` | `integer` FK | FK → `kur24.cpmk.cpmk_id` |
| `bobot` | `integer` | Bobot kontribusi CPMK ke Sub-CPL (%) |
 
PK: `(sub_cpl_id, cpmk_id)`
 
---
 
### `kur24.peo`
Program Educational Objectives — tujuan program jangka panjang.
 
| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `peo_id` | `integer` PK | ID PEO |
| `kurikulum_id` | `integer` FK | FK → `kur24.kurikulum.kurikulum_id` |
| `nama` | `jsonb` | Deskripsi PEO dua bahasa |
| `weight` | `integer` | Urutan |
| `active` | `boolean` | `true` = aktif |
 

---
 
### `kur24.paket`
Paket program/track studi dalam suatu kurikulum.
 
| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `paket_id` | `integer` PK | ID paket |
| `no_ps` | `integer` FK | FK → `utama.program_studi.no_ps` |
| `th_kur` | `integer` | Tahun kurikulum |
| `kd_jenis` | `char(1)` FK | Tipe paket → `kur24.ref_jenis_paket` |
| `nama` | `jsonb` | Nama paket dua bahasa |
| `deskripsi` | `jsonb` | Deskripsi paket |
| `sks` | `smallint` | Total SKS paket |
| `tgl_aktif` | `date` | Tanggal aktif |
| `active` | `boolean` | `true` = aktif |
| `syarat` | `jsonb` | Syarat pendaftaran paket |
 
---
 
### `kur24.paket_mk`
MK yang termasuk dalam suatu paket program.
 
| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `paket_id` | `integer` FK | FK → `kur24.paket.paket_id` |
| `mata_kuliah_id` | `integer` FK | FK → `utama.mata_kuliah.mata_kuliah_id` |
| `kd_sifat` | `char(1)` | `'W'` = wajib dalam paket, `'P'` = pilihan |
| `semester_kur` | `integer` | Semester rencana dalam paket |
| `no_urut_kur` | `integer` | Urutan dalam paket |
 
PK: `(paket_id, mata_kuliah_id)`
 
---
 
### `kur24.relasi_mk`
Relasi antar MK (prasyarat, ekuivalensi, dll.) dalam konteks kurikulum 2024.
 
| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `relasi_id` | `integer` PK | ID relasi |
| `mata_kuliah_id` | `integer` FK | MK yang memiliki relasi |
| `mata_kuliah_id_relasi` | `integer` FK | MK yang menjadi target relasi |
| `no_ps` | `integer` FK | Prodi konteks relasi ini (nullable = berlaku umum) |
| `kd_relasi` | `char(1)` FK | Tipe relasi → `kur24.ref_relasi_mk` |
 
---
 
### `kur24.rpmk`
Rencana Pembelajaran Mata Kuliah (kurikulum 2024).
 
| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `mata_kuliah_id` | `integer` PK | FK → `utama.mata_kuliah.mata_kuliah_id` |
| `silabus` | `jsonb` | Silabus ringkas, default `[]` |
| `silabus_lengkap` | `jsonb` | Silabus lengkap per pertemuan |
| `kajian` | `jsonb` | Kajian/topik utama yang diajarkan |
| `metode` | `jsonb` | Metode pembelajaran |
| `kegiatan` | `jsonb` | Rencana kegiatan pembelajaran |
| `modalitas` | `jsonb` | Modalitas (tatap muka, daring, dll.) |
| `penilaian` | `jsonb` | Skema penilaian |
| `outcomes` | `jsonb` | CPMK yang dipetakan |
| `evaluasi` | `jsonb` | Instrumen evaluasi |
| `catatan` | `jsonb` | Catatan pengembang |
 
---
 
### `kur24.reg_paket`
Registrasi mahasiswa ke paket program (pendaftaran track/jalur studi).
 
| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `reg_id` | `integer` PK | ID registrasi |
| `mahasiswa_id` | `integer` FK | FK → `utama.mahasiswa.mahasiswa_id` |
| `paket_id` | `integer` FK | FK → `kur24.paket.paket_id` |
| `ts_submit` | `timestamptz` | Waktu pengajuan |
| `kd_approve_wali` | `char(1)` | Status persetujuan dosen wali |
| `kd_approve_host` | `char(1)` | Status persetujuan prodi tujuan |
| `kd_status` | `char(1)` | Status aktif registrasi |
| `ts_start` | `timestamptz` | Waktu mulai aktif di paket |
| `ts_quit` | `timestamptz` | Waktu keluar dari paket |
| `ts_completed` | `timestamptz` | Waktu selesai/lulus paket |
 
---
 
### `kur24.skema_program`
Definisi skema/jenis program studi (S1 reguler, S1 internasional, dll.).
 
| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `skema_id` | `integer` PK | ID skema |
| `kd_strata` | `char(2)` | Jenjang: `"S1"`, `"S2"`, `"S3"` |
| `kd_jenis` | `char(1)` | Jenis program |
| `nama` | `jsonb` | Nama skema |
| `deskripsi` | `jsonb` | Deskripsi |
| `deskripsi_struktur` | `jsonb` | Deskripsi struktur program |
| `active` | `boolean` | `true` = aktif |
 
---
 
### Tabel Referensi `kur24`
 
| Tabel | Keterangan |
|-------|-----------|
| `kur24.ref_jenis_paket` | Lookup tipe paket (`kd_jenis char(1)`, `nama jsonb`, `semester boolean`) |
| `kur24.ref_relasi_mk` | Lookup tipe relasi antar MK (`kd_relasi char(1)`, `nama jsonb`, `deskripsi jsonb`) |
| `kur24.ref_depth_kajian` | Kedalaman kajian MK (`kd_depth char(1)`, `nama jsonb`) |
| `kur24.ref_muatan_mk` | Muatan/kategori MK dalam kurikulum (`kd_muatan integer`, `kategori varchar`, `nama jsonb`) |

---

## Deprecated / Temporary / Inactive Schemas

These schemas must not be queried by the analytics agent.

**`__*` schemas** (`__kelas`, `__mahasiswa`, `__utama`, etc.): Legacy backup snapshots of the corresponding live schemas. Data is stale. Identical structure to live schemas but read from a snapshot state.

**`tmp` schema**: Contains ~60+ ad-hoc migration and operation tables. All are transient. Naming conventions include date suffixes (e.g., `tmp.kelas_kelas_20241`). No stable schema.

**`x_*` schemas** (`x_hris`, `x_pddikti`, `x_kemahasiswaan`, `x_sibpp`): Data synchronized to/from external government and HR systems. Read-only integration tables; structure mirrors external APIs, not SIX internal models.

**`v_*` schemas** (`v_ditkeu`, `v_ditpeg`, `v_myitb`, `v_pddikti`, etc.): Views exposed to external consumers. Contain no tables of value beyond what the source schemas already provide.

**`template` schema**: Abstract base table definitions. `template.entry` is the base inherited by most SIX tables (provides `ts_entri` and `user_id_entri` audit columns). Not queryable directly.

---

## Application State Tables

The following tables exist in `dev_six` under the `analitik` schema for the analytics system's own state:

| Table | Purpose |
|-------|---------|
| `analitik.llm_analysis_cache` | SHA256-keyed LLM narrative cache; includes `refreshed_at` for invalidation on `analitik_mv` refresh |
| `analitik.vector_chunks` | pgvector embeddings for portfolio text from `evaluasi.portofolio.isian` and `komentar` |
| `analitik.mv_refresh_log` | Tracks last refresh timestamp of `analitik_mv.*`; used to invalidate stale `llm_analysis_cache` entries |

The 13 `analitik.*` views (5 public + 8 `SECURITY DEFINER`-backed) and their underlying `analitik_mv.*` materialized views are already created — see "Analytics Views" section.

The existing `users.user` and `users.user_role` tables in SIX cover authentication and role assignment — no separate `pengguna` or `user_scope` table is needed.

---

## Key Domain Mappings (Schema → Prior Design)

The prior `SCHEMA_REFERENCE.md` used a custom schema design. The actual SIX tables map as follows:

| Prior Design | Actual SIX Table | Notes |
|---|---|---|
| `kelas` (public) | `kelas.kelas` | Different schema prefix |
| `pengajar_kelas` | `kelas.pengajar` | |
| `mata_kuliah` | `utama.mata_kuliah` | `kode_matkul` = `kd_kuliah`, UUID PK → INTEGER |
| `program_studi` | `utama.program_studi` | `prodi_id` → `no_ps` which is `no_prodi` (INTEGER), `kode_prodi` → `kd_ps` |
| `fakultas` | `utama.fakultas` | `fakultas_id` → `kd_fak` (VARCHAR), `nama_fakultas` → `nama->>'id'` or `nama->>'en'` |
| `dosen` | `utama.dosen` | `dosen_id` is INTEGER not UUID, `nama_gelar` is GENERATED column |
| `kelompok_keahlian` | `utama.kk` | |
| `distribusi_nilai` | `mahasiswa.kuliah` | No separate table; computed via COUNT FILTER |
| `skor_kuesioner` | `evaluasi.nilai_kelas.kuesioner` (JSONB) | Q-number is a string key, not a column |
| `teks_portofolio` | `analitik.v_akademik_portofolio` or `evaluasi.portofolio.isian` (JSONB) | JSONB keyed by `kd_pertanyaan` |
| `komentar_mahasiswa` | `analitik.v_akademik_komentar_mahasiswa` or raw through `evaluasi.portofolio.isian` with `kd_pertanyaan = 103` | |
| `pengguna` | `users.user` | |
| `user_scope` | `users.user_role` (multi-row) | One user, many roles, each with `scope` and `ts_valid` |
| `jenis_nilai = 'ABCDE'` | `kd_penilaian = 'A'` | |
| `jenis_nilai = 'Pass/Fail'` | `kd_penilaian = 'P'` | |

---

**Gaps and limitations:**

1. **Portfolio free-text now in `analitik.v_akademik_portofolio`.** `evaluasi.portofolio.isian` is the raw source. `analitik.v_akademik_portofolio` is the recommended query surface — all text is HTML-stripped and all class dimensions are pre-joined. Use `analitik.v_akademik_komentar_mahasiswa` for student comments specifically.

3. **Q25/Q26/Q27 NULL for older semesters.** Data before the new questionnaire system contains `{}` in `evaluasi.nilai_dosen.kuesioner`. All dosen-specific Q scores will be NULL in `analitik.v_akademik_statistik_dosen` for historical data. Queries comparing trends must handle this.

4. **`avg_nilai_akhir` is unreliable.** `evaluasi.nilai_dosen.nilai_akhir` is inconsistently populated. Avoid this column for any meaningful metric.

5. **`jumlah_mahasiswa_aktif` is by home prodi.** Students enrolled in cross-prodi courses are not counted in the host prodi's `jumlah_mahasiswa_aktif`. This is correct for enrollment counts but may create confusion in queries mixing class-level and prodi-level student counts.

7. **RLS via `analitik.*` view layer, not `analitik_mv.*`.** `analitik_mv.*` has no RLS. Row/column filtering is enforced only when querying through `analitik.*`, via `SECURITY DEFINER` functions reading the `app.*` session variables (see "Analytics Views" section). Without these session variables set, all 8 Group B views return zero rows.

8. **Multi-role user scope resolution.** A user may hold valid roles at multiple scopes simultaneously (e.g., dekan at two faculties). The application must resolve which scope is active for a given request, or handle returning union results across all valid scopes.

# Schema Tabel: `evaluasi_wisudawan`

## Gambaran Umum

Schema ini menyimpan **data mentah hasil survey kepuasan wisudawan ITB** dalam bentuk yang dinormalisasi. Terdiri dari 4 tabel: 2 tabel referensi, 1 katalog pertanyaan, dan 1 tabel respons utama.

```
ref_grup_opsi ──┐
               ├──► ref_opsi
               └──► pertanyaan ──► respons
                                      │
                         FK ke: referensi.strata
                                 utama.fakultas
                                 utama.program_studi
                                 wisuda.periode_ijazah
```

### Keputusan Desain Penting

| # | Keputusan | Alasan |
|---|-----------|--------|
| 1 | Tidak `INHERITS (template.entry)` | Menunggu konfirmasi DSI ITB |
| 2 | Tidak ada FK ke `utama.mahasiswa` | Survey anonim |
| 3 | Surrogate PK `response_id SERIAL` | LimeSurvey ID bisa overlap antar export batch |
| 4 | `periode_ijazah_id` NULLABLE | 66.6% NULL di data aktual, tidak bisa diimputasi |
| 5 | Semua jawaban di satu kolom `jawaban JSONB` | Struktur pertanyaan sparse & conditional per strata/fakultas |
| 6 | Nilai jawaban disimpan sebagai INTEGER | Ordinal (Likert) dan nominal (kategoris) — kecuali free-text yang disimpan sebagai TEXT |

---

## Helper Tables: Pemetaan Periode Seremoni (Dummy / Sementara)

Tiga tabel berikut berfungsi sebagai **dummy mapping** untuk keperluan join periode wisuda ke seremoni. Ini adalah tabel sementara yang seharusnya digantikan oleh data asli dari schema `wisuda.*` setelah tersedia.

> **⚠️ Catatan Sementara:** Ketika data asli sudah tersedia di `wisuda.*`, ganti referensi tabel-tabel ini dengan:
> - `periode_ijazah_sementara` → `wisuda.periode_ijazah`
> - `periode_seremoni_sementara` → `wisuda.periode_seremoni`
> - `ijazah_to_seremoni` → `mahasiswa.wisuda` (tabel mapping wisuda asli)

### `evaluasi_wisudawan.periode_ijazah_sementara`

Menyimpan master periode ijazah (identik struktur dengan `wisuda.periode_ijazah`).

| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `periode_ijazah_id` | `INTEGER` PK | Format YYYYMM, misal `202502` |
| `tahun` | `INTEGER` | Tahun ijazah |
| `bulan` | `INTEGER` | Bulan ijazah |

### `evaluasi_wisudawan.periode_seremoni_sementara`

Menyimpan master periode seremoni wisuda.

| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `periode_seremoni_id` | `INTEGER` PK | ID unik seremoni |
| `nama_seremoni` | `TEXT` | Nama resmi seremoni wisuda |
| `tahun` | `INTEGER` | Tahun seremoni |
| `bulan` | `INTEGER` | Bulan seremoni |

### `evaluasi_wisudawan.ijazah_to_seremoni`

Tabel mapping: 1 periode_ijazah dapat dipetakan ke 1 periode_seremoni.

| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `periode_ijazah_id` | `INTEGER` FK | → `periode_ijazah_sementara.periode_ijazah_id` |
| `periode_seremoni_id` | `INTEGER` FK | → `periode_seremoni_sementara.periode_seremoni_id` |

PK: `(periode_ijazah_id, periode_seremoni_id)`

Digunakan oleh ketiga MV wisudawan untuk menambahkan kolom seremoni (`periode_seremoni_id`, `nama_seremoni`, `tahun_seremoni`, `bulan_seremoni`) ke setiap baris.

---

## Tabel 1: `ref_grup_opsi`

**Tujuan:** Mendefinisikan *jenis* skala jawaban — apakah ordinal (bisa di-AVG) atau nominal (tidak boleh di-AVG).

### Atribut

| Kolom | Tipe | Nullable | Keterangan |
|-------|------|----------|------------|
| `kd_grup_opsi` | `VARCHAR(30)` | NOT NULL | **Primary Key.** Kode unik set opsi. |
| `nama` | `JSONB` | NOT NULL | Nama set dalam dua bahasa: `{"id": "...", "en": "..."}`. |
| `tipe` | `CHAR(1)` | NOT NULL | `'O'` = Ordinal (boleh AVG/STDDEV). `'N'` = Nominal (hanya frekuensi/distribusi). |
| `active` | `BOOLEAN` | NOT NULL | Default `true`. Set ke `false` jika skala tidak lagi digunakan. |
| `ts_entry` | `TIMESTAMPTZ` | NOT NULL | Timestamp insert, default `now()`. |
| `user_id_entry` | `INTEGER` | NOT NULL | ID user yang menginsert (referensi ke `users.user`, belum ada FK eksplisit). |

### Data yang Tersedia 

| `kd_grup_opsi` | `nama` | `tipe` |
|------------|----------|------------|
| `SETUJU` | {"en": "4-point Agreement", "id": "Persetujuan 4-poin"} | O |
| `FREKUENSI` | {"en": "4-point Frequency", "id": "Frekuensi 4-poin"} | O |
| `HARAPAN` | {"en": "5-point Expectation Fulfillment", "id": "Pemenuhan Harapan 5-poin"} | O |
| `HARAPAN_FSRD` | {"en": "5-point Expectation Fulfillment (FSRD)", "id": "Pemenuhan Harapan 5-poin (FSRD)"} | O |
| `PERKEMBANGAN_SBM` | {"en": "5-point Level of Development (SBM)", "id": "Tingkat Perkembangan 5-poin (SBM)"} | O |
| `YA_TIDAK` | {"en": "Yes/No", "id": "Ya/Tidak"} | N |
| `LOKASI_STUDI_LANJUT` | {"en": "Further Study Location", "id": "Lokasi Studi Lanjut"} | N |
| `BIDANG_STUDI_LANJUT` | {"en": "Field of Study Continuation", "id": "Kelanjutan Bidang Studi"} | N |
| `REKOMENDASI_PRODI` | {"en": "Study Program Recommendation", "id": "Rekomendasi Prodi"} | N |

> ⚠️ **Penting untuk Text-to-SQL & analitik:** Hanya set dengan `tipe = 'O'` yang boleh di-AVG atau di-STDDEV. Set `tipe = 'N'` hanya boleh dihitung frekuensinya (COUNT/distribusi).

---

## Tabel 2: `ref_opsi`

**Tujuan:** Menyimpan label teks untuk setiap nilai jawaban per grup opsi jawaban.

### Atribut

| Kolom | Tipe | Nullable | Keterangan |
|-------|------|----------|------------|
| `kd_grup_opsi` | `VARCHAR(30)` | NOT NULL | **Part of PK.** FK ke `ref_grup_opsi(kd_grup_opsi)`. |
| `nilai` | `SMALLINT` | NOT NULL | **Part of PK.** Angka jawaban yang tersimpan di `respons.jawaban`. |
| `label` | `JSONB` | NOT NULL | Teks opsi dalam dua bahasa: `{"id": "...", "en": "..."}`. |
| `ts_entry` | `TIMESTAMPTZ` | NOT NULL | Timestamp insert. |
| `user_id_entry` | `INTEGER` | NOT NULL | ID user yang menginsert. |

**Primary Key:** `(kd_grup_opsi, nilai)`

### Referensi Nilai per Set Opsi

#### `SETUJU` — 4-poin Persetujuan
| Nilai | Label (ID) | Label (EN) |
|-------|-----------|-----------|
| 1 | Tidak Setuju | Disagree |
| 2 | Cenderung Tidak Setuju | Somewhat Disagree |
| 3 | Cenderung Setuju | Somewhat Agree |
| 4 | Setuju | Agree |

#### `FREKUENSI` — 4-poin Frekuensi
| Nilai | Label (ID) | Label (EN) |
|-------|-----------|-----------|
| 1 | Tidak pernah atau sama sekali tidak | Never |
| 2 | Jarang atau kecil | Rarely |
| 3 | Sering atau cukup | Often |
| 4 | Selalu atau besar | Always |

#### `HARAPAN` — 5-poin Pemenuhan Harapan (D2/U07)
| Nilai | Label (ID) | Label (EN) |
|-------|-----------|-----------|
| 1 | Tidak sesuai harapan | Does not meet expectations |
| 2 | Ada yang memenuhi harapan | Partially meets expectations |
| 3 | Sebagian besar memenuhi harapan | Mostly meets expectations |
| 4 | Sepenuhnya memenuhi harapan | Fully meets expectations |
| 5 | Melampaui harapan | Exceeds expectations |

#### `HARAPAN_FSRD` — 5-poin Pemenuhan Harapan (Section J/FSRD)
| Nilai | Label (ID) | Label (EN) |
|-------|-----------|-----------|
| 1 | Tidak sesuai harapan | Does not meet expectations |
| 2 | Ada yang memenuhi harapan | Partially meets expectations |
| 3 | Sebagian besar memenuhi harapan | Mostly meets expectations |
| 4 | Memenuhi harapan | Meets expectations |
| 5 | Melampaui harapan | Exceeds expectations |

> ⚠️ **FSRD vs D2:** Nilai-4 berbeda label antara `HARAPAN` dan `HARAPAN_FSRD`. Jangan gabungkan skor kedua skala ini dalam satu agregasi tanpa normalisasi terlebih dahulu.

#### `PERKEMBANGAN_SBM` — 5-poin Tingkat Perkembangan (Section K/SBM)
| Nilai | Label (ID) | Label (EN) |
|-------|-----------|-----------|
| 1 | Undeveloped – Tidak berkembang | Undeveloped |
| 2 | Slightly Developed – Sedikit berkembang | Slightly Developed |
| 3 | Moderately Developed – Cukup berkembang | Moderately Developed |
| 4 | Substantially Developed – Berkembang secara substansial | Substantially Developed |
| 5 | Highly Developed – Berkembang dengan sangat tinggi | Highly Developed |

#### `YA_TIDAK`
| Nilai | Label |
|-------|-------|
| 1 | Ya / Yes |
| 2 | Tidak / No |

#### `LOKASI_STUDI_LANJUT`
| Nilai | Label (ID) |
|-------|-----------|
| 1 | ITB |
| 2 | Perguruan tinggi dalam negeri selain ITB |
| 3 | Di luar negeri |
| 4 | Tidak ada rencana studi lanjut |

#### `BIDANG_STUDI_LANJUT`
| Nilai | Label (ID) Ringkas |
|-------|-------------------|
| 1 | Ya, kelanjutan bidang studi ITB |
| 2 | Tidak, tapi masih serumpun |
| 3 | Tidak, tapi masih butuh pengetahuan ITB |
| 4 | Tidak, sangat berbeda |
| 5 | Tidak ada rencana studi lanjut |

#### `OPT_U02` — Rekomendasi Prodi
| Nilai | Label (ID) |
|-------|-----------|
| 1 | Kualitas dosen |
| 2 | Suasana akademik |
| 3 | Jejaring alumni |
| 4 | Lapangan pekerjaan |
| 5 | Fasilitas akademik |
| 6 | Tidak merekomendasikan |
| 7 | Other (teks bebas di key `U02_other`) |

### Cara Query Label dari Jawaban

```sql
-- Decode jawaban nominal/ordinal ke teks
SELECT
    r.response_id,
    p.pertanyaan->>'id'  AS pertanyaan,
    o.label->>'id'       AS jawaban_teks,
    (r.jawaban ->> p.kd_pertanyaan)::SMALLINT AS jawaban_nilai
FROM evaluasi_wisudawan.respons r
JOIN evaluasi_wisudawan.pertanyaan p ON r.jawaban ? p.kd_pertanyaan
JOIN evaluasi_wisudawan.ref_opsi o
    ON o.kd_grup_opsi = p.kd_grup_opsi
   AND o.nilai = (r.jawaban ->> p.kd_pertanyaan)::SMALLINT
WHERE p.kd_pertanyaan = 'U03_SQ001';
```

---

## Tabel 3: `pertanyaan`

**Tujuan:** Katalog lengkap 137 pertanyaan valid — metadata tiap butir kuesioner, termasuk skala yang digunakan dan batasan populasi (strata/fakultas mana yang menjawab pertanyaan ini).

### Atribut

| Kolom | Tipe | Nullable | Keterangan |
|-------|------|----------|------------|
| `kd_pertanyaan` | `VARCHAR(20)` | NOT NULL | **Primary Key.** Kode pertanyaan, contoh: `'U03_SQ001'`, `'G01Q23'`, `'S101'`. |
| `header_csv_raw` | `VARCHAR(500)` | NULL | Header pertanyaan dari CSV LimeSurvey |
| `kd_grup_pertanyaan` | `VARCHAR(15)` | NOT NULL | Prefix grup LimeSurvey, contoh: `'U03'`, `'FSRD01'`, `'SBM01'`. Bukan FK. |
| `pertanyaan` | `JSONB` | NOT NULL | Teks pertanyaan bilingual: `{"id": "...", "en": "..."}`. |
| `kd_grup_opsi` | `VARCHAR(30)` | NULL | FK ke `ref_grup_opsi(kd_grup_opsi)`. `NULL` = pertanyaan free-text. |
| `batasan` | `JSONB` | NULL | `NULL` = universal. Lihat tabel batasan di bawah. |
| `urutan` | `SMALLINT` | NULL | Urutan tampil dalam grup. |
| `active` | `BOOLEAN` | NOT NULL | Default `true`. |
| `ts_entry` | `TIMESTAMPTZ` | NOT NULL | Timestamp insert. |
| `user_id_entry` | `INTEGER` | NOT NULL | ID user yang menginsert. |

to get answer type : null (free text), not null (see kd_grup_opsi)
### Makna Kolom `batasan`

| Nilai `batasan` | Berlaku untuk |
|-----------------|---------------|
| `NULL` | Semua strata & semua fakultas (universal) |
| `{"strata": ["S1"]}` | Hanya strata S1 (Section G) |
| `{"strata": ["S2"]}` | Hanya strata S2 (Section H) |
| `{"strata": ["S3"]}` | Hanya strata S3 (Section I) |
| `{"fakultas": ["FSRD"]}` | Hanya fakultas FSRD (Section J) |
| `{"fakultas": ["SBM"]}` | Hanya fakultas SBM (Section K) |

> Strata PR tidak memiliki `batasan` khusus, namun PR hanya mengisi Section A–D (tidak ada section khusus PR di kuesioner).

### Breakdown 137 Pertanyaan per Section

| Section | Grup | Topik | Jml | Tipe | Populasi |
|---------|------|-------|-----|------|---------|
| **A** | U03 | Fasilitas & Kepuasan ITB | 12 | Likert SETUJU | Universal |
| **B** | U01 | Pendidikan di Program Studi | 12 | Likert SETUJU | Universal |
| **B** | U02 | Rekomendasi Prodi | 1 | Nominal OPT_U02 | Universal |
| **C1** | U04 | Kemampuan Softskills | 9 | Likert SETUJU | Universal |
| **C2** | U05 | Pengembangan Karakter | 7 | Likert SETUJU | Universal |
| **D1** | U06 | Permasalahan Selama Studi | 9 | Likert FREKUENSI | Universal |
| **D2** | U07 | Ketersediaan Dukungan | 4 | Likert HARAPAN | Universal |
| **E** | G10, G01 | Free-text Pengalaman Studi | 8 | Free-text | Universal |
| **F** | G11, G01 | Free-text Saran & Aspirasi | 6 | Free-text | Universal |
| **G** | S1 | Rencana Studi Lanjut + MKU | 7 | 3 Nominal + 4 Likert | Hanya S1 |
| **H** | M | Rencana Studi Lanjut S2 | 3 | Nominal | Hanya S2 |
| **I** | D01 | MKU untuk Doktor | 4 | Likert SETUJU | Hanya S3 |
| **J** | FSRD01–FSRD05 | Evaluasi Spesifik FSRD | 24 | Likert HARAPAN_FSRD | Hanya FSRD |
| **K** | SBM01 | Outcomes Program SBM | 31 | Likert PERKEMBANGAN_SBM | Hanya SBM |
| | | **Total** | **137** | | |

### Detail Pertanyaan per Section

#### Section A — Fasilitas & Kepuasan ITB (U03, 12 item)
Skala: `SETUJU` (1–4)

| `kd_pertanyaan` | Pertanyaan |
|-----------------|-----------|
| U03_SQ001 | Tersedia cukup ruang kelas |
| U03_SQ002 | Ruang kelas kondusif untuk pembelajaran |
| U03_SQ003 | Laboratorium kondusif untuk pembelajaran |
| U03_SQ004 | Akses internet memadai |
| U03_SQ005 | Fasilitas keprofesian memadai |
| U03_SQ006 | Akses perpustakaan memadai |
| U03_SQ007 | Perangkat pembelajaran up-to-date |
| U03_SQ008 | Fasilitas toilet memadai |
| U03_SQ009 | Fasilitas kantin memadai |
| U03_SQ010 | Fasilitas rekreasi/olahraga memadai |
| U03_SQ011 | Fasilitas kesehatan memadai |
| U03_SQ012 | Secara keseluruhan saya puas dengan fasilitas ITB |

#### Section B — Pendidikan di Program Studi (U01 + U02)
Skala: `SETUJU` untuk U01; `OPT_U02` (nominal) untuk U02

| `kd_pertanyaan` | Pertanyaan |
|-----------------|-----------|
| U01_SQ001 | Wali akademik selalu tersedia saat dibutuhkan |
| U01_SQ002 | Wali akademik membantu memenuhi persyaratan akademik |
| U01_SQ003 | Dosen berinteraksi secara informal dengan mahasiswa |
| U01_SQ004 | Dosen memperhatikan proses pembelajaran mahasiswa |
| U01_SQ005 | Dosen memiliki kemampuan profesional yang baik |
| U01_SQ006 | Matakuliah wajib memberikan dasar yang baik |
| U01_SQ007 | Matakuliah pilihan memberikan keleluasaan eksplorasi |
| U01_SQ008 | Praktikum sejalan dengan teori di kelas |
| U01_SQ009 | Sarana program studi memadai |
| U01_SQ010 | Program studi memberikan gambaran dunia kerja |
| U01_SQ011 | Saya menikmati bidang studi saya |
| U01_SQ012 | Saya akan memilih program studi yang sama lagi |
| U02 | Aspek yang paling ditonjolkan saat merekomendasikan prodi (nominal) |

#### Section C1 — Kemampuan Softskills (U04, 9 item)
Skala: `SETUJU`

`U04_SQ001` Komunikasi lisan · `U04_SQ002` Komunikasi tertulis · `U04_SQ003` Bahasa asing · `U04_SQ004` Penyelesaian masalah · `U04_SQ005` Berpikir kritis · `U04_SQ006` Introspeksi diri · `U04_SQ007` Menyampaikan pendapat · `U04_SQ008` Kerja tim · `U04_SQ009` Kerja mandiri

#### Section C2 — Pengembangan Karakter (U05, 7 item)
Skala: `SETUJU`

`U05_SQ001` Kejujuran · `U05_SQ002` Komitmen · `U05_SQ003` Kecerdasan emosi · `U05_SQ004` Kepedulian terhadap sesama · `U05_SQ005` Objektivitas · `U05_SQ006` Ketidakmudahan menyerah · `U05_SQ007` Kepatuhan terhadap aturan

#### Section D1 — Permasalahan Selama Studi (U06, 9 item)
Skala: `FREKUENSI` — nilai ≥ 2 berarti *pernah mengalami*

`U06_SQ001` Permasalahan akademis · `U06_SQ002` Keuangan · `U06_SQ003` Pengaruh keuangan ke akademis · `U06_SQ004` Psikologis · `U06_SQ005` Pengaruh psikologis ke studi · `U06_SQ006` Sosial budaya · `U06_SQ007` Pengaruh sosial budaya ke studi · `U06_SQ008` Kesehatan · `U06_SQ009` Pengaruh kesehatan ke studi

#### Section D2 — Ketersediaan Dukungan (U07, 4 item)
Skala: `HARAPAN` — hanya diisi oleh yang pernah mengalami masalah

`U07_SQ001` Ketersediaan beasiswa/pinjaman · `U07_SQ002` Bimbingan konseling · `U07_SQ003` Nasehat dari wali akademik · `U07_SQ004` Nasehat dari dosen matakuliah

#### Section E — Free-text Pengalaman Studi (8 item, universal)

| `kd_pertanyaan` | Topik |
|-----------------|-------|
| G10Q22 | Kebiasaan belajar |
| G01Q23 | Kesan dan prestasi dalam belajar |
| G01Q24 | Pengalaman lain yang sangat berkesan |
| G01Q25 | Aktivitas kemahasiswaan |
| G01Q26 | Cita-cita dalam karier |
| G01Q27 | Cita-cita dalam hidup |
| G01Q28 | Motto untuk sukses studi di ITB |
| G01Q29 | Sifat khas diri sendiri |

#### Section F — Free-text Saran & Aspirasi (6 item, universal)

| `kd_pertanyaan` | Topik |
|-----------------|-------|
| G11Q30 | Suka duka menempuh studi di ITB |
| G01Q31 | Segi positif studi di ITB |
| G01Q32 | Segi negatif studi di ITB |
| G01Q33 | Saran untuk perbaikan proses dan sarana pendidikan di ITB |
| G01Q34 | Saran untuk mahasiswa lain dalam menempuh studi di ITB |
| G01Q35 | Catatan atau komentar lain |

> Section E & F adalah sumber utama data RAG (Retrieval-Augmented Generation) untuk chatbot berbasis teks.

#### Section G — Rencana Studi Lanjut + MKU, khusus S1 (7 item)

| `kd_pertanyaan` | Topik | Skala |
|-----------------|-------|-------|
| S101 | Rencana melanjutkan ke pendidikan lebih tinggi | YA_TIDAK |
| S102 | Lokasi rencana studi lanjut | LOKASI_STUDI_LANJUT |
| S103 | Kelanjutan bidang studi | BIDANG_STUDI_LANJUT |
| S104_SQ001 | MKU ITB membekali softskill | SETUJU |
| S104_SQ002 | MKU ITB membekali hardskill | SETUJU |
| S104_SQ003 | MKU ITB membangun karakter | SETUJU |
| S104_SQ004 | MKU ITB memperluas wawasan | SETUJU |

#### Section H — Rencana Studi Lanjut, khusus S2 (3 item)

`M01` Rencana studi lanjut (YA_TIDAK) · `M02` Lokasi (LOKASI_STUDI_LANJUT) · `M03` Kelanjutan bidang (BIDANG_STUDI_LANJUT)

#### Section I — MKU untuk Doktor, khusus S3 (4 item, SETUJU)

`D01_SQ001` MKU membekali softskill · `D01_SQ002` MKU membekali hardskill · `D01_SQ003` MKU membangun karakter · `D01_SQ004` MKU memperluas wawasan

#### Section J — Evaluasi Spesifik FSRD (24 item, HARAPAN_FSRD, hanya FSRD)

| Grup | Topik | Jml |
|------|-------|-----|
| FSRD01 | Tahap Persiapan Bersama (TPB) | 5 |
| FSRD02 | Sistem Perwalian | 3 |
| FSRD03 | Mata Kuliah Teori | 6 |
| FSRD04 | Mata Kuliah Praktika/Studio | 6 |
| FSRD05 | Tugas Akhir | 4 |

#### Section K — Outcomes Program SBM (31 item, PERKEMBANGAN_SBM, hanya SBM)

31 kompetensi SBM01_SQ001–SQ031, mencakup: komunikasi, pengetahuan bisnis (marketing, operasi, HRM, keuangan, kewirausahaan), analisis data, riset bisnis, jejaring, kepemimpinan, tanggung jawab profesional & etis, pembelajaran seumur hidup.

---

## Tabel 4: `respons`

**Tujuan:** Tabel utama yang menyimpan satu baris per responden. Semua jawaban tersimpan dalam satu kolom `jawaban JSONB`.

### Atribut

| Kolom | Tipe | Nullable | Keterangan |
|-------|------|----------|------------|
| `response_id` | `SERIAL` | NOT NULL | **Primary Key.** Surrogate key internal. Auto-increment. |
| `survey_platform_response_id` | `INTEGER` | NULL | ID asli dari LimeSurvey. Bisa NULL jika tidak tercatat. UNIQUE jika NOT NULL (partial unique index). |
| `submit_date` | `TIMESTAMPTZ` | NULL | Waktu responden submit kuesioner. |
| `start_date` | `TIMESTAMPTZ` | NULL | Waktu responden mulai mengisi kuesioner. |
| `last_page` | `SMALLINT` | NULL | Halaman terakhir yang diisi. `11` = respons complete. |
| `kd_strata` | `CHAR(2)` | NOT NULL | Jenjang studi. FK ke `referensi.strata`. Nilai: `'S1'`, `'S2'`, `'S3'`, `'PR'`. |
| `kd_fak` | `VARCHAR` | NOT NULL | Kode fakultas. FK ke `utama.fakultas`. Contoh: `'STEI'`, `'SBM'`, `'FSRD'`. |
| `no_ps` | `INTEGER` | NOT NULL | Kode program studi. FK ke `utama.program_studi`. Contoh: `135` = Teknik Informatika S1. |
| `periode_ijazah_id` | `INTEGER` | **NULL** | FK ke `wisuda.periode_ijazah`. Format integer YYYYMM. **66.6% NULL** di data aktual. |
| `jawaban` | `JSONB` | NULL | Payload seluruh jawaban. Key = `kd_pertanyaan`. Lihat struktur di bawah. |
| `ts_entry` | `TIMESTAMPTZ` | NOT NULL | Timestamp insert ke database, default `now()`. |
| `user_id_entry` | `INTEGER` | NOT NULL | ID user yang melakukan import. |

### Sumber Nilai Setiap Atribut

| Kolom | Sumber Nilai |
|-------|-------------|
| `kd_strata` | `referensi.strata(kd_strata)` — nilai: S1, S2, S3, PR |
| `kd_fak` | `utama.fakultas(kd_fak)` — 14 fakultas/sekolah |
| `no_ps` | `utama.program_studi(no_ps)` — kode numerik 3 digit |
| `periode_ijazah_id` | `wisuda.periode_ijazah(periode_ijazah_id)` — nilai non-NULL aktual: 202502, 202504, 202507, 202509, 202602, 202604 |
| `jawaban` (nilai integer) | `ref_opsi(kd_grup_opsi, nilai)` — di-resolve saat query |
| `jawaban` (free-text) | Input langsung dari responden, disimpan as-is |

### Struktur `jawaban` JSONB

```jsonc
// Contoh respons S1 dari STEI:
{
  // Section A: Fasilitas ITB (Likert 1–4)
  "U03_SQ001": 4,
  "U03_SQ002": 3,

  // Section D1: Permasalahan (Likert 1–4)
  "U06_SQ004": 2,

  // Section D2: Dukungan (Likert 1–5)
  "U07_SQ001": 3,

  // Section B: Rekomendasi prodi (nominal)
  "U02": 1,               // 1 = "Kualitas dosen"

  // Section B: Free-text jika U02 = 7 (Other)
  "U02_other": "Lingkungan riset yang aktif",

  // Section E: Free-text
  "G01Q23": "Senang bisa belajar di ITB...",

  // Section G: S1-spesifik (nominal)
  "S101": 1,              // 1 = "Ya" (rencana studi lanjut)
  "S102": 1,              // 1 = "ITB"
  "S103": 1,              // 1 = "Kelanjutan bidang ITB"
  "S104_SQ001": 4         // Likert 1–4
}
```

**Aturan penting `jawaban`:**
- Hanya key yang **dijawab** yang ada dalam JSONB (sparse — tidak ada key dengan nilai NULL).
- Nilai ordinal & nominal disimpan sebagai **INTEGER**.
- Nilai free-text disimpan sebagai **TEXT string**.
- Key `U02_other` hanya muncul ketika `U02 = 7`.
- Responden strata PR hanya punya key dari Section A–D (tidak ada G/H/I/J/K).
- Responden FSRD punya key Section J (`FSRD01_SQ001` dst.), bukan Section K.
- Responden SBM punya key Section K (`SBM01_SQ001` dst.), bukan Section J.

---

## Panduan Penggunaan per Use Case

### 1. Dashboard Agregasi (Rata-rata Skor per Pertanyaan)

Gunakan **Materialized View** `analitik.v_wisudawan_statistik_pertanyaan` (lihat dokumen MV), bukan query langsung ke `respons`. Tabel `respons` adalah sumber data mentah.

Filter yang tersedia di `respons`: `kd_fak`, `no_ps`, `kd_strata`, `periode_ijazah_id`.

**Hierarki akses filter dashboard:**

| Level Pengguna | Filter Tersedia |
|----------------|-----------------|
| Admin / Institusi | Semua filter: fakultas, prodi, strata, tahun/periode wisuda |
| Dekanat & jajaran | Tanpa filter fakultas — scope dikunci ke `kd_fak` dekan |
| Kaprodi & jajaran | Tanpa filter prodi — scope dikunci ke `no_ps` kaprodi |

Implementasi di SQL: tambah `WHERE kd_fak = $fak` untuk dekanat, `WHERE no_ps = $ps` untuk kaprodi.

### 2. Agen Text-to-SQL — Contoh Query Tipikal

```sql
-- Rata-rata kepuasan fasilitas per fakultas (hanya S1)
SELECT
    kd_fak,
    ROUND(AVG((jawaban->>'U03_SQ012')::NUMERIC), 2) AS avg_kepuasan_fasilitas
FROM evaluasi_wisudawan.respons
WHERE kd_strata = 'S1'
  AND jawaban ? 'U03_SQ012'
GROUP BY kd_fak
ORDER BY avg_kepuasan_fasilitas DESC;

-- Distribusi rencana studi lanjut lulusan S1
SELECT
    (jawaban->>'S101')::SMALLINT AS nilai,
    o.label->>'id'               AS rencana,
    COUNT(*)                     AS n
FROM evaluasi_wisudawan.respons r
JOIN evaluasi_wisudawan.ref_opsi o
    ON o.kd_grup_opsi = 'YA_TIDAK'
   AND o.nilai = (r.jawaban->>'S101')::SMALLINT
WHERE r.kd_strata = 'S1'
  AND r.jawaban ? 'S101'
GROUP BY 1, 2
ORDER BY 1;

-- Persentase pernah alami masalah psikologis (U06_SQ004 >= 2)
SELECT
    kd_fak,
    ROUND(
        SUM(CASE WHEN (jawaban->>'U06_SQ004')::SMALLINT >= 2 THEN 1 ELSE 0 END)
        * 100.0 / COUNT(*), 1
    ) AS pct_pernah_masalah_psikologis
FROM evaluasi_wisudawan.respons
WHERE jawaban ? 'U06_SQ004'
GROUP BY kd_fak;
```

### 3. Agen RAG — Akses Free-text

Free-text dari Section E & F adalah sumber utama untuk chatbot berbasis RAG.

```sql
-- Ambil semua saran untuk ITB dari responden FTSL S1
SELECT
    response_id,
    kd_fak,
    kd_strata,
    jawaban->>'G01Q33' AS saran_perbaikan,
    jawaban->>'G01Q34' AS saran_untuk_mahasiswa
FROM evaluasi_wisudawan.respons
WHERE kd_fak = 'FTSL'
  AND kd_strata = 'S1'
  AND (jawaban ? 'G01Q33' OR jawaban ? 'G01Q34');
```

Untuk RAG, **index full-text atau embedding vector** sebaiknya dibangun di atas konten free-text dari kolom `jawaban` (key G-series). Gunakan `analitik.v_wisudawan_jawaban_responden` yang sudah memisahkan kolom free-text untuk kemudahan akses.

### 4. Query Katalog Pertanyaan (untuk System Prompt Agen)

```sql
-- Daftar semua pertanyaan dengan tipe skala dan populasi
SELECT
    p.kd_pertanyaan,
    p.kd_grup,
    p.pertanyaan->>'id'    AS pertanyaan_id,
    p.kd_grup_opsi,
    s.tipe                 AS tipe_opsi,
    p.batasan
FROM evaluasi_wisudawan.pertanyaan p
LEFT JOIN evaluasi_wisudawan.ref_grup_opsi s ON s.kd_grup_opsi = p.kd_grup_opsi
WHERE p.active = true
ORDER BY p.kd_grup, p.urutan;
```

---

## Catatan Penting untuk Developer

### ETL dari CSV LimeSurvey

1. **Ordinal Likert:** konversi teks label → integer via `ref_opsi.label` (kd_grup_opsi ordinal).
2. **Nominal:** konversi teks label → integer via `ref_opsi.label` (kd_grup_opsi nominal).
3. **Free-text:** simpan as-is sebagai TEXT string di JSONB.
4. **U02 = "Other":** simpan `{"U02": 7, "U02_other": "<teks bebas>"}`.
5. **Strata PR:** hanya isi Section A–D; key Section G/H/I/J/K tidak ada di JSONB-nya.

### Hal yang Tidak Boleh Dilakukan

- ❌ Jangan AVG kolom nominal (`tipe = 'N'`): `U02`, `S101`, `S102`, `S103`, `M01`, `M02`, `M03`.
- ❌ Jangan gabungkan skor D2 (`U07`, `HARAPAN`) dan Section J FSRD (`HARAPAN_FSRD`) dalam satu AVG — nilai-4 berbeda secara semantik.
- ❌ Jangan anggap `periode_ijazah_id = NULL` sebagai data hilang — 66.6% memang NULL dan tidak bisa diimputasi.
- ❌ Jangan filter `last_page = 11` sebagai satu-satunya filter "complete" — mayoritas data sudah complete.

---

# Schema Materialized View: `evaluasi_wisudawan`

> **Untuk:** Developer agen RAG, agen Text-to-SQL, dan dashboard Data Ulasan Wisudawan ITB  
> **File SQL:** `schema_mv_ulasan_wisudawan.sql`  
> **Prasyarat:** `schema_ulasan_wisudawan.sql` sudah dieksekusi terlebih dahulu  
> **Database:** `dev_six` (cloud DB ITB, schema `evaluasi_wisudawan`)

---

## Gambaran Umum

Tiga Materialized View (MV) ini adalah **lapisan analitik** di atas tabel `respons`. Masing-masing memiliki granularitas berbeda, dirancang untuk use case yang berbeda, dan tidak saling menggantikan. Ketiga MV ini sekarang berada di `analitik_mv.*` (raw, **dilarang diakses agen**) dan diakses agen melalui wrapper `analitik.v_wisudawan_*` (RLS via `SECURITY DEFINER` — lihat "Analytics Views").

```
respons (raw) ──────────────────────────────────────────────────────┐
                                                                    │
                     ┌──────────────────────────────────────────────┘
                     ▼
        ┌────────────────────────────────┐
        │   analitik.v_wisudawan_distribusi_jawaban        │  ← Distribusi & persentase
        │   1 baris per:                 │    per (periode, strata,
        │   (periode, strata, fak,       │    fak, pertanyaan, nilai)
        │    no_ps, pertanyaan, nilai)   │
        └────────────────────────────────┘

        ┌────────────────────────────────┐
        │   analitik.v_wisudawan_statistik_pertanyaan           │  ← Rata-rata skor ordinal
        │   1 baris per:                 │    per (periode, strata,
        │   (periode, strata, fak,       │    fak, no_ps, pertanyaan)
        │    no_ps, pertanyaan)          │
        └────────────────────────────────┘

        ┌────────────────────────────────┐
        │   analitik.v_wisudawan_jawaban_responden              │  ← Flat table per responden
        │   1 baris per responden        │    untuk RAG & Text-to-SQL
        │   Semua jawaban = kolom flat   │    individual
        └────────────────────────────────┘
```

### Kapan Menggunakan MV Mana?

| Kebutuhan | Gunakan MV |
|-----------|-----------|
| Grafik distribusi jawaban (bar chart), top-2-box, % setuju | `analitik.v_wisudawan_distribusi_jawaban` |
| Grafik rata-rata skor, ranking pertanyaan, trend per periode | `analitik.v_wisudawan_statistik_pertanyaan` |
| Query per responden, analisis individual, chatbot RAG, Text-to-SQL natural | `analitik.v_wisudawan_jawaban_responden` |
| AVG/STDDEV langsung dari data mentah | Query ke `respons` langsung |

---

## Strategi Refresh
```sql
-- Jalankan setelah setiap batch import CSV (target analitik_mv, bukan analitik):

-- 1. Distribusi jawaban (TANPA CONCURRENTLY)
REFRESH MATERIALIZED VIEW analitik_mv.mv_wisudawan_distribusi_jawaban;

-- 2. Skor rata-rata (TANPA CONCURRENTLY)
REFRESH MATERIALIZED VIEW analitik_mv.mv_wisudawan_statistik_pertanyaan;

-- 3. Wide respons (CONCURRENTLY aman — unique index hanya pada response_id SERIAL)
REFRESH MATERIALIZED VIEW CONCURRENTLY analitik_mv.mv_wisudawan_jawaban_responden;
```

> **Akses agen:** agen TIDAK pernah query `analitik_mv.*` di atas secara langsung. Agen selalu query lewat `analitik.v_wisudawan_*` (wrapper `SECURITY DEFINER`), yang otomatis mengikuti hasil refresh MV terbaru. **Row filter** untuk ketiga `v_wisudawan_*`: `kode_fakultas` utk dekan/jajaran_dekanat, `no_prodi` utk kaprodi/jajaran_prodi/dosen — lihat tabel RLS di bagian "Analytics Views". **Column masking:** tidak ada.

---

### `analitik.v_wisudawan_distribusi_jawaban`

## MV 1: `analitik.v_wisudawan_distribusi_jawaban`

**Tujuan:** Sumber tunggal untuk semua kebutuhan **distribusi & persentase jawaban** — bar chart, top-2-box, incidence rate. Mencakup pertanyaan ordinal (Likert) dan nominal (kategoris). Free-text otomatis dikecualikan.

**Granularitas:** 1 baris per kombinasi `(periode_ijazah_id, kd_strata, kd_fak, no_ps, kd_pertanyaan, nilai)`.

### Kolom

| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `periode_ijazah_id` | `INTEGER` | Periode wisuda (YYYYMM). NULL = tanpa info periode. |
| `tahun_ijazah` | `INTEGER` | |
| `bulan_ijazah` | `INTEGER` | |
| `periode_seremoni_id` | `INTEGER` | |
| `tahun_seremoni` | `INTEGER` | |
| `bulan_seremoni` | `INTEGER` | |
| `nama_seremoni` | `TEXT` | |
| `kode_fakultas` | `VARCHAR` | Kode fakultas. |
| `nama_fakultas_id` | `TEXT` | Nama fakultas. |
| `nama_fakultas_en` | `TEXT` | Nama fakultas. |
| `no_prodi` | `INTEGER` | Kode program studi. |
| `kode_prodi` | `VARCHAR(2)` | Singkatan program studi. |
| `nama_prodi_id` | `TEXT` | Nama program studi. |
| `nama_prodi_en` | `TEXT` | Nama program studi. |
| `jenjang` | `CHAR(2)` | Jenjang studi. |
| `kode_pertanyaan` | `VARCHAR(20)` | Kode pertanyaan (hanya ordinal). |
| `kode_grup_pertanyaan` | `VARCHAR(15)` | Grup pertanyaan. |
| `kode_grup_opsi` | `VARCHAR(30)` | Set opsi (`SETUJU`, `FREKUENSI`, `HARAPAN`, `HARAPAN_FSRD`, `PERKEMBANGAN_SBM`). |
| `jumlah_responden` | `BIGINT` |Jumlah responden yang memilih nilai ini pada kombinasi dimensi tersebut. |
| `tipe_opsi` | `CHAR(1)` | `'O'` = Ordinal, `'N'` = Nominal. Dari `ref_grup_opsi.tipe`. |
| `nilai` | `SMALLINT` | Nilai jawaban (1–4 atau 1–5 untuk ordinal; 1–N untuk nominal). |
| `persentase` | `NUMERIC` | Persentase `n` terhadap total responden untuk pertanyaan yang sama pada dimensi yang sama. Dibulatkan 2 desimal. |

### Logika `persentase`

`persentase` dihitung sebagai window function dengan partisi `(periode_ijazah_id, kd_strata, kd_fak, no_ps, kd_pertanyaan)`. Artinya:
- `persentase` adalah **persentase dalam grup dimensi yang sama**, bukan persentase keseluruhan.
- Row dengan `periode_ijazah_id = NULL` membentuk partisi sendiri — persentasenya dihitung di antara sesama responden "no-period".

### Contoh Query

#### Top-2-Box: % Setuju (nilai ≥ 3) untuk Section A per Fakultas
```sql
SELECT
    kode_fakultas ,
    kode_pertanyaan ,
    SUM(jumlah_responden) FILTER (WHERE nilai >= 3) * 100.0 / SUM(jumlah_responden) AS pct_setuju
FROM analitik.v_wisudawan_distribusi_jawaban
WHERE kode_grup_opsi  = 'SETUJU'
  AND kode_grup_pertanyaan  = 'U03'
GROUP BY kode_fakultas, kode_pertanyaan
ORDER BY kode_fakultas, kode_pertanyaan;
```

#### Incidence Rate: % Pernah Mengalami Masalah (Section D1)
```sql
-- nilai >= 2 berarti "pernah" (Jarang/Sering/Selalu)
SELECT
    p.pertanyaan->'en' as pertanyaan,
    SUM(mv.jumlah_responden) FILTER (WHERE nilai >= 2) * 100.0 / SUM(mv.jumlah_responden) AS pct_pernah_alami
FROM analitik.v_wisudawan_distribusi_jawaban mv join evaluasi_wisudawan.pertanyaan p 
on p.kd_pertanyaan = mv.kode_pertanyaan 
WHERE kode_grup_opsi = 'FREKUENSI'
GROUP BY p.pertanyaan
ORDER BY pct_pernah_alami DESC;
```

#### Distribusi Pilihan Rekomendasi Prodi (U02, nominal)
```sql
SELECT
    d.kode_fakultas,
    o.label->>'id' AS pilihan,
    d.jumlah_responden,
    d.persentase
FROM analitik.v_wisudawan_distribusi_jawaban d
JOIN evaluasi_wisudawan.ref_opsi o
    ON o.kd_grup_opsi = d.kode_grup_opsi AND o.nilai = d.nilai
WHERE d.kode_pertanyaan = 'U02'
ORDER BY d.kode_fakultas, d.nilai;
ORDER BY d.kd_fak, d.nilai;
```

#### Dashboard Dekanat: Distribusi per Prodi (scope STEI)
```sql
SELECT
    periode_ijazah_id,
    no_prodi ,
    kode_pertanyaan ,
    nilai,
    jumlah_responden ,
    persentase 
FROM analitik.v_wisudawan_distribusi_jawaban
WHERE kode_fakultas  = 'STEI'          -- dikunci oleh scope dekanat
  AND kode_grup_pertanyaan  = 'U01'
  AND jenjang  = 'S1'
ORDER BY no_prodi, kode_pertanyaan, nilai;
```

#### Dashboard Kaprodi: Distribusi per Periode untuk Satu Prodi
```sql
SELECT
    periode_ijazah_id,
    kode_pertanyaan,
    nilai,
    jumlah_responden,
    persentase 
FROM analitik.v_wisudawan_distribusi_jawaban
WHERE no_prodi = 135              -- dikunci oleh scope kaprodi
  AND kode_grup_opsi = 'SETUJU'
  AND periode_ijazah_id IS NOT NULL  -- hanya yang ada info periode
ORDER BY periode_ijazah_id, kode_pertanyaan, nilai;
```

---

### `analitik.v_wisudawan_statistik_pertanyaan`

## MV 2: `analitik.v_wisudawan_statistik_pertanyaan`

**Tujuan:** Sumber untuk **grafik rata-rata skor**, ranking pertanyaan, dan perbandingan antar dimensi. Hanya mencakup pertanyaan **ordinal** (`tipe = 'O'`) — nominal tidak boleh di-AVG.
**Granularitas:** 1 baris per kombinasi `(periode_ijazah_id, kd_strata, kd_fak, no_ps, kd_pertanyaan)`.

### Kolom

| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `periode_ijazah_id` | `INTEGER` | Periode wisuda (YYYYMM). NULL = tanpa info periode. |
| `tahun_ijazah` | `INTEGER` | |
| `bulan_ijazah` | `INTEGER` | |
| `periode_seremoni_id` | `INTEGER` | |
| `tahun_seremoni` | `INTEGER` | |
| `bulan_seremoni` | `INTEGER` | |
| `nama_seremoni` | `TEXT` | |
| `kode_fakultas` | `VARCHAR` | Kode fakultas. |
| `nama_fakultas_id` | `TEXT` | Nama fakultas. |
| `nama_fakultas_en` | `TEXT` | Nama fakultas. |
| `no_prodi` | `INTEGER` | Kode program studi. |
| `kode_prodi` | `VARCHAR(2)` | Singkatan program studi. |
| `nama_prodi_id` | `TEXT` | Nama program studi. |
| `nama_prodi_en` | `TEXT` | Nama program studi. |
| `jenjang` | `CHAR(2)` | Jenjang studi. |
| `kode_pertanyaan` | `VARCHAR(20)` | Kode pertanyaan (hanya ordinal). |
| `kode_grup_pertanyaan` | `VARCHAR(15)` | Grup pertanyaan. |
| `kode_grup_opsi` | `VARCHAR(30)` | Set opsi (`SETUJU`, `FREKUENSI`, `HARAPAN`, `HARAPAN_FSRD`, `PERKEMBANGAN_SBM`). |
| `jumlah_responden` | `BIGINT` | Jumlah responden yang menjawab pertanyaan ini. |
| `rata_rata` | `NUMERIC` | Rata-rata skor. Dibulatkan 4 desimal. |
| `median` | `NUMERIC` | Median skor. Dibulatkan 4 desimal. |
| `std_dev` | `NUMERIC` | Standar deviasi skor. Dibulatkan 4 desimal. |
| `skor_min` | `NUMERIC` | Skor minimum yang diberikan. |
| `skor_max` | `NUMERIC` | Skor maksimum yang diberikan. |

### Catatan Interpretasi Skor per Skala

| `kode_grup_opsi` | Range | Makna Skor Tinggi |
|---------------|-------|-------------------|
| `SETUJU` | 1–4 | Tingkat persetujuan tinggi |
| `FREKUENSI` | 1–4 | Frekuensi masalah tinggi (skor tinggi = lebih buruk) |
| `HARAPAN` | 1–5 | Harapan terpenuhi / terlampaui |
| `HARAPAN_FSRD` | 1–5 | Harapan terpenuhi (versi FSRD — nilai-4 berbeda dari HARAPAN) |
| `PERKEMBANGAN_SBM` | 1–5 | Tingkat perkembangan kompetensi tinggi |

> ⚠️ **Jangan bandingkan** `rata_rata` antara `HARAPAN` dan `HARAPAN_FSRD` secara langsung — nilai-4 berbeda secara semantik.  
> ⚠️ **`FREKUENSI`:** skor tinggi bermakna negatif (sering mengalami masalah). Perlu perhatian khusus saat memvisualisasikan.

### Sumber Data Tiap Kolom

| Kolom MV | Sumber |
|----------|--------|
| Dimensi (periode, strata, fak, no_ps, pertanyaan, grup, set_opsi) | Join `respons` × `pertanyaan` × `ref_grup_opsi` |
| `n_responden` | `COUNT(*)` |
| `rata_rata` | `AVG((respons.jawaban ->> kd_pertanyaan)::NUMERIC)` |
| `std_dev` | `STDDEV(...)` |
| `skor_min` / `skor_max` | `MIN(...)` / `MAX(...)` |

### Contoh Query

#### Rata-rata Skor Section A per Fakultas (S1 saja)
```sql
SELECT
    kode_fakultas,
    kode_pertanyaan,
    rata_rata,
    std_dev,
    jumlah_responden
FROM analitik.v_wisudawan_statistik_pertanyaan
WHERE jenjang = 'S1'
  AND kode_grup_pertanyaan = 'U03'
ORDER BY kode_fakultas, rata_rata DESC;
```

#### Ranking Pertanyaan Softskills per Prodi
```sql
SELECT
    kode_pertanyaan,
    rata_rata,
    jumlah_responden,
    RANK() OVER (PARTITION BY no_prodi ORDER BY rata_rata DESC) AS ranking
FROM analitik.v_wisudawan_statistik_pertanyaan
WHERE no_prodi = 135
  AND kode_grup_pertanyaan = 'U04'
ORDER BY ranking;
```

#### Trend Rata-rata Skor Fasilitas per Periode (non-NULL)
```sql
SELECT
    periode_ijazah_id,
    kode_pertanyaan,
    rata_rata,
    jumlah_responden
FROM analitik.v_wisudawan_statistik_pertanyaan
WHERE kode_pertanyaan = 'U03_SQ012'   -- overall satisfaction ITB
  AND periode_ijazah_id IS NOT NULL
ORDER BY periode_ijazah_id;
```

#### Perbandingan Rata-rata Seluruh Section B antar Fakultas
```sql
SELECT
    kode_fakultas,
    ROUND(AVG(rata_rata), 3) AS rata_rata_section_b
FROM analitik.v_wisudawan_statistik_pertanyaan
WHERE kode_grup_pertanyaan = 'U01'
  AND jenjang = 'S1'
GROUP BY kode_fakultas
ORDER BY rata_rata_section_b DESC;
```

#### Dashboard Kaprodi: Skor vs Rata-rata Institusi
```sql
-- Bandingkan prodi dengan rata-rata seluruh ITB per pertanyaan
SELECT
    m.kode_pertanyaan,
    m.rata_rata          AS skor_prodi,
    avg_itb.rata_rata    AS skor_itb,
    m.rata_rata - avg_itb.rata_rata AS selisih
FROM analitik.v_wisudawan_statistik_pertanyaan m
JOIN (
    SELECT kode_pertanyaan, AVG(rata_rata) AS rata_rata
    FROM analitik.v_wisudawan_statistik_pertanyaan
    WHERE jenjang = 'S1' AND kode_grup_pertanyaan = 'U01'
    GROUP BY kode_pertanyaan
) avg_itb USING (kode_pertanyaan)
WHERE m.no_prodi = 135              -- dikunci scope kaprodi
  AND m.jenjang = 'S1'
  AND m.kode_grup_pertanyaan = 'U01'
ORDER BY selisih;
```

---

### `analitik.v_wisudawan_jawaban_responden`

## MV 3: `analitik.v_wisudawan_jawaban_responden`

**Tujuan:** Tabel **flat per responden** — setiap kolom merepresentasikan satu pertanyaan. Digunakan untuk analisis individual, chatbot RAG, dan agen Text-to-SQL yang membutuhkan akses per baris (bukan agregasi).

**Granularitas:** 1 baris per responden (1:1 dengan `respons`).

**Catatan NULL:** Kolom section-spesifik akan `NULL` untuk responden yang tidak mengisi section tersebut — bukan berarti data hilang, tapi memang tidak berlaku (contoh: kolom `s101` akan NULL untuk responden S2/S3).

### Kolom Identitas

| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `response_id` | `INTEGER` | Surrogate PK dari `respons`. Unique index. |
| `survey_platform_response_id` | `INTEGER` | ID asli LimeSurvey. Bisa NULL. |
| `tahun_ijazah` | `INTEGER` | |
| `bulan_ijazah` | `INTEGER` | |
| `periode_seremoni_id` | `INTEGER` | |
| `tahun_seremoni` | `INTEGER` | |
| `bulan_seremoni` | `INTEGER` | |
| `nama_seremoni` | `TEXT` | |
| `kode_fakultas` | `VARCHAR` | Kode fakultas. |
| `nama_fakultas_id` | `TEXT` | Nama fakultas. |
| `nama_fakultas_en` | `TEXT` | Nama fakultas. |
| `no_prodi` | `INTEGER` | Kode program studi. |
| `kode_prodi` | `VARCHAR(2)` | Singkatan program studi. |
| `nama_prodi_id` | `TEXT` | Nama program studi. |
| `nama_prodi_en` | `TEXT` | Nama program studi. |
| `jenjang` | `CHAR(2)` | Jenjang studi. |
| `submit_date` | `TIMESTAMPTZ` | Waktu submit kuesioner. |
| `u03_sq001` | `TEXT` | Nama program studi. |
...flatten all response

### Kolom Jawaban — Section A: Fasilitas ITB (U03)

Semua SMALLINT, skala `SETUJU` (1–4). Populasi: semua.

| Kolom | Pertanyaan |
|-------|-----------|
| `u03_sq001` | Tersedia cukup ruang kelas |
| `u03_sq002` | Ruang kelas kondusif untuk pembelajaran |
| `u03_sq003` | Laboratorium kondusif untuk pembelajaran |
| `u03_sq004` | Akses internet memadai |
| `u03_sq005` | Fasilitas keprofesian memadai |
| `u03_sq006` | Akses perpustakaan memadai |
| `u03_sq007` | Perangkat pembelajaran up-to-date |
| `u03_sq008` | Fasilitas toilet memadai |
| `u03_sq009` | Fasilitas kantin memadai |
| `u03_sq010` | Fasilitas rekreasi/olahraga memadai |
| `u03_sq011` | Fasilitas kesehatan memadai |
| `u03_sq012` | **Secara keseluruhan puas dengan fasilitas ITB** |

### Kolom Jawaban — Section B: Pendidikan di Prodi (U01 + U02)

Skala `SETUJU` (1–4) untuk U01. `u02` nominal (1–7). `u02_other` TEXT. Populasi: semua.

| Kolom | Pertanyaan |
|-------|-----------|
| `u01_sq001` | Wali akademik selalu tersedia saat dibutuhkan |
| `u01_sq002` | Wali akademik membantu memenuhi persyaratan akademik |
| `u01_sq003` | Dosen berinteraksi secara informal dengan mahasiswa |
| `u01_sq004` | Dosen memperhatikan proses pembelajaran mahasiswa |
| `u01_sq005` | Dosen memiliki kemampuan profesional yang baik |
| `u01_sq006` | Matakuliah wajib memberikan dasar yang baik |
| `u01_sq007` | Matakuliah pilihan memberikan keleluasaan eksplorasi |
| `u01_sq008` | Praktikum sejalan dengan teori di kelas |
| `u01_sq009` | Sarana program studi memadai |
| `u01_sq010` | Program studi memberikan gambaran dunia kerja |
| `u01_sq011` | Saya menikmati bidang studi saya |
| `u01_sq012` | **Saya akan memilih program studi yang sama lagi** |
| `u02` | Aspek rekomendasi prodi (nominal: 1=Kualitas dosen … 7=Other) |
| `u02_other` | Teks bebas jika `u02 = 7` |

### Kolom Jawaban — Section C1: Softskills (U04)

Skala `SETUJU` (1–4). Populasi: semua.

`u04_sq001` Komunikasi lisan · `u04_sq002` Komunikasi tertulis · `u04_sq003` Bahasa asing · `u04_sq004` Penyelesaian masalah · `u04_sq005` Berpikir kritis · `u04_sq006` Introspeksi diri · `u04_sq007` Menyampaikan pendapat · `u04_sq008` Kerja tim · `u04_sq009` Kerja mandiri

### Kolom Jawaban — Section C2: Karakter (U05)

Skala `SETUJU` (1–4). Populasi: semua.

`u05_sq001` Kejujuran · `u05_sq002` Komitmen · `u05_sq003` Kecerdasan emosi · `u05_sq004` Kepedulian terhadap sesama · `u05_sq005` Objektivitas · `u05_sq006` Ketidakmudahan menyerah · `u05_sq007` Kepatuhan terhadap aturan

### Kolom Jawaban — Section D1: Permasalahan Studi (U06)

Skala `FREKUENSI` (1–4). Nilai ≥ 2 = pernah mengalami. Populasi: semua.

`u06_sq001` Permasalahan akademis · `u06_sq002` Keuangan · `u06_sq003` Pengaruh keuangan ke akademis · `u06_sq004` Psikologis · `u06_sq005` Pengaruh psikologis ke studi · `u06_sq006` Sosial budaya · `u06_sq007` Pengaruh sosial budaya ke studi · `u06_sq008` Kesehatan · `u06_sq009` Pengaruh kesehatan ke studi

### Kolom Jawaban — Section D2: Ketersediaan Dukungan (U07)

Skala `HARAPAN` (1–5). Hanya diisi responden yang pernah mengalami masalah. Populasi: semua.

`u07_sq001` Beasiswa/pinjaman · `u07_sq002` Bimbingan konseling · `u07_sq003` Nasehat wali akademik · `u07_sq004` Nasehat dosen matakuliah

### Kolom Jawaban — Section E & F: Free-text (universal)

Tipe: `TEXT`. `NULL` jika responden tidak mengisi. Ini adalah **sumber utama RAG**.

| Kolom | Topik |
|-------|-------|
| `g10q22` | Kebiasaan belajar |
| `g01q23` | Kesan dan prestasi dalam belajar |
| `g01q24` | Pengalaman lain yang sangat berkesan |
| `g01q25` | Aktivitas kemahasiswaan |
| `g01q26` | Cita-cita dalam karier |
| `g01q27` | Cita-cita dalam hidup |
| `g01q28` | Motto untuk sukses studi di ITB |
| `g01q29` | Sifat khas diri sendiri |
| `g11q30` | Suka duka menempuh studi di ITB |
| `g01q31` | Segi positif studi di ITB |
| `g01q32` | Segi negatif studi di ITB |
| `g01q33` | **Saran perbaikan proses & sarana pendidikan ITB** |
| `g01q34` | **Saran untuk mahasiswa lain** |
| `g01q35` | Catatan atau komentar lain |

### Kolom Jawaban — Section G: Rencana Studi Lanjut + MKU (khusus S1)

`NULL` untuk strata S2, S3, PR.

| Kolom | Pertanyaan | Skala |
|-------|-----------|-------|
| `s101` | Rencana studi lanjut | YA_TIDAK (1=Ya, 2=Tidak) |
| `s102` | Lokasi studi lanjut | LOKASI_STUDI_LANJUT (1–4) |
| `s103` | Kelanjutan bidang studi | BIDANG_STUDI_LANJUT (1–5) |
| `s104_sq001` | MKU membekali softskill | SETUJU (1–4) |
| `s104_sq002` | MKU membekali hardskill | SETUJU (1–4) |
| `s104_sq003` | MKU membangun karakter | SETUJU (1–4) |
| `s104_sq004` | MKU memperluas wawasan | SETUJU (1–4) |

### Kolom Jawaban — Section H: Rencana Studi Lanjut (khusus S2)

`NULL` untuk strata S1, S3, PR.

| Kolom | Pertanyaan | Skala |
|-------|-----------|-------|
| `m01` | Rencana studi lanjut | YA_TIDAK |
| `m02` | Lokasi studi lanjut | LOKASI_STUDI_LANJUT |
| `m03` | Kelanjutan bidang studi | BIDANG_STUDI_LANJUT |

### Kolom Jawaban — Section I: MKU (khusus S3)

`NULL` untuk strata S1, S2, PR.

| Kolom | Pertanyaan |
|-------|-----------|
| `d01_sq001` | MKU membekali softskill |
| `d01_sq002` | MKU membekali hardskill |
| `d01_sq003` | MKU membangun karakter |
| `d01_sq004` | MKU memperluas wawasan |

### Kolom Jawaban — Section J: FSRD Spesifik (24 kolom)

`NULL` untuk semua fakultas selain FSRD. Skala `HARAPAN_FSRD` (1–5).

| Grup | Kolom | Topik |
|------|-------|-------|
| FSRD01 | `fsrd01_sq001` – `fsrd01_sq005` | Tahap Persiapan Bersama (TPB) |
| FSRD02 | `fsrd02_sq001` – `fsrd02_sq003` | Sistem Perwalian |
| FSRD03 | `fsrd03_sq001` – `fsrd03_sq006` | Mata Kuliah Teori |
| FSRD04 | `fsrd04_sq001` – `fsrd04_sq006` | Mata Kuliah Praktika/Studio |
| FSRD05 | `fsrd05_sq001` – `fsrd05_sq004` | Tugas Akhir |

### Kolom Jawaban — Section K: SBM Spesifik (31 kolom)

`NULL` untuk semua fakultas selain SBM. Skala `PERKEMBANGAN_SBM` (1–5).

`sbm01_sq001` – `sbm01_sq031` — 31 kompetensi outcomes program SBM (komunikasi, pengetahuan bisnis, analisis data, riset, jejaring, tanggung jawab profesional & etis, dll).
### Contoh Query

#### RAG — Ambil Semua Free-text Saran dari Satu Prodi
```sql
SELECT
    response_id,
    jenjang,
    g01q31 AS segi_positif,
    g01q32 AS segi_negatif,
    g01q33 AS saran_perbaikan,
    g01q34 AS saran_mahasiswa
FROM analitik.v_wisudawan_jawaban_responden
WHERE no_prodi  = 135
  AND (g01q31 IS NOT NULL OR g01q32 IS NOT NULL
       OR g01q33 IS NOT NULL OR g01q34 IS NOT NULL);
```

#### Dashboard — Data Individual Mahasiswa per Prodi (kaprodi scope)
```sql
SELECT
    response_id,
    submit_date,
    u03_sq012  AS kepuasan_fasilitas_itb,
    u01_sq012  AS pilih_prodi_lagi,
    u02        AS rekomendasi_prodi
FROM analitik.v_wisudawan_jawaban_responden
WHERE no_prodi = 135        -- dikunci scope kaprodi
  AND jenjang = 'S1'
ORDER BY submit_date DESC;
```

---

## Hierarki Filter Dashboard

Implementasi akses berjenjang pada semua MV menggunakan **filter WHERE statis** berdasarkan scope pengguna, bukan row-level security terpisah (karena mv tak support).

| Level | Constraint SQL | Keterangan |
|-------|---------------|-----------|
| **Admin / Institusi** | *(tidak ada constraint tambahan)* | Akses seluruh data: semua filter tersedia (fakultas, prodi, strata, periode) |
| **Dekanat** | `WHERE kode_fakultas = '<kode_fakultas_dekan>'` | Scope dikunci ke satu fakultas. Filter prodi, strata, periode tetap tersedia. |
| **Kaprodi** | `WHERE no_prodi = <no_prodi_kaprodi>` | Scope dikunci ke satu prodi. Filter strata dan periode tetap tersedia. |

### Contoh Implementasi Filter Berjenjang

```sql
-- Fungsi helper: tambah WHERE clause sesuai scope user
-- (diimplementasikan di layer aplikasi/API)

-- Admin: query bebas
SELECT * FROM analitik.v_wisudawan_statistik_pertanyaan
WHERE jenjang = $strata_filter
  AND periode_ijazah_id = $periode_filter;

-- Dekanat STEI: tambah kd_fak
SELECT * FROM analitik.v_wisudawan_statistik_pertanyaan
WHERE kode_fakultas = 'STEI'              -- injected dari session user
  AND jenjang = $strata_filter
  AND periode_ijazah_id = $periode_filter;

-- Kaprodi IF (no_ps=135): tambah no_ps
SELECT * FROM analitik.v_wisudawan_statistik_pertanyaan
WHERE no_prodi = 135                  -- injected dari session user
  AND jenjang = $strata_filter
  AND periode_ijazah_id = $periode_filter;
```

---

## Ringkasan Perbandingan Ketiga MV

| Aspek | `analitik.v_wisudawan_distribusi_jawaban` | `analitik.v_wisudawan_statistik_pertanyaan` | `analitik.v_wisudawan_jawaban_responden` |
|-------|------------------------|---------------------|-------------------|
| **Granularitas** | Per (dimensi, pertanyaan, **nilai**) | Per (dimensi, pertanyaan) | Per **responden** |
| **Baris perkiraan** | ~300K–500K (banyak) | ~50K–100K | 7.535 |
| **Mencakup nominal** | ✅ Ya | ❌ Tidak (hanya ordinal) | ✅ Ya |
| **Mencakup free-text** | ❌ Tidak | ❌ Tidak | ✅ Ya |
| **Kolom utama** | `n`, `pct` | `rata_rata`, `std_dev` | Semua jawaban flat |
| **Cocok untuk** | Bar chart distribusi, top-2-box, incidence | Line/rank chart, benchmark | RAG, Text-to-SQL individual |
| **REFRESH mode** | Tanpa CONCURRENTLY | Tanpa CONCURRENTLY | **CONCURRENTLY** |
| **UNIQUE INDEX** | `(periode, strata, fak, no_ps, pertanyaan, nilai)` | `(periode, strata, fak, no_ps, pertanyaan)` | `response_id` |