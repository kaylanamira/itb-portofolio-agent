# Schema Materialized View: `evaluasi_wisudawan`

> **Untuk:** Developer agen RAG, agen Text-to-SQL, dan dashboard Data Ulasan Wisudawan ITB  
> **File SQL:** `schema_mv_ulasan_wisudawan.sql`  
> **Prasyarat:** `schema_ulasan_wisudawan.sql` sudah dieksekusi terlebih dahulu  
> **Database:** `dev_six` (cloud DB ITB, schema `evaluasi_wisudawan`)

---

## Gambaran Umum

Tiga Materialized View (MV) ini adalah **lapisan analitik** di atas tabel `respons`. Masing-masing memiliki granularitas berbeda, dirancang untuk use case yang berbeda, dan tidak saling menggantikan.

```
respons (raw) ──────────────────────────────────────────────────────┐
                                                                    │
                     ┌──────────────────────────────────────────────┘
                     ▼
        ┌────────────────────────────────┐
        │   mv_distribusi_jawaban        │  ← Distribusi & persentase
        │   1 baris per:                 │    per (periode, strata,
        │   (periode, strata, fak,       │    fak, pertanyaan, nilai)
        │    no_ps, pertanyaan, nilai)   │
        └────────────────────────────────┘

        ┌────────────────────────────────┐
        │   mv_skor_pertanyaan           │  ← Rata-rata skor ordinal
        │   1 baris per:                 │    per (periode, strata,
        │   (periode, strata, fak,       │    fak, no_ps, pertanyaan)
        │    no_ps, pertanyaan)          │
        └────────────────────────────────┘

        ┌────────────────────────────────┐
        │   mv_wide_respons              │  ← Flat table per responden
        │   1 baris per responden        │    untuk RAG & Text-to-SQL
        │   Semua jawaban = kolom flat   │    individual
        └────────────────────────────────┘
```

### Kapan Menggunakan MV Mana?

| Kebutuhan | Gunakan MV |
|-----------|-----------|
| Grafik distribusi jawaban (bar chart), top-2-box, % setuju | `mv_distribusi_jawaban` |
| Grafik rata-rata skor, ranking pertanyaan, trend per periode | `mv_skor_pertanyaan` |
| Query per responden, analisis individual, chatbot RAG, Text-to-SQL natural | `mv_wide_respons` |
| AVG/STDDEV langsung dari data mentah | Query ke `respons` langsung |

---

## Strategi Refresh

> ⚠️ **Catatan kritis:** `mv_distribusi_jawaban` dan `mv_skor_pertanyaan` menggunakan `REFRESH` **tanpa** `CONCURRENTLY`. Hal ini karena kolom `periode_ijazah_id` nullable (66.6% NULL di data aktual) — UNIQUE INDEX PostgreSQL memperlakukan NULL ≠ NULL, sehingga `REFRESH CONCURRENTLY` berisiko gagal meng-match baris lama vs baru untuk row dengan periode NULL. Karena data survey diimport secara batch (bukan real-time), downtime singkat saat refresh tidak berdampak ke operasional.

```sql
-- Jalankan setelah setiap batch import CSV:

-- 1. Distribusi jawaban (TANPA CONCURRENTLY)
REFRESH MATERIALIZED VIEW evaluasi_wisudawan.mv_distribusi_jawaban;

-- 2. Skor rata-rata (TANPA CONCURRENTLY)
REFRESH MATERIALIZED VIEW evaluasi_wisudawan.mv_skor_pertanyaan;

-- 3. Wide respons (CONCURRENTLY aman — unique index hanya pada response_id SERIAL)
REFRESH MATERIALIZED VIEW CONCURRENTLY evaluasi_wisudawan.mv_wide_respons;
```

---

## MV 1: `mv_distribusi_jawaban`

**Tujuan:** Sumber tunggal untuk semua kebutuhan **distribusi & persentase jawaban** — bar chart, top-2-box, incidence rate. Mencakup pertanyaan ordinal (Likert) dan nominal (kategoris). Free-text otomatis dikecualikan.

**Granularitas:** 1 baris per kombinasi `(periode_ijazah_id, kd_strata, kd_fak, no_ps, kd_pertanyaan, nilai)`.

