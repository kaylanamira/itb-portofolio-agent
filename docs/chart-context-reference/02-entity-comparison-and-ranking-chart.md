# Chart: Perbandingan Entitas / Ranking Mata Kuliah 

> Struktur field `ChartContext` umum ada di `01-chart-context-type.md`. File ini hanya menjelaskan isi `series` spesifik untuk 2 `chart_type`: `entity_comparison_bar_chart` dan `course_ranking_top_bottom_list`.

Komponen ini dipakai di **~17 titik** di dashboard (semua card berbasis skor kuesioner per fakultas/prodi, termasuk rata-rata IP mahasiswa).

---

## 1. Apa isi chart ini

Menampilkan rata-rata 1 metrik skor (kuesioner atau IP), dalam salah satu dari 2 mode:

- **(1) Mode perbandingan** (`chart_type: "entity_comparison_bar_chart"`) — dipakai kalau entitas yang ditampilkan berjumlah lebih dari 1 entitas. Banyak baris, 1 bar per fakultas/prodi. Mode ini muncul pada user dengan `user_role`:
  1. **Admin** — secara default punya view perbandingan lintas-fakultas, dan bisa drill-down ke view perbandingan lintas-prodi.
  2. **Direktorat** — sama seperti Admin: default lintas-fakultas, bisa drill-down ke lintas-prodi.
  3. **Dekanat** — secara default langsung mendapat view perbandingan lintas-prodi (dalam 1 fakultas).

- **(2) Mode ranking matkul** (`chart_type: "course_ranking_top_bottom_list"`) — list top-5 & list bottom-5 mata kuliah **dalam 1 entitas** (fakultas/prodi) berdasarkan metrik yang sama. Muncul saat scope user sudah mengerucut ke 1 entitas (Kaprodi selalu, atau Direktorat/Dekan setelah drill-down manual).

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
- Apakah ada entitas dengan skor di bawah batas wajar/di bawah threshold, yakni di bawah 3.0 dari skala 1-4 (untuk metric IP, threshold ini tidak berlaku — skala IP tetap 0-4 tapi tidak ada ambang "perlu perhatian" baku).

**Mode ranking matkul (1 entitas):**
- Mata kuliah mana yang perlu perhatian (bottom-5) vs mata kuliah mana jadi contoh baik (top-5).
- Kalau top dan bottom **tumpang tindih** (edge case) — itu sinyal prodi/fakultas ini punya sedikit mata kuliah aktif, bukan indikasi mutu.
- Perbandingan skor top vs bottom dalam konteks jumlah mahasiswa (`jumlah_mahasiswa`) — mata kuliah skor rendah dengan mahasiswa banyak lebih prioritas dibanding yang sedikit.

---

## 3. Struktur payload `chart_context`

### 3.1 Mode perbandingan (`entity_comparison_bar_chart`)

Dipakai untuk **17 metric** (16 metric skor kuesioner + rata-rata IP). Strukturnya identik antar-metric kecuali nama field skor.

**Field yang SELALU ada (identitas + filter), terlepas metric apa pun:**

| Field | Tipe | Catatan |
|---|---|---|
| `kode_fakultas` | string | ada kalau granularity fakultas |
| `nama_fakultas_id` | string | ada kalau granularity fakultas |
| `no_prodi` | int | ada kalau granularity prodi |
| `kode_prodi` | string | ada kalau granularity prodi |
| `nama_prodi_id` | string | ada kalau granularity prodi |
| `delta_periode_lalu` | float \| null | bisa `null`, lihat §4c |

**Field skor — skema kosong untuk semua 17 metric:**

