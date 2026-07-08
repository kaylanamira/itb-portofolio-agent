# Chart: Heatmap Skor per Entitas × Pertanyaan (`ScoreHeatmap`, `score_heatmap_matrix_chart`)

> Struktur field `ChartContext` umum ada di `01-chart-context-type.md`.

---

## 1. Apa isi chart ini

Heatmap skor merupakan matrix/tabel berwarna dengan:
baris = entitas (fakultas/prodi),
kolom = 12 pertanyaan kuesioner (Q1-Q12 UI / `q21`-`q37` database — lihat `00-README.md` §4).

Tiap sel diwarnai berdasar rentang skor (hijau tua = tinggi, merah = rendah). 3 skor terendah per baris ditandai outline merah.

---

## 2. Insight yang diharapkan

- Pertanyaan kuesioner mana yang **konsisten** rendah di banyak entitas (masalah sistemik, bukan spesifik 1 fakultas/prodi).
- Untuk 1 entitas: pertanyaan kuesioner mana yang jadi titik lemah entitas dan perlu perhatian.

---

## 3. Struktur payload `chart_context`

```json
{
  "chart_type": "score_heatmap_matrix_chart",
  "title": "Heatmap Rata-Rata Skor per Fakultas × Pertanyaan",
  "series": [
    {
      "kode_fakultas": "STEI",
      "nama_fakultas_id": "Sekolah Teknik Elektro dan Informatika",
      "skor_q21": 3.72, "skor_q22": 3.68, "skor_q23": 3.75,
      "skor_q24": 3.81, "skor_q25": 3.79, "skor_q26": 3.70, "skor_q27": 3.65,
      "skor_q28": 3.38,
      "skor_q29": 3.55, "skor_q30": 3.50,
      "skor_q35": 3.81, "skor_q37": 3.73,
      "bottom_3_kolom": ["skor_q28", "skor_q30", "skor_q27"]
    },
    {
      "kode_fakultas": "FTMD",
      "nama_fakultas_id": "Fakultas Teknik Mesin dan Dirgantara",
      "skor_q21": 3.65, "skor_q22": 3.60, "skor_q23": 3.70,
      "skor_q24": 3.75, "skor_q25": 3.72, "skor_q26": 3.66, "skor_q27": 3.58,
      "skor_q28": 3.30,
      "skor_q29": 3.48, "skor_q30": 3.42,
      "skor_q35": 3.74, "skor_q37": 3.68,
      "bottom_3_kolom": ["skor_q28", "skor_q30", "skor_q29"]
    }
  ],
  "filters_applied": {
    "tahun_ajaran": "2024/2025",
    "semester": 1
  }
}
```

`bottom_3_kolom` — field tambahan (bukan kolom database) yang **sudah dihitung frontend**, berisi 3 nama kolom dengan skor terendah pada baris itu — supaya agen tidak perlu menghitung ulang sendiri dari 12 angka.

---

## 4. Edge case

- Semua 12 kolom bisa `null` untuk 1 baris kalau entitas itu tidak punya data kuesioner sama sekali pada periode difilter — jangan mengarang skor kalau field-nya `null`.
- `bottom_3_kolom` cuma menghitung dari kolom yang **tidak null** — kalau ada baris dengan <3 kolom terisi, array ini bisa berisi <3 item.
- Nama field **persis** sama dengan yang dipakai `02-entity-comparison-and-ranking-chart.md` (`skor_q21` s.d. `skor_q37`).