### Kolom

| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `periode_ijazah_id` | `INTEGER` | Periode wisuda (YYYYMM). NULL = responden tanpa info periode (66.6% data). FK ke `wisuda.periode_ijazah`. |
| `kd_strata` | `CHAR(2)` | Jenjang studi: `S1`, `S2`, `S3`, `PR`. FK ke `referensi.strata`. |
| `kd_fak` | `VARCHAR` | Kode fakultas. FK ke `utama.fakultas`. |
| `no_ps` | `INTEGER` | Kode program studi. FK ke `utama.program_studi`. |
| `kd_pertanyaan` | `VARCHAR(20)` | Kode pertanyaan. FK ke `evaluasi_wisudawan.pertanyaan`. |
| `kd_grup` | `VARCHAR(15)` | Grup pertanyaan (prefix LimeSurvey), contoh: `'U03'`, `'SBM01'`. |
| `kd_set_opsi` | `VARCHAR(20)` | Set opsi yang digunakan, contoh: `'S4_AGREE'`. FK ke `ref_set_opsi`. |
| `tipe_opsi` | `CHAR(1)` | `'O'` = Ordinal, `'N'` = Nominal. Dari `ref_set_opsi.tipe`. |
| `nilai` | `SMALLINT` | Nilai jawaban (1–4 atau 1–5 untuk ordinal; 1–N untuk nominal). |
| `n` | `BIGINT` | Jumlah responden yang memilih nilai ini pada kombinasi dimensi tersebut. |
| `pct` | `NUMERIC` | Persentase `n` terhadap total responden untuk pertanyaan yang sama pada dimensi yang sama. Dibulatkan 2 desimal. |

### Logika `pct`

`pct` dihitung sebagai window function dengan partisi `(periode_ijazah_id, kd_strata, kd_fak, no_ps, kd_pertanyaan)`. Artinya:
- `pct` adalah **persentase dalam grup dimensi yang sama**, bukan persentase keseluruhan.
- Row dengan `periode_ijazah_id = NULL` membentuk partisi sendiri — persentasenya dihitung di antara sesama responden "no-period".

### Sumber Data Tiap Kolom

| Kolom MV | Sumber |
|----------|--------|
| `periode_ijazah_id` | `respons.periode_ijazah_id` |
| `kd_strata` | `respons.kd_strata` |
| `kd_fak` | `respons.kd_fak` |
| `no_ps` | `respons.no_ps` |
| `kd_pertanyaan` | `pertanyaan.kd_pertanyaan` |
| `kd_grup` | `pertanyaan.kd_grup` |
| `kd_set_opsi` | `pertanyaan.kd_set_opsi` |
| `tipe_opsi` | `ref_set_opsi.tipe` |
| `nilai` | Cast dari `respons.jawaban ->> kd_pertanyaan` ke SMALLINT |
| `n` | `COUNT(*)` per grup |
| `pct` | Window function `COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (...)` |

### Index

| Index | Kolom | Tujuan |
|-------|-------|--------|
| UNIQUE | `(periode_ijazah_id, kd_strata, kd_fak, no_ps, kd_pertanyaan, nilai)` | Identifikasi unik baris |
| B-tree | `(kd_set_opsi, nilai)` | Filter per skala dan nilai tertentu |
| B-tree | `kd_grup` | Filter per section/grup pertanyaan |
| B-tree | `tipe_opsi` | Filter ordinal vs nominal |
| B-tree | `(kd_strata, kd_fak)` | Filter komposit dashboard |
| B-tree | `no_ps` | Filter per prodi |
| B-tree | `(kd_strata, kd_fak, no_ps)` | Filter komposit tiga dimensi |

### Contoh Query

#### Top-2-Box: % Setuju (nilai ≥ 3) untuk Section A per Fakultas
```sql
SELECT
    kd_fak,
    kd_pertanyaan,
    SUM(n) FILTER (WHERE nilai >= 3) * 100.0 / SUM(n) AS pct_setuju
FROM evaluasi_wisudawan.mv_distribusi_jawaban
WHERE kd_set_opsi = 'S4_AGREE'
  AND kd_grup = 'U03'
GROUP BY kd_fak, kd_pertanyaan
ORDER BY kd_fak, kd_pertanyaan;
```