| Metric | Field skor di `series` | Tipe |
|---|---|---|
| `overall` | `avg_skor_overall` | float |
| `capaian` (Q1-Q3) | `avg_skor_capaian` | float |
| `q21` (Q1) | `skor_q21` | float |
| `q22` (Q2) | `skor_q22` | float |
| `q23` (Q3) | `skor_q23` | float |
| `q4_q7` (Q4-Q7, KHUSUS — lihat §3.1.1) | `rata_rata_dari_kolom` (array) + `nilai` (float) | array + float |
| `q24` (Q4) | `skor_q24` | float |
| `q25` (Q5) | `skor_q25` | float |
| `q26` (Q6) | `skor_q26` | float |
| `q27` (Q7) | `skor_q27` | float |
| `q28` (Q8) | `skor_q28` | float |
| `sarana_prasarana` (Q9-Q10) | `avg_skor_sarana_prasarana` | float |
| `q29` (Q9) | `skor_q29` | float |
| `q30` (Q10) | `skor_q30` | float |
| `perilaku_mahasiswa` (Q11-Q12) | `avg_skor_perilaku_mahasiswa` | float |
| `q35` (Q11) | `skor_q35` | float |
| `q37` (Q12) | `skor_q37` | float |
| `avg_ip` | `avg_ip_akhir_mahasiswa` | float |

**Contoh JSON lengkap — granularity fakultas, metric `overall`:**
```json
{
  "chart_type": "entity_comparison_bar_chart",
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
  "filters_applied": {
    "tahun_ajaran": "2024/2025",
    "semester": 1
  }
}
```

**Contoh JSON lengkap — granularity prodi, metric `q21` (Q1 individual):**
```json
{
  "chart_type": "entity_comparison_bar_chart",
  "title": "Q1 — Informasi Luaran Mata Kuliah per Prodi",
  "y_axis_label": "Skor rata-rata (skala 1-4)",
  "series": [
    {
      "no_prodi": 135,
      "kode_prodi": "IF",
      "nama_prodi_id": "Teknik Informatika",
      "skor_q21": 3.72,
      "delta_periode_lalu": 0.02
    },
    {
      "no_prodi": 132,
      "kode_prodi": "EL",
      "nama_prodi_id": "Teknik Elektro",
      "skor_q21": 3.68,
      "delta_periode_lalu": null
    }
  ],
  "filters_applied": {
    "tahun_ajaran": "2024/2025",
    "semester": 1
  }
}
```

**Contoh JSON lengkap — granularity fakultas, metric `avg_ip` (rata-rata IP mahasiswa, BUKAN skor kuesioner):**
```json
{
  "chart_type": "entity_comparison_bar_chart",
  "title": "Rata-Rata Nilai per Fakultas",
  "y_axis_label": "IP rata-rata (skala 0-4)",
  "series": [
    {
      "kode_fakultas": "STEI",
      "nama_fakultas_id": "Sekolah Teknik Elektro dan Informatika",
      "avg_ip_akhir_mahasiswa": 3.42,
      "delta_periode_lalu": 0.05
    },
    {
      "kode_fakultas": "FTMD",
      "nama_fakultas_id": "Fakultas Teknik Mesin dan Dirgantara",
      "avg_ip_akhir_mahasiswa": 3.31,
      "delta_periode_lalu": -0.02
    },
    {
      "kode_fakultas": "SF",
      "nama_fakultas_id": "Sekolah Farmasi",
      "avg_ip_akhir_mahasiswa": 3.18,
      "delta_periode_lalu": null
    }
  ],
  "filters_applied": {
    "tahun_ajaran": "2024/2025",
    "semester": 1
  }
}
```

#### 3.1.1 Kasus KHUSUS — metric `q4_q7` (satu-satunya yang field skornya BUKAN nama kolom tunggal)

