# Template Skema Kosong `chart_context` — Seluruh `chart_type` × Granularitas Entitas

Gunakan file ini sebagai **rujukan implementasi** (frontend saat menyusun payload, agent/synthesizer saat memverifikasi bentuk payload yang diterima) — bukan untuk dibaca sebagai narasi.

"Granularitas" di sini artinya bentuk field identitas baris pada `series`: 
- **fakultas** (`kode_fakultas` + `nama_fakultas_id`) atau 
- **prodi** (`no_prodi` + `kode_prodi` + `nama_prodi_id`). 

Beberapa `chart_type` tidak punya granularitas entitas sama sekali (grain-nya periode atau bucket SKS).

---

## 1. `entity_comparison_bar_chart`

Granularitas: **fakultas** atau **prodi** (2 varian).

### 1.1 Granularitas fakultas
```json
{
  "chart_type": "entity_comparison_bar_chart",
  "title": "string",
  "y_axis_label": "string",
  "series": [
    {
      "kode_fakultas": "string",
      "nama_fakultas_id": "string",
      "<field_skor>": "float",
      "delta_periode_lalu": "float | null"
    }
  ],
  "filters_applied": { "tahun_ajaran": "string", "semester": "int" },
  "hint": [
    "Identifikasi fakultas dengan nilai tertinggi dan terendah pada metrik ini.",
    "Identifikasi seberapa lebar kesenjangan antarfakultas (apakah merata, atau ada outlier jauh di bawah rata-rata)",
    "Untuk metrik skor kuesioner (skor_q21 sampai skor_q37), nilai di bawah 3.0 (skala 1-4) mengindikasikan area yang perlu perhatian; ambang ini tidak berlaku untuk metrik avg_ip."
  ],
  "question_reference": {
    "<field_skor>": { "kode_pertanyaan": "string (mis. \"Q8\")", "pertanyaan": "string" }
  }
}
```

### 1.2 Granularitas prodi
```json
{
  "chart_type": "entity_comparison_bar_chart",
  "title": "string",
  "y_axis_label": "string",
  "series": [
    {
      "no_prodi": "int",
      "kode_prodi": "string",
      "nama_prodi_id": "string",
      "<field_skor>": "float",
      "delta_periode_lalu": "float | null"
    }
  ],
  "filters_applied": { "tahun_ajaran": "string", "semester": "int", "kode_fakultas": "string" },
  "hint": [
    "Identifikasi program studi dengan nilai tertinggi dan terendah pada metrik ini.",
    "Identifikasi seberapa lebar kesenjangan antarprogram studi (apakah merata, atau ada outlier jauh di bawah rata-rata)",
    "Untuk metrik skor kuesioner (skor_q21 sampai skor_q37), nilai di bawah 3.0 (skala 1-4) mengindikasikan area yang perlu perhatian; ambang ini tidak berlaku untuk metrik avg_ip."
  ],
  "question_reference": {
    "<field_skor>": { "kode_pertanyaan": "string (mis. \"Q8\")", "pertanyaan": "string" }
  }
}
```
**Pengecualian metric:** `q4_q7` mengganti `<field_skor>` dengan `rata_rata_dari_kolom` (array) + `nilai` (float) — lihat `03` §3.1.1.

---

## 2. `course_ranking_top_bottom_list`

Granularitas: **fakultas** atau **prodi** (menentukan isi `filters_applied`). Grain baris `series` adalah **kelas** (bukan mata kuliah) — 1 `kode_matkul` yang sama boleh muncul lebih dari sekali di `series`, termasuk sekaligus di posisi `top` dan `bottom`, selama `no_kelas`-nya berbeda. Itu bukan anomali — justru tujuan chart ini: membedah kinerja per kelas (dosen, sarana, komposisi mahasiswa berbeda tiap kelas walau mata kuliahnya sama).