#### Incidence Rate: % Pernah Mengalami Masalah (Section D1)
```sql
-- nilai >= 2 berarti "pernah" (Jarang/Sering/Selalu)
SELECT
    kd_pertanyaan,
    SUM(n) FILTER (WHERE nilai >= 2) * 100.0 / SUM(n) AS pct_pernah_alami
FROM evaluasi_wisudawan.mv_distribusi_jawaban
WHERE kd_set_opsi = 'S4_FREQ'
GROUP BY kd_pertanyaan
ORDER BY pct_pernah_alami DESC;
```

#### Distribusi Pilihan Rekomendasi Prodi (U02, nominal)
```sql
SELECT
    d.kd_fak,
    o.label->>'id' AS pilihan,
    d.n,
    d.pct
FROM evaluasi_wisudawan.mv_distribusi_jawaban d
JOIN evaluasi_wisudawan.ref_opsi o
    ON o.kd_set = d.kd_set_opsi AND o.nilai = d.nilai
WHERE d.kd_pertanyaan = 'U02'
ORDER BY d.kd_fak, d.nilai;
```

#### Dashboard Dekanat: Distribusi Section B per Prodi (scope STEI)
```sql
SELECT
    no_ps,
    kd_pertanyaan,
    nilai,
    n,
    pct
FROM evaluasi_wisudawan.mv_distribusi_jawaban
WHERE kd_fak = 'STEI'          -- dikunci oleh scope dekanat
  AND kd_grup = 'U01'
  AND kd_strata = 'S1'
ORDER BY no_ps, kd_pertanyaan, nilai;
```

#### Dashboard Kaprodi: Distribusi per Periode untuk Satu Prodi
```sql
SELECT
    periode_ijazah_id,
    kd_pertanyaan,
    nilai,
    n,
    pct
FROM evaluasi_wisudawan.mv_distribusi_jawaban
WHERE no_ps = 135              -- dikunci oleh scope kaprodi
  AND kd_set_opsi = 'S4_AGREE'
  AND periode_ijazah_id IS NOT NULL  -- hanya yang ada info periode
ORDER BY periode_ijazah_id, kd_pertanyaan, nilai;
```

---

## MV 2: `mv_skor_pertanyaan`

**Tujuan:** Sumber untuk **grafik rata-rata skor**, ranking pertanyaan, dan perbandingan antar dimensi. Hanya mencakup pertanyaan **ordinal** (`tipe = 'O'`) — nominal tidak boleh di-AVG.

**Alasan dibuat MV (bukan VIEW biasa):** Dashboard memerlukan respons cepat untuk query berulang dengan pola sama dari banyak user. Pre-computed lebih efisien daripada on-the-fly aggregation atas 7.500+ baris dengan JSONB.

**Granularitas:** 1 baris per kombinasi `(periode_ijazah_id, kd_strata, kd_fak, no_ps, kd_pertanyaan)`.

### Kolom

| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `periode_ijazah_id` | `INTEGER` | Periode wisuda (YYYYMM). NULL = tanpa info periode. |
| `kd_strata` | `CHAR(2)` | Jenjang studi. |
| `kd_fak` | `VARCHAR` | Kode fakultas. |
| `no_ps` | `INTEGER` | Kode program studi. |
| `kd_pertanyaan` | `VARCHAR(20)` | Kode pertanyaan (hanya ordinal). |
| `kd_grup` | `VARCHAR(15)` | Grup pertanyaan. |
| `kd_set_opsi` | `VARCHAR(20)` | Set opsi (`S4_AGREE`, `S4_FREQ`, `S5_EXPECT`, `S5_EXPECT_FSRD`, `S5_DEVELOP_SBM`). |
| `n_responden` | `BIGINT` | Jumlah responden yang menjawab pertanyaan ini. |
| `rata_rata` | `NUMERIC` | Rata-rata skor. Dibulatkan 4 desimal. |
| `std_dev` | `NUMERIC` | Standar deviasi skor. Dibulatkan 4 desimal. |
| `skor_min` | `NUMERIC` | Skor minimum yang diberikan. |
| `skor_max` | `NUMERIC` | Skor maksimum yang diberikan. |

