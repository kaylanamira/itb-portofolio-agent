# Tipe `ChartContext` — Definisi Tunggal

> **File ini menjelaskan struktur `ChartContext` secara detail.** 

---

## 1. Kenapa `chart_type` sekarang closed enum (bukan `string` bebas)

Sekarang ada **10 nilai tertutup**, didaftar eksplisit di bawah.
Semua nama sekarang mengikuti pola: **`{konten}_{bentuk_visual}_{chart|list|value}`** — tujuannya supaya nama itu sendiri (tanpa buka dokumentasi apa pun) sudah cukup untuk menebak bentuk visualnya.

---

## 2. TypeScript

```ts
type ChartType =
  | "entity_comparison_bar_chart"
  | "course_ranking_top_bottom_list"
  | "single_entity_percentage_value"
  | "grade_distribution_stacked_bar_chart"
  | "grade_distribution_single_entity_bar_chart"
  | "score_trend_line_chart"
  | "score_heatmap_matrix_chart"
  | "grading_composition_stacked_bar_chart"
  | "grading_composition_single_entity_bar_chart"
  | "score_by_sks_bucket_bar_chart";

interface QuestionReference {
  kode_pertanyaan_frontend: string;   // contoh: "Q8"
  pertanyaan: string;   // teks pertanyaan asli (Bahasa Indonesia)
}

interface ChartContext {
  chart_type: ChartType;
  title: string;
  x_axis_label?: string;
  y_axis_label?: string;
  series: Record<string, unknown>[];
  filters_applied: Record<string, string | number>;
  hint: string[];
  jumlah_kelas_aktif?: number;
  question_reference?: Record<string, QuestionReference>;
}
```

## 3. Python

```python
from typing import Literal, Optional
from pydantic import BaseModel, Field

ChartType = Literal[
    "entity_comparison_bar_chart",
    "course_ranking_top_bottom_list",
    "single_entity_percentage_value",
    "grade_distribution_stacked_bar_chart",
    "grade_distribution_single_entity_bar_chart",
    "score_trend_line_chart",
    "score_heatmap_matrix_chart",
    "grading_composition_stacked_bar_chart",
    "grading_composition_single_entity_bar_chart",
    "score_by_sks_bucket_bar_chart",
]

class ChartContext(BaseModel):
    chart_type: ChartType
    title: str
    x_axis_label: Optional[str] = None
    y_axis_label: Optional[str] = None
    series: list[dict]
    filters_applied: dict = {}
    hint: list[str] = Field(default_factory=list)
    jumlah_kelas_aktif: Optional[int] = None
    question_reference: Optional[dict[str, QuestionReference]] = None
```

---

## 4. Field `hint` — konteks tambahan untuk synthesizer, bukan sumber tunggal

### 4.1 Definisi

`hint` adalah array string berisi arahan singkat tentang insight/observasi yang bisa diambil dari `chart_type` dan bentuk `series` yang bersangkutan. Isinya bersifat generik per `chart_type` — frontend mengirim daftar hint yang sama untuk semua instance chart dengan `chart_type` yang sama. Nama `hint` menekankan bahwa field ini adalah **konteks pengarah** (apa yang layak diperiksa), bukan **jawaban akhir**.

### 4.2 Isi per `chart_type`

Untuk **template skema kosong** yang mencakup **seluruh kombinasi `chart_type` × granularitas entitas** (fakultas/prodi) sekaligus dengan `hint` final/tetap per `chart_type`, lihat `02-chart-context-empty-templates.md`.

Contoh payload untuk tiap `chart_type` didokumentasikan di file per-chart masing-masing (§3 di tiap file `03`-`09`).

---

## 5. Field `question_reference`
 
### 5.1 Definisi
 
`question_reference` adalah dict opsional dengan : 
key : **nama field skor persis seperti yang muncul di `series`** (mis. `"skor_q28"`)

value : `QuestionReference` berisi kode pertanyaan versi UI (`kode_pertanyaan_frontend`, mis. `"Q8"`) dan teks pertanyaan aslinya (`pertanyaan`).
 
### 5.2 Kapan field `question_reference` ADA
 
Hanya pada baris/chart yang memuat kolom skor kuesioner:
- ChartType `entity_comparison_bar_chart` / `course_ranking_top_bottom_list` 