### 2.1 Scope fakultas (collapse terjadi di level fakultas)
```json
{
  "chart_type": "course_ranking_top_bottom_list",
  "title": "string",
  "series": [
    {
      "posisi_ranking": "top",
      "kode_matkul": "string",
      "nama_matkul_id": "string",
      "kelas_id" : "int",
      "no_kelas": "string",
      "<field_skor>": "float",
      "jumlah_mahasiswa": "int"
    },
    {
      "posisi_ranking": "bottom",
      "kode_matkul": "string",
      "nama_matkul_id": "string",
      "kelas_id" : "int",
      "no_kelas": "string",
      "<field_skor>": "float",
      "jumlah_mahasiswa": "int"
    }
  ],
  "filters_applied": { "tahun_ajaran": "string", "semester": "int", "kode_fakultas": "string" },
  "hint": [
    "Bandingkan kelas top-5 dan bottom-5 untuk metrik ini.",
    "Prioritaskan kelas yang masuk list bottom-5 dengan jumlah_mahasiswa besar karena dampaknya lebih luas."
  ],
  "jumlah_kelas_aktif": "int",
  "question_reference": {
    "<field_skor>": { "kode_pertanyaan": "string (mis. \"Q8\")", "pertanyaan": "string" }
  }
}
```

### 2.2 Scope prodi (collapse terjadi di level prodi — kasus paling umum, Kaprodi)
```json
{
  "chart_type": "course_ranking_top_bottom_list",
  "title": "string",
  "series": [
    {
      "posisi_ranking": "top",
      "kode_matkul": "string",
      "nama_matkul_id": "string",
      "kelas_id" : "int",
      "no_kelas": "string",
      "<field_skor>": "float",
      "jumlah_mahasiswa": "int"
    },
    {
      "posisi_ranking": "bottom",
      "kode_matkul": "string",
      "nama_matkul_id": "string",
      "kelas_id" : "int",
      "no_kelas": "string",
      "<field_skor>": "float",
      "jumlah_mahasiswa": "int"
    }
  ],
  "filters_applied": { "tahun_ajaran": "string", "semester": "int", "no_prodi": "int" },
  "hint": [
    "Bandingkan kelas top-5 dan bottom-5 untuk metrik ini.",
    "Prioritaskan kelas bottom dengan jumlah_mahasiswa besar karena dampaknya lebih luas."
  ],
  "jumlah_kelas_aktif": "int",
  "question_reference": {
    "<field_skor>": { "kode_pertanyaan": "string (mis. \"Q8\")", "pertanyaan": "string" }
  }
}
```
**Pengecualian metric:** `q4_q7` mengganti `<field_skor>` dengan `rata_rata_dari_kolom` (array) + `nilai` (float) — lihat `03` §3.1.1.

---

## 3. `single_entity_percentage_value`

Granularitas: **fakultas** atau **prodi** (2 varian).

### 3.1 Granularitas fakultas
```json
{
  "chart_type": "single_entity_percentage_value",
  "title": "string",
  "series": [
    {
      "kode_fakultas": "string",
      "nama_fakultas_id": "string",
      "avg_pct_kehadiran_dosen": "float",
      "delta_periode_lalu": "float | null"
    }
  ],
  "filters_applied": { "tahun_ajaran": "string", "semester": "int", "kode_fakultas": "string" },
  "hint": [
    "Bandingkan angka ini dengan delta_periode_lalu untuk menilai tren membaik atau memburuk.",
    "Nilai berskala 0-100%, bukan skala skor kuesioner 1-4."
  ]
}
```

### 3.2 Granularitas prodi
```json
{
  "chart_type": "single_entity_percentage_value",
  "title": "string",
  "series": [
    {
      "no_prodi": "int",
      "kode_prodi": "string",
      "nama_prodi_id": "string",
      "avg_pct_kehadiran_dosen": "float",
      "delta_periode_lalu": "float | null"
    }
  ],
  "filters_applied": { "tahun_ajaran": "string", "semester": "int", "no_prodi": "int" },
  "hint": [
    "Bandingkan angka ini dengan delta_periode_lalu untuk menilai tren membaik atau memburuk.",
    "Nilai berskala 0-100%, bukan skala skor kuesioner 1-4."
  ]
}
```
**Catatan field:** ganti `avg_pct_kehadiran_dosen` dengan `avg_pct_kehadiran_mahasiswa` untuk kartu kehadiran mahasiswa — struktur dan `hint` lainnya identik.