### Catatan Interpretasi Skor per Skala

| `kd_set_opsi` | Range | Makna Skor Tinggi |
|---------------|-------|-------------------|
| `S4_AGREE` | 1–4 | Tingkat persetujuan tinggi |
| `S4_FREQ` | 1–4 | Frekuensi masalah tinggi (skor tinggi = lebih buruk) |
| `S5_EXPECT` | 1–5 | Harapan terpenuhi / terlampaui |
| `S5_EXPECT_FSRD` | 1–5 | Harapan terpenuhi (versi FSRD — nilai-4 berbeda dari S5_EXPECT) |
| `S5_DEVELOP_SBM` | 1–5 | Tingkat perkembangan kompetensi tinggi |

> ⚠️ **Jangan bandingkan** `rata_rata` antara `S5_EXPECT` dan `S5_EXPECT_FSRD` secara langsung — nilai-4 berbeda secara semantik.  
> ⚠️ **`S4_FREQ`:** skor tinggi bermakna negatif (sering mengalami masalah). Perlu perhatian khusus saat memvisualisasikan.

### Sumber Data Tiap Kolom

| Kolom MV | Sumber |
|----------|--------|
| Dimensi (periode, strata, fak, no_ps, pertanyaan, grup, set_opsi) | Join `respons` × `pertanyaan` × `ref_set_opsi` |
| `n_responden` | `COUNT(*)` |
| `rata_rata` | `AVG((respons.jawaban ->> kd_pertanyaan)::NUMERIC)` |
| `std_dev` | `STDDEV(...)` |
| `skor_min` / `skor_max` | `MIN(...)` / `MAX(...)` |

### Index

| Index | Kolom | Tujuan |
|-------|-------|--------|
| UNIQUE | `(periode_ijazah_id, kd_strata, kd_fak, no_ps, kd_pertanyaan)` | Identifikasi unik baris |
| B-tree | `kd_grup` | Filter per section |
| B-tree | `(kd_strata, kd_fak)` | Filter komposit dashboard |

### Contoh Query

#### Rata-rata Skor Section A per Fakultas (S1 saja)
```sql
SELECT
    kd_fak,
    kd_pertanyaan,
    rata_rata,
    std_dev,
    n_responden
FROM evaluasi_wisudawan.mv_skor_pertanyaan
WHERE kd_strata = 'S1'
  AND kd_grup = 'U03'
ORDER BY kd_fak, rata_rata DESC;
```

#### Ranking Pertanyaan Softskills per Prodi
```sql
SELECT
    kd_pertanyaan,
    rata_rata,
    n_responden,
    RANK() OVER (PARTITION BY no_ps ORDER BY rata_rata DESC) AS ranking
FROM evaluasi_wisudawan.mv_skor_pertanyaan
WHERE no_ps = 135
  AND kd_grup = 'U04'
ORDER BY ranking;
```

#### Trend Rata-rata Skor Fasilitas per Periode (non-NULL)
```sql
SELECT
    periode_ijazah_id,
    kd_pertanyaan,
    rata_rata,
    n_responden
FROM evaluasi_wisudawan.mv_skor_pertanyaan
WHERE kd_pertanyaan = 'U03_SQ012'   -- overall satisfaction ITB
  AND periode_ijazah_id IS NOT NULL
ORDER BY periode_ijazah_id;
```

#### Perbandingan Rata-rata Seluruh Section B antar Fakultas
```sql
SELECT
    kd_fak,
    ROUND(AVG(rata_rata), 3) AS rata_rata_section_b
FROM evaluasi_wisudawan.mv_skor_pertanyaan
WHERE kd_grup = 'U01'
  AND kd_strata = 'S1'
GROUP BY kd_fak
ORDER BY rata_rata_section_b DESC;
```

