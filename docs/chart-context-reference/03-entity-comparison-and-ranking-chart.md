# Chart: Perbandingan Entitas / Ranking Kelas

Komponen ini dipakai di **~17 titik** di dashboard (semua card berbasis skor kuesioner per fakultas/prodi, termasuk rata-rata IP mahasiswa).

---

## 1. Apa isi chart ini

Menampilkan rata-rata 1 metrik skor (kuesioner atau IP), dalam salah satu dari 2 mode:

- **(1) Mode perbandingan** (`chart_type: "entity_comparison_bar_chart"`) — dipakai kalau entitas yang ditampilkan berjumlah lebih dari 1 entitas (perbandingan lintasfakultas atau lintasprogram studi). Mode ini muncul pada user dengan `user_role`:
  1. **Admin** — secara default punya view perbandingan lintas-fakultas, dan bisa drill-down ke view perbandingan lintas-prodi.
  2. **Direktorat** — sama seperti Admin: default lintas-fakultas, bisa drill-down ke lintas-prodi.
  3. **Dekanat** — secara default langsung mendapat view perbandingan lintas-prodi (dalam 1 fakultas).

- **(2) Mode ranking kelas** (`chart_type: "course_ranking_top_bottom_list"`) — list top-5 & list bottom-5 **kelas** (bukan mata kuliah) **dalam 1 entitas** (fakultas/prodi) berdasarkan metrik yang sama. Muncul saat scope user sudah mengerucut ke 1 entitas (Kaprodi selalu, atau Direktorat/Dekan setelah drill-down manual). 1 mata kuliah (`kode_matkul`) yang sama boleh muncul lebih dari sekali di `series` kalau ia punya beberapa kelas paralel (`kelas_id`/`no_kelas` berbeda) dengan kinerja berbeda.

**Kartu yang memakai komponen ini** (title berbeda-beda, struktur payload sama):
- Rata-Rata Skor Kuesioner per Fakultas/Prodi (Tab Info Umum, metric `overall`)
- Q1, Q2, Q3 individual + Rata-Rata Q1-Q3 (Tab Luaran, metric `q21`/`q22`/`q23`/`capaian`)
- Q4, Q5, Q6, Q7 individual + Rata-Rata Q4-Q7 (Performa Dosen, metric `q24`-`q27`)
- Q8 (Rancangan Pelaksanaan, metric `q28`)
- Q9, Q10 individual + Rata-Rata Q9-Q10 (Sarana Prasarana, metric `q29`/`q30`/`sarana_prasarana`)
- Q11, Q12 individual + Rata-Rata Q11-Q12 (Performa Mahasiswa, metric `q35`/`q37`/`perilaku_mahasiswa`)
- Rata-Rata IP (Tab Luaran, panel kanan `GradeTrendSection`, metric `avg_ip`)

---

## 2. Struktur payload `chart_context`

### 2.1 Mode perbandingan (`entity_comparison_bar_chart`)

Dipakai untuk **17 metric** (16 metric skor kuesioner + rata-rata IP). Strukturnya identik antar-metric kecuali nama field skor. Termasuk metric `q4_q7` (lihat §2.1.1) — `hint`-nya tetap sama dengan metric lain di granularitas yang sama, tidak ada varian khusus.

**Field yang SELALU ada (identitas + filter), terlepas metric apa pun:**

| Field | Tipe | Catatan |
|---|---|---|
| `kode_fakultas` | string | ada kalau granularity fakultas |
| `nama_fakultas_id` | string | ada kalau granularity fakultas |
| `no_prodi` | int | ada kalau granularity prodi |
| `kode_prodi` | string | ada kalau granularity prodi |
| `nama_prodi_id` | string | ada kalau granularity prodi |
| `delta_periode_lalu` | float \| null | bisa `null` |

**Field skor — skema kosong untuk semua 17 metric:**