```json
{
  "chart_type": "entity_comparison_bar_chart",
  "title": "Peringkat — Rata-Rata Q4-Q7 (Performa Dosen)",
  "y_axis_label": "Skor rata-rata (skala 1-4)",
  "series": [
    {
      "kode_fakultas": "STEI",
      "nama_fakultas_id": "Sekolah Teknik Elektro dan Informatika",
      "rata_rata_dari_kolom": ["skor_q24", "skor_q25", "skor_q26", "skor_q27"],
      "nilai": 3.79,
      "delta_periode_lalu": 0.03
    },
    {
      "kode_fakultas": "FTMD",
      "nama_fakultas_id": "Fakultas Teknik Mesin dan Dirgantara",
      "rata_rata_dari_kolom": ["skor_q24", "skor_q25", "skor_q26", "skor_q27"],
      "nilai": 3.71,
      "delta_periode_lalu": -0.02
    },
    {
      "kode_fakultas": "SF",
      "nama_fakultas_id": "Sekolah Farmasi",
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
```
**Alasan `q4_q7` beda:** tidak ada 1 kolom database tunggal untuk "rata-rata Q4-Q7 saja" (kolom komposit `avg_skor_pelaksanaan` mencakup Q4-**Q8**, bukan Q4-Q7 — lihat `00-README.md` §4). Jadi field skornya harus berupa 2 bagian: `rata_rata_dari_kolom` (array nama kolom asli yang dirata-ratakan) + `nilai` (hasil rata-ratanya).

---

### 3.2 Mode ranking matkul (`course_ranking_top_bottom_list`)

Dipakai untuk **17 metric yang sama** seperti §3.1, tapi saat scope sudah collapse ke 1 entitas. Struktur `series` sama sekali beda dari §3.1 (berisi mata kuliah, bukan fakultas/prodi).

**Field yang SELALU ada:**

| Field | Tipe |
|---|---|
| `posisi_ranking` | `"top"` \| `"bottom"` (satu-satunya field buatan, murni hasil `ORDER BY`, tidak ada representasi kolom database) |
| `kode_matkul` | string |
| `nama_matkul_id` | string |
| *(field skor sesuai metric, lihat tabel §3.1)* | float / array+float |
| `jumlah_mahasiswa` | int |
| `jumlah_kelas` | int |

**Contoh JSON lengkap — metric `q28` (Q8):**
```json
{
  "chart_type": "course_ranking_top_bottom_list",
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
      "jumlah_kelas": 1
    },
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
  "filters_applied": {
    "tahun_ajaran": "2024/2025",
    "semester": 1,
    "no_prodi": 135
  }
}
```

**Contoh JSON lengkap — metric `avg_ip` (rata-rata IP, dalam mode ranking matkul):**
```json
{
  "chart_type": "course_ranking_top_bottom_list",
  "title": "Rata-Rata IP",
  "series": [
    {
      "posisi_ranking": "top",
      "kode_matkul": "IF2211",
      "nama_matkul_id": "Struktur Data",
      "avg_ip_akhir_mahasiswa": 3.68,
      "jumlah_mahasiswa": 42,
      "jumlah_kelas": 2
    },
    {
      "posisi_ranking": "bottom",
      "kode_matkul": "MA1101",
      "nama_matkul_id": "Kalkulus Lanjut",
      "avg_ip_akhir_mahasiswa": 2.85,
      "jumlah_mahasiswa": 61,
      "jumlah_kelas": 1
    }
  ],
  "filters_applied": {
    "tahun_ajaran": "2024/2025",
    "semester": 1,
    "no_prodi": 135
  }
}
```

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

Menggunakan field "rata_rata_dari_kolom": ["skor_q24", "skor_q25", "skor_q26", "skor_q27"] karena nilai tidak dapat diambil langsung dari regular view.

---

## 5. Catatan untuk agen

- Skala skor kuesioner **selalu 1.00-4.00**. Nilai IP (`avg_ip_akhir_mahasiswa`) juga skala **0.00-4.00** (bukan 0-100), tapi merupakan metrik yang secara konseptual berbeda dari skor kuesioner — jangan campur adukkan keduanya saat membandingkan angka.
- Threshold umum yang dipakai UI dashboard untuk "perlu perhatian" pada skor kuesioner: skor **di bawah 3.0**. Kalau relevan dengan pertanyaan user, agen boleh pakai ambang ini sebagai rujukan, tapi **jangan klaim ini standar resmi ITB** kalau tidak diminta eksplisit — cukup sebut sebagai observasi.
- `jumlah_kelas` = jumlah kelas paralel mata kuliah itu pada periode yang difilter (bisa >1 kalau matkul besar dibuka beberapa kelas).