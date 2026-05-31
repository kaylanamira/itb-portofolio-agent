# `mv_jenis_dan_status_matkul` — Dokumentasi Materialized View

## Ringkasan

`mv_jenis_dan_status_matkul` adalah materialized view yang menyimpan posisi setiap mata kuliah dalam struktur kurikulum ITB. MV ini menjawab pertanyaan: *"MK ini termasuk jalur apa, dan sifatnya wajib atau pilihan, di prodi mana?"*

MV ini **bukan** tabel kelas aktual — melainkan referensi kurikulum yang bisa di-join ke `mv_kelas` atau tabel lainnya untuk memperkaya informasi status MK.

---

## Struktur & Grain

**Grain:** 1 baris = 1 kombinasi `(mata_kuliah_id, kode_prodi, kode_fakultas, paket/struktur)`

Satu mata kuliah **bisa menghasilkan lebih dari satu baris** untuk prodi yang sama, karena satu MK dapat masuk ke beberapa paket kurikulum sekaligus (misalnya: wajib di Major sekaligus menjadi inti di Minor). Ini bukan bug — ini mencerminkan realita struktur kurikulum ITB.

---

## Sumber Data

| Sumber | Nilai kolom `sumber` | Cakupan `tahun_kurikulum` | Jumlah kelas yang tercakup |
|---|---|---|---|
| `kur24.*` | `'kurikulum_2024'` | 2024, 2026 | ~14.102 kelas (7%) |
| `kurikulum.*` | `'kurikulum_lama'` | 2003–2023 | ~181.661 kelas (89%) |
| Tidak tercakup | — | 2000 ke bawah | ~7.734 kelas (3,8%) — dead zone historis |

> **Catatan:** Overlap antar kedua sumber = 0. Tidak ada MK yang terdaftar di keduanya secara bersamaan. `UNION ALL` aman tanpa risiko duplikasi.

---

## Skema Kolom

| Kolom | Tipe | Nullable | Deskripsi |
|---|---|---|---|
| `mata_kuliah_id` | `INTEGER` | NO | FK ke `utama.mata_kuliah`. Join key utama ke `mv_kelas`. |
| `kode_prodi` | `INTEGER` | NO | FK ke `utama.program_studi`. Prodi pemilik paket/struktur kurikulum. |
| `singkatan_prodi` | `TEXT` | NO | Singkatan prodi, misal `'IF'`, `'TM'`. Dari `utama.program_studi.kd_ps`. |
| `kode_fakultas` | `CHAR(4)` | NO | Kode fakultas dari `utama.program_studi`. Didapat via JOIN, tidak pernah NULL. |
| `tahun_kurikulum` | `INTEGER` | NO | Tahun kurikulum. Nilai yang tercakup: 2003, 2006, 2008, 2013, 2019, 2022, 2023, 2024, 2026. |
| `sumber` | `TEXT` | NO | Asal data: `'kurikulum_2024'` atau `'kurikulum_lama'`. Gunakan untuk filter per era. |
| `paket_id` | `INTEGER` | YES | ID paket dari `kur24.paket`. Terisi hanya untuk `sumber='kurikulum_2024'`, NULL untuk kurikulum lama. |
| `struktur_id` | `INTEGER` | YES | ID baris dari `kurikulum.struktur`. Terisi hanya untuk `sumber='kurikulum_lama'`, NULL untuk kurikulum 2024. |
| `kode_jenis` | `CHAR(1)` | YES | Kode jenis paket kurikulum. Hanya tersedia untuk `sumber='kurikulum_2024'`. NULL untuk kurikulum lama. Lihat referensi di bawah. |
| `nama_jenis` | `TEXT` | YES | Label `kode_jenis` dalam Bahasa Indonesia. Contoh: `'Major (Wajib)'`, `'Spesialisasi'`. NULL untuk kurikulum lama. |
| `nama_paket` | `TEXT` | YES | Nama spesifik paket. Contoh: `'Sains Biomedik'`, `'Teknik Pantai dan Manajemen Kawasan Pesisir'`. NULL jika paket tidak bernama atau kurikulum lama. |
| `kode_sifat` | `CHAR(1)` | NO | Sifat MK dalam paket/struktur, **sudah dinormalisasi ke `C`/`E` untuk kedua sumber**. Kurikulum lama: `W`→`C`, `P`→`E`. Lihat referensi di bawah. |
| `is_wajib_itb` | `BOOLEAN` | NO | `TRUE` jika MK ini termasuk dalam `kurikulum.struktur_wajib_itb` untuk prodi tersebut (misal: Agama, Pancasila, Sustainability). Hanya bermakna untuk `sumber='kurikulum_lama'`. Untuk kurikulum 2024 selalu `FALSE` — gunakan `kode_jenis='B'` (TPB) sebagai indikator wajib ITB di era 2024. |

