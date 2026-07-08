# Chart: Tren Skor Antar-Semester (`GradeTrendSection`, `score_trend_line_chart`)

> Struktur field `ChartContext` umum ada di `01-chart-context-type.md`.

---

## 1. Apa isi chart ini

Line chart (multiline) menunjukkan perkembangan skor kuesioner dari semester ke semester (Tab Info Umum), untuk **N semester terakhir** (default 6). **Ini SATU-SATUNYA chart di dashboard yang sengaja menampilkan banyak periode sekaligus**. Filter `semester` diabaikan khusus di endpoint ini.

---

## 2. Insight yang diharapkan

- Tren membaik/memburuk dari waktu ke waktu — bukan cuma angka 1 semester.
- Titik infleksi — semester mana terjadi lonjakan/penurunan tajam, dan apakah bertepatan dengan sesuatu yang bisa dikorelasikan (pergantian kurikulum, dsb — meski dashboard ini sendiri tidak punya data penyebabnya, cukup tunjukkan pola waktunya).

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
    "kode_fakultas": "STEI"
  }
}
```

`series` **diurutkan secara kronologis** (terlama ke terbaru).

Untuk chart tren Q8 spesifik (sub-tab Rancangan Pelaksanaan), field skor jadi `avg_skor_q28`, bukan `avg_skor_overall` — struktur baris lainnya identik.

---

## 4. Edge case

- **`filters_applied` tidak akan pernah berisi `semester`** — chart ini secara sengaja mengabaikan filter semester (karena tujuannya memang menampilkan semua semester). Kalau user sedang memfilter semester tertentu di UI, nilai semester itu **tidak masuk** parameter filter untuk chart ini.
- Jumlah titik di `series` bisa **kurang dari N** yang diminta (default 6) kalau data historis belum tersedia sebanyak itu (misal prodi baru berdiri 3 semester lalu) — jangan menganggap ini error.