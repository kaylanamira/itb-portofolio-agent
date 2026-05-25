# Database Reference — ITB Academic Portfolio Analytics
**Database:** `dev_six` (PostgreSQL, accessed via SSH tunnel)
**Last updated from:** `dev_six_schema.sql` + `mv_dokumentasi.md` + `schema_mv_portofolio_kuesioner.sql`
**Scope:** This document covers every schema in `dev_six`. Schemas are classified by relevance to the portfolio analytics system.

---

## Schema Classification Index

| Schema | Relevance | Purpose |
|--------|-----------|---------|
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
| `wisuda` | **NO** | Graduation data — out of scope per PRD |
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
- Presensi granular per pertemuan per mahasiswa (hanya agregat dari sistem evaluasi yang tersedia di `mv_kelas`)
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
The primary transactional schema for class data. `kelas.kelas` is the base table from which `mv_kelas` is derived.

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
Contains all questionnaire scores and portfolio free-text data. This is the most critical schema for the analytics system alongside `mv_kelas`.

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

## Materialized Views

**primary query surface for the analytics agent.**

Most MVs are defined in `schema_mv_portofolio_kuesioner.sql` and documented in `mv_dokumentasi.md` (living in the `public` schema). The comments materialized view `mv_komentar_mahasiswa` is located in the `analitik` schema.

---

### `mv_kelas`

**Granularity: 1 row = 1 class.**
The primary analytics view. All dimensions are pre-joined and flattened. Query this before any base table for numeric analytics.

#### Refresh dependency
Must be refreshed first before `mv_statistik_prodi` and `mv_statistik_dosen`.

#### Key columns

| Column | Type | Example |
|--------|------|---------|
| `kelas_id` | `integer` | `10342` |
| `mata_kuliah_id` | `integer` | `501` |
| `no_kelas` | `integer` | `1`, `2`, `3` |
| `semester` | `smallint` | `1` (Ganjil), `2` (Genap), `3` (SP) |
| `tahun` | `smallint` | `2024` |
| `tahun_ajaran` | `text` | `"2024/2025"` |
| `kode_mk` | `varchar` | `"IF2210"` |
| `nama_mk_id` | `text` | `"Pemrograman Berorientasi Objek"` |
| `nama_mk_en` | `text` | `"Object-Oriented Programming"` |
| `sks` | `integer` | `3` |
| `jenis_nilai` | `text` | `"ABCDE"` or `"PassFail"` |
| `tahun_kurikulum` | `integer` | `2019` |
| `kode_prodi` | `integer` | `135` (= `no_ps`) |
| `singkatan_prodi` | `varchar` | `"IF"` |
| `nama_prodi_id` | `text` | `"Teknik Informatika"` |
| `jenjang` | `varchar` | `"S1"`, `"S2"`, `"S3"` |
| `kode_fakultas` | `varchar` | `"STEI"` |
| `nama_fakultas_id` | `text` | `"Sekolah Teknik Elektro dan Informatika"` |
| `semua_dosen_id` | `integer[]` | `{123, 456}` |
| `semua_dosen_nama_gelar` | `text[]` | `{"Prof. Dr. Budi, M.T.", "Dr. Siti, Ph.D."}` |
| `pct_kehadiran_dosen` | `numeric` | `92.50` |
| `pct_kehadiran_mahasiswa` | `numeric` | `88.00` |
| `rata_ip_akhir_mahasiswa` | `numeric` | `3.12` |
| `jumlah_mahasiswa` | `integer` | `40` |
| `skor_dna` | `numeric` | `3.80` |
| `ip_mhs_dna` | `numeric` | `3.15` |
| `dist_jumlah_a` .. `dist_jumlah_e` | `integer` | `12`, `8`, `10`, `5`, `3`, `1`, `1` |
| `dist_jumlah_pass` / `dist_jumlah_fail` | `integer` | For PassFail courses only |
| `dist_pct_a` .. `dist_pct_fail` | `numeric` | `30.00`, `20.00`, ... |
| `dist_pct_lulus_A_C` | `numeric` | `95.00` — % with grade ≥ C (or Pass) |
| `dist_pct_lulus_A_D` | `numeric` | `97.50` — % with grade ≥ D (or Pass) |
| `skor_q21` .. `skor_q24`, `skor_q28` .. `skor_q30`, `skor_q35`, `skor_q37` | `numeric` | `3.74` (Likert 1–5, class-level) |
| `skor_q25_avg`, `skor_q26_avg`, `skor_q27_avg` | `numeric` | `3.67` (averaged across dosen) |
| `skor_kues_dosen_q25` | `jsonb` | `{"123": 3.6667, "456": 4.0000}` |
| `skor_kues_dosen_q26` | `jsonb` | Same structure |
| `skor_kues_dosen_q27` | `jsonb` | Same structure |
| `avg_skor_capaian` | `numeric` | Avg(Q21, Q22, Q23) |
| `avg_skor_pelaksanaan` | `numeric` | Avg(Q24, Q25\_avg, Q26\_avg, Q27\_avg, Q28) |
| `avg_skor_sarana_prasarana` | `numeric` | Avg(Q29, Q30) |
| `avg_skor_perilaku_mahasiswa` | `numeric` | Avg(Q35, Q37) |
| `avg_skor_overall` | `numeric` | Avg of all Q with data |

