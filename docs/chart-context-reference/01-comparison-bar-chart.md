# Chart: Perbandingan Entitas / Ranking Mata Kuliah (`EntityAwareChart`)

Komponen ini dipakai di **~16 titik** di dashboard (semua card berbasis skor kuesioner per fakultas/prodi). 

---

## 1. Apa isi chart ini

Menampilkan rata-rata 1 metrik skor kuesioner, dalam salah satu dari 2 mode:

- **(1) Mode perbandingan** (`chart_type: "bar_horizontal"`) — Mode perbandingan digunakan jika entitas yang ditampilkan berjumlah lebih dari 1 entitas. Banyak baris, 1 bar per fakultas/prodi. 
Mode ini muncul pada user dengan user_role : 
1. User Role 'Admin' : 
Secara default, 'Admin' akan memiliki view perbandingan lintas-fakultas. Kemudian, admin juga dapat melakukan drill down sehingga memiliki view perbandingan lintas-prodi.

2. User Role 'Direktorat' :
Secara default, 'Direktorat' akan memiliki view perbandingan lintas-fakultas. Kemudian, admin juga dapat melakukan drill down sehingga memiliki view perbandingan lintas-prodi.

3. User Role 'Dekanat' :
Secara default, 'Direktorat' akan memiliki view perbandingan lintas-prodi. 

- **(2) Mode ranking matkul** (`chart_type: "ranking_top_bottom"`) — List top-5 & List bottom-5 mata kuliah **dalam 1 entitas** (fakultas/prodi) berdasarkan metrik yang sama. Muncul saat scope user sudah mengerucut ke 1 entitas (Kaprodi selalu, atau Direktorat/Dekan setelah drill-down manual).

**Kartu yang memakai komponen ini** (title berbeda-beda, struktur payload sama):
- Rata-Rata Skor Kuesioner per Fakultas/Prodi (Tab Info Umum, metric `overall`)
- Q1, Q2, Q3 individual + Rata-Rata Q1-Q3 (Tab Luaran, metric `q21`/`q22`/`q23`/`capaian`)
- Q4, Q5, Q6, Q7 individual + Rata-Rata Q4-Q7 (Performa Dosen, metric `q24`-`q27`)
- Q8 (Rancangan Pelaksanaan, metric `q28`)
- Q9, Q10 individual + Rata-Rata Q9-Q10 (Sarana Prasarana, metric `q29`/`q30`/`sarana_prasarana`)
- Q11, Q12 individual + Rata-Rata Q11-Q12 (Performa Mahasiswa, metric `q35`/`q37`/`perilaku_mahasiswa`)
- Rata-Rata IP (Tab Luaran, panel kanan `GradeTrendSection`, metric `avg_ip`)

---

## 2. Insight yang diharapkan bisa diambil

**Mode perbandingan (banyak entitas):**
- Fakultas/prodi mana yang menonjol (tertinggi/terendah) untuk metrik ini.
- Seberapa lebar kesenjangan antar-entitas (apakah merata, atau ada outlier jauh di bawah rata-rata).
- Apakah ada entitas dengan skor di bawah batas wajar/di bawah threshold, yakni di bawah 3.0 dari skala 1-4.

**Mode ranking matkul (1 entitas):**
- Mata kuliah mana yang perlu perhatian (bottom-5) vs mata kuliah mana jadi contoh baik (top-5).
- Kalau top dan bottom **tumpang tindih** (edge case) — itu sinyal prodi/fakultas ini punya sedikit mata kuliah aktif, bukan indikasi mutu.
- Perbandingan skor top vs bottom dalam konteks jumlah mahasiswa (`jumlah_mahasiswa`) — mata kuliah skor rendah dengan mahasiswa banyak lebih prioritas dibanding yang sedikit.

---

## 3. Struktur payload `chart_context`

### Mode perbandingan (`bar_horizontal`)

Format chart_context perbandingan **lintas-fakultas** (milik user role 'Admin' & 'Direktorat'):
```json
{
  "chart_type": "bar_horizontal",
  "title": "Rata-Rata Skor Kuesioner per Fakultas",
  "y_axis_label": "Skor rata-rata (skala 1-4)",
  "series": [
    { 
      "kode_fakultas": "STEI", 
      "nama_fakultas_id": "Sekolah Teknik Elektro dan Informatika", 
      "avg_skor_overall": 3.86, 
      "delta_periode_lalu": 0.04 
    },
    { 
      "kode_fakultas": "FTMD", 
      "nama_fakultas_id": "Fakultas Teknik Mesin dan Dirgantara", 
      "avg_skor_overall": 3.81, 
      "delta_periode_lalu": -0.02 
    }
  ],
  "filters_applied": 
  { 
    "tahun_ajaran": "2024/2025", 
    "semester": 1
  }
}
```