| Metric | Field skor di `series` | Tipe |
|---|---|---|
| `overall` | `avg_skor_overall` | float |
| `capaian` (Q1-Q3) | `avg_skor_capaian` | float |
| `q21` (Q1) | `skor_q21` | float |
| `q22` (Q2) | `skor_q22` | float |
| `q23` (Q3) | `skor_q23` | float |
| `q4_q7` (Q4-Q7, KHUSUS — lihat §2.1.1) | `rata_rata_dari_kolom` (array) + `nilai` (float) | array + float |
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
    "semester": [1],
    "kode_fakultas": ["STEI", "FTMD"]
  },
  "hint": [
    "Identifikasi fakultas dengan nilai tertinggi dan terendah pada metrik ini.",
    "Identifikasi seberapa lebar kesenjangan antarfakultas (apakah merata, atau ada outlier jauh di bawah rata-rata)",
    "Untuk metrik skor kuesioner (skor_q21 sampai skor_q37), nilai di bawah 3.0 (skala 1-4) mengindikasikan area yang perlu perhatian; ambang ini tidak berlaku untuk metrik avg_ip."
  ]
}
```
**Tidak ada `question_reference` di sini** — `avg_skor_overall` adalah metric komposit (rata-rata Q1-Q12), bukan 1 pertanyaan individual (lihat `01-chart-context-type.md` §5.3).

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
    "semester": [1],
    "kode_fakultas": ["STEI"],
    "no_prodi": [132, 135]
  },
  "hint": [
    "Identifikasi program studi dengan nilai tertinggi dan terendah pada metrik ini.",
    "Identifikasi seberapa lebar kesenjangan antarprogram studi (apakah merata, atau ada outlier jauh di bawah rata-rata)",
    "Untuk metrik skor kuesioner (skor_q21 sampai skor_q37), nilai di bawah 3.0 (skala 1-4) mengindikasikan area yang perlu perhatian; ambang ini tidak berlaku untuk metrik avg_ip."
  ],
  "question_reference": {
    "skor_q21": { "kode_pertanyaan_frontend": "Q1", "pertanyaan": "Mahasiswa memperoleh cukup informasi luaran mata kuliah" }
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
    "semester": [1],
    "kode_fakultas": ["STEI", "FTMD", "SF"]
  },
  "hint": [
    "Identifikasi fakultas dengan nilai tertinggi dan terendah pada metrik ini.",
    "Identifikasi seberapa lebar kesenjangan antarfakultas (apakah merata, atau ada outlier jauh di bawah rata-rata)",
    "Untuk metrik skor kuesioner (skor_q21 sampai skor_q37), nilai di bawah 3.0 (skala 1-4) mengindikasikan area yang perlu perhatian; ambang ini tidak berlaku untuk metrik avg_ip."
  ]
}
```
**Tidak ada `question_reference` di sini** — `avg_ip_akhir_mahasiswa` bukan kolom pertanyaan kuesioner (lihat `01-chart-context-type.md` §5.3).