#### Indexes

| Index | Columns |
|-------|---------|
| `idx_mv_kelas_pk` (UNIQUE) | `kelas_id` |
| `idx_mv_kelas_prodi_sem` | `(kode_prodi, semester, tahun)` |
| `idx_mv_kelas_fak_sem` | `(kode_fakultas, semester, tahun)` |
| `idx_mv_kelas_matkul_sem` | `(kode_mk, semester, tahun)` |
| `idx_mv_kelas_tahun_ajaran` | `(tahun_ajaran, kode_prodi)` |
| `idx_mv_kelas_dosen_arr` (GIN) | `semua_dosen_id` |
| `idx_mv_kelas_skor_dosen_q2{5,6,7}` (GIN) | JSONB dosen score fields |

#### Common query patterns

```sql
-- All classes for a course in a semester
SELECT * FROM mv_kelas
WHERE kode_mk = 'IF2210' AND semester = 1 AND tahun = 2024;

-- Filter by prodi (scoped user)
WHERE kode_prodi = 135 AND semester = 1 AND tahun = 2024

-- Filter by fakultas (scoped user)
WHERE kode_fakultas = 'STEI' AND semester = 1 AND tahun = 2024

-- Text search for course name (bilingual)
WHERE (nama_mk_id || ' ' || COALESCE(nama_mk_en, '')) ILIKE '%basis data%'

-- Per-dosen Q25 score from JSONB
(skor_kues_dosen_q25->>:dosen_id_str)::numeric
```

---

### `mv_statistik_prodi`

**Granularity: 1 row = 1 prodi × 1 semester × 1 tahun.**
Pre-aggregated for prodi-level dashboard panels.

#### Key columns

| Column | Type | Notes |
|--------|------|-------|
| `kode_prodi` | `integer` | PK component (= `no_ps`) |
| `singkatan_prodi` | `varchar` | `"IF"` |
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
| `avg_ip_mhs` | `numeric` | |
| `total_jumlah_a` .. `total_jumlah_fail` | `bigint` | SUM across all kelas |
| `total_mahasiswa_dinilai` | `bigint` | Total graded students (denominator) |
| `dist_pct_a` .. `dist_pct_fail` | `numeric` | Computed from absolute sums, not averaged percentages |
| `dist_pct_lulus_A_C` / `dist_pct_lulus_A_D` | `numeric` | |
| `avg_skor_q21` .. `avg_skor_q37` | `numeric` | Per-question averages across kelas |
| `avg_skor_capaian` / `avg_skor_pelaksanaan` / `avg_skor_sarana_prasarana` / `avg_skor_perilaku_mahasiswa` / `avg_skor_overall` | `numeric` | |

