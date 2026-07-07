# Chart: Kehadiran Dosen & Mahasiswa (`AttendanceSection`)

---

## 1. Apa isi chart ini

Card yang berisi informasi rata-rata persentase kehadiran dosen dan kehadiran mahasiswa, per fakultas/prodi. Sama seperti chart perbandingan lain (lihat `01-entity-aware-comparison-chart.md`), chart ini **collapse** ke mode profil, yaitu menampilkan angka persentase kehadiran saja tanpa ada bar chart apapun, saat data hanya berisi 1 entitas (1 prodi) saja.

**Perbedaan penting dari `01-entity-aware-comparison-chart.md`:** saat collapse ke 1 entitas, chart ini menampilkan **1 angka rata-rata persentase kehadiran + delta**, bukan ranking top/bottom mata kuliah.

---

## 2. Insight yang diharapkan

- Fakultas/prodi mana dengan kehadiran dosen/mahasiswa terendah — sinyal masalah operasional (dosen sering tidak hadir) atau motivasi (mahasiswa sering bolos).
- Perbandingan tren kehadiran dosen vs mahasiswa — kalau kehadiran dosen tinggi tapi mahasiswa rendah (atau sebaliknya).
- Perubahan dibanding periode sebelumnya (`delta`) — apakah membaik atau memburuk.

---

## 3. Struktur payload `chart_context`

**Mode perbandingan** (banyak entitas):
```json
{
  "chart_type": "bar_horizontal",
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
  "filters_applied": 
    {
    "tahun_ajaran": "2024/2025", 
    "semester": 1 
    }
}
```
Untuk kartu kehadiran mahasiswa, field-nya `kehadiran_mahasiswa` (bukan `kehadiran_dosen`), title "Rata-Rata Kehadiran Mahasiswa per Fakultas/Prodi".

**Mode 1 entitas** (Kaprodi, atau Dekan/Direktorat setelah drill):
```json
{
  "chart_type": "kpi_single",
  "title": "Rata-Rata Kehadiran Dosen",
  "series": [
    { 
        "no_prodi": "135",
        "kode_prodi": "IF", 
        "nama_prodi_id": "Teknik Informatika", 
        "avg_pct_kehadiran_dosen": 94.2, 
        "delta_periode_lalu": 1.8 }
  ],
  "filters_applied": 
  { 
    "tahun_ajaran": "2024/2025", 
    "semester": 1, 
    "no_prodi": "135" }
}
```

Untuk granularity prodi (Dekan, atau Direktorat sudah drill 1 fakultas), field menggunakan : `no_prodi`, `kode_prodi`, dan `nama_prodi_id`.
Untuk granularity fakultas, field menggunakan :`kode_fakultas`/`nama_fakultas_id`.


---

## 4. Edge case

- **Nilai berbentuk persentase, bukan skala 1-4** — jangan disamakan dengan skor kuesioner (§ file `01`). Kehadiran selalu **0-100**.
- `delta_periode_lalu` bisa `null` (periode pertama, belum ada pembanding) — sama seperti aturan di file `01`, jangan diinterpretasi sebagai "0% perubahan".
- Kartu ini **tidak pernah** menampilkan ranking mata kuliah individual (beda dari chart skor kuesioner) — karena data kehadiran memang diagregasi di level entitas (fakultas/prodi), bukan tersedia per-mata-kuliah di dashboard ini.