# Schema Tabel: `evaluasi_wisudawan`

> **Untuk:** Developer agen RAG, agen Text-to-SQL, dan dashboard Data Ulasan Wisudawan ITB  
> **File SQL:** `schema_ulasan_wisudawan.sql`  
> **Database:** `dev_six` (cloud DB ITB, schema `evaluasi_wisudawan`)  
> **Sumber data:** LimeSurvey export `resultssurvey926755_2.csv` — Kuesioner Lulusan ITB 2025

---

## Gambaran Umum

Schema ini menyimpan **data mentah hasil survey kepuasan wisudawan ITB** dalam bentuk yang dinormalisasi. Terdiri dari 4 tabel: 2 tabel referensi, 1 katalog pertanyaan, dan 1 tabel respons utama.

```
ref_set_opsi ──┐
               ├──► ref_opsi
               └──► pertanyaan ──► respons
                                      │
                         FK ke: referensi.strata
                                 utama.fakultas
                                 utama.program_studi
                                 wisuda.periode_ijazah
```

### Statistik Data Aktual

| Dimensi | Jumlah |
|---------|--------|
| Total respons | 7.535 |
| Strata S1 | 3.930 |
| Strata S2 | 3.185 |
| Strata S3 | 349 |
| Strata PR (Profesi) | 71 |
| Total pertanyaan valid | 137 |
| Pertanyaan universal | 69 |
| Pertanyaan strata-spesifik | 14 |
| Pertanyaan fakultas-spesifik | 55 (FSRD: 24, SBM: 31) |

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

## Tabel 1: `ref_set_opsi`

**Tujuan:** Mendefinisikan *jenis* skala jawaban — apakah ordinal (bisa di-AVG) atau nominal (tidak boleh di-AVG).

### Atribut

| Kolom | Tipe | Nullable | Keterangan |
|-------|------|----------|------------|
| `kd_set` | `VARCHAR(20)` | NOT NULL | **Primary Key.** Kode unik set opsi. |
| `nama` | `JSONB` | NOT NULL | Nama set dalam dua bahasa: `{"id": "...", "en": "..."}`. |
| `tipe` | `CHAR(1)` | NOT NULL | `'O'` = Ordinal (boleh AVG/STDDEV). `'N'` = Nominal (hanya frekuensi/distribusi). |
| `jumlah_poin` | `SMALLINT` | NULL | Jumlah opsi. Diisi untuk ordinal (`4` atau `5`), NULL untuk nominal. |
| `active` | `BOOLEAN` | NOT NULL | Default `true`. Set ke `false` jika skala tidak lagi digunakan. |
| `ts_entry` | `TIMESTAMPTZ` | NOT NULL | Timestamp insert, default `now()`. |
| `user_id_entry` | `INTEGER` | NOT NULL | ID user yang menginsert (referensi ke `users.user`, belum ada FK eksplisit). |

### Data yang Tersedia (Seed)

| `kd_set` | `tipe` | Poin | Digunakan di Section |
|----------|--------|------|----------------------|
| `S4_AGREE` | O | 4 | A, B, C1, C2, G (S104), I (D01) |
| `S4_FREQ` | O | 4 | D1 (U06) |
| `S5_EXPECT` | O | 5 | D2 (U07) |
| `S5_EXPECT_FSRD` | O | 5 | J (FSRD01–FSRD05) — versi FSRD, nilai-4 berbeda |
| `S5_DEVELOP_SBM` | O | 5 | K (SBM01) |
| `OPT_YA_TIDAK` | N | — | G (S101), H (M01) |
| `OPT_LOKASI_STUDI` | N | — | G (S102), H (M02) |
| `OPT_KELANJUTAN_STUDI` | N | — | G (S103), H (M03) |
| `OPT_U02` | N | — | B (U02) |

> ⚠️ **Penting untuk Text-to-SQL & analitik:** Hanya set dengan `tipe = 'O'` yang boleh di-AVG atau di-STDDEV. Set `tipe = 'N'` hanya boleh dihitung frekuensinya (COUNT/distribusi).

---

## Tabel 2: `ref_opsi`

**Tujuan:** Menyimpan label teks untuk setiap nilai jawaban per set opsi.

### Atribut

| Kolom | Tipe | Nullable | Keterangan |
|-------|------|----------|------------|
| `kd_set` | `VARCHAR(20)` | NOT NULL | **Part of PK.** FK ke `ref_set_opsi(kd_set)`. |
| `nilai` | `SMALLINT` | NOT NULL | **Part of PK.** Angka jawaban yang tersimpan di `respons.jawaban`. |
| `label` | `JSONB` | NOT NULL | Teks opsi dalam dua bahasa: `{"id": "...", "en": "..."}`. |
| `ts_entry` | `TIMESTAMPTZ` | NOT NULL | Timestamp insert. |
| `user_id_entry` | `INTEGER` | NOT NULL | ID user yang menginsert. |

