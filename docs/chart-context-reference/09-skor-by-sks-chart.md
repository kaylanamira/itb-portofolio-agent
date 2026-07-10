# Chart: Rata-Rata Skor Q8 per Kelompok SKS (Tab Pelaksanaan → Rancangan Perkuliahan, `score_by_sks_bucket_bar_chart`)

---

## 1. Apa isi chart ini

Bar chart sederhana menampilkan rata-rata skor Q8 (`avg_skor_q28` — kesesuaian beban kerja dengan SKS), dikelompokkan ke **3 bucket SKS tetap**: `"1-2 SKS"`, `"3 SKS"`, `"4+ SKS"`. Hanya kelas dengan `avg_skor_q28 IS NOT NULL` yang ikut dihitung.

**Berbeda dari semua chart lain di folder ini:** grain-nya adalah kelompok SKS, **bukan** entitas organisasi (fakultas/prodi).

---

## 2. Insight yang diharapkan

- Apakah skor Q8 (kesesuaian beban kerja) menurun seiring bertambahnya SKS mata kuliah atau tetap stabil (misalnya semakin besar SKS, beban cenderung makin tidak proporsional).

---

## 3. Struktur payload `chart_context`

**Field di tiap baris `series`:**

| Field | Tipe | Catatan |
|---|---|---|
| `sks_label` | string | salah satu dari `"1-2 SKS"`, `"3 SKS"`, `"4+ SKS"` |
| `jumlah_kelas` | int | jumlah kelas dalam bucket ini pada periode difilter |
| `skor_q28` | float | null | rata-rata `skor_q28`, `null` kalau tidak ada kelas dengan data Q8 pada bucket itu |

**Contoh:**
```json
{
  "chart_type": "score_by_sks_bucket_bar_chart",
  "title": "Q8 per Kelompok SKS",
  "x_axis_label": "Kelompok SKS",
  "y_axis_label": "Skor rata-rata (skala 1-4)",
  "series": [
    { "sks_label": "1-2 SKS", "jumlah_kelas": 58, "skor_q28": 3.71 },
    { "sks_label": "3 SKS", "jumlah_kelas": 214, "skor_q28": 3.52 },
    { "sks_label": "4+ SKS", "jumlah_kelas": 37, "skor_q28": 3.28 }
  ],
  "filters_applied": {
    "tahun_ajaran": "2024/2025",
    "semester": [1],
    "kode_fakultas": ["SBM"]
  },
  "hint": [
    "Identifikasi apakah skor Q8 menurun seiring bertambahnya jumlah SKS.",
    "Bandingkan jumlah_kelas antar-bucket untuk menilai keterwakilan rata-rata skor tiap bucket."
  ],
  "question_reference": {
    "skor_q21": { "kode_pertanyaan_frontend": "Q1", "pertanyaan": "Mahasiswa memperoleh cukup informasi luaran mata kuliah" }
  }
}
```

---

## 4. Edge case

- `skor_q28` bisa `null` untuk 1 bucket kalau tidak ada kelas dengan SKS di rentang itu yang punya data Q8 terisi pada periode difilter.
- `question_reference` hanya ada untuk metrik yang menggunakan skor kuesioner (`skor_q21` - `skor_q37`). 