### Referensi `kode_jenis`

| `kode_jenis` | `nama_jenis` | Keterangan |
|---|---|---|
| `W` | Major (Wajib) | Jalur utama prodi. MK inti program studi. |
| `B` | TPB | Tahap Persiapan Bersama. Setara Wajib ITB di era kurikulum 2024. |
| `S` | Spesialisasi | Mahasiswa memilih satu jalur spesialisasi dalam prodi. |
| `M` | Minor | Paket MK dari prodi lain yang diambil sebagai pelengkap. |
| `X` | Multidisiplin | Paket lintas disiplin. |
| `O` | Opsi (Magister) | Jalur pilihan untuk program S2. |
| `T` | Jalur Proses Pendidikan (Magister) | Jalur pendidikan spesifik S2. |
| `H` | Penyelarasan dari Sarjana Non-Linier | Untuk mahasiswa S2 dari latar S1 berbeda. |

> `kode_jenis` hanya tersedia untuk `sumber='kurikulum_2024'`. Untuk `sumber='kurikulum_lama'` nilainya selalu NULL karena schema kurikulum lama tidak memiliki konsep jenis paket.

### Referensi `kode_sifat`

Kolom ini **selalu bernilai `C` atau `E`** untuk kedua sumber. Normalisasi dilakukan saat MV dibentuk sehingga tidak perlu konversi tambahan di query.

| `kode_sifat` | Makna | Nilai asli di sumber |
|---|---|---|
| `C` | Core — MK **wajib diambil** dalam paket/jalur tersebut | `kurikulum_2024`: `C` · `kurikulum_lama`: `W` |
| `E` | Elective — MK **boleh dipilih** dari sekumpulan MK dalam paket | `kurikulum_2024`: `E` · `kurikulum_lama`: `P` |

---

## Contoh Isi Data

### Contoh 1 — MK yang masuk satu jalur saja (kurikulum lama)

| mata_kuliah_id | kode_prodi | singkatan_prodi | kode_fakultas | tahun_kurikulum | sumber | paket_id | struktur_id | kode_jenis | nama_jenis | nama_paket | kode_sifat | is_wajib_itb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 38156 | 129 | GL | FITB | 2019 | kurikulum_lama | NULL | 5821 | NULL | NULL | NULL | C | TRUE |

> MK "Agama dan Etika" di prodi GL (FITB), kurikulum 2019. Wajib (`W`→`C`) dan berstatus Wajib ITB.

---

### Contoh 2 — MK yang masuk banyak jalur sekaligus (kurikulum 2024)

| mata_kuliah_id | kode_prodi | singkatan_prodi | kode_fakultas | tahun_kurikulum | sumber | paket_id | struktur_id | kode_jenis | nama_jenis | nama_paket | kode_sifat | is_wajib_itb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 49408 | 125 | KL | FTSL | 2024 | kurikulum_2024 | 1583 | NULL | S | Spesialisasi | Manajemen Rekayasa Konstruksi dan Infrastruktur Kelautan | C | FALSE |
| 49408 | 125 | KL | FTSL | 2024 | kurikulum_2024 | 1579 | NULL | S | Spesialisasi | Teknik Pantai dan Manajemen Kawasan Pesisir | E | FALSE |
| 49408 | 125 | KL | FTSL | 2024 | kurikulum_2024 | 1584 | NULL | S | Spesialisasi | Energi Kelautan Terbarukan | E | FALSE |
| 49408 | 125 | KL | FTSL | 2024 | kurikulum_2024 | 1582 | NULL | S | Spesialisasi | Lingkungan Laut, Reklamasi dan Pengerukan | E | FALSE |

> MK "Metode Konstruksi Bangunan Laut" (KL) muncul 4 kali — wajib (`C`) di satu spesialisasi, pilihan (`E`) di tiga spesialisasi lainnya.

---

### Contoh 3 — MK yang masuk lintas jenis paket (kurikulum 2024)

| mata_kuliah_id | kode_prodi | singkatan_prodi | kode_fakultas | tahun_kurikulum | sumber | paket_id | struktur_id | kode_jenis | nama_jenis | nama_paket | kode_sifat | is_wajib_itb |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 51494 | 192 | MK | SBM | 2024 | kurikulum_2024 | 1050 | NULL | W | Major (Wajib) | NULL | C | FALSE |
| 51494 | 192 | MK | SBM | 2024 | kurikulum_2024 | 1814 | NULL | M | Minor | Kewirausahaan Teknologi | C | FALSE |
| 51494 | 192 | MK | SBM | 2024 | kurikulum_2024 | 1799 | NULL | X | Multidisiplin | Narasi Visual Dijital | C | FALSE |
| 51494 | 192 | MK | SBM | 2024 | kurikulum_2024 | 1801 | NULL | X | Multidisiplin | Bisnis Berbasis Hayati | C | FALSE |