**Primary Key:** `(kd_set, nilai)`

### Referensi Nilai per Set Opsi

#### `S4_AGREE` — 4-poin Persetujuan
| Nilai | Label (ID) | Label (EN) |
|-------|-----------|-----------|
| 1 | Tidak Setuju | Disagree |
| 2 | Cenderung Tidak Setuju | Somewhat Disagree |
| 3 | Cenderung Setuju | Somewhat Agree |
| 4 | Setuju | Agree |

#### `S4_FREQ` — 4-poin Frekuensi
| Nilai | Label (ID) | Label (EN) |
|-------|-----------|-----------|
| 1 | Tidak pernah atau sama sekali tidak | Never |
| 2 | Jarang atau kecil | Rarely |
| 3 | Sering atau cukup | Often |
| 4 | Selalu atau besar | Always |

#### `S5_EXPECT` — 5-poin Pemenuhan Harapan (D2/U07)
| Nilai | Label (ID) | Label (EN) |
|-------|-----------|-----------|
| 1 | Tidak sesuai harapan | Does not meet expectations |
| 2 | Ada yang memenuhi harapan | Partially meets expectations |
| 3 | Sebagian besar memenuhi harapan | Mostly meets expectations |
| 4 | **Sepenuhnya memenuhi harapan** | Fully meets expectations |
| 5 | Melampaui harapan | Exceeds expectations |

#### `S5_EXPECT_FSRD` — 5-poin Pemenuhan Harapan (Section J/FSRD)
| Nilai | Label (ID) | Label (EN) |
|-------|-----------|-----------|
| 1 | Tidak sesuai harapan | Does not meet expectations |
| 2 | Ada yang memenuhi harapan | Partially meets expectations |
| 3 | Sebagian besar memenuhi harapan | Mostly meets expectations |
| 4 | **Memenuhi harapan** | Meets expectations |
| 5 | Melampaui harapan | Exceeds expectations |

> ⚠️ **FSRD vs D2:** Nilai-4 berbeda label antara `S5_EXPECT` dan `S5_EXPECT_FSRD`. Jangan gabungkan skor kedua skala ini dalam satu agregasi tanpa normalisasi terlebih dahulu.

#### `S5_DEVELOP_SBM` — 5-poin Tingkat Perkembangan (Section K/SBM)
| Nilai | Label (ID) | Label (EN) |
|-------|-----------|-----------|
| 1 | Undeveloped – Tidak berkembang | Undeveloped |
| 2 | Slightly Developed – Sedikit berkembang | Slightly Developed |
| 3 | Moderately Developed – Cukup berkembang | Moderately Developed |
| 4 | Substantially Developed – Berkembang secara substansial | Substantially Developed |
| 5 | Highly Developed – Berkembang dengan sangat tinggi | Highly Developed |

#### `OPT_YA_TIDAK`
| Nilai | Label |
|-------|-------|
| 1 | Ya / Yes |
| 2 | Tidak / No |

#### `OPT_LOKASI_STUDI`
| Nilai | Label (ID) |
|-------|-----------|
| 1 | ITB |
| 2 | Perguruan tinggi dalam negeri selain ITB |
| 3 | Di luar negeri |
| 4 | Tidak ada rencana studi lanjut |

