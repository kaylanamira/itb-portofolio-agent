# Chart: Komposisi Bobot Komponen Penilaian (`GradingCompChart`)

---

## 1. Apa isi chart ini

Menunjukkan rata-rata persentase bobot tiap komponen penilaian (UTS, UAS, Tugas, Kuis, Praktikum, Projek, Partisipasi) yang dipakai dosen dalam menilai mahasiswa. 

**Mode perbandingan** (stacked bar per fakultas/program studi) collapse jadi **mode profil** yaitu bar chart bentuknya bukan stacked bar chart susunan seluruh komponen penilaian untuk setiap fakultas/program studi lagi, tapi berubah menjadi bar chart biasa sejumlah komponen penilain yang digunakan oleh 1 fakultas/program studi.

---

## 2. Insight yang diharapkan

- Pola penilaian yang dominan — apakah suatu fakultas/prodi cenderung berbasis ujian (UTS+UAS besar) atau berbasis tugas/proyek berkelanjutan.
- Komponen penilaian yang **tidak dipakai sama sekali** — bisa jadi insight ("hampir tidak ada kelas pakai praktikum di prodi ini").
- Perbandingan pola antar-fakultas — fakultas teknik vs sosial-humaniora biasanya beda pola bobot, ini konteks alami yang boleh disebut kalau relevan.

### Seluruh komponen penilaian yang mungkin

| Komponen Penilaian |
|---|
| UTS |
| UAS |
| Tugas |
| Kuis |
| Praktikum |
| Projek |
| Aktivitas Partisipastif |


---

## 3. Struktur payload `chart_context`

**Mode perbandingan:**
```json
{
  "chart_type": "grading_composition_stacked",
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
      "kode_fakultas": "FITB",
      "nama_fakultas_id": "Fakultas Ilmu Teknologi Kebumian",
      "avg_bobot_uts": 28.0, 
      "avg_bobot_uas": 30.0, 
      "avg_bobot_tugas": 20.0,
      "avg_bobot_kuis": 8.0, 
      "avg_bobot_praktikum": 9.0, 
      "avg_bobot_projek": 3.0, 
      "avg_bobot_partisipatif": 2.0,
      "jumlah_kelas": 142
    }
  ],
  "filters_applied": 
  { 
    "tahun_ajaran": "2024/2025", 
    "semester": 1
  }
}
```

**Mode profil (1 entitas):**
```json
{
  "chart_type": "grading_composition_profile",
  "title": "Komposisi Komponen Penilaian — Teknik Informatika",
  "series": [
    { 
      "avg_bobot_uts": 28.0, 
      "avg_bobot_uas": 30.0, 
      "avg_bobot_tugas": 20.0,
      "avg_bobot_kuis": 8.0, 
      "avg_bobot_praktikum": 9.0, 
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

---

## 4. Edge case

- **Komponen dengan bobot 0 tidak dikirim sama sekali** (bukan dikirim sebagai `0`).
Backend menyaring komponen yang benar-benar tidak dipakai. 
Kalau `avg_bobot_praktikum` tidak muncul di `series` milik suatu fakultas/program studi, itu berarti **tidak ada kelas** di fakultas/program studi itu yang memakai komponen praktikum sebagai penilaian.