untuk metric individual (`q21`, `q22`, ..., `q37`), termasuk kasus khusus `q4_q7` (4 entry: `skor_q24`-`skor_q27`).

- ChartType `score_heatmap_matrix_chart`

selalu ada, berisi 12 entry (`skor_q21` s.d. `skor_q37`).

- ChartType `score_by_sks_bucket_bar_chart`

selalu ada, 1 entry (`skor_q28`).

### 5.3 Kapan field `question_reference` TIDAK ADA
 
Pada metric **komposit** (`overall`, `capaian`, `sarana_prasarana`, `perilaku_mahasiswa`) dan `avg_ip` — karena itu bukan 1 pertanyaan individual. Juga tidak ada pada chart yang sama sekali tidak menyentuh kolom `skor_qXX` (kehadiran, distribusi nilai, komposisi penilaian).
 
### 5.4 Kenapa tetap ditambahkan meski `title` sering sudah menjelaskan pertanyaannya
 
Untuk chart individual-Q (`entity_comparison_bar_chart`/`course_ranking_top_bottom_list`), `title` biasanya sudah memuat teks pertanyaan (mis. "Q8 — Kesesuaian Beban Kerja dengan SKS"), jadi `question_reference` di situ sifatnya **redundan by design** — ditambahkan demi konsistensi struktural (semua chart yang menyentuh `skor_qXX` individual selalu punya `question_reference`, tanpa perlu agent menghafal chart mana yang "kebetulan" sudah punya title informatif dan mana yang tidak).
 
### 5.5 Contoh
 
```json
"question_reference": {
  "skor_q28": { "kode_pertanyaan_frontend": "Q8", "pertanyaan": "Kesesuaian beban kerja dengan SKS" }
}
```
 
Detail isi lengkap per chart ada di file `02`, `03`, `07`, `09`.
 
---

## 6. Field umum lain (berlaku semua `chart_type`, kecuali disebutkan opsional-khusus)

- **`title`** — judul card, sudah dalam Bahasa Indonesia, siap ditampilkan/dikutip apa adanya ke user.
- **`x_axis_label` / `y_axis_label`** — opsional, hanya ada kalau chart itu punya sumbu (chart list/value tidak punya).
- **`series`** — array baris data.
- **`filters_applied`** — hanya berisi filter yang **aktif**. Kalau tidak ada filter aktif sama sekali, objeknya kosong `{}`. Contoh umum:
  ```json
  { "tahun_ajaran": "2024/2025", "semester": 1, "kode_fakultas": "STEI", "no_prodi": 135 }
  ```
- **`hint`** — array string berisi arahan singkat tentang insight.
- **`jumlah_matkul_aktif`** — opsional, **hanya ada** pada `chart_type: "course_ranking_top_bottom_list"`. Total jumlah mata kuliah aktif yang jadi basis perhitungan top/bottom pada entitas & periode yang difilter. Tujuannya memberi agent angka pasti untuk mengonfirmasi kenapa `kode_matkul` yang sama bisa muncul di posisi `top` dan `bottom` sekaligus.
- **`question_reference`** — dict dengan key `field pertanyaan yang ada di payload (misal skor_q28)` dan value berupa `kode_pertanyaan_frontend` dan `pertanyaan`.

**Field yang TIDAK pernah dikirim** (sengaja dihilangkan dari semua chart untuk hemat token & hindari noise): `page`, `total_pages`.

---

## 7. Bentuk request penuh ke `/api/chat` saat trigger dari tombol "tanya insight"

`chart_context` tidak pernah dikirim sendirian — dia salah satu field dalam body request ke `/api/chat`. Bentuk lengkapnya:

```json
{
  "query": "Insight apa yang bisa saya ambil dari grafik ini?",
  "session_id": "b7e1a2c3-9f4d-4a1e-8b2c-1d3e5f7a9b0c",
  "chart_context": { "...": "..." }
}
```

### `query` — string tetap, bukan ketikan user

Setiap tombol "tanya insight" di **semua** card, untuk **semua** `chart_type`, memicu request dengan `query` yang **persis sama**:

```
"Insight apa yang bisa saya ambil dari grafik ini?"
```