#### `OPT_KELANJUTAN_STUDI`
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
    ON o.kd_set = p.kd_set_opsi
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
| `limesurvey_key` | `VARCHAR(50)` | NULL | Key asli di CSV LimeSurvey, contoh: `'U03[SQ001]'`. Untuk traceability ETL. |
| `kd_grup` | `VARCHAR(15)` | NOT NULL | Prefix grup LimeSurvey, contoh: `'U03'`, `'FSRD01'`, `'SBM01'`. Bukan FK. |
| `pertanyaan` | `JSONB` | NOT NULL | Teks pertanyaan bilingual: `{"id": "...", "en": "..."}`. |
| `kd_set_opsi` | `VARCHAR(20)` | NULL | FK ke `ref_set_opsi(kd_set)`. `NULL` = pertanyaan free-text. |
| `batasan` | `JSONB` | NULL | `NULL` = universal. Lihat tabel batasan di bawah. |
| `urutan` | `SMALLINT` | NULL | Urutan tampil dalam grup. |
| `active` | `BOOLEAN` | NOT NULL | Default `true`. |
| `ts_entry` | `TIMESTAMPTZ` | NOT NULL | Timestamp insert. |
| `user_id_entry` | `INTEGER` | NOT NULL | ID user yang menginsert. |

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
| **A** | U03 | Fasilitas & Kepuasan ITB | 12 | Likert S4_AGREE | Universal |
| **B** | U01 | Pendidikan di Program Studi | 12 | Likert S4_AGREE | Universal |
| **B** | U02 | Rekomendasi Prodi | 1 | Nominal OPT_U02 | Universal |
| **C1** | U04 | Kemampuan Softskills | 9 | Likert S4_AGREE | Universal |
| **C2** | U05 | Pengembangan Karakter | 7 | Likert S4_AGREE | Universal |
| **D1** | U06 | Permasalahan Selama Studi | 9 | Likert S4_FREQ | Universal |
| **D2** | U07 | Ketersediaan Dukungan | 4 | Likert S5_EXPECT | Universal |
| **E** | G10, G01 | Free-text Pengalaman Studi | 8 | Free-text | Universal |
| **F** | G11, G01 | Free-text Saran & Aspirasi | 6 | Free-text | Universal |
| **G** | S1 | Rencana Studi Lanjut + MKU | 7 | 3 Nominal + 4 Likert | Hanya S1 |
| **H** | M | Rencana Studi Lanjut S2 | 3 | Nominal | Hanya S2 |
| **I** | D01 | MKU untuk Doktor | 4 | Likert S4_AGREE | Hanya S3 |
| **J** | FSRD01–FSRD05 | Evaluasi Spesifik FSRD | 24 | Likert S5_EXPECT_FSRD | Hanya FSRD |
| **K** | SBM01 | Outcomes Program SBM | 31 | Likert S5_DEVELOP_SBM | Hanya SBM |
| | | **Total** | **137** | | |

### Detail Pertanyaan per Section

#### Section A — Fasilitas & Kepuasan ITB (U03, 12 item)
Skala: `S4_AGREE` (1–4)

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
Skala: `S4_AGREE` untuk U01; `OPT_U02` (nominal) untuk U02

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
Skala: `S4_AGREE`

`U04_SQ001` Komunikasi lisan · `U04_SQ002` Komunikasi tertulis · `U04_SQ003` Bahasa asing · `U04_SQ004` Penyelesaian masalah · `U04_SQ005` Berpikir kritis · `U04_SQ006` Introspeksi diri · `U04_SQ007` Menyampaikan pendapat · `U04_SQ008` Kerja tim · `U04_SQ009` Kerja mandiri

#### Section C2 — Pengembangan Karakter (U05, 7 item)
Skala: `S4_AGREE`

`U05_SQ001` Kejujuran · `U05_SQ002` Komitmen · `U05_SQ003` Kecerdasan emosi · `U05_SQ004` Kepedulian terhadap sesama · `U05_SQ005` Objektivitas · `U05_SQ006` Ketidakmudahan menyerah · `U05_SQ007` Kepatuhan terhadap aturan

#### Section D1 — Permasalahan Selama Studi (U06, 9 item)
Skala: `S4_FREQ` — nilai ≥ 2 berarti *pernah mengalami*

`U06_SQ001` Permasalahan akademis · `U06_SQ002` Keuangan · `U06_SQ003` Pengaruh keuangan ke akademis · `U06_SQ004` Psikologis · `U06_SQ005` Pengaruh psikologis ke studi · `U06_SQ006` Sosial budaya · `U06_SQ007` Pengaruh sosial budaya ke studi · `U06_SQ008` Kesehatan · `U06_SQ009` Pengaruh kesehatan ke studi

#### Section D2 — Ketersediaan Dukungan (U07, 4 item)
Skala: `S5_EXPECT` — hanya diisi oleh yang pernah mengalami masalah

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
| S101 | Rencana melanjutkan ke pendidikan lebih tinggi | OPT_YA_TIDAK |
| S102 | Lokasi rencana studi lanjut | OPT_LOKASI_STUDI |
| S103 | Kelanjutan bidang studi | OPT_KELANJUTAN_STUDI |
| S104_SQ001 | MKU ITB membekali softskill | S4_AGREE |
| S104_SQ002 | MKU ITB membekali hardskill | S4_AGREE |
| S104_SQ003 | MKU ITB membangun karakter | S4_AGREE |
| S104_SQ004 | MKU ITB memperluas wawasan | S4_AGREE |

#### Section H — Rencana Studi Lanjut, khusus S2 (3 item)

`M01` Rencana studi lanjut (OPT_YA_TIDAK) · `M02` Lokasi (OPT_LOKASI_STUDI) · `M03` Kelanjutan bidang (OPT_KELANJUTAN_STUDI)