---

## 4. `grade_distribution_stacked_bar_chart`

Granularitas: **fakultas** atau **prodi** (2 varian).

### 4.1 Granularitas fakultas
```json
{
  "chart_type": "grade_distribution_stacked_bar_chart",
  "title": "string",
  "series": [
    {
      "kode_fakultas": "string",
      "nama_fakultas_id": "string",
      "dist_pct_a": "float", 
      "dist_pct_ab": "float", 
      "dist_pct_b": "float", 
      "dist_pct_bc": "float",
      "dist_pct_c": "float", 
      "dist_pct_d": "float", 
      "dist_pct_e": "float", 
      "dist_pct_t": "float",
      "total_mahasiswa": "int"
    }
  ],
  "filters_applied": { "tahun_ajaran": "string", "semester": "int" },
  "hint": [
    "Bandingkan proporsi grade lulus (A-C) vs bermasalah (D-E-T) antarfakultas.",
    "Identifikasi mayoritas nilai yang diraih oleh setiap fakultas untuk mendapat gambaran pemahaman umum mahasiswa fakultas terkait terhadap pelaksanaan perkuliahan di fakultas tersebut.",
    "Identifikasi apakah terdapat flag pada hasil yang diraih, ditandai dengan 100% mahasiswa meraih suatu kategori nilai."
  ]
}
```

### 4.2 Granularitas prodi
```json
{
  "chart_type": "grade_distribution_stacked_bar_chart",
  "title": "string",
  "series": [
    {
      "no_prodi": "int",
      "kode_prodi": "string",
      "nama_prodi_id": "string",
      "dist_pct_a": "float", 
      "dist_pct_ab": "float", 
      "dist_pct_b": "float", 
      "dist_pct_bc": "float",
      "dist_pct_c": "float", 
      "dist_pct_d": "float", 
      "dist_pct_e": "float", 
      "dist_pct_t": "float",
      "total_mahasiswa": "int"
    }
  ],
  "filters_applied": { "tahun_ajaran": "string", "semester": "int", "kode_fakultas": "string" },
  "hint": [
    "Bandingkan proporsi grade lulus (A-C) vs bermasalah (D-E-T) antarfakultas.",
    "Identifikasi mayoritas nilai yang diraih oleh setiap program studi untuk mendapat gambaran pemahaman umum mahasiswa program studi terkait terhadap pelaksanaan perkuliahan di program studi tersebut.",
    "Identifikasi apakah terdapat flag pada hasil yang diraih, ditandai dengan 100% mahasiswa meraih suatu kategori nilai."
  ]
}
```

---

## 5. `grade_distribution_single_entity_bar_chart`

Granularitas: **fakultas** atau **prodi** (2 varian).

### 5.1 Granularitas fakultas
```json
{
  "chart_type": "grade_distribution_single_entity_bar_chart",
  "title": "string",
  "series": [
    {
      "kode_fakultas": "string",
      "nama_fakultas_id": "string",
      "dist_pct_a": "float", 
      "dist_pct_ab": "float", 
      "dist_pct_b": "float", 
      "dist_pct_bc": "float",
      "dist_pct_c": "float", 
      "dist_pct_d": "float", 
      "dist_pct_e": "float", 
      "dist_pct_t": "float",
      "total_mahasiswa": "int"
    }
  ],
  "filters_applied": { "tahun_ajaran": "string", "semester": "int", "kode_fakultas": "string" },
  "hint": [
    "Bandingkan proporsi grade lulus (A-C) vs bermasalah (D-E-T) antarfakultas.",
    "Identifikasi mayoritas nilai yang diraih oleh setiap fakultas untuk mendapat gambaran pemahaman umum mahasiswa fakultas terkait terhadap pelaksanaan perkuliahan di fakultas tersebut.",
    "Identifikasi apakah terdapat flag pada hasil yang diraih, ditandai dengan 100% mahasiswa meraih suatu kategori nilai."
  ]
}
```

