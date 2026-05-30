# `analitik.mv_portofolio` — Dokumentasi Lengkap

> **Materialized View** | Schema: `analitik` | Grain: **1 baris = 1 kelas**
>
> Sumber: `evaluasi.portofolio` ⋈ `analitik.mv_kelas`

---

## Deskripsi

`mv_portofolio` adalah wide table yang meratakan semua jawaban naratif dosen dalam portofolio perkuliahan menjadi kolom-kolom terstruktur. Dirancang sebagai sumber data utama untuk agen RAG dan query Text-to-SQL — semua teks sudah bersih dari HTML, semua dimensi kelas sudah tersedia tanpa JOIN tambahan.

Data portofolio adalah refleksi tahunan dosen setelah satu semester mengajar: metode yang digunakan, evaluasi ketercapaian outcomes, refleksi jujur terhadap proses, dan rekomendasi perbaikan ke depan. Ini adalah satu-satunya sumber teks kualitatif di sistem evaluasi ITB yang ditulis langsung oleh dosen.

---

## Konteks Historis

Sistem portofolio ITB pernah mengalami **phased rollout** — dua komponen evaluasi diperbarui di waktu berbeda:

| Komponen | Skema Lama | Skema Baru | Berlaku Mulai |
|---|---|---|---|
| Kuesioner Mahasiswa | q1–q20 | **q21–q37** | 2016 / Semester 1 |
| Portofolio Dosen | q1–q11 | **q12–q19** | 2018 / Semester 1 |

Akibatnya, **~11.618 kelas** dari rentang 2016/1 – 2017/2 berada dalam kondisi "era campur": kuesioner mahasiswa sudah format baru (q21+), tapi portofolio dosen masih format lama (q1–q11). Ini bukan anomali — kedua sistem memang dikelola secara independen.

Kolom `skema_pertanyaan` menandai kondisi ini per baris.

---

## Struktur Kolom

### Dimensi Kelas
*Diambil langsung dari `analitik.mv_kelas`, tidak perlu JOIN tambahan.*

| Kolom | Tipe | Keterangan |
|---|---|---|
| `kelas_id` | integer | **PK**. Identitas unik kelas |
| `kode_matkul` | char(6) | Kode mata kuliah, contoh: `MA1101` |
| `nama_matkul_id` | text | Nama mata kuliah (Bahasa Indonesia) |
| `nama_matkul_en` | text | Nama mata kuliah (Bahasa Inggris) |
| `sks` | integer | Jumlah SKS |
| `no_kelas` | integer | Nomor urut kelas dalam satu MK per semester |
| `semester` | smallint | `1` = ganjil, `2`/`3` = genap/pendek |
| `tahun` | smallint | Tahun akademik (4 digit) |
| `tahun_ajaran` | text | Format `YYYY/YYYY`, contoh: `2022/2023` |
| `tahun_kurikulum` | integer | Tahun kurikulum yang berlaku untuk MK ini |
| `jenis_nilai` | text | `ABCDE` atau `PassFail` |
| `kode_prodi` | integer | `no_ps` program studi penyelenggara |
| `singkatan_prodi` | char(2) | Singkatan prodi |
| `nama_prodi_id` | text | Nama program studi (Bahasa Indonesia) |
| `jenjang` | char(2) | `S1`, `S2`, `S3`, `D3`, dst. |
| `kode_fakultas` | varchar | Kode fakultas: `FMIPA`, `STEI`, `FTI`, dst. |
| `nama_fakultas_id` | text | Nama fakultas (Bahasa Indonesia) |
| `semua_dosen_id` | integer[] | Array `dosen_id` semua pengajar kelas |
| `semua_dosen_nama_gelar` | varchar[] | Array nama lengkap + gelar semua pengajar |

---

### Metadata Portofolio

| Kolom | Tipe | Keterangan |
|---|---|---|
| `tgl_entri` | date | Tanggal dosen menyelesaikan pengisian |
| `lengkap` | boolean | `TRUE` jika sudah diverifikasi lengkap |
| `nilai_portofolio` | integer | Nilai numerik hasil verifikasi |
| `skema_pertanyaan` | text | `'baru'` / `'lama'` / `'kosong'` — lihat tabel di bawah |

**Nilai `skema_pertanyaan`:**

| Nilai | Pertanyaan | Rentang Semester | Jumlah Baris |
|---|---|---|---|
| `'baru'` | kd_pertanyaan 12–19 | [20181, ∞) | ~54.533 |
| `'lama'` | kd_pertanyaan 1–11 | sebelum 20181 | ~27.363 |
| `'kosong'` | isian NULL atau `{}` | — | 1 |