#### 2.1.1 Kasus KHUSUS — metric `q4_q7` (satu-satunya yang field skornya BUKAN nama kolom tunggal)

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
    "semester": [1],
    "kode_fakultas": ["STEI", "FTMD", "SF"]
  },
  "hint": [
    "Identifikasi fakultas dengan nilai tertinggi dan terendah pada metrik ini.",
    "Identifikasi seberapa lebar kesenjangan antarfakultas (apakah merata, atau ada outlier jauh di bawah rata-rata)",
    "Untuk metrik skor kuesioner (skor_q21 sampai skor_q37), nilai di bawah 3.0 (skala 1-4) mengindikasikan area yang perlu perhatian; ambang ini tidak berlaku untuk metrik avg_ip."
  ],
  "question_reference": {
    "skor_q24": { "kode_pertanyaan_frontend": "Q4", "pertanyaan": "Pelaksanaan perkuliahan terorganisir dengan baik" },
    "skor_q25": { "kode_pertanyaan_frontend": "Q5", "pertanyaan": "Dosen berkomunikasi dengan efektif" },
    "skor_q26": { "kode_pertanyaan_frontend": "Q6", "pertanyaan": "Dosen peduli terhadap pencapaian mahasiswa akan luaran mata kuliah" },
    "skor_q27": { "kode_pertanyaan_frontend": "Q7", "pertanyaan": "Dosen berlaku adil kepada mahasiswa" }
  }
}
```
**Alasan `q4_q7` beda (field, bukan hint):** tidak ada 1 kolom database tunggal untuk "rata-rata Q4-Q7 saja" (kolom komposit `avg_skor_pelaksanaan` mencakup Q4-**Q8**, bukan Q4-Q7 — lihat `00-README.md` §4). Jadi field skornya berupa 2 bagian: `rata_rata_dari_kolom` (array nama kolom asli yang dirata-ratakan) + `nilai` (hasil rata-ratanya). `hint`-nya sendiri tetap identik dengan metric lain di granularitas yang sama — tidak ada varian khusus untuk `q4_q7`. **`question_reference`-nya berisi 4 entry sekaligus** (satu per kolom di `rata_rata_dari_kolom`), bukan 1 entry seperti metric individual lain.

---

### 2.2 Mode ranking kelas (`course_ranking_top_bottom_list`)

Dipakai untuk **17 metric yang sama** seperti §2.1, tapi saat scope sudah collapse ke 1 entitas. Struktur `series` sama sekali beda dari §2.1 (berisi **kelas**, bukan fakultas/prodi).

**Field yang SELALU ada di tiap baris `series`:**

| Field | Tipe |
|---|---|
| `posisi_ranking` | `"top"` \| `"bottom"` (satu-satunya field buatan, murni hasil `ORDER BY`, tidak ada representasi kolom database) |
| `kode_matkul` | string |
| `nama_matkul_id` | string |
| `kelas_id` | int |
| `no_kelas` | string |
| *(field skor sesuai metric, lihat tabel §2.1)* | float / array+float |
| `jumlah_mahasiswa` | int |

**Field top-level tambahan (di luar `series`, sejajar dengan `title`/`filters_applied`/`hint`):**

| Field | Tipe |
|---|---|
| `jumlah_kelas_aktif` | int |

**Contoh JSON lengkap — metric `q28` (Q8), granularity prodi:**
```json
{
  "chart_type": "course_ranking_top_bottom_list",
  "title": "Q8 — Kesesuaian Beban Kerja dengan SKS",
  "series": [
    {
      "posisi_ranking": "top",
      "kode_matkul": "IF2211",
      "nama_matkul_id": "Struktur Data",
      "kelas_id": 10231,
      "no_kelas": "01",
      "skor_q28": 3.94,
      "jumlah_mahasiswa": 42
    },
    {
      "posisi_ranking": "top",
      "kode_matkul": "IF3130",
      "nama_matkul_id": "Interaksi Manusia Komputer",
      "kelas_id": 10254,
      "no_kelas": "01",
      "skor_q28": 3.91,
      "jumlah_mahasiswa": 38
    },
    {
      "posisi_ranking": "bottom",
      "kode_matkul": "IF2211",
      "nama_matkul_id": "Struktur Data",
      "kelas_id": 10232,
      "no_kelas": "02",
      "skor_q28": 2.85,
      "jumlah_mahasiswa": 45
    },
    {
      "posisi_ranking": "bottom",
      "kode_matkul": "II3220",
      "nama_matkul_id": "Arsitektur Enterprise",
      "kelas_id": 10298,
      "no_kelas": "01",
      "skor_q28": 3.05,
      "jumlah_mahasiswa": 47
    }
  ],
  "filters_applied": {
    "tahun_ajaran": "2024/2025",
    "semester": [1],
    "no_prodi": [135]
  },
  "hint": [
    "Bandingkan kelas top-5 dan bottom-5 untuk metrik ini.",
    "Prioritaskan kelas bottom dengan jumlah_mahasiswa besar karena dampaknya lebih luas."
  ],
  "jumlah_kelas_aktif": 58,
  "question_reference": {
    "skor_q28": { "kode_pertanyaan_frontend": "Q8", "pertanyaan": "Kesesuaian beban kerja dengan SKS" }
  }
}
```

**Contoh JSON lengkap — metric `avg_ip` (rata-rata IP), granularity prodi:**
```json
{
  "chart_type": "course_ranking_top_bottom_list",
  "title": "Rata-Rata IP",
  "series": [
    {
      "posisi_ranking": "top",
      "kode_matkul": "IF2211",
      "nama_matkul_id": "Struktur Data",
      "kelas_id": 10231,
      "no_kelas": "01",
      "avg_ip_akhir_mahasiswa": 3.68,
      "jumlah_mahasiswa": 42
    },
    {
      "posisi_ranking": "bottom",
      "kode_matkul": "MA1101",
      "nama_matkul_id": "Kalkulus Lanjut",
      "kelas_id": 10310,
      "no_kelas": "01",
      "avg_ip_akhir_mahasiswa": 2.85,
      "jumlah_mahasiswa": 61
    }
  ],
  "filters_applied": {
    "tahun_ajaran": "2024/2025",
    "semester": [1],
    "no_prodi": [135]
  },
  "hint": [
    "Bandingkan kelas top-5 dan bottom-5 untuk metrik ini.",
    "Prioritaskan kelas bottom dengan jumlah_mahasiswa besar karena dampaknya lebih luas."
  ],
  "jumlah_kelas_aktif": 42
}
```
**Tidak ada `question_reference` di sini** — `avg_ip_akhir_mahasiswa` bukan kolom pertanyaan kuesioner.

**Pengecualian metric:** `q4_q7` mengganti *(field skor)* dengan `rata_rata_dari_kolom` (array) + `nilai` (float), sama seperti §2.1.1 — `hint`-nya tetap identik dengan metric lain, dan `question_reference`-nya berisi 4 entry (sama seperti §2.1.1).

---

## 3. Catatan untuk agen

- Skala skor kuesioner **selalu 1.00-4.00**. Nilai IP (`avg_ip_akhir_mahasiswa`) juga skala **0.00-4.00** (bukan 0-100).
- `no_kelas` adalah identitas kelas (mis. `"01"`), sedangkan `kelas_id` adalah ID numerik internal kelas.
- `jumlah_kelas_aktif` hanya ada pada `chart_type: "course_ranking_top_bottom_list"` dan berada di **level top `chart_context`** (sejajar `title`/`filters_applied`), bukan di dalam tiap baris `series`.
- `question_reference` hanya ada untuk metrik yang menggunakan skor kuesioner (`skor_q21` - `skor_q37`). 
- `delta_periode_lalu` bisa `null` (periode pertama, belum ada pembanding).