### 5.2 Granularitas prodi
```json
{
  "chart_type": "grade_distribution_single_entity_bar_chart",
  "title": "string",
  "series": [
    {
      "no_prodi": "int",
      "kode_prodi": "string",
      "nama_prodi_id": "string",
      "dist_pct_a": "float", "dist_pct_ab": "float", "dist_pct_b": "float", "dist_pct_bc": "float",
      "dist_pct_c": "float", "dist_pct_d": "float", "dist_pct_e": "float", "dist_pct_t": "float",
      "total_mahasiswa": "int"
    }
  ],
  "filters_applied": { "tahun_ajaran": "string", "semester": "int", "no_prodi": "int" },
  "hint": [
    "Bandingkan proporsi grade lulus (A-C) vs bermasalah (D-E-T) antarfakultas.",
    "Identifikasi mayoritas nilai yang diraih oleh setiap program studi untuk mendapat gambaran pemahaman umum mahasiswa program studi terkait terhadap pelaksanaan perkuliahan di program studi tersebut.",
    "Identifikasi apakah terdapat flag pada hasil yang diraih, ditandai dengan 100% mahasiswa meraih suatu kategori nilai."
  ]
}
```

---

## 6. `score_trend_line_chart`

**Tidak punya granularitas struktural** — grain-nya periode (semester), bukan entitas. 

Entitas hanya muncul sebagai filter opsional di `filters_applied` (`kode_fakultas` atau `no_prodi`), tidak mengubah bentuk `series`. 

```json
{
  "chart_type": "score_trend_line_chart",
  "title": "string",
  "x_axis_label": "Semester",
  "y_axis_label": "string",
  "series": [
    { "period_label": "string", "tahun_ajaran": "string", "semester": "int", "avg_skor_overall": "float | null" }
  ],
  "filters_applied": { "kode_fakultas": "string (opsional)", "no_prodi": "int (opsional)" },
  "hint": [
    "Identifikasi arah tren (naik/turun) sepanjang periode yang tersedia.",
    "Perhatikan titik semester dengan kenaikan atau penurunan nilai yang tajam."
  ]
}
```

---

## 7. `score_heatmap_matrix_chart`

Granularitas: **fakultas** atau **prodi** (2 varian).

### 7.1 Granularitas fakultas
```json
{
  "chart_type": "score_heatmap_matrix_chart",
  "title": "string",
  "series": [
    {
      "kode_fakultas": "string",
      "nama_fakultas_id": "string",
      "skor_q21": "float | null", 
      "skor_q22": "float | null", 
      "skor_q23": "float | null",
      "skor_q24": "float | null", 
      "skor_q25": "float | null", 
      "skor_q26": "float | null", 
      "skor_q27": "float | null",
      "skor_q28": "float | null",
      "skor_q29": "float | null", 
      "skor_q30": "float | null",
      "skor_q35": "float | null", 
      "skor_q37": "float | null",
      "bottom_3_kolom": ["string"]
    }
  ],
  "filters_applied": { "tahun_ajaran": "string", "semester": "int" },
  "hint": [
    "Identifikasi pertanyaan (kolom) yang konsisten rendah di banyak fakultas.",
    "Identifikasi pertanyaan (kolom) bottom_3_kolom (3 pertanyaan dengan skor terendah) di setiap fakultas untuk mengidentifikasi poin pertanyaan apa yang perlu menjadi perhatian untuk evaluasi setiap fakultas"
  ],
  "question_reference": {
    "skor_q21": { "kode_pertanyaan": "Q1", "pertanyaan": "Mahasiswa memperoleh cukup informasi luaran mata kuliah" },
    "skor_q22": { "kode_pertanyaan": "Q2", "pertanyaan": "Perkuliahan diarahkan agar mahasiswa mencapai luaran mata kuliah" },
    "skor_q23": { "kode_pertanyaan": "Q3", "pertanyaan": "Mahasiswa mencapai luaran mata kuliah" },
    "skor_q24": { "kode_pertanyaan": "Q4", "pertanyaan": "Pelaksanaan perkuliahan terorganisir dengan baik" },
    "skor_q25": { "kode_pertanyaan": "Q5", "pertanyaan": "Dosen berkomunikasi dengan efektif" },
    "skor_q26": { "kode_pertanyaan": "Q6", "pertanyaan": "Dosen peduli terhadap pencapaian mahasiswa akan luaran mata kuliah" },
    "skor_q27": { "kode_pertanyaan": "Q7", "pertanyaan": "Dosen berlaku adil kepada mahasiswa" },
    "skor_q28": { "kode_pertanyaan": "Q8", "pertanyaan": "Kesesuaian beban kerja dengan SKS" },
    "skor_q29": { "kode_pertanyaan": "Q9", "pertanyaan": "Sarana prasarana untuk mata kuliah tersedia dengan memadai" },
    "skor_q30": { "kode_pertanyaan": "Q10", "pertanyaan": "Tersedia cukup fasilitas pendukung di luar kuliah" },
    "skor_q35": { "kode_pertanyaan": "Q11", "pertanyaan": "Mahasiswa berusaha dengan sungguh-sungguh mengikuti mata kuliah" },
    "skor_q37": { "kode_pertanyaan": "Q12", "pertanyaan": "Mahasiswa memperoleh pengalaman belajar yang positif" }
  }
}
```

