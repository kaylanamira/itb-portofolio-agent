# Chart: Distribusi Nilai & Rata-Rata IP (`GradeDistributionSection`)

---

## 1. Apa isi chart ini

2 sub-komponen (format chart) dalam 1 section:
- **`GradePie`** — donut chart distribusi grade A/AB/B/BC/C/D/E/T, **selalu 1 pie** (rata-rata tertimbang otomatis benar di semua scope, tidak perlu mode collapse khusus).
- **`GradeStackedBar`** — stacked bar 8 kategori grade per entitas. **Collapse** ke profil 8-bar horizontal (bukan stacked) saat 1 entitas.

---

## 2. Insight yang diharapkan

- Proporsi mahasiswa dengan nilai baik (A-C) vs bermasalah (D-E-T) — indikator langsung kualitas capaian.
- Perbandingan distribusi antar-fakultas/prodi — apakah ada yang jomplang (misal proporsi E jauh lebih tinggi).
- Hubungan dengan `avg_ip` — distribusi condong ke grade tinggi harusnya sejalan dengan IP rata-rata tinggi; kalau tidak sejalan, itu layak dipertanyakan (potensi anomali data atau kebijakan penilaian yang tidak konsisten antar dosen).

---

## 3. Struktur payload `chart_context`

### 3.1 Struktur payload `chart_context`**Distribusi Nilai Mahasiswa**
Berikut contoh lengkap untuk metric **Distribusi Nilai Mahasiswa**, di kedua mode :
**Mode perbandingan** (`GradeStackedBar`, banyak entitas):
```json
{
  "chart_type": "grade_distribution_comparison",
  "title": "Distribusi Grade per Fakultas",
  "series": [
    {
      "kode_fakultas": "STEI",
      "nama_fakultas_id": "Sekolah Teknik Elektro dan Informatika",
      "dist_pct_a": 34.2, 
      "dist_pct_ab": 22.1, 
      "dist_pct_b": 19.5, 
      "dist_pct_bc": 12.0,
      "dist_pct_c": 7.8, 
      "dist_pct_d": 2.9, 
      "dist_pct_e": 1.5, 
      "dist_pct_t": 0.0,
      "total_mahasiswa": 1240
    },
    {
      "kode_fakultas": "FTMD",
      "nama_fakultas_id": "Fakultas Teknik Mesin dan Dirgantara",
      "dist_pct_a": 34.2, 
      "dist_pct_ab": 22.1, 
      "dist_pct_b": 19.5, 
      "dist_pct_bc": 12.0,
      "dist_pct_c": 7.8, 
      "dist_pct_d": 2.9, 
      "dist_pct_e": 1.5, 
      "dist_pct_t": 0.0,
      "total_mahasiswa": 1240
    },
    {
      "kode_fakultas": "FTSL",
      "nama_fakultas_id": "Fakultas Teknik Sipil dan Lingkungan",
      "dist_pct_a": 34.2, 
      "dist_pct_ab": 22.1, 
      "dist_pct_b": 19.5, 
      "dist_pct_bc": 12.0,
      "dist_pct_c": 7.8, 
      "dist_pct_d": 2.9, 
      "dist_pct_e": 1.5, 
      "dist_pct_t": 0.0,
      "total_mahasiswa": 1240
    },
  ],
  "filters_applied": 
    { 
    "tahun_ajaran": "2024/2025", 
    "semester": 1
    }
}
```

**Mode 1 entitas** (profil, bukan stacked lagi):
```json
{
  "chart_type": "grade_distribution_profile",
  "title": "Distribusi Grade — Teknik Informatika",
  "series": [
    {
      "dist_pct_a": 34.2, 
      "dist_pct_ab": 22.1, 
      "dist_pct_b": 19.5, 
      "dist_pct_bc": 12.0,
      "dist_pct_c": 7.8, 
      "dist_pct_d": 2.9, 
      "dist_pct_e": 1.5, 
      "dist_pct_t": 0.0,
      "total_mahasiswa": 1240
    },
  ],
  "filters_applied": 
    { 
    "tahun_ajaran": "2024/2025", 
    "no_prodi": "135" 
    }
}
```
Untuk granularity prodi (Dekan, atau Direktorat sudah drill 1 fakultas), field menggunakan : `no_prodi`, `kode_prodi`, dan `nama_prodi_id`.
Untuk granularity fakultas, field menggunakan :`kode_fakultas`/`nama_fakultas_id`.

### 3.2 Struktur payload `chart_context`**Rata-Rata IP Mahasiswa**
Berikut contoh lengkap untuk metric **Rata-Rata IP** mahasiswa, di kedua mode :

**Mode perbandingan** (`GradeStackedBar`, banyak entitas):
```json
{
    "chart_type": "bar_horizontal",
    "title": "Rata-Rata Nilai per Fakultas",
    "y_axis_label": "IP rata-rata (skala 0-4)",
    "series": [
        { 
        "kode_fakultas": "STEI", 
        "nama_fakultas_id": "Sekolah Teknik Elektro dan Informatika",
        "avg_ip_akhir_mahasiswa": 3.42, 
        "delta_periode_lalu": 0.05 
        },
        { 
        "kode_fakultas": "FTMD", 
        "nama_fakultas_id": "Fakultas Teknik Mesin dan Dirgantara",
        "avg_ip_akhir_mahasiswa": 3.31, 
        "delta_periode_lalu": -0.02 
        },
        { 
        "kode_fakultas": "SF", 
        "nama_fakultas_id": "Sekolah Farmasi",
        "avg_ip_akhir_mahasiswa": 3.18, 
        "delta_periode_lalu": null 
        }
    ],
    "filters_applied": {
        "tahun_ajaran": "2024/2025",
        "semester": 1
    }
}
```

**Mode 1 entitas** (profil, bukan stacked lagi):
```json
{
  "chart_context": {
    "chart_type": "ranking_top_bottom",
    "title": "Rata-Rata IP",
    "series": [
      {
        "posisi_ranking": "top",
        "kode_matkul": "IF2211",
        "nama_matkul_id": "Struktur Data",
        "avg_ip_akhir_mahasiswa": 3.68,
        "jumlah_mahasiswa": 42,
        "jumlah_kelas": 2
      },
      {
        "posisi_ranking": "bottom",
        "kode_matkul": "MA1101",
        "nama_matkul_id": "Kalkulus Lanjut",
        "avg_ip_akhir_mahasiswa": 2.85,
        "jumlah_mahasiswa": 61,
        "jumlah_kelas": 1
      }
    ],
    "filters_applied": {
      "tahun_ajaran": "2024/2025",
      "semester": 1,
      "no_prodi": "135"
    }
  }
}
```
---

## 4. Edge case

- `dist_pct_t` = persentase nilai "T" (pengisian nilai tertunda/belum lengkap) — **bukan** kegagalan akademik, jangan disamakan dengan grade E saat interpretasi.
- Total 8 persentase (`dist_pct_a` s.d. `dist_pct_t`) idealnya berjumlah ~100%, tapi bisa ada pembulatan kecil — jangan mempermasalahkan selisih desimal.
- `total_mahasiswa` adalah jumlah mahasiswa yang **dinilai** pada periode itu.