#### Dashboard Kaprodi: Skor vs Rata-rata Institusi
```sql
-- Bandingkan prodi dengan rata-rata seluruh ITB per pertanyaan
SELECT
    m.kd_pertanyaan,
    m.rata_rata          AS skor_prodi,
    avg_itb.rata_rata    AS skor_itb,
    m.rata_rata - avg_itb.rata_rata AS selisih
FROM evaluasi_wisudawan.mv_skor_pertanyaan m
JOIN (
    SELECT kd_pertanyaan, AVG(rata_rata) AS rata_rata
    FROM evaluasi_wisudawan.mv_skor_pertanyaan
    WHERE kd_strata = 'S1' AND kd_grup = 'U01'
    GROUP BY kd_pertanyaan
) avg_itb USING (kd_pertanyaan)
WHERE m.no_ps = 135              -- dikunci scope kaprodi
  AND m.kd_strata = 'S1'
  AND m.kd_grup = 'U01'
ORDER BY selisih;
```

---

## MV 3: `mv_wide_respons`

**Tujuan:** Tabel **flat per responden** — setiap kolom merepresentasikan satu pertanyaan. Digunakan untuk analisis individual, chatbot RAG, dan agen Text-to-SQL yang membutuhkan akses per baris (bukan agregasi).

**Granularitas:** 1 baris per responden (1:1 dengan `respons`).

**Catatan NULL:** Kolom section-spesifik akan `NULL` untuk responden yang tidak mengisi section tersebut — bukan berarti data hilang, tapi memang tidak berlaku (contoh: kolom `s101` akan NULL untuk responden S2/S3).

### Kolom Identitas

| Kolom | Tipe | Keterangan |
|-------|------|-----------|
| `response_id` | `INTEGER` | Surrogate PK dari `respons`. Unique index. |
| `survey_platform_response_id` | `INTEGER` | ID asli LimeSurvey. Bisa NULL. |
| `kd_strata` | `CHAR(2)` | Jenjang studi: `S1`, `S2`, `S3`, `PR`. |
| `kd_fak` | `VARCHAR` | Kode fakultas. |
| `no_ps` | `INTEGER` | Kode program studi. |
| `periode_ijazah_id` | `INTEGER` | Periode wisuda YYYYMM. 66.6% NULL. |
| `submit_date` | `TIMESTAMPTZ` | Waktu submit kuesioner. |

### Kolom Jawaban — Section A: Fasilitas ITB (U03)

Semua SMALLINT, skala `S4_AGREE` (1–4). Populasi: semua.

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

Skala `S4_AGREE` (1–4) untuk U01. `u02` nominal (1–7). `u02_other` TEXT. Populasi: semua.

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

Skala `S4_AGREE` (1–4). Populasi: semua.

`u04_sq001` Komunikasi lisan · `u04_sq002` Komunikasi tertulis · `u04_sq003` Bahasa asing · `u04_sq004` Penyelesaian masalah · `u04_sq005` Berpikir kritis · `u04_sq006` Introspeksi diri · `u04_sq007` Menyampaikan pendapat · `u04_sq008` Kerja tim · `u04_sq009` Kerja mandiri

### Kolom Jawaban — Section C2: Karakter (U05)

Skala `S4_AGREE` (1–4). Populasi: semua.

`u05_sq001` Kejujuran · `u05_sq002` Komitmen · `u05_sq003` Kecerdasan emosi · `u05_sq004` Kepedulian terhadap sesama · `u05_sq005` Objektivitas · `u05_sq006` Ketidakmudahan menyerah · `u05_sq007` Kepatuhan terhadap aturan

### Kolom Jawaban — Section D1: Permasalahan Studi (U06)

Skala `S4_FREQ` (1–4). Nilai ≥ 2 = pernah mengalami. Populasi: semua.

`u06_sq001` Permasalahan akademis · `u06_sq002` Keuangan · `u06_sq003` Pengaruh keuangan ke akademis · `u06_sq004` Psikologis · `u06_sq005` Pengaruh psikologis ke studi · `u06_sq006` Sosial budaya · `u06_sq007` Pengaruh sosial budaya ke studi · `u06_sq008` Kesehatan · `u06_sq009` Pengaruh kesehatan ke studi

### Kolom Jawaban — Section D2: Ketersediaan Dukungan (U07)