### 7.2 Granularitas prodi
```json
{
  "chart_type": "score_heatmap_matrix_chart",
  "title": "string",
  "series": [
    {
      "no_prodi": "int",
      "kode_prodi": "string",
      "nama_prodi_id": "string",
      "skor_q21": "float | null", "skor_q22": "float | null", "skor_q23": "float | null",
      "skor_q24": "float | null", "skor_q25": "float | null", "skor_q26": "float | null", "skor_q27": "float | null",
      "skor_q28": "float | null",
      "skor_q29": "float | null", "skor_q30": "float | null",
      "skor_q35": "float | null", "skor_q37": "float | null",
      "bottom_3_kolom": ["string"]
    }
  ],
  "filters_applied": { "tahun_ajaran": "string", "semester": "int", "kode_fakultas": "string" },
  "hint": [
    "Identifikasi pertanyaan (kolom) yang konsisten rendah di banyak program studi.",
    "Identifikasi pertanyaan (kolom) bottom_3_kolom (3 pertanyaan dengan skor terendah) di setiap program studi untuk mengidentifikasi poin pertanyaan apa yang perlu menjadi perhatian untuk evaluasi setiap program studi"
  ],
  "question_reference": {
    "skor_q21": { "kode_pertanyaan": "Q1", "pertanyaan": "Mahasiswa memperoleh cukup informasi luaran mata kuliah" },
    "skor_q22": { "kode_pertanyaan": "Q2", "pertanyaan": "Perkuliahan diarahkan agar mahasiswa mencapai luaran mata kuliah" },
    "skor_q23": { "kode_pertanyaan": "Q3", "pertanyaan": "Mahasiswa mencapai luaran mata kuliah" },
    "skor_q24": { "kode_pertanyaan": "Q4", "pertanyaan": "Pelaksanaan perkuliahan terorganisir dengan baik" },
    "skor_q25": { "kode_pertanyaan": "Q5", "pertanyaan": "Dosen berkomunikasi dengan efektif" },
    "skor_q26": { "kode_pertanyaan": "Q6", "pertanyaan": "Dosen peduli terhadap pencapaian mahasiswa akan luaran mata kuliah" },
    "skor_q27": { "kode_pertanyaan": "Q7", "pertanyaan": "Dosen berlaku adil kepada mahasiswa" },
    "skor_q28": { "kode_pertanyaan": "Q8", "pertanyaan": "Kesesuaian beban kerja dengan SKS" },
    "skor_q29": { "kode_pertanyaan": "Q9", "pertanyaan": "Sarana prasarana untuk mata kuliah tersedia dengan memadai" },
    "skor_q30": { "kode_pertanyaan": "Q10", "pertanyaan": "Tersedia cukup fasilitas pendukung di luar kuliah" },
    "skor_q35": { "kode_pertanyaan": "Q11", "pertanyaan": "Mahasiswa berusaha dengan sungguh-sungguh mengikuti mata kuliah" },
    "skor_q37": { "kode_pertanyaan": "Q12", "pertanyaan": "Mahasiswa memperoleh pengalaman belajar yang positif" }
  }
}
```

