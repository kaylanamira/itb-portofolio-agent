# Dashboard Akademik ITB — Overview Total

Dokumen ini untuk **pengembang** dan sebagai **referensi agen** tentang keseluruhan dashboard, sebelum masuk ke detail per-chart di file lain dalam folder ini.

---

## 1. Apa dashboard ini

Dashboard analitik portofolio & kuesioner akademik ITB. Menampilkan hasil evaluasi perkuliahan (skor kuesioner mahasiswa, kehadiran, distribusi nilai, komposisi penilaian) untuk 4 level pengguna:

| Role | Scope data |
|---|---|
| Direktorat / Admin | Seluruh ITB, bisa lihat perbandingan antar-fakultas dan antar-prodi |
| Dekan / Jajaran Dekanat | 1 fakultas, perbandingan antar-prodi dalam fakultas itu |
| Kaprodi / Jajaran Prodi | 1 program studi |
| Dosen | Data personal (kelas yang diajar) |

Scope ditegakkan di level RLS database — **tidak pernah** dikontrol dari frontend semata.

---

## 2. Struktur dashboard — 4 tab

| Tab | Isi |
|---|---|
| **Informasi Umum** | Ranking 12 pertanyaan kuesioner dengan informasi top-5 pertanyaan (5 pertanyaan peraih skor tertinggi) dan bottom-5 pertanyaan (5 pertanyaan peraih skor terendah), heatmap skor per entitas × pertanyaan, tren skor keseluruhan, perbandingan skor per fakultas/prodi, isu dominan komentar (placeholder, menunggu RAG) |
| **Luaran Mata Kuliah** | Distribusi nilai A-E, tren rata-rata IP, ranking Q1-Q3 (capaian pembelajaran) |
| **Pelaksanaan Perkuliahan** | 4 sub-tab: Rancangan (Q8/beban kerja & komposisi penilaian), Performa Dosen (Q4-Q7 & kehadiran dosen), Performa Mahasiswa (Q11-Q12 & kehadiran mahasiswa), Sarana Prasarana (Q9-Q10) |
| **Ringkasan Komentar** | Top Isu dan Komentar mentah mahasiswa/dosen/ITB (paginated, teks bebas) — **di luar scope fitur chart-interpret** |

---

## 3. Perilaku khusus: chart "collapse" jadi ranking mata kuliah

Ini **pola arsitektur terpenting** untuk dipahami sebelum baca file chart lain di folder ini.

Banyak chart di dashboard ini berupa **perbandingan antar-entitas** (bar chart fakultas/prodi). Misalnya, membandingkan skor Q5 antar-prodi.

 Tapi begitu data yang tersisa cuma **1 entitas** (karena scope Kaprodi hanya dapat mengamati 1 entitas program studi, atau karena Direktorat drill-down ke 1 fakultas), chart itu **otomatis berubah bentuk** — bukan lagi bar 1 batang yang percuma, tapi jadi **list top-5/bottom-5 mata kuliah** dalam entitas tersebut.

**Implikasi untuk `chart_context`:** `chart_type` yang dikirim akan **berbeda** tergantung kondisi ini — bisa `"bar_horizontal"` (mode perbandingan banyak entitas menggunakan format bar chart) atau `"ranking_top_bottom"` (mode top/bottom matkul menggunakan format list, saat sudah collapse ke 1 entitas). Detail lengkap ada di file `01-entity-aware-comparison-chart.md`.

---

## 4. Penomoran pertanyaan kuesioner — WAJIB dibaca sebelum file lain

UI menampilkan **Q1 sampai Q12**, tapi ini **bukan** nama kolom database. Kolom asli: `q21`-`q30`, `q35`, `q37`.