---

### Jawaban Dosen — Era Baru (`skema_pertanyaan = 'baru'`)
*Semua kolom bertipe `text`, sudah distrip HTML. `NULL` = tidak diisi.*

| Kolom | kd_pertanyaan | Grup | Pertanyaan |
|---|---|---|---|
| `metode_perkuliahan` | 12 | Penyelenggaraan Perkuliahan | Metode yang digunakan: diskusi, collaborative learning, kuliah tamu, project, dsb. |
| `komponen_penilaian` | 13 | Penyelenggaraan Perkuliahan | Komponen penilaian (UTS, UAS, kuis, tugas, dll.) beserta bobot dan konversi ke indeks |
| `statistik_nilai_kelas` | 14 | Ketercapaian Outcomes | Distribusi nilai ujian, PR, kuis, dan statistik kelas lainnya |
| `analisis_ketercapaian_outcomes` | 15 | Ketercapaian Outcomes | Tingkat keberhasilan pembelajaran dan ketercapaian outcomes beserta faktor-faktornya |
| `tanggapan_kuesioner_mahasiswa` | 16 | Refleksi Dosen | Tanggapan dosen terhadap hasil kuesioner mahasiswa |
| `refleksi_perkuliahan` | 17 | Refleksi Dosen | Refleksi pelaksanaan: keberhasilan, kegagalan, masalah belajar, temuan penting |
| `usulan_perbaikan_dosen` | 18 | Rekomendasi Tindak Lanjut | Hal yang perlu dilakukan dosen pada perkuliahan mendatang |
| `rekomendasi_ke_itb` | 19 | Rekomendasi Tindak Lanjut | Hal yang perlu dilakukan ITB: kurikulum, sarpras, fasilitas |

---

### Jawaban Dosen — Era Lama (`skema_pertanyaan = 'lama'`)
*Semua kolom bertipe `text`, sudah distrip HTML. `NULL` = tidak diisi.*

| Kolom | kd_pertanyaan | Grup | Pertanyaan |
|---|---|---|---|
| `lama_metode_perkuliahan` | 1 | Pelaksanaan Kuliah | Metode Perkuliahan |
| `lama_statistik_kelas` | 7 | Pelaksanaan Kuliah | Statistik Kelas |
| `lama_outcomes_matakuliah` | 2 | Pencapaian Tujuan/Outcomes | Outcomes Matakuliah |
| `lama_sistem_penilaian` | 3 | Pencapaian Tujuan/Outcomes | Sistem Penilaian |
| `lama_analisis_statistik_ketercapaian` | 8 | Pencapaian Tujuan/Outcomes | Analisis terhadap Statistik Kelas dan Ketercapaian Outcomes |
| `lama_uraian_kuesioner_statistik` | 4 | Refleksi | Uraian terhadap Hasil Kuesioner dan Statistik Kelas |
| `lama_komentar_kuesioner_mahasiswa` | 9 | Refleksi | Komentar terhadap Hasil Kuesioner Mahasiswa |
| `lama_refleksi_perkuliahan` | 5 | Refleksi | Refleksi Pelaksanaan Perkuliahan |
| `lama_rencana_tindak_lanjut` | 6 | Rencana Tindak Lanjut | Rencana Tindak Lanjut |
| `lama_rekomendasi_perbaikan_dosen` | 10 | Rekomendasi Tindak Lanjut | Rekomendasi Perbaikan oleh Dosen Berikutnya |
| `lama_rekomendasi_itb` | 11 | Rekomendasi Tindak Lanjut | Rekomendasi Perbaikan oleh ITB |

> **Catatan era campur (2016–2017):** 11.618 baris berlabel `'lama'` ini sudah menerima
> kuesioner mahasiswa format baru (q21–q37). Respons dosen terhadap kuesioner tersebut
> ada di `lama_uraian_kuesioner_statistik` dan `lama_komentar_kuesioner_mahasiswa`.

---

### Komentar Verifikator — Era Baru

| Kolom | kd_grup | Grup |
|---|---|---|
| `komentar_penyelenggaraan` | 6 | Penyelenggaraan Perkuliahan |
| `komentar_ketercapaian` | 7 | Ketercapaian Outcomes |
| `komentar_refleksi` | 8 | Refleksi Dosen |
| `komentar_rekomendasi` | 9 | Rekomendasi Tindak Lanjut |