> MK "Wawasan Pelanggan dan Model Bisnis" (SBM) adalah wajib prodi SBM, sekaligus menjadi inti di Minor Kewirausahaan dan dua paket Multidisiplin.

---

## Insight yang Bisa Diambil

**1. MK dengan peran paling luas dalam kurikulum**
MK yang muncul di banyak paket dan banyak jenis jalur adalah MK yang paling "universal" — relevan lintas program. Berguna untuk prioritasi pengembangan silabus.

**2. Distribusi beban wajib vs pilihan per prodi**
Dengan filter `kode_sifat='C'` dan `kode_jenis='W'`, bisa dihitung berapa banyak MK inti yang harus diambil mahasiswa di setiap prodi. Dibandingkan dengan `kode_sifat='E'`, bisa dilihat fleksibilitas kurikulum per prodi.

**3. MK wajib ITB yang coverage prodinya luas atau sempit**
Dengan filter `is_wajib_itb=TRUE`, bisa dilihat kategori wajib ITB mana (Agama, Pancasila, Lingkungan, dll.) yang diikuti hampir semua prodi vs yang hanya ada di sebagian prodi.

**4. Transisi kurikulum lama ke kurikulum 2024**
Dengan membandingkan `sumber='kurikulum_lama'` vs `sumber='kurikulum_2024'` untuk prodi yang sama, bisa dilihat apakah ada perubahan signifikan pada struktur kewajiban MK antar generasi kurikulum.

**5. Popularitas MK di paket Minor/Multidisiplin**
MK yang masuk ke banyak paket Minor atau Multidisiplin adalah MK yang dianggap bernilai lintas disiplin. Berguna untuk evaluasi relevansi MK secara institusional.

---

## Use Case & Contoh Query

### Use Case 1 — Lihat semua status MK untuk satu kelas tertentu

Berguna untuk menampilkan konteks kurikulum di dashboard kelas.

```sql
SELECT
    mv.kelas_id,
    mv.kode_mk,
    mv.nama_mk_id,
    mv.kode_prodi,
    ms.sumber,
    ms.kode_jenis,
    ms.nama_jenis,
    ms.nama_paket,
    ms.kode_sifat,
    ms.is_wajib_itb
FROM mv_kelas mv
LEFT JOIN mv_jenis_dan_status_matkul ms
       ON ms.mata_kuliah_id = mv.mata_kuliah_id
      AND ms.kode_prodi     = mv.kode_prodi
WHERE mv.kelas_id = 12345
ORDER BY ms.kode_jenis, ms.kode_sifat;
```

---

### Use Case 2 — Berapa MK wajib (Core) vs pilihan per prodi di kurikulum 2024

```sql
SELECT
    ms.kode_prodi,
    ms.singkatan_prodi,
    ms.kode_fakultas,
    ms.kode_jenis,
    ms.nama_jenis,
    COUNT(DISTINCT ms.mata_kuliah_id)
        FILTER (WHERE ms.kode_sifat = 'C')      AS jumlah_mk_core,
    COUNT(DISTINCT ms.mata_kuliah_id)
        FILTER (WHERE ms.kode_sifat = 'E')      AS jumlah_mk_elective
FROM mv_jenis_dan_status_matkul ms
WHERE ms.sumber     = 'kurikulum_2024'
  AND ms.kode_jenis = 'W'                       -- hanya jalur Major Wajib
GROUP BY ms.kode_prodi, ms.singkatan_prodi, ms.kode_fakultas,
         ms.kode_jenis, ms.nama_jenis
ORDER BY ms.kode_fakultas, ms.singkatan_prodi;
```

---

### Use Case 3 — MK yang masuk ke paling banyak paket (MK paling universal)

```sql
SELECT
    ms.mata_kuliah_id,
    mk.kd_kuliah,
    mk.nama->>'id'                          AS nama_mk,
    ms.kode_prodi,
    ms.singkatan_prodi,
    COUNT(DISTINCT ms.paket_id)             AS jumlah_paket,
    COUNT(DISTINCT ms.kode_jenis)           AS jumlah_jenis_paket,
    array_agg(DISTINCT ms.kode_jenis
              ORDER BY ms.kode_jenis)       AS daftar_kode_jenis
FROM mv_jenis_dan_status_matkul ms
JOIN utama.mata_kuliah mk ON mk.mata_kuliah_id = ms.mata_kuliah_id
WHERE ms.sumber = 'kurikulum_2024'
GROUP BY ms.mata_kuliah_id, mk.kd_kuliah, mk.nama,
         ms.kode_prodi, ms.singkatan_prodi
HAVING COUNT(DISTINCT ms.paket_id) > 2
ORDER BY jumlah_paket DESC
LIMIT 20;
```

---

### Use Case 4 — Semua MK wajib ITB beserta cakupan prodinya