---

## 8. `grading_composition_stacked_bar_chart`

Granularitas: **fakultas** atau **prodi** (2 varian). Semua field `avg_bobot_*` **opsional** — dihilangkan total dari baris kalau bobotnya 0 (lihat `08` §4).

### 8.1 Granularitas fakultas
```json
{
  "chart_type": "grading_composition_stacked_bar_chart",
  "title": "string",
  "series": [
    {
      "kode_fakultas": "string",
      "nama_fakultas_id": "string",
      "avg_bobot_uts": "float (opsional)",
      "avg_bobot_uas": "float (opsional)",
      "avg_bobot_tugas": "float (opsional)",
      "avg_bobot_kuis": "float (opsional)",
      "avg_bobot_praktikum": "float (opsional)",
      "avg_bobot_projek": "float (opsional)",
      "avg_bobot_partisipatif": "float (opsional)",
      "jumlah_kelas": "int"
    }
  ],
  "filters_applied": { "tahun_ajaran": "string", "semester": "int" },
  "hint": [
    "Identifikasi pola penilaian dominan tiap fakultas: berbasis ujian (total bobot rata-rata UTS dan bobot rata-rata UAS besar) atau berbasis tugas/proyek.",
    "Identifikasi komponen penilaian yang dominan digunakan oleh setiap fakultas.",
    "Bandingkan pola bobot antarfakultas untuk melihat perbedaan karakteristik penilaian antarfakultas."
  ]
}
```

### 8.2 Granularitas prodi
```json
{
  "chart_type": "grading_composition_stacked_bar_chart",
  "title": "string",
  "series": [
    {
      "no_prodi": "int",
      "kode_prodi": "string",
      "nama_prodi_id": "string",
      "avg_bobot_uts": "float (opsional)",
      "avg_bobot_uas": "float (opsional)",
      "avg_bobot_tugas": "float (opsional)",
      "avg_bobot_kuis": "float (opsional)",
      "avg_bobot_praktikum": "float (opsional)",
      "avg_bobot_projek": "float (opsional)",
      "avg_bobot_partisipatif": "float (opsional)",
      "jumlah_kelas": "int"
    }
  ],
  "filters_applied": { "tahun_ajaran": "string", "semester": "int", "kode_fakultas": "string" },
  "hint": [
    "Identifikasi pola penilaian dominan tiap program studi: berbasis ujian (total bobot rata-rata UTS dan bobot rata-rata UAS besar) atau berbasis tugas/proyek.",
    "Identifikasi komponen penilaian yang dominan digunakan oleh setiap program studi.",
    "Bandingkan pola bobot antarprogram studi untuk melihat perbedaan karakteristik penilaian antarprogram studi."
  ]
}
```

---

## 9. `grading_composition_single_entity_bar_chart`

Granularitas: **fakultas** atau **prodi** (2 varian). Field `avg_bobot_*` sama-sama opsional seperti §8.

### 9.1 Granularitas fakultas
```json
{
  "chart_type": "grading_composition_single_entity_bar_chart",
  "title": "string",
  "series": [
    {
      "kode_fakultas": "string",
      "nama_fakultas_id": "string",
      "avg_bobot_uts": "float (opsional)",
      "avg_bobot_uas": "float (opsional)",
      "avg_bobot_tugas": "float (opsional)",
      "avg_bobot_kuis": "float (opsional)",
      "avg_bobot_praktikum": "float (opsional)",
      "avg_bobot_projek": "float (opsional)",
      "avg_bobot_partisipatif": "float (opsional)",
      "jumlah_kelas": "int"
    }
  ],
  "filters_applied": { "tahun_ajaran": "string", "semester": "int", "kode_fakultas": "string" },
  "hint": [
    "Identifikasi pola penilaian dominan fakultas ini: berbasis ujian (total bobot rata-rata UTS dan bobot rata-rata UAS besar) atau berbasis tugas/proyek.",
    "Identifikasi komponen penilaian yang dominan digunakan oleh fakultas ini."
  ]
}
```