| Label UI | Kolom database | Topik |
|---|---|---|
| Q1 | `q21` | Mahasiswa memperoleh cukup informasi luaran mata kuliah |
| Q2 | `q22` | Perkuliahan diarahkan agar mahasiswa mencapai luaran mata kuliah |
| Q3 | `q23` | Mahasiswa mencapai luaran mata kuliah |
| Q4 | `q24` | Pelaksanaan perkuliahan terorganisir dengan baik |
| Q5 | `q25` | Dosen berkomunikasi dengan efektif |
| Q6 | `q26` | Dosen peduli terhadap pencapaian mahasiswa akan luaran mata kuliah |
| Q7 | `q27` | Dosen berlaku adil kepada mahasiswa |
| Q8 | `q28` | Kesesuaian beban kerja dengan SKS |
| Q9 | `q29` | Sarana prasarana untuk mata kuliah tersedia dengan memadai |
| Q10 | `q30` | Tersedia cukup fasilitas pendukung di luar kuliah |
| Q11 | `q35` | Mahasiswa berusaha dengan sungguh-sungguh mengikuti mata kuliah |
| Q12 | `q37` | Mahasiswa memperoleh pengalaman belajar yang positif |

**Semua field di request payload pada field `chart_context.series` di seluruh dashboard memakai nama kolom database asli** (`skor_q28`, bukan `skor_q8`) — bukan alias UI. Ini disengaja, supaya agen bisa mencocokkan nama field langsung ke `COMMENT ON COLUMN` di database (lihat `agent/tools/schema_retriever.py`), tanpa perlu tabel terjemahan tambahan.

### Kelompok gabungan (composite)

| Kolom komposit | Cakupan |
|---|---|
| `avg_skor_capaian` | Q1-Q3 |
| `avg_skor_sarana_prasarana` | Q9-Q10 |
| `avg_skor_perilaku_mahasiswa` | Q11-Q12 |
| `avg_skor_overall` | Semua Q1-Q12 |

**Perhatian khusus:** card dashboard "Performa Dosen (Q4-Q7)" **sengaja tidak** memakai `avg_skor_pelaksanaan` (yang mencakup Q8 juga). 
Nilai dashboard "Performa Dosen (Q4-Q7)" dihitung manual dari `skor_q24`+`skor_q25`+`skor_q26`+`skor_q27` saja. Kalau agen melihat metric ini di `chart_context`, field-nya akan berupa `rata_rata_dari_kolom: ["skor_q24","skor_q25","skor_q26","skor_q27"]`, bukan `avg_skor_pelaksanaan` — **ini bukan kesalahan data**, ini keputusan desain yang disengaja.

---

## 5. Yang TIDAK termasuk fitur "tanya insight chart"

- **Tab Ringkasan Komentar** (`RawCommentList`) — ini teks bebas, bukan metrik numerik. Tidak ada tombol insight di sana (belum ada rencana menambahkannya).
- **4 stat card di atas** (jumlah kelas/matkul/dosen/mahasiswa) — angka ringkasan sederhana.
- **Filter bar, breadcrumb, navigasi tab** — bukan chart, tidak relevan.

---

## 6. Daftar file dalam folder ini

| File | Chart yang dijelaskan |
|---|---|
| `01-comparison-bar-chart.md` | Semua bar chart perbandingan entitas + semua varian ranking top/bottom matkul (16 metric) — **paling sering dipakai** |
| `02-attendance-chart.md` | Kehadiran dosen & mahasiswa |
| `03-grade-distribution-chart.md` | Distribusi nilai A-E + rata-rata IP |
| `04-grade-trend-chart.md` | Tren skor & IP antar-semester |
| `05-score-heatmap-chart.md` | Matrix 12 skor pertanyaan × entitas |

---

## 7. Kontrak umum `chart_context` (berlaku semua file)

```ts
interface ChartContext {
  chart_type: string;
  title: string;
  x_axis_label?: string;
  y_axis_label?: string;
  series: Record<string, unknown>[];
  filters_applied: Record<string, string>;
}
```

`filters_applied` **selalu** dibangun dengan pola yang sama di seluruh dashboard — hanya berisi filter yang **aktif** :
```json
{ "tahun_ajaran": "2024/2025", "semester": 1, "fakultas": "STEI", "no_prodi": "135" }
```
Kalau tidak ada filter aktif sama sekali, `filters_applied` adalah objek kosong `{}`.

**Field yang TIDAK pernah dikirim** (sengaja dihilangkan dari semua chart untuk hemat token & hindari noise): `page`, `total_pages`