Kalau granularity prodi (Dekan, atau Direktorat sudah drill 1 fakultas), field ganti jadi `kode_prodi`/`nama_prodi_id` alih-alih `kode_fakultas`/`nama_fakultas_id`. Kemudian, ditambahkan juga `no_prodi` karena kode_prodi bisa bernilai sama untuk jenjang yang berbeda.

Contoh isi chart_context perbandingan **lintas-prodi** (milik user role 'Dekanat'dan milik 'Admin' & 'Direktorat' jika melakukan drill-down):
```json
{
  "chart_type": "bar_horizontal",
  "title": "Rata-Rata Skor Kuesioner per Prodi",
  "y_axis_label": "Skor rata-rata (skala 1-4)",
  "series": [
    { 
      "no_prodi": 135, 
      "kode_prodi": "IF", 
      "nama_prodi_id": "Teknik Informatika", 
      "avg_skor_overall": 3.86, 
      "delta_periode_lalu": 0.04 
    },
    { 
      "no_prodi": 235, 
      "kode_prodi": "IF", 
      "nama_prodi_id": "Teknik Informatika", 
      "avg_skor_overall": 3.81, 
      "delta_periode_lalu": -0.02 
    },
    { 
      "no_prodi": 132, 
      "kode_prodi": "EL", 
      "nama_prodi_id": "Teknik Elektro", 
      "avg_skor_overall": 3.86, 
      "delta_periode_lalu": 0.04 
    },
    { 
      "no_prodi": 232, 
      "kode_prodi": "EL", 
      "nama_prodi_id": "Teknik Elektro", 
      "avg_skor_overall": 3.81, 
      "delta_periode_lalu": -0.02
    }
  ],
  "filters_applied": 
  { 
    "tahun_ajaran": "2024/2025", 
    "semester": 1 
  }
}
```

### Mode ranking matkul (`ranking_top_bottom`)

```json
{
  "chart_type": "ranking_top_bottom",
  "title": "Q8 — Kesesuaian Beban Kerja dengan SKS",
  "series": [
    { 
      "posisi_ranking": "top", 
      "kode_matkul": "IF2211", 
      "nama_matkul_id": "Struktur Data", 
      "skor_q28": 3.94, 
      "jumlah_mahasiswa": 42, 
      "jumlah_kelas": 2 
    },
    { 
      "posisi_ranking": "top", 
      "kode_matkul": "IF3130", 
      "nama_matkul_id": "Interaksi Manusia Komputer", 
      "skor_q28": 3.91, 
      "jumlah_mahasiswa": 38, 
      "jumlah_kelas": 1 },
    { 
      "posisi_ranking": "bottom", 
      "kode_matkul": "II3120", 
      "nama_matkul_id": "Layanan Sistem dan Teknologi Informasi", 
      "skor_q28": 2.92, 
      "jumlah_mahasiswa": 54, 
      "jumlah_kelas": 1 
    },
    { 
      "posisi_ranking": "bottom", 
      "kode_matkul": "II3220", 
      "nama_matkul_id": "Arsitektur Enterprise", 
      "skor_q28": 3.05, 
      "jumlah_mahasiswa": 47, 
      "jumlah_kelas": 1 
    }
  ],
  "filters_applied": 
  { 
    "tahun_ajaran": "2024/2025", 
    "semester": 1, 
    "no_prodi": "135" 
  }
}
```

`posisi_ranking` (`"top"` / `"bottom"`) adalah **satu-satunya field buatan** di seluruh payload ini — tidak ada representasi kolom database untuknya, murni hasil `ORDER BY` di query. Semua field lain (`kode_matkul`, `nama_matkul_id`, `skor_q28`, `jumlah_mahasiswa`, `jumlah_kelas`) adalah nama kolom/alias yang identik dengan response API backend.

---

## 4. Edge case yang WAJIB diketahui agen

### 4a. Top dan bottom bisa **tumpang tindih** (mata kuliah yang sama muncul di top matkul dan bottom matkul)