Faculty-level aggregation: `GROUP BY kode_fakultas, nama_fakultas_id, semester, tahun` on this view — no separate MV needed.

#### Indexes

| Index | Columns |
|-------|---------|
| `idx_mv_prodi_pk` (UNIQUE) | `(kode_prodi, semester, tahun)` |
| `idx_mv_prodi_fak_sem` | `(kode_fakultas, semester, tahun)` |
| `idx_mv_prodi_tahun_ajaran` | `(tahun_ajaran, kode_prodi)` |

---

### `mv_statistik_dosen`

**Granularity: 1 row = 1 dosen × 1 semester × 1 tahun.**
Pre-aggregated for dosen-level dashboard panels.

#### Key columns

| Column | Type | Notes |
|--------|------|-------|
| `dosen_id` | `integer` | PK component |
| `nama_dosen_gelar` | `varchar` | Full name with titles |
| `nip` | `varchar` | |
| `kk_id` | `integer` | |
| `nama_kk_id` / `nama_kk_en` | `text` | |
| `kode_fakultas_dosen` | `varchar` | Home faculty from `utama.dosen.kd_fak` |
| `kode_prodi` | `integer` | Home prodi from `utama.dosen.no_ps` |
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
| `kode_mk_list` | `varchar[]` | Unique course codes taught |
| `kode_prodi_diajar` | `integer[]` | Prodi where this dosen taught (may differ from home prodi) |
| `singkatan_prodi_diajar` | `varchar[]` | |

#### Indexes

| Index | Columns |
|-------|---------|
| `idx_mv_dosen_pk` (UNIQUE) | `(dosen_id, semester, tahun)` |
| `idx_mv_dosen_kk_sem` | `(kk_id, semester, tahun)` |
| `idx_mv_dosen_fak_dosen_sem` | `(kode_fakultas_dosen, semester, tahun)` |
| `idx_mv_dosen_no_ps_sem` | `(kode_prodi, semester, tahun)` |
| `idx_mv_dosen_tahun_ajaran` | `(tahun_ajaran, dosen_id)` |

### `mv_komentar_mahasiswa` (under `analitik` schema)

**Granularity: 1 row = 1 student free-text comment per class.**
Contains pre-joined student evaluation comments for easy RAG ingestion and analysis. Excludes `mahasiswa_id` (comment content only).

#### Key columns

| Column | Type | Notes |
|--------|------|-------|
| `jawaban_id` | `integer` | PK component |
| `kelas_id` | `integer` | Class identifier |
| `tahun` | `smallint` | Year |
| `semester` | `smallint` | Semester code |
| `tahun_ajaran` | `text` | e.g. `"2024/2025"` |
| `kode_mk` | `varchar` | Course code (e.g., `"IF2210"`) |
| `nama_mk_id` | `text` | Indonesian course name |
| `nama_mk_en` | `text` | English course name |
| `sks` | `integer` | Course credit weight |
| `no_kelas` | `integer` | Class number |
| `kode_prodi` | `integer` | Prodi identifier |
| `singkatan_prodi` | `varchar` | Prodi code abbreviation (e.g., `"IF"`) |
| `nama_prodi_id` | `text` | Prodi name |
| `jenjang` | `varchar` | Degree level (e.g., `"S1"`) |
| `kode_fakultas` | `varchar` | Faculty abbreviation (e.g., `"STEI"`) |
| `nama_fakultas_id` | `text` | Faculty name |
| `semua_dosen_id` | `integer[]` | Array of dosen IDs teaching the class |
| `semua_dosen_nama_gelar` | `text[]` | Array of teaching dosen names with titles |
| `komentar_teks` | `text` | Raw comment text (question code 103) |
| `ts_jawaban` | `timestamp` | Entry timestamp |

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

## Application State Tables (To Be Created)

The following tables must be created in `dev_six` under a dedicated application schema (e.g., `analitik`) for the analytics system's own state, WHICH IS ALREADY CREATED.