### Komentar Verifikator — Era Lama

| Kolom | kd_grup | Grup |
|---|---|---|
| `lama_komentar_pencapaian_outcomes` | 1 | Pencapaian Tujuan/Outcomes |
| `lama_komentar_pelaksanaan_kuliah` | 2 | Pelaksanaan Kuliah |
| `lama_komentar_refleksi` | 3 | Refleksi |
| `lama_komentar_rencana_tindak_lanjut` | 4 | Rencana Tindak Lanjut |
| `lama_komentar_rekomendasi` | 5 | Rekomendasi Tindak Lanjut |

---

## Insight yang Bisa Diambil

### 1. Tren Kualitas Pengajaran per Prodi / Fakultas
Kolom `refleksi_perkuliahan` dan `analisis_ketercapaian_outcomes` berisi evaluasi diri dosen yang jujur. Dengan membandingkan teks dari semester ke semester per prodi, bisa terlihat apakah ada isu sistemik yang berulang (misal: rendahnya kehadiran mahasiswa, sulitnya mencapai outcome tertentu).

### 2. Pola Rekomendasi ke ITB yang Berulang
Kolom `rekomendasi_ke_itb` adalah channel dosen untuk menyampaikan kebutuhan institusional. Clustering teks dari kolom ini dapat mengidentifikasi kebutuhan sarpras atau kurikulum yang paling sering dimunculkan lintas fakultas.

### 3. Respons Dosen terhadap Kuesioner Mahasiswa
Kolom `tanggapan_kuesioner_mahasiswa` (era baru) dan `lama_uraian_kuesioner_statistik` + `lama_komentar_kuesioner_mahasiswa` (era lama) menunjukkan bagaimana dosen merespons feedback mahasiswa — apakah defensif, konstruktif, atau mengakui adanya masalah.

### 4. Gap antara Rencana dan Realisasi
Membandingkan `usulan_perbaikan_dosen` dari semester T dengan `metode_perkuliahan` atau `refleksi_perkuliahan` di semester T+1 (kelas yang sama, dosen yang sama) bisa menunjukkan apakah perbaikan yang diusulkan benar-benar diimplementasikan.

### 5. Kelengkapan Portofolio per Unit
Filter `lengkap = TRUE` vs `FALSE` per `kode_fakultas` atau `kode_prodi` memberi gambaran compliance pengisian portofolio — unit mana yang konsisten dan mana yang tidak.

### 6. Pengaruh Metode Pengajaran terhadap Ketercapaian Outcomes
Korelasi antara narasi di `metode_perkuliahan` (apakah pakai PBL, flipped classroom, dsb.) dengan `analisis_ketercapaian_outcomes` bisa menjadi bahan kajian pedagogik.

---

## Use Case

### RAG Agent
Setiap baris adalah satu dokumen portofolio. Chunk per kolom teks (bukan seluruh baris) karena temanmu pakai **chunk-level retrieval**. Kolom yang paling relevan untuk di-embed:

- Era baru: `metode_perkuliahan`, `analisis_ketercapaian_outcomes`, `refleksi_perkuliahan`, `usulan_perbaikan_dosen`, `rekomendasi_ke_itb`
- Era lama: padanan semantiknya (lihat tabel di atas)
- Filter metadata saat retrieval: `tahun_ajaran`, `kode_prodi`, `kode_fakultas`, `semua_dosen_id`

### Text-to-SQL / Analitik
Query langsung ke MV tanpa JOIN — semua dimensi sudah tersedia. Gunakan `skema_pertanyaan` sebagai filter era agar tidak mencampur kolom yang salah.

### Dashboard Monitoring Portofolio
Filter `lengkap`, `nilai_portofolio`, `tgl_entri` untuk monitoring compliance dan kualitas pengisian per unit per semester.

---

## Contoh Query

### Semua portofolio era baru dari satu prodi di satu tahun ajaran
```sql
SELECT
    kelas_id,
    kode_matkul,
    nama_matkul_id,
    semua_dosen_nama_gelar,
    refleksi_perkuliahan,
    usulan_perbaikan_dosen
FROM analitik.mv_portofolio
WHERE skema_pertanyaan  = 'baru'
  AND kode_prodi        = 232          -- ganti dengan no_ps yang diinginkan
  AND tahun_ajaran      = '2022/2023'
  AND lengkap           = TRUE
ORDER BY kode_matkul;
```

