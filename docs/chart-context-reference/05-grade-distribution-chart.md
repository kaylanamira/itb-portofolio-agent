# Chart: Distribusi Nilai (`GradeDistributionSection`)

---

## 1. Apa isi chart ini

2 sub-komponen (format chart) dalam 1 section:
- **`GradePie`** — donut chart distribusi grade A/AB/B/BC/C/D/E/T, **selalu 1 pie**. 
- **`GradeStackedBar`** — stacked bar 8 kategori grade per entitas. **Collapse** ke bar chart profil 8-bar horizontal (bukan stacked) saat 1 entitas.

---

## 2. Insight yang diharapkan

- Proporsi mahasiswa dengan nilai baik (A-C) vs bermasalah (D-E-T) — indikator langsung kualitas capaian.
- Perbandingan distribusi antar-fakultas/prodi — apakah ada yang jomplang (misal proporsi E jauh lebih tinggi).

---

## 3. Struktur payload `chart_context`

**Mode perbandingan** (`grade_distribution_stacked_bar_chart`, perbandingan antarfakultas/antarprogram studi):
```json
{
  "chart_type": "grade_distribution_stacked_bar_chart",
  "title": "Distribusi Grade per Fakultas",
  "series": [
    {
      "kode_fakultas": "STEI",
      "nama_fakultas_id": "Sekolah Teknik Elektro dan Informatika",
      "dist_pct_a": 34.2,
      "dist_pct_ab": 22.1,
      "dist_pct_b": 19.5,
      "dist_pct_bc": 12.0,
      "dist_pct_c": 7.8,
      "dist_pct_d": 2.9,
      "dist_pct_e": 1.5,
      "dist_pct_t": 0.0,
      "total_mahasiswa": 1240
    },
    {
      "kode_fakultas": "FTMD",
      "nama_fakultas_id": "Fakultas Teknik Mesin dan Dirgantara",
      "dist_pct_a": 30.1,
      "dist_pct_ab": 24.0,
      "dist_pct_b": 20.2,
      "dist_pct_bc": 13.5,
      "dist_pct_c": 8.0,
      "dist_pct_d": 2.7,
      "dist_pct_e": 1.5,
      "dist_pct_t": 0.0,
      "total_mahasiswa": 980
    }
  ],
  "filters_applied": {
    "tahun_ajaran": "2024/2025",
    "semester": [1],
    "kode_fakultas": ["STEI", "FTMD"]
  },
  "hint": [
    "Bandingkan proporsi grade lulus (A-C) vs bermasalah (D-E-T) antarfakultas.",
    "Identifikasi mayoritas nilai yang diraih oleh setiap fakultas untuk mendapat gambaran pemahaman umum mahasiswa setiap fakultas terhadap pelaksanaan perkuliahan di fakultas tersebut.",
    "Identifikasi apakah terdapat flag pada hasil yang diraih, ditandai dengan 100% mahasiswa meraih suatu kategori nilai."
  ]
}
```
Untuk granularity prodi (Dekan, atau Direktorat sudah drill 1 fakultas), field menggunakan: `no_prodi`, `kode_prodi`, dan `nama_prodi_id` menggantikan `kode_fakultas`/`nama_fakultas_id`.

**Mode 1 entitas** (`grade_distribution_single_entity_bar_chart`; bar chart biasa 8-kategori, bukan stacked lagi):
```json
{
  "chart_type": "grade_distribution_single_entity_bar_chart",
  "title": "Distribusi Grade — Teknik Informatika",
  "series": [
    {
      "no_prodi": 135,
      "kode_prodi": "IF",
      "nama_prodi_id": "Teknik Informatika",
      "dist_pct_a": 34.2,
      "dist_pct_ab": 22.1,
      "dist_pct_b": 19.5,
      "dist_pct_bc": 12.0,
      "dist_pct_c": 7.8,
      "dist_pct_d": 2.9,
      "dist_pct_e": 1.5,
      "dist_pct_t": 0.0,
      "total_mahasiswa": 210
    }
  ],
  "filters_applied": {
    "tahun_ajaran": "2024/2025",
    "semester": [1],
    "no_prodi": [135]
  },
  "hint": [
    "Bandingkan proporsi grade lulus (A-C) vs bermasalah (D-E-T) antarprogram studi.",
    "Identifikasi mayoritas nilai yang diraih oleh setiap program studi untuk mendapat gambaran pemahaman umum mahasiswa setiap program studi terhadap pelaksanaan perkuliahan di program studi tersebut.",
    "Identifikasi apakah terdapat flag pada hasil yang diraih, ditandai dengan 100% mahasiswa meraih suatu kategori nilai."
  ]
}
```

---

## 4. Edge case

- `dist_pct_t` = persentase nilai "T" (pengisian nilai tertunda/belum lengkap) — **bukan** kegagalan akademik.
- Total 8 persentase (`dist_pct_a` s.d. `dist_pct_t`) idealnya berjumlah ~100%.
- `total_mahasiswa` adalah jumlah mahasiswa yang **dinilai** pada periode itu.