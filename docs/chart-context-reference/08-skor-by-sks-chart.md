# Chart: Rata-Rata Skor Q8 per Kelompok SKS (Tab Pelaksanaan → Rancangan Perkuliahan)

> Struktur field `ChartContext` umum ada di `01-chart-context-type.md`.

---

## 1. Apa isi chart ini

Bar chart sederhana menampilkan rata-rata skor Q8 (`avg_skor_q28` — kesesuaian beban kerja dengan SKS), dikelompokkan ke **3 bucket SKS tetap**: `"1-2 SKS"`, `"3 SKS"`, `"4+ SKS"`. Hanya kelas dengan `avg_skor_q28 IS NOT NULL` yang ikut dihitung.

**Berbeda dari semua chart lain di folder ini:** grain-nya adalah kelompok SKS, **bukan** entitas organisasi (fakultas/prodi) — jadi chart ini **tidak** punya mode "collapse" ke 1 entitas maupun ke ranking mata kuliah. Selalu tampil sebagai 3 bucket tetap, terlepas dari role atau granularity user.

---

## 2. Insight yang diharapkan

- Apakah skor Q8 (kesesuaian beban kerja) menurun seiring bertambahnya SKS mata kuliah — pola umum yang diharapkan UI dashboard (semakin besar SKS, beban cenderung makin tidak proporsional).
- Bucket SKS mana yang paling banyak kelasnya (`jumlah_kelas`) — memberi konteks seberapa representatif rata-rata skor tiap bucket.

---

## 3. Struktur payload (bentuk data API saat ini — belum tentu identik dengan `chart_context` final)

**Field di tiap baris `series`:**

| Field | Tipe | Catatan |
|---|---|---|
| `sks_label` | string | salah satu dari `"1-2 SKS"`, `"3 SKS"`, `"4+ SKS"` |
| `jumlah_kelas` | int | jumlah kelas dalam bucket ini pada periode difilter |
| `avg_skor_q8` | float \| null | rata-rata `avg_skor_q28`, `null` kalau tidak ada kelas dengan data Q8 pada bucket itu |

**Contoh:**
```json
{
  "chart_type": "score_by_sks_bucket_bar_chart",
  "title": "Q8 per Kelompok SKS",
  "x_axis_label": "Kelompok SKS",
  "y_axis_label": "Skor rata-rata (skala 1-4)",
  "series": [
    { "sks_label": "1-2 SKS", "jumlah_kelas": 58, "avg_skor_q8": 3.71 },
    { "sks_label": "3 SKS", "jumlah_kelas": 214, "avg_skor_q8": 3.52 },
    { "sks_label": "4+ SKS", "jumlah_kelas": 37, "avg_skor_q8": 3.28 }
  ],
  "filters_applied": {
    "tahun_ajaran": "2024/2025",
    "semester": 1
  }
}
```

---

## 4. Edge case

- `avg_skor_q8` bisa `null` untuk 1 bucket kalau tidak ada kelas dengan SKS di rentang itu yang punya data Q8 terisi pada periode difilter.
- chart ini tidak mengenal mode drill-down per-entitas seperti chart lain.