Skala `S5_EXPECT` (1–5). Hanya diisi responden yang pernah mengalami masalah. Populasi: semua.

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
| `s101` | Rencana studi lanjut | OPT_YA_TIDAK (1=Ya, 2=Tidak) |
| `s102` | Lokasi studi lanjut | OPT_LOKASI_STUDI (1–4) |
| `s103` | Kelanjutan bidang studi | OPT_KELANJUTAN_STUDI (1–5) |
| `s104_sq001` | MKU membekali softskill | S4_AGREE (1–4) |
| `s104_sq002` | MKU membekali hardskill | S4_AGREE (1–4) |
| `s104_sq003` | MKU membangun karakter | S4_AGREE (1–4) |
| `s104_sq004` | MKU memperluas wawasan | S4_AGREE (1–4) |

### Kolom Jawaban — Section H: Rencana Studi Lanjut (khusus S2)

`NULL` untuk strata S1, S3, PR.

| Kolom | Pertanyaan | Skala |
|-------|-----------|-------|
| `m01` | Rencana studi lanjut | OPT_YA_TIDAK |
| `m02` | Lokasi studi lanjut | OPT_LOKASI_STUDI |
| `m03` | Kelanjutan bidang studi | OPT_KELANJUTAN_STUDI |

### Kolom Jawaban — Section I: MKU (khusus S3)

`NULL` untuk strata S1, S2, PR.

| Kolom | Pertanyaan |
|-------|-----------|
| `d01_sq001` | MKU membekali softskill |
| `d01_sq002` | MKU membekali hardskill |
| `d01_sq003` | MKU membangun karakter |
| `d01_sq004` | MKU memperluas wawasan |

### Kolom Jawaban — Section J: FSRD Spesifik (24 kolom)

`NULL` untuk semua fakultas selain FSRD. Skala `S5_EXPECT_FSRD` (1–5).

| Grup | Kolom | Topik |
|------|-------|-------|
| FSRD01 | `fsrd01_sq001` – `fsrd01_sq005` | Tahap Persiapan Bersama (TPB) |
| FSRD02 | `fsrd02_sq001` – `fsrd02_sq003` | Sistem Perwalian |
| FSRD03 | `fsrd03_sq001` – `fsrd03_sq006` | Mata Kuliah Teori |
| FSRD04 | `fsrd04_sq001` – `fsrd04_sq006` | Mata Kuliah Praktika/Studio |
| FSRD05 | `fsrd05_sq001` – `fsrd05_sq004` | Tugas Akhir |

### Kolom Jawaban — Section K: SBM Spesifik (31 kolom)

`NULL` untuk semua fakultas selain SBM. Skala `S5_DEVELOP_SBM` (1–5).

`sbm01_sq001` – `sbm01_sq031` — 31 kompetensi outcomes program SBM (komunikasi, pengetahuan bisnis, analisis data, riset, jejaring, tanggung jawab profesional & etis, dll).

### Index

| Index | Kolom | Tujuan |
|-------|-------|--------|
| UNIQUE | `response_id` | Identifikasi unik baris (wajib untuk REFRESH CONCURRENTLY) |
| B-tree | `kd_strata` | Filter per strata |
| B-tree | `kd_fak` | Filter per fakultas |
| B-tree | `periode_ijazah_id` | Filter per periode |
| B-tree | `(kd_strata, kd_fak)` | Filter komposit |

### Contoh Query

#### RAG — Ambil Semua Free-text Saran dari Satu Prodi
```sql
SELECT
    response_id,
    kd_strata,
    g01q31 AS segi_positif,
    g01q32 AS segi_negatif,
    g01q33 AS saran_perbaikan,
    g01q34 AS saran_mahasiswa
FROM evaluasi_wisudawan.mv_wide_respons
WHERE no_ps = 135
  AND (g01q31 IS NOT NULL OR g01q32 IS NOT NULL
       OR g01q33 IS NOT NULL OR g01q34 IS NOT NULL);
```

#### Text-to-SQL — Responden yang Merencanakan Studi Lanjut ke Luar Negeri
```sql
SELECT
    response_id,
    kd_fak,
    no_ps,
    s102   AS lokasi_studi_lanjut,
    s103   AS kelanjutan_bidang
FROM evaluasi_wisudawan.mv_wide_respons
WHERE kd_strata = 'S1'
  AND s101 = 1           -- rencana studi lanjut = Ya
  AND s102 = 3;          -- lokasi = Luar Negeri
```

