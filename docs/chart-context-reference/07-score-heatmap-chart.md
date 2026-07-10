# Chart: Heatmap Skor per Entitas × Pertanyaan (`ScoreHeatmap`, `score_heatmap_matrix_chart`)

> Struktur field `ChartContext` umum ada di `01-chart-context-type.md`, termasuk field `hint`.

---

## 1. Apa isi chart ini

Heatmap skor merupakan matrix/tabel berwarna dengan:
baris = entitas (fakultas/prodi),
kolom = 12 pertanyaan kuesioner (Q1-Q12 UI / `q21`-`q37` database).

3 skor terendah per baris ditandai outline merah. Info ini ada di payload request lewat field `bottom_3_kolom`.

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
    "semester": [1],
    "kode_fakultas": ["STEI", "FTMD"]
  },
  "hint": [
    "Identifikasi pertanyaan (kolom) yang konsisten rendah di banyak fakultas.",
    "Identifikasi pertanyaan (kolom) bottom_3_kolom (3 pertanyaan dengan skor terendah) di setiap fakultas untuk mengidentifikasi poin pertanyaan apa yang perlu menjadi perhatian untuk evaluasi setiap fakultas"
  ],
  "question_reference": {
    "skor_q21": { "kode_pertanyaan_frontend": "Q1", "pertanyaan": "Mahasiswa memperoleh cukup informasi luaran mata kuliah" },
    "skor_q22": { "kode_pertanyaan_frontend": "Q2", "pertanyaan": "Perkuliahan diarahkan agar mahasiswa mencapai luaran mata kuliah" },
    "skor_q23": { "kode_pertanyaan_frontend": "Q3", "pertanyaan": "Mahasiswa mencapai luaran mata kuliah" },
    "skor_q24": { "kode_pertanyaan_frontend": "Q4", "pertanyaan": "Pelaksanaan perkuliahan terorganisir dengan baik" },
    "skor_q25": { "kode_pertanyaan_frontend": "Q5", "pertanyaan": "Dosen berkomunikasi dengan efektif" },
    "skor_q26": { "kode_pertanyaan_frontend": "Q6", "pertanyaan": "Dosen peduli terhadap pencapaian mahasiswa akan luaran mata kuliah" },
    "skor_q27": { "kode_pertanyaan_frontend": "Q7", "pertanyaan": "Dosen berlaku adil kepada mahasiswa" },
    "skor_q28": { "kode_pertanyaan_frontend": "Q8", "pertanyaan": "Kesesuaian beban kerja dengan SKS" },
    "skor_q29": { "kode_pertanyaan_frontend": "Q9", "pertanyaan": "Sarana prasarana untuk mata kuliah tersedia dengan memadai" },
    "skor_q30": { "kode_pertanyaan_frontend": "Q10", "pertanyaan": "Tersedia cukup fasilitas pendukung di luar kuliah" },
    "skor_q35": { "kode_pertanyaan_frontend": "Q11", "pertanyaan": "Mahasiswa berusaha dengan sungguh-sungguh mengikuti mata kuliah" },
    "skor_q37": { "kode_pertanyaan_frontend": "Q12", "pertanyaan": "Mahasiswa memperoleh pengalaman belajar yang positif" }
  }
}
```
---

## 4. Edge case

- `bottom_3_kolom` cuma menghitung dari kolom yang **tidak null** — kalau ada baris dengan <3 kolom terisi, array ini bisa berisi <3 item.
- `question_reference` hanya ada untuk metrik yang menggunakan skor kuesioner (`skor_q21` - `skor_q37`). 