### Portofolio dari dosen tertentu lintas tahun
```sql
SELECT
    tahun_ajaran,
    kode_matkul,
    nama_matkul_id,
    refleksi_perkuliahan,
    usulan_perbaikan_dosen
FROM analitik.mv_portofolio
WHERE semua_dosen_id @> ARRAY[12345]   -- ganti dengan dosen_id
  AND skema_pertanyaan = 'baru'
ORDER BY tahun, semester;
```

### Rekomendasi ke ITB dari seluruh fakultas tahun terakhir
```sql
SELECT
    kode_fakultas,
    nama_fakultas_id,
    kode_matkul,
    nama_matkul_id,
    semua_dosen_nama_gelar,
    rekomendasi_ke_itb
FROM analitik.mv_portofolio
WHERE skema_pertanyaan = 'baru'
  AND tahun_ajaran     = '2023/2024'
  AND rekomendasi_ke_itb IS NOT NULL
ORDER BY kode_fakultas, kode_matkul;
```

### Tingkat kelengkapan portofolio per fakultas per tahun ajaran
```sql
SELECT
    kode_fakultas,
    nama_fakultas_id,
    tahun_ajaran,
    COUNT(*)                                        AS total_kelas,
    COUNT(*) FILTER (WHERE lengkap = TRUE)          AS sudah_lengkap,
    COUNT(*) FILTER (WHERE lengkap = FALSE
                        OR lengkap IS NULL)         AS belum_lengkap,
    ROUND(
        COUNT(*) FILTER (WHERE lengkap = TRUE)
        * 100.0 / COUNT(*), 1
    )                                               AS pct_lengkap
FROM analitik.mv_portofolio
WHERE skema_pertanyaan = 'baru'
GROUP BY kode_fakultas, nama_fakultas_id, tahun_ajaran
ORDER BY tahun_ajaran DESC, pct_lengkap ASC;
```

### Kelas era campur: portofolio lama + kuesioner baru (2016–2017)
```sql
SELECT
    p.kelas_id,
    p.kode_matkul,
    p.nama_matkul_id,
    p.tahun_ajaran,
    p.lama_uraian_kuesioner_statistik,
    p.lama_komentar_kuesioner_mahasiswa
FROM analitik.mv_portofolio p
WHERE p.skema_pertanyaan = 'lama'
  AND p.tahun IN (2016, 2017)
  AND p.lama_uraian_kuesioner_statistik IS NOT NULL
ORDER BY p.tahun, p.semester;
```

### Portofolio per dosen untuk satu mata kuliah lintas tahun (lacak konsistensi perbaikan)
```sql
SELECT
    tahun_ajaran,
    semester,
    semua_dosen_nama_gelar,
    metode_perkuliahan,
    analisis_ketercapaian_outcomes,
    refleksi_perkuliahan,
    usulan_perbaikan_dosen
FROM analitik.mv_portofolio
WHERE kode_matkul      = 'IF3110'      -- ganti kode MK
  AND skema_pertanyaan = 'baru'
ORDER BY tahun, semester;
```

---

## Catatan Teknis

**Refresh:** Jalankan setelah `analitik.mv_kelas` selesai di-refresh.
```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY analitik.mv_kelas;
REFRESH MATERIALIZED VIEW CONCURRENTLY analitik.mv_portofolio;
```

**HTML stripping:** Semua kolom teks diproses via `analitik.strip_html()` — tag HTML (`<p>`, `<br>`, dll.) dan entitas (`&amp;`, `&nbsp;`, dll.) sudah dihilangkan. Nilai kosong setelah stripping dikembalikan sebagai `NULL`.

**Index yang tersedia:**

| Index | Kolom | Kegunaan |
|---|---|---|
| `idx_mv_portofolio_pk` | `kelas_id` | UNIQUE, wajib untuk `REFRESH CONCURRENTLY` |
| `idx_mv_portofolio_tahun_ajaran` | `(tahun_ajaran, kode_prodi)` | Filter utama analitik & RAG |
| `idx_mv_portofolio_matkul` | `(kode_matkul, tahun_ajaran)` | Cari satu MK lintas tahun |
| `idx_mv_portofolio_dosen_arr` | `semua_dosen_id` (GIN) | `@>` filter per dosen |
| `idx_mv_portofolio_fak_semester` | `(kode_fakultas, semester, tahun)` | Dashboard per fakultas |
| `idx_mv_portofolio_era_baru` | `kelas_id WHERE skema='baru'` | Partial index era baru |