| Table | Purpose |
|-------|---------|
| `analitik.llm_analysis_cache` | SHA256-keyed LLM narrative cache; must include `refreshed_at` for invalidation on MV refresh |
| `analitik.vector_chunks` | pgvector embeddings for portfolio text from `evaluasi.portofolio.isian` and `komentar` |
| `analitik.mv_refresh_log` | Tracks last MV refresh timestamp; used to invalidate `llm_analysis_cache` stale entries |
| `analitik.mv_*` | already created |

The existing `users.user` and `users.user_role` tables in SIX cover authentication and role assignment — no separate `pengguna` or `user_scope` table is needed.

---

## Key Domain Mappings (Schema → Prior Design)

The prior `SCHEMA_REFERENCE.md` used a custom schema design. The actual SIX tables map as follows:

| Prior Design | Actual SIX Table | Notes |
|---|---|---|
| `kelas` (public) | `kelas.kelas` | Different schema prefix |
| `pengajar_kelas` | `kelas.pengajar` | |
| `mata_kuliah` | `utama.mata_kuliah` | `kode_mk` = `kd_kuliah`, UUID PK → INTEGER |
| `program_studi` | `utama.program_studi` | `prodi_id` → `no_ps` which is `kode_prodi` (INTEGER), `singkatan_prodi` → `kd_ps` |
| `fakultas` | `utama.fakultas` | `fakultas_id` → `kd_fak` (VARCHAR), `nama_fakultas` → `nama->>'id'` or `nama->>'en'` |
| `dosen` | `utama.dosen` | `dosen_id` is INTEGER not UUID, `nama_gelar` is GENERATED column |
| `kelompok_keahlian` | `utama.kk` | |
| `distribusi_nilai` | `mahasiswa.kuliah` | No separate table; computed via COUNT FILTER |
| `skor_kuesioner` | `evaluasi.nilai_kelas.kuesioner` (JSONB) | Q-number is a string key, not a column |
| `teks_portofolio` | `analitik.mv_komentar_mahasiswa` or `evaluasi.portofolio.isian` (JSONB) | JSONB keyed by `kd_pertanyaan` |
| `komentar_mahasiswa` | `analitik.mv_komentar_mahasiswa` or raw through `evaluasi.portofolio.isian` with `kd_pertanyaan = 103` | |
| `pengguna` | `users.user` | |
| `user_scope` | `users.user_role` (multi-row) | One user, many roles, each with `scope` and `ts_valid` |
| `jenis_nilai = 'ABCDE'` | `kd_penilaian = 'A'` | |
| `jenis_nilai = 'Pass/Fail'` | `kd_penilaian = 'P'` | |
| `kode_prodi` (VARCHAR) | `no_ps` (INTEGER) | |

---

**Gaps and limitations:**

1. **Portfolio free-text not in MVs.** `evaluasi.portofolio.isian` and `komentar` (JSONB) are not surfaced in `mv_kelas`. The agent must query analitik.mv_komentar_mahasiswa.

3. **Q25/Q26/Q27 NULL for older semesters.** Data before the new questionnaire system contains `{}` in `evaluasi.nilai_dosen.kuesioner`. All dosen-specific Q scores will be NULL in `mv_statistik_dosen` for historical data. Queries comparing trends must handle this.

4. **`avg_nilai_akhir` is unreliable.** `evaluasi.nilai_dosen.nilai_akhir` is inconsistently populated. Avoid this column for any meaningful metric.

5. **`jumlah_mahasiswa_aktif` is by home prodi.** Students enrolled in cross-prodi courses are not counted in the host prodi's `jumlah_mahasiswa_aktif`. This is correct for enrollment counts but may create confusion in queries mixing class-level and prodi-level student counts.

7. **MV scope injection must be in WHERE, not RLS.** The MVs have no RLS. All scope filtering (by `kode_prodi`, `kode_fakultas`, or `semua_dosen_id`) must be injected by the SQL executor before running queries.

8. **Multi-role user scope resolution.** A user may hold valid roles at multiple scopes simultaneously (e.g., dekan at two faculties). The application must resolve which scope is active for a given request, or handle returning union results across all valid scopes.
