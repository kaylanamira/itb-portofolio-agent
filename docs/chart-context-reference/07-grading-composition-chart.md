# Chart: Komposisi Bobot Komponen Penilaian (`GradingCompChart`)

> Struktur field `ChartContext` umum ada di `01-chart-context-type.md`.

---

## 1. Apa isi chart ini

Menunjukkan rata-rata persentase bobot tiap komponen penilaian (UTS, UAS, Tugas, Kuis, Praktikum, Projek, Partisipasi) yang dipakai dosen dalam menilai mahasiswa.

**Mode perbandingan** (`grading_composition_stacked_bar_chart` — stacked bar per fakultas/program studi) collapse jadi **mode 1 entitas** (`grading_composition_single_entity_bar_chart`) saat data tersisa 1 entitas: bentuknya bukan lagi stacked bar susunan seluruh komponen penilaian untuk banyak fakultas/prodi, melainkan bar chart biasa berisi komponen penilaian yang dipakai oleh 1 fakultas/prodi itu saja.

### Seluruh komponen penilaian yang mungkin

| Komponen Penilaian |
|---|
| UTS |
| UAS |
| Tugas |
| Kuis |
| Praktikum |
| Projek |
| Aktivitas Partisipatif |

---

## 2. Insight yang diharapkan

- Pola penilaian yang dominan — apakah suatu fakultas/prodi cenderung berbasis ujian (UTS+UAS besar) atau berbasis tugas/proyek berkelanjutan.
- Komponen penilaian yang **tidak dipakai sama sekali** — bisa jadi insight ("hampir tidak ada kelas pakai praktikum di prodi ini").
- Perbandingan pola antar-fakultas — fakultas teknik vs sosial-humaniora biasanya beda pola bobot, ini konteks alami yang boleh disebut kalau relevan.

---

## 3. Struktur payload `chart_context`

**Mode perbandingan** (`grading_composition_stacked_bar_chart`):
```json
{
  "chart_type": "grading_composition_stacked_bar_chart",
  "title": "Komposisi Komponen Penilaian per Fakultas",
  "series": [
    {
      "kode_fakultas": "STEI",
      "nama_fakultas_id": "Sekolah Teknik Elektro dan Informatika",
      "avg_bobot_uts": 28.0,
      "avg_bobot_uas": 30.0,
      "avg_bobot_tugas": 20.0,
      "avg_bobot_kuis": 8.0,
      "avg_bobot_praktikum": 9.0,
      "avg_bobot_projek": 3.0,
      "avg_bobot_partisipatif": 2.0,
      "jumlah_kelas": 142
    },
    {
      "kode_fakultas": "FTSL",
      "nama_fakultas_id": "Fakultas Teknik Sipil dan Lingkungan",
      "avg_bobot_uts": 25.0,
      "avg_bobot_uas": 25.0,
      "avg_bobot_tugas": 30.0,
      "avg_bobot_praktikum": 20.0,
      "jumlah_kelas": 88
    }
  ],
  "filters_applied": {
    "tahun_ajaran": "2024/2025",
    "semester": 1
  }
}
```
**Perhatikan baris kedua (FTSL):** tidak ada `avg_bobot_kuis`, `avg_bobot_projek`, `avg_bobot_partisipatif` — karena bobotnya 0, field-nya **dihilangkan total**, bukan dikirim sebagai `0` (lihat §4).

**Mode 1 entitas** (`grading_composition_single_entity_bar_chart`):
```json
{
  "chart_type": "grading_composition_single_entity_bar_chart",
  "title": "Komposisi Komponen Penilaian — Teknik Informatika",
  "series": [
    {
      "no_prodi": 135,
      "kode_prodi": "IF",
      "nama_prodi_id": "Teknik Informatika",
      "avg_bobot_uts": 28.0,
      "avg_bobot_uas": 30.0,
      "avg_bobot_tugas": 20.0,
      "avg_bobot_kuis": 8.0,
      "avg_bobot_praktikum": 9.0,
      "avg_bobot_projek": 3.0,
      "avg_bobot_partisipatif": 2.0,
      "jumlah_kelas": 45
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

## 4. Edge case

- **Komponen dengan bobot 0 tidak dikirim sama sekali** (bukan dikirim sebagai `0`). Backend menyaring komponen yang benar-benar tidak dipakai (lihat `dashboard_akademik.py::get_akademik_grading_comp` — field diset `None` kalau `avg_bobot_*` bernilai 0, dan field bernilai `None` tidak diserialisasi ke payload). Kalau `avg_bobot_praktikum` tidak muncul di `series` milik suatu fakultas/program studi, itu berarti **tidak ada kelas** di fakultas/program studi itu yang memakai komponen praktikum sebagai penilaian.