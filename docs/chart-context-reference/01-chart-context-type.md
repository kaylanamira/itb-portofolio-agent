# Tipe `ChartContext` — Definisi Tunggal

> **Ini satu-satunya tempat di seluruh `docs/chart-context-reference/` yang menjelaskan struktur `ChartContext` secara detail.** File lain dalam folder ini **merujuk** ke file ini, tidak menyalin ulang definisi tipe. Kalau kamu mengedit struktur tipe, cukup edit di sini.

---

## 1. Kenapa `chart_type` sekarang closed enum (bukan `string` bebas)

Sebelumnya `chart_type` bertipe `string` bebas — konsekuensinya tidak ada satu tempat pun yang menjawab pasti "chart_type apa saja yang mungkin dikirim frontend?". Sekarang ada **9 nilai tertutup**, didaftar eksplisit di bawah, dan setiap penambahan chart baru di masa depan **wajib** menambah nilai baru ke enum ini (jangan reuse nilai lama untuk bentuk visual yang berbeda).

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

interface ChartContext {
  chart_type: ChartType;
  title: string;
  x_axis_label?: string;
  y_axis_label?: string;
  series: Record<string, unknown>[];
  filters_applied: Record<string, string | number>;
}
```

## 3. Python

```python
from typing import Literal, Optional
from pydantic import BaseModel

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
]

class ChartContext(BaseModel):
    chart_type: ChartType
    title: str
    x_axis_label: Optional[str] = None
    y_axis_label: Optional[str] = None
    series: list[dict]
    filters_applied: dict = {}
```

---
## 4. Field umum (berlaku semua `chart_type`)

- **`title`** — judul card, sudah dalam Bahasa Indonesia, siap ditampilkan/dikutip apa adanya ke user.
- **`x_axis_label` / `y_axis_label`** — opsional, hanya ada kalau chart itu punya sumbu (chart list/value tidak punya).
- **`series`** — array baris data. Bentuk field di dalamnya **berbeda-beda per `chart_type`** — lihat file spesifik masing-masing chart.
- **`filters_applied`** — hanya berisi filter yang **aktif**. Kalau tidak ada filter aktif sama sekali, objeknya kosong `{}`. Contoh umum:
  ```json
  { "tahun_ajaran": "2024/2025", "semester": 1, "kode_fakultas": "STEI", "no_prodi": 135 }
  ```

**Field yang TIDAK pernah dikirim** (sengaja dihilangkan dari semua chart untuk hemat token & hindari noise): `page`, `total_pages`.

---

## 5. Aturan penamaan untuk `chart_type` baru di masa depan

Kalau menambah chart baru:

 Nama **harus** menjelaskan konten (apa yang dibandingkan/ditampilkan) DAN bentuk visual (bar/list/line/matrix/value), dipisah underscore.

---

## 6. Bentuk request penuh ke `/api/chat` saat trigger dari tombol "tanya insight"

`chart_context` tidak pernah dikirim sendirian — dia salah satu field dalam body request ke `/api/chat`. Bentuk lengkapnya:

```json
{
  "query": "Insight apa yang bisa saya ambil dari grafik ini?",
  "session_id": "b7e1a2c3-9f4d-4a1e-8b2c-1d3e5f7a9b0c",
  "chart_context": { "...": "..."}
}
```

### 7.1 `query` — **string tetap, bukan ketikan user**

Setiap tombol "tanya insight" di **semua** card, untuk **semua** `chart_type`, memicu request dengan `query` yang **persis sama**:

```
"Insight apa yang bisa saya ambil dari grafik ini?"
```

Ini bukan placeholder contoh — ini nilai literal tetap yang dikirim frontend. Implikasi untuk agent:

- **Jangan** coba menganalisis kalimat `query` ini secara literal (mis. mencari entitas/metric spesifik dari kata-katanya) — kalimatnya generik dan sama untuk semua chart. Sinyal yang sebenarnya soal chart mana, metric apa, dan filter apa ada di `chart_context`, bukan di `query`.
- Perlakukan trigger ini sebagai instruksi umum: "berikan insight yang relevan dari data pada `chart_context` yang dilampirkan".
- Kalau user melanjutkan percakapan setelah respons pertama (mengetik pertanyaan susulan sendiri), itu adalah **turn baru** dengan `query` bebas ketikan user — bukan lagi bagian dari initial trigger ini, dan `chart_context` pada turn susulan itu **belum tentu ikut dikirim ulang** (perlu dicek per-implementasi frontend saat itu; jangan asumsikan selalu ada).

### 7.2 `session_id`

UUID session percakapan yang sedang berjalan. Dipakai backend untuk continuity histori antar-turn. Bukan bagian dari `ChartContext`, tapi selalu hadir berdampingan dengannya di request yang sama.