#### Section I — MKU untuk Doktor, khusus S3 (4 item, S4_AGREE)

`D01_SQ001` MKU membekali softskill · `D01_SQ002` MKU membekali hardskill · `D01_SQ003` MKU membangun karakter · `D01_SQ004` MKU memperluas wawasan

#### Section J — Evaluasi Spesifik FSRD (24 item, S5_EXPECT_FSRD, hanya FSRD)

| Grup | Topik | Jml |
|------|-------|-----|
| FSRD01 | Tahap Persiapan Bersama (TPB) | 5 |
| FSRD02 | Sistem Perwalian | 3 |
| FSRD03 | Mata Kuliah Teori | 6 |
| FSRD04 | Mata Kuliah Praktika/Studio | 6 |
| FSRD05 | Tugas Akhir | 4 |

#### Section K — Outcomes Program SBM (31 item, S5_DEVELOP_SBM, hanya SBM)

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
| `jawaban` (nilai integer) | `ref_opsi(kd_set, nilai)` — di-resolve saat query |
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

### Index pada Tabel `respons`

| Index | Tipe | Kolom | Tujuan |
|-------|------|-------|--------|
| Primary Key | B-tree | `response_id` | Lookup individual row |
| Unique (partial) | B-tree | `survey_platform_response_id` WHERE NOT NULL | Cegah duplikasi import |
| B-tree | — | `kd_strata` | Filter dashboard strata |
| B-tree | — | `kd_fak` | Filter dashboard fakultas |
| B-tree | — | `no_ps` | Filter dashboard prodi |
| B-tree | — | `periode_ijazah_id` | Filter dashboard periode |
| B-tree | — | `(kd_strata, kd_fak)` | Filter komposit |
| B-tree | — | `(kd_strata, periode_ijazah_id)` | Filter komposit |
| GIN | — | `jawaban` | Query key/value dalam JSONB |

---

## Panduan Penggunaan per Use Case

### 1. Dashboard Agregasi (Rata-rata Skor per Pertanyaan)

Gunakan **Materialized View** `mv_skor_pertanyaan` (lihat dokumen MV), bukan query langsung ke `respons`. Tabel `respons` adalah sumber data mentah.

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
    ON o.kd_set = 'OPT_YA_TIDAK'
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

Untuk RAG, **index full-text atau embedding vector** sebaiknya dibangun di atas konten free-text dari kolom `jawaban` (key G-series). Gunakan `mv_wide_respons` yang sudah memisahkan kolom free-text untuk kemudahan akses.

### 4. Query Katalog Pertanyaan (untuk System Prompt Agen)

```sql
-- Daftar semua pertanyaan dengan tipe skala dan populasi
SELECT
    p.kd_pertanyaan,
    p.kd_grup,
    p.pertanyaan->>'id'    AS pertanyaan_id,
    p.kd_set_opsi,
    s.tipe                 AS tipe_opsi,
    s.jumlah_poin,
    p.batasan
FROM evaluasi_wisudawan.pertanyaan p
LEFT JOIN evaluasi_wisudawan.ref_set_opsi s ON s.kd_set = p.kd_set_opsi
WHERE p.active = true
ORDER BY p.kd_grup, p.urutan;
```

---

## Catatan Penting untuk Developer

### ETL dari CSV LimeSurvey

1. **Ordinal Likert:** konversi teks label → integer via `ref_opsi.label` (kd_set ordinal).
2. **Nominal:** konversi teks label → integer via `ref_opsi.label` (kd_set nominal).
3. **Free-text:** simpan as-is sebagai TEXT string di JSONB.
4. **U02 = "Other":** simpan `{"U02": 7, "U02_other": "<teks bebas>"}`.
5. **Strata PR:** hanya isi Section A–D; key Section G/H/I/J/K tidak ada di JSONB-nya.

### Hal yang Tidak Boleh Dilakukan

- ❌ Jangan AVG kolom nominal (`tipe = 'N'`): `U02`, `S101`, `S102`, `S103`, `M01`, `M02`, `M03`.
- ❌ Jangan gabungkan skor D2 (`U07`, `S5_EXPECT`) dan Section J FSRD (`S5_EXPECT_FSRD`) dalam satu AVG — nilai-4 berbeda secara semantik.
- ❌ Jangan anggap `periode_ijazah_id = NULL` sebagai data hilang — 66.6% memang NULL dan tidak bisa diimputasi.
- ❌ Jangan filter `last_page = 11` sebagai satu-satunya filter "complete" — mayoritas data sudah complete.
