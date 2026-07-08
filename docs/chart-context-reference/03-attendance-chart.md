# Chart: Kehadiran Dosen & Mahasiswa (`AttendanceSection`)

> Struktur field `ChartContext` umum ada di `01-chart-context-type.md`.

---

## 1. Apa isi chart ini

Card yang berisi informasi rata-rata persentase kehadiran dosen dan kehadiran mahasiswa, per fakultas/prodi. Sama seperti chart perbandingan lain (lihat `02-entity-comparison-and-ranking-chart.md`), chart ini **collapse** saat data hanya berisi 1 entitas (1 prodi) saja.

**Perbedaan penting dari `02-entity-comparison-and-ranking-chart.md`:** saat collapse ke 1 entitas, chart ini menampilkan **1 angka rata-rata persentase kehadiran + delta** (`chart_type: "single_entity_percentage_value"`), bukan list ranking top/bottom mata kuliah.

---

## 2. Insight yang diharapkan

- Fakultas/prodi mana dengan kehadiran dosen/mahasiswa terendah — sinyal masalah operasional (dosen sering tidak hadir) atau motivasi (mahasiswa sering bolos).
- Perbandingan tren kehadiran dosen vs mahasiswa — kalau kehadiran dosen tinggi tapi mahasiswa rendah (atau sebaliknya).
- Perubahan dibanding periode sebelumnya (`delta`) — apakah membaik atau memburuk.

---

## 3. Struktur payload `chart_context`

**Mode perbandingan** (`entity_comparison_bar_chart`, banyak entitas):
```json
{
  "chart_type": "entity_comparison_bar_chart",
  "title": "Rata-Rata Kehadiran Dosen per Fakultas",
  "y_axis_label": "Persentase kehadiran (%)",
  "series": [
    {
      "kode_fakultas": "STEI",
      "nama_fakultas_id": "Sekolah Teknik Elektro dan Informatika",
      "avg_pct_kehadiran_dosen": 94.2,
      "delta_periode_lalu": 1.8
    },
    {
      "kode_fakultas": "FTMD",
      "nama_fakultas_id": "Fakultas Teknik Mesin dan Dirgantara",
      "avg_pct_kehadiran_dosen": 91.5,
      "delta_periode_lalu": -0.5
    }
  ],
  "filters_applied": {
    "tahun_ajaran": "2024/2025",
    "semester": 1
  }
}
```
Untuk kartu kehadiran mahasiswa, field-nya `avg_pct_kehadiran_mahasiswa` (bukan `avg_pct_kehadiran_dosen`), title "Rata-Rata Kehadiran Mahasiswa per Fakultas/Prodi".

**Mode 1 entitas** (`single_entity_percentage_value`; Kaprodi, atau Dekan/Direktorat setelah drill):
```json
{
  "chart_type": "single_entity_percentage_value",
  "title": "Rata-Rata Kehadiran Dosen",
  "series": [
    {
      "no_prodi": 135,
      "kode_prodi": "IF",
      "nama_prodi_id": "Teknik Informatika",
      "avg_pct_kehadiran_dosen": 94.2,
      "delta_periode_lalu": 1.8
    }
  ],
  "filters_applied": {
    "tahun_ajaran": "2024/2025",
    "semester": 1,
    "no_prodi": 135
  }
}
```

Untuk granularity prodi (Dekan, atau Direktorat sudah drill 1 fakultas), field menggunakan: `no_prodi`, `kode_prodi`, dan `nama_prodi_id`.
Untuk granularity fakultas, field menggunakan: `kode_fakultas`/`nama_fakultas_id`.

---

## 4. Edge case

- **Nilai berbentuk persentase, bukan skala 1-4** — jangan disamakan dengan skor kuesioner (lihat `02-entity-comparison-and-ranking-chart.md`). Kehadiran selalu **0-100**.
- `delta_periode_lalu` bisa `null` (periode pertama, belum ada pembanding) — sama seperti aturan di `02-entity-comparison-and-ranking-chart.md`, jangan diinterpretasi sebagai "0% perubahan".
- Kartu ini **tidak pernah** menampilkan ranking mata kuliah individual (beda dari chart skor kuesioner) — karena data kehadiran memang diagregasi di level entitas (fakultas/prodi), bukan tersedia per-mata-kuliah di dashboard ini. Ini kenapa mode collapse-nya `single_entity_percentage_value`, bukan `course_ranking_top_bottom_list`.