#### Text-to-SQL — Korelasi Masalah Psikologis vs Kepuasan Prodi (S1)
```sql
SELECT
    kd_fak,
    ROUND(AVG(u06_sq004::NUMERIC), 2)   AS avg_freq_masalah_psikologis,
    ROUND(AVG(u01_sq012::NUMERIC), 2)   AS avg_pilih_prodi_lagi,
    COUNT(*)                             AS n
FROM evaluasi_wisudawan.mv_wide_respons
WHERE kd_strata = 'S1'
  AND u06_sq004 IS NOT NULL
  AND u01_sq012 IS NOT NULL
GROUP BY kd_fak
ORDER BY avg_freq_masalah_psikologis DESC;
```

#### Dashboard — Data Individual Mahasiswa per Prodi (kaprodi scope)
```sql
SELECT
    response_id,
    submit_date,
    u03_sq012  AS kepuasan_fasilitas_itb,
    u01_sq012  AS pilih_prodi_lagi,
    u02        AS rekomendasi_prodi
FROM evaluasi_wisudawan.mv_wide_respons
WHERE no_ps = 135        -- dikunci scope kaprodi
  AND kd_strata = 'S1'
ORDER BY submit_date DESC;
```

---

## Hierarki Filter Dashboard

Implementasi akses berjenjang pada semua MV menggunakan **filter WHERE statis** berdasarkan scope pengguna, bukan row-level security terpisah.

| Level | Constraint SQL | Keterangan |
|-------|---------------|-----------|
| **Admin / Institusi** | *(tidak ada constraint tambahan)* | Akses seluruh data: semua filter tersedia (fakultas, prodi, strata, periode) |
| **Dekanat** | `WHERE kd_fak = '<kd_fak_dekan>'` | Scope dikunci ke satu fakultas. Filter prodi, strata, periode tetap tersedia. |
| **Kaprodi** | `WHERE no_ps = <no_ps_prodi>` | Scope dikunci ke satu prodi. Filter strata dan periode tetap tersedia. |

### Contoh Implementasi Filter Berjenjang

```sql
-- Fungsi helper: tambah WHERE clause sesuai scope user
-- (diimplementasikan di layer aplikasi/API)

-- Admin: query bebas
SELECT * FROM evaluasi_wisudawan.mv_skor_pertanyaan
WHERE kd_strata = $strata_filter
  AND periode_ijazah_id = $periode_filter;

-- Dekanat STEI: tambah kd_fak
SELECT * FROM evaluasi_wisudawan.mv_skor_pertanyaan
WHERE kd_fak = 'STEI'              -- injected dari session user
  AND kd_strata = $strata_filter
  AND periode_ijazah_id = $periode_filter;

-- Kaprodi IF (no_ps=135): tambah no_ps
SELECT * FROM evaluasi_wisudawan.mv_skor_pertanyaan
WHERE no_ps = 135                  -- injected dari session user
  AND kd_strata = $strata_filter
  AND periode_ijazah_id = $periode_filter;
```

---

## Ringkasan Perbandingan Ketiga MV

| Aspek | `mv_distribusi_jawaban` | `mv_skor_pertanyaan` | `mv_wide_respons` |
|-------|------------------------|---------------------|-------------------|
| **Granularitas** | Per (dimensi, pertanyaan, **nilai**) | Per (dimensi, pertanyaan) | Per **responden** |
| **Baris perkiraan** | ~300K–500K (banyak) | ~50K–100K | 7.535 |
| **Mencakup nominal** | ✅ Ya | ❌ Tidak (hanya ordinal) | ✅ Ya |
| **Mencakup free-text** | ❌ Tidak | ❌ Tidak | ✅ Ya |
| **Kolom utama** | `n`, `pct` | `rata_rata`, `std_dev` | Semua jawaban flat |
| **Cocok untuk** | Bar chart distribusi, top-2-box, incidence | Line/rank chart, benchmark | RAG, Text-to-SQL individual |
| **REFRESH mode** | Tanpa CONCURRENTLY | Tanpa CONCURRENTLY | **CONCURRENTLY** |
| **UNIQUE INDEX** | `(periode, strata, fak, no_ps, pertanyaan, nilai)` | `(periode, strata, fak, no_ps, pertanyaan)` | `response_id` |
