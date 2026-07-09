# Chart: Kehadiran Dosen & Mahasiswa (`AttendanceSection`)

---

## 1. Apa isi chart ini

Card yang berisi informasi rata-rata persentase kehadiran dosen dan kehadiran mahasiswa, per fakultas/prodi. Chart ini **collapse** saat data hanya berisi 1 prodi saja (view default jajaran prodi/kaprodi).

**Perbedaan penting dari `03-entity-comparison-and-ranking-chart.md`:** saat collapse ke 1 entitas, chart ini menampilkan **1 angka rata-rata persentase kehadiran + delta** (`chart_type: "single_entity_percentage_value"`), bukan list ranking top/bottom kelas.

---

## 2. Struktur payload `chart_context`

**Mode perbandingan** (`entity_comparison_bar_chart`, banyak entitas, granularity fakultas):
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
  },
  "hint": [
    "Identifikasi fakultas dengan nilai tertinggi dan terendah pada metrik ini.",
    "Identifikasi seberapa lebar kesenjangan antarfakultas (apakah merata, atau ada outlier jauh di bawah rata-rata)",
    "Nilai berskala 0-100%, bukan skala skor kuesioner 1-4."
  ]
}
```
Untuk kehadiran mahasiswa, field-nya `avg_pct_kehadiran_mahasiswa` (bukan `avg_pct_kehadiran_dosen`), title "Rata-Rata Kehadiran Mahasiswa per Fakultas/Prodi", dan `hint` yang sama berlaku (ini adalah `hint` standar `entity_comparison_bar_chart` granularitas fakultas, bukan `hint` khusus kehadiran).

**Mode 1 entitas** (`single_entity_percentage_value`; Kaprodi, atau Dekan/Direktorat setelah drill), granularity prodi:
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
  },
  "hint": [
    "Bandingkan angka ini dengan delta_periode_lalu untuk menilai tren membaik atau memburuk.",
    "Nilai berskala 0-100%, bukan skala skor kuesioner 1-4."
  ]
}
```

Untuk granularity prodi (Dekan, atau Direktorat sudah drill 1 fakultas), field menggunakan: `no_prodi`, `kode_prodi`, dan `nama_prodi_id`.
Untuk granularity fakultas, field menggunakan: `kode_fakultas`/`nama_fakultas_id`.

---

## 3. Catatan untuk agen

- **Nilai berbentuk persentase, bukan skala 1-4** — jangan disamakan dengan skor kuesioner. Kehadiran selalu **0-100**.
- `delta_periode_lalu` bisa `null` (periode pertama, belum ada pembanding) — jangan diinterpretasi sebagai "0% perubahan".
- Kartu ini **tidak pernah** menampilkan ranking kelas individual (beda dari chart skor kuesioner) — karena data kehadiran memang diagregasi di level entitas (fakultas/prodi), bukan tersedia per-kelas di dashboard ini. Ini kenapa mode collapse-nya `single_entity_percentage_value`, bukan `course_ranking_top_bottom_list`.