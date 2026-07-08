# Dashboard Akademik ITB — Overview Total

Dokumen ini untuk **pengembang** dan sebagai **referensi agen** tentang keseluruhan dashboard, sebelum masuk ke detail per-chart di file lain dalam folder ini.

> Untuk definisi lengkap tipe `ChartContext` (struktur field, enum `chart_type`, tabel padanan nama lama→baru), lihat **`01-chart-context-type.md`** — file ini **tidak** mengulang definisi itu.

---

## 1. Apa isi dashboard ini

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
| **Pelaksanaan Perkuliahan** | 4 sub-tab: Rancangan Perkuliahan (Q8/beban kerja & komposisi penilaian), Performa Dosen (Q4-Q7 & kehadiran dosen), Performa Mahasiswa (Q11-Q12 & kehadiran mahasiswa), Sarana Prasarana (Q9-Q10) |
| **Ringkasan Komentar** | Top Isu dan Komentar mentah mahasiswa/dosen/ITB (paginated, teks bebas) — **di luar scope fitur chart-interpret** |

---

## 3. Perilaku khusus: chart perbandingan "collapse" jadi bentuk 1-entitas ketika hanya ada 1 entitas

Ini **pola arsitektur terpenting** untuk dipahami sebelum baca file chart lain di folder ini.

Banyak chart di dashboard ini berupa **perbandingan antar-entitas** (bar chart fakultas/prodi). Misalnya, membandingkan skor Q5 antar-prodi.

Tapi begitu data yang tersisa cuma **1 entitas** (karena scope Kaprodi hanya dapat mengamati 1 entitas program studi, atau karena Direktorat/Dekan drill-down manual ke 1 entitas), chart itu **otomatis berubah bentuk** — bentuk penggantinya berbeda-beda tergantung chart:

| Chart | Mode banyak entitas (`chart_type`) | Mode 1 entitas (`chart_type`) |
|---|---|---|
| Skor kuesioner per fakultas/prodi | `entity_comparison_bar_chart` | `course_ranking_top_bottom_list` (list top/bottom-5 matkul) |
| Kehadiran dosen/mahasiswa | `entity_comparison_bar_chart` | `single_entity_percentage_value` (1 angka + delta) |
| Distribusi nilai | `grade_distribution_stacked_bar_chart` | `grade_distribution_single_entity_bar_chart` |
| Komposisi penilaian | `grading_composition_stacked_bar_chart` | `grading_composition_single_entity_bar_chart` |

Detail lengkap tiap chart ada di file masing-masing (§6).

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

**Semua field di `chart_context.series` di seluruh dashboard memakai nama kolom database asli** (`skor_q28`, bukan `skor_q8`) — bukan alias UI. Ini disengaja, supaya agen bisa mencocokkan nama field langsung ke `COMMENT ON COLUMN` di database (lihat `agent/tools/schema_retriever.py`), tanpa perlu tabel terjemahan tambahan.

### Kelompok gabungan (composite)

| Kolom komposit | Cakupan |
|---|---|
| `avg_skor_capaian` | Q1-Q3 |
| `avg_skor_pelaksanaan` | Q4-Q8 (**bukan** Q4-Q7 — lihat catatan di bawah) |
| `avg_skor_sarana_prasarana` | Q9-Q10 |
| `avg_skor_perilaku_mahasiswa` | Q11-Q12 |
| `avg_skor_overall` | Semua Q1-Q12 |

**Perhatian khusus:**
Card dashboard "Performa Dosen (Q4-Q7)" **sengaja tidak** memakai kolom `avg_skor_pelaksanaan` karena kolom itu mencakup Q8.

Nilai dashboard "Performa Dosen (Q4-Q7)" dihitung manual dari merata-ratakan `skor_q24`+`skor_q25`+`skor_q26`+`skor_q27`.

Kalau agen melihat metric ini di `chart_context`, field-nya akan berupa:
`rata_rata_dari_kolom: ["skor_q24","skor_q25","skor_q26","skor_q27"]`, bukan `avg_skor_pelaksanaan`. Detail lengkap ada di `02-entity-comparison-and-ranking-chart.md` §3.1.1.

---

## 5. Yang TIDAK termasuk fitur "tanya insight chart"

- **Tab Ringkasan Komentar** (`RawCommentList`) — ini teks bebas, bukan metrik numerik. Tidak ada tombol insight di sana (belum ada rencana menambahkannya).
- **4 stat card di atas** (jumlah kelas/matkul/dosen/mahasiswa) — angka ringkasan sederhana.
- **Filter bar, breadcrumb, navigasi tab** — bukan chart, tidak relevan.

---

## 6. Daftar file dalam folder ini

| File | Chart yang dijelaskan |
|---|---|
| `01-chart-context-type.md` | Definisi tipe `ChartContext` & enum `chart_type` (rujukan tunggal) |
| `02-entity-comparison-and-ranking-chart.md` | Semua bar chart perbandingan entitas + semua varian ranking top/bottom matkul (16 metric, termasuk rata-rata IP) — **paling sering dipakai** |
| `03-attendance-chart.md` | Kehadiran dosen & mahasiswa |
| `04-grade-distribution-chart.md` | Distribusi nilai A-E |
| `05-grade-trend-chart.md` | Tren skor antar-semester |
| `06-score-heatmap-chart.md` | Matrix 12 skor pertanyaan × entitas |
| `07-grading-composition-chart.md` | Komposisi bobot komponen penilaian |
| `08-skor-by-sks-chart.md` | Rata-rata skor Q8 per kelompok SKS |

---

## 7. Kontrak umum `chart_context`

Lihat `01-chart-context-type.md` untuk definisi tipe TypeScript/Python lengkap dan aturan field umum (`filters_applied`, field yang tidak pernah dikirim, dll).

`chart_context` sendiri dikirim sebagai bagian dari body request ke `/api/chat` bersama `query` dan `session_id`. **`query` pada trigger tombol "tanya insight" selalu berupa string tetap yang sama untuk semua chart** ("Insight apa yang bisa saya ambil dari grafik ini?") — bukan pertanyaan bebas user. Detail lengkap & implikasinya untuk agent ada di `01-chart-context-type.md` §7.