```sql
SELECT
    wi.nama->>'id'                              AS kategori_wajib_itb,
    wi.kd_strata,
    COUNT(DISTINCT ms.kode_prodi)               AS jumlah_prodi,
    COUNT(DISTINCT ms.mata_kuliah_id)           AS jumlah_mk_unik,
    array_agg(DISTINCT mk.kd_kuliah
              ORDER BY mk.kd_kuliah)            AS kode_mk_list
FROM mv_jenis_dan_status_matkul ms
JOIN kurikulum.struktur_wajib_itb swi
       ON swi.mata_kuliah_id = ms.mata_kuliah_id
      AND swi.no_ps          = ms.kode_prodi
JOIN kurikulum.wajib_itb wi  ON wi.kd_wajib_itb  = swi.kd_wajib_itb
JOIN utama.mata_kuliah   mk  ON mk.mata_kuliah_id = ms.mata_kuliah_id
WHERE ms.is_wajib_itb = TRUE
GROUP BY wi.nama, wi.kd_strata
ORDER BY jumlah_prodi DESC;
```

---

### Use Case 5 — Perbandingan kewajiban MK antara kurikulum lama dan kurikulum 2024 untuk satu prodi

```sql
-- Contoh: prodi IF (kode_prodi=135), bandingkan tahun_kurikulum 2019 vs 2024
SELECT
    ms.sumber,
    ms.tahun_kurikulum,
    ms.kode_sifat,
    COUNT(DISTINCT ms.mata_kuliah_id)   AS jumlah_mk
FROM mv_jenis_dan_status_matkul ms
WHERE ms.kode_prodi      = 135
  AND ms.tahun_kurikulum IN (2019, 2024)
GROUP BY ms.sumber, ms.tahun_kurikulum, ms.kode_sifat
ORDER BY ms.tahun_kurikulum, ms.kode_sifat;
```

---

### Use Case 6 — Join ke mv_kelas: rata-rata skor kuesioner MK wajib vs pilihan

```sql
SELECT
    ms.kode_sifat,
    CASE ms.kode_sifat
        WHEN 'C' THEN 'Wajib / Core'
        WHEN 'E' THEN 'Pilihan / Elective'
    END                                         AS label_sifat,
    COUNT(DISTINCT mv.kelas_id)                 AS jumlah_kelas,
    ROUND(AVG(mv.avg_skor_overall), 2)          AS rata_skor_overall,
    ROUND(AVG(mv.avg_skor_capaian), 2)          AS rata_skor_capaian,
    ROUND(AVG(mv.dist_pct_lulus_A_C), 2)        AS rata_pct_lulus
FROM mv_kelas mv
JOIN mv_jenis_dan_status_matkul ms
       ON ms.mata_kuliah_id = mv.mata_kuliah_id
      AND ms.kode_prodi     = mv.kode_prodi
WHERE mv.tahun_ajaran  = '2023/2024'
  AND ms.kode_jenis    = 'W'                    -- hanya jalur Major Wajib
GROUP BY ms.kode_sifat
ORDER BY ms.kode_sifat;
```

---

## Keterbatasan & Catatan Penting

**1. MK dengan `tahun_kurikulum` 2000 ke bawah tidak tercakup**
Sekitar 7.734 kelas historis tidak akan mendapat data dari MV ini karena tidak ada sistem kurikulum yang mencatatnya. JOIN akan menghasilkan NULL — ini bukan error, melainkan fakta historis.

**2. `is_wajib_itb` hanya bermakna untuk kurikulum lama**
Untuk kurikulum 2024, gunakan `kode_jenis = 'B'` (TPB) sebagai indikator setara wajib ITB. Tidak ada tabel equivalen `struktur_wajib_itb` di schema `kur24.*`.

**3. JOIN ke `mv_kelas` bisa menghasilkan >1 baris per kelas**
Ini by design. Jika hanya butuh satu status per kelas (flatten), perlu tambahkan aturan prioritas di query, misalnya `DISTINCT ON (kelas_id)` dengan `ORDER BY kode_jenis` sesuai prioritas yang disepakati.

**4. Gap ~3.151 MK di kurikulum 2024**
Dari 7.232 MK ber-`tahun_kurikulum=2024` di `utama.mata_kuliah`, hanya 4.081 yang terdaftar di `kur24.paket_mk`. Sisa ~3.151 MK kemungkinan belum dimasukkan ke paket oleh prodi masing-masing — bukan kesalahan MV ini.

**5. Refresh tidak perlu ikut jadwal `mv_kelas`**
`mv_jenis_dan_status_matkul` hanya berubah jika ada update struktur kurikulum di `kur24.*` atau `kurikulum.*`. Refresh bisa dilakukan secara terpisah, tidak perlu setiap semester.

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_jenis_dan_status_matkul;
```