### 9.2 Granularitas prodi
```json
{
  "chart_type": "grading_composition_single_entity_bar_chart",
  "title": "string",
  "series": [
    {
      "no_prodi": "int",
      "kode_prodi": "string",
      "nama_prodi_id": "string",
      "avg_bobot_uts": "float (opsional)",
      "avg_bobot_uas": "float (opsional)",
      "avg_bobot_tugas": "float (opsional)",
      "avg_bobot_kuis": "float (opsional)",
      "avg_bobot_praktikum": "float (opsional)",
      "avg_bobot_projek": "float (opsional)",
      "avg_bobot_partisipatif": "float (opsional)",
      "jumlah_kelas": "int"
    }
  ],
  "filters_applied": { "tahun_ajaran": "string", "semester": "int", "no_prodi": "int" },
  "hint": [
    "Identifikasi pola penilaian dominan program studi ini: berbasis ujian (total bobot rata-rata UTS dan bobot rata-rata UAS besar) atau berbasis tugas/proyek.",
    "Identifikasi komponen penilaian yang dominan digunakan oleh program studi ini."
  ]
}
```

---

## 10. `score_by_sks_bucket_bar_chart`

**Tidak punya granularitas entitas** — grain-nya bucket SKS tetap (`"1-2 SKS"`, `"3 SKS"`, `"4+ SKS"`), sama untuk semua role/scope. 1 template berlaku untuk semua kasus.

```json
{
  "chart_type": "score_by_sks_bucket_bar_chart",
  "title": "string",
  "x_axis_label": "Kelompok SKS",
  "y_axis_label": "string",
  "series": [
    { "sks_label": "1-2 SKS", "jumlah_kelas": "int", "skor_q28": "float | null" },
    { "sks_label": "3 SKS", "jumlah_kelas": "int", "skor_q28": "float | null" },
    { "sks_label": "4+ SKS", "jumlah_kelas": "int", "skor_q28": "float | null" }
  ],
  "filters_applied": { "tahun_ajaran": "string", "semester": "int" },
  "hint": [
    "Identifikasi apakah skor Q8 menurun seiring bertambahnya jumlah SKS.",
    "Bandingkan jumlah_kelas antar-bucket untuk menilai keterwakilan rata-rata skor tiap bucket."
  ],
  "question_reference": {
    "skor_q28": { "kode_pertanyaan": "Q8", "pertanyaan": "Kesesuaian beban kerja dengan SKS" }
  }
}
```

---

## 11. Ringkasan cakupan (checklist)

| `chart_type` | Granularitas fakultas | Granularitas prodi | Tanpa granularitas entitas |
|---|:---:|:---:|:---:|
| `entity_comparison_bar_chart` | ✅ §1.1 | ✅ §1.2 | — |
| `course_ranking_top_bottom_list` | ✅ §2.1 | ✅ §2.2 | — |
| `single_entity_percentage_value` | ✅ §3.1 | ✅ §3.2 | — |
| `grade_distribution_stacked_bar_chart` | ✅ §4.1 | ✅ §4.2 | — |
| `grade_distribution_single_entity_bar_chart` | ✅ §5.1 | ✅ §5.2 | — |
| `score_trend_line_chart` | — | — | ✅ §6 |
| `score_heatmap_matrix_chart` | ✅ §7.1 | ✅ §7.2 | — |
| `grading_composition_stacked_bar_chart` | ✅ §8.1 | ✅ §8.2 | — |
| `grading_composition_single_entity_bar_chart` | ✅ §9.1 | ✅ §9.2 | — |
| `score_by_sks_bucket_bar_chart` | — | — | ✅ §10 |

Total 18 template skema kosong, mencakup seluruh 10 `chart_type` × granularitas entitas yang berlaku secara struktural.