Terjadi kalau total mata kuliah aktif dalam suatu fakultas/program studi **kurang dari 10** (limit top + limit bottom). Contoh nyata: prodi dengan 7 mata kuliah aktif, `limit=5` → otomatis 3 mata kuliah muncul di kedua sisi top dan bottom.

**Ini bukan bug** — itu tandanya "seluruh mata kuliah yang ada ditampilkan", bukan ranking ketat dari populasi besar. Kalau agen melihat `kode_matkul` yang sama di posisi `top` dan `bottom`, **jangan** menyimpulkan itu kontradiksi data — jelaskan ke user bahwa itu karena jumlah mata kuliah di prodi ini memang sedikit.

### 4b. `series` bisa kosong

Kalau tidak ada data untuk filter yang aktif (misal semester yang dipilih belum ada data kuesioner masuk), `series: []`. Agen **harus** menjawab bahwa data tidak tersedia untuk kondisi filter tersebut — jangan mengarang angka.

### 4c. `delta_periode_lalu` bisa `null`

Kalau entitas ini baru pertama kali punya data (tidak ada periode sebelumnya untuk dibandingkan), `delta_periode_lalu: null`. Jangan diinterpretasi sebagai "tidak berubah" (0) — itu berarti "tidak ada data pembanding".

### 4d. Metric `q4_q7` — TIDAK ADA kolom tunggal

```json
{ "rata_rata_dari_kolom": ["skor_q24", "skor_q25", "skor_q26", "skor_q27"], "nilai": 3.72 }
```
Kalau `metric` yang aktif adalah `q4_q7`, field skor **bukan** nama kolom tunggal — dia array `rata_rata_dari_kolom` + `nilai` hasil rata-ratanya. Ini karena Q4-Q7 sengaja dipisah dari Q8.

Contoh isi chart_context khusus metric rata-rata skor q4-q7 :
```json
{
  "query": "Insight apa yang bisa saya ambil dari grafik ini?",
  "session_id": "b7e1a2c3-9f4d-4a1e-8b2c-1d3e5f7a9b0c",
  "chart_context": {
    "chart_type": "bar_horizontal",
    "title": "Peringkat — Rata-Rata Q4-Q7 (Performa Dosen)",
    "y_axis_label": "Skor rata-rata (skala 1-4)",
    "series": [
      {
        "kode_fakultas": "STEI",
        "rata_rata_dari_kolom": ["skor_q24", "skor_q25", "skor_q26", "skor_q27"],
        "nilai": 3.79,
        "delta_periode_lalu": 0.03
      },
      {
        "kode_fakultas": "FTMD",
        "rata_rata_dari_kolom": ["skor_q24", "skor_q25", "skor_q26", "skor_q27"],
        "nilai": 3.71,
        "delta_periode_lalu": -0.02
      },
      {
        "kode_fakultas": "SF",
        "rata_rata_dari_kolom": ["skor_q24", "skor_q25", "skor_q26", "skor_q27"],
        "nilai": 3.65,
        "delta_periode_lalu": null
      }
    ],
    "filters_applied": {
      "tahun_ajaran": "2024/2025",
      "semester": 1
    }
  }
}
```

---

## 5. Tabel lengkap `metric` → nama field di `series`

| Nama field di `series` | Cakupan |
|---|---|
|`avg_skor_overall` | Q1-Q12 |
| `avg_skor_capaian` | Q1-Q3 |
| `avg_skor_sarana_prasarana` | Q9-Q10 |
| `avg_skor_perilaku_mahasiswa` | Q11-Q12 |
| `avg_ip_akhir_mahasiswa` | Rata-rata IP mahasiswa (bukan skor kuesioner) |
| `rata_rata_dari_kolom` + `nilai`| Q4-Q7 saja, exclude Q8 |
| `skor_qNN` (nama kolom persis : `q21` s.d. `q30`, `q35`, `q37` ) | 1 pertanyaan individual |

---
## 6. Perilaku khusus: chart "collapse" jadi ranking mata kuliah

Ini **pola arsitektur terpenting** untuk dipahami sebelum baca file chart lain di folder ini.

