# Chart: Tren Skor Antar-Semester (`GradeTrendSection`, `score_trend_line_chart`)

---

## 1. Apa isi chart ini

Line chart (multiline) menunjukkan perkembangan skor kuesioner dari semester ke semester (Tab Info Umum), untuk **N semester terakhir** (default 9). **Ini SATU-SATUNYA chart di dashboard yang sengaja menampilkan banyak periode sekaligus**. 

---

## 2. Insight yang diharapkan

- Tren membaik/memburuk dari waktu ke waktu — bukan cuma angka 1 semester.
- Titik semester terjadinya kenaikan/penurunan tajam pada pola waktu tertentu.

---

## 3. Struktur payload `chart_context`

```json
{
  "chart_type": "score_trend_line_chart",
  "title": "Tren Rata-Rata Skor Kuesioner ITB",
  "x_axis_label": "Semester",
  "y_axis_label": "Skor (skala 1-4)",
  "series": [
    { "period_label": "2022/2023-1", "tahun_ajaran": "2022/2023", "semester": 1, "avg_skor_overall": 3.68 },
    { "period_label": "2022/2023-2", "tahun_ajaran": "2022/2023", "semester": 2, "avg_skor_overall": 3.72 },
    { "period_label": "2023/2024-1", "tahun_ajaran": "2023/2024", "semester": 1, "avg_skor_overall": 3.79 }
  ],
  "filters_applied": {
    "kode_fakultas": ["STEI"]
  },
  "hint": [
    "Identifikasi arah tren (naik/turun) sepanjang periode yang tersedia.",
    "Perhatikan titik semester dengan kenaikan atau penurunan nilai yang tajam."
  ]
}
```

`series` **diurutkan secara kronologis** (tahun_ajaran terlama ke terbaru).

---

## 4. Edge case

- Jumlah titik di `series` bisa **kurang dari N** yang diminta (default 9) kalau data historis belum tersedia sebanyak itu (misal prodi baru berdiri 3 semester lalu).