Banyak chart di dashboard ini berupa **perbandingan antar-entitas** (bar chart fakultas/prodi). Misalnya, membandingkan skor Q5 antar-prodi.

 Tapi begitu data yang tersisa cuma **1 entitas** (karena scope Kaprodi hanya dapat mengamati 1 entitas program studi, atau karena Direktorat drill-down ke 1 fakultas), chart itu **otomatis berubah bentuk** — bukan lagi bar 1 batang yang percuma, tapi jadi **list top-5/bottom-5 mata kuliah** dalam entitas tersebut.

**Implikasi untuk `chart_context`:** `chart_type` yang dikirim akan **berbeda** tergantung kondisi ini — bisa `"bar_horizontal"` (mode perbandingan banyak entitas menggunakan format bar chart) atau `"ranking_top_bottom"` (mode top/bottom matkul menggunakan format list, saat sudah collapse ke 1 entitas). Detail lengkap ada di file `01-entity-aware-comparison-chart.md`.

---

## 7. Penomoran pertanyaan kuesioner

UI menampilkan **Q1 sampai Q12**, tapi ini **bukan** nama kolom database. Kolom asli: `q21`-`q30`, `q35`, `q37`.

| Label UI | Kolom database | Topik |
|---|---|---|
| Q1 | `q21` | Mahasiswa memperoleh cukup informasi luaran mata kuliah |
| Q2 | `q22` | Perkuliahan diarahkan agar mahasiswa mencapai luaran mata kuliah |
| Q3 | `q23` | Mahasiswa mencapai luaran mata kuliah |
| Q4 | `q24` | Pelaksanaan perkuliahan terorganisir dengan baik |
| Q5 | `q25` | Dosen berkomunikasi dengan efektif |
| Q6 | `q26` | Dosen peduli terhadap pencapaian mahasiswa akan luaran mata kuliah |
| Q7 | `q27` | Dosen berlaku adil kepada mahasiswa |
| Q8 | `q28` | Kesesuaian beban kerja dengan SKS |
| Q9 | `q29` | Sarana prasarana untuk mata kuliah tersedia dengan memadai |
| Q10 | `q30` | Tersedia cukup fasilitas pendukung di luar kuliah |
| Q11 | `q35` | Mahasiswa berusaha dengan sungguh-sungguh mengikuti mata kuliah |
| Q12 | `q37` | Mahasiswa memperoleh pengalaman belajar yang positif |

**Semua field di request payload pada field `chart_context.series` di seluruh dashboard memakai nama kolom database asli** (`skor_q28`, bukan `skor_q8`) — bukan alias UI. Ini disengaja, supaya agen bisa mencocokkan nama field langsung ke `COMMENT ON COLUMN` di database (lihat `agent/tools/schema_retriever.py`), tanpa perlu tabel terjemahan tambahan.

### Kelompok gabungan (composite)

| Kolom komposit | Cakupan |
|---|---|
| `avg_skor_capaian` | Q1-Q3 |
| `avg_skor_sarana_prasarana` | Q9-Q10 |
| `avg_skor_perilaku_mahasiswa` | Q11-Q12 |
| `avg_skor_overall` | Semua Q1-Q12 |

**Perhatian khusus:** 
Card dashboard "Performa Dosen (Q4-Q7)" **sengaja tidak** memakai kolom `avg_skor_pelaksanaan` yang ada di regular view karena mencakup Q8. 

Nilai dashboard "Performa Dosen (Q4-Q7)" dihitung manual dari merata-ratakan `skor_q24`+`skor_q25`+`skor_q26`+`skor_q27`. 

Kalau agen melihat metric ini di `chart_context`, field-nya akan berupa :
`rata_rata_dari_kolom: ["skor_q24","skor_q25","skor_q26","skor_q27"]`,
bukan `avg_skor_pelaksanaan`.

---

## 8. Catatan untuk agen

- Skala skor kuesioner **selalu 1.00-4.00**. Nilai IP (`avg_ip_akhir_mahasiswa`) juga skala **0.00-4.00** (bukan 0-100).
- Threshold umum yang dipakai UI dashboard untuk "perlu perhatian": skor **di bawah 3.0**. Kalau relevan dengan pertanyaan user, agen boleh pakai ambang ini sebagai rujukan, tapi **jangan klaim ini standar resmi ITB** kalau tidak diminta eksplisit — cukup sebut sebagai observasi.
- `jumlah_kelas` = jumlah kelas paralel mata kuliah itu pada periode yang difilter (bisa >1 kalau matkul besar dibuka beberapa kelas).