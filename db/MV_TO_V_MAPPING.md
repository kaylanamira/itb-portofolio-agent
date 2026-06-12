# Mapping `analitik.mv_*` (lama) → `analitik.v_akademik_*` (baru)

Sumber kebenaran: `view_akademik.md`, `view_wisudawan.md`, `comment_on_view_wrapper.sql`.
Dokumen ini dipakai sebagai referensi untuk update:
`schema_linker.py`, `sql_generator.py` (domain rules), `data/few_shots/*.yaml`,
`db/DB_REFERENCE.md`, `sql_pipeline.py`, `visualize_all_graphs.py`, test files.

---

## Perubahan paling berisiko: makna `kode_prodi` TERTUKAR

Di MV lama, `kode_prodi` adalah **integer** (=`no_ps`) dan `singkatan_prodi` adalah
**string 2-karakter** ("IF", "EL"). Di view baru, **konvensi dibalik**:

| Lama (`mv_*`) | Baru (`v_akademik_*`) | Tipe | Isi |
|---|---|---|---|
| `kode_prodi` (integer) | `no_prodi` | integer | =`utama.program_studi.no_ps`, contoh `135` |
| `singkatan_prodi` (varchar) | `kode_prodi` | varchar(2) | =`utama.program_studi.kd_ps`, contoh `"IF"` |

Setiap query lama `WHERE kode_prodi = 135` harus jadi `WHERE no_prodi = 135`,
dan setiap query lama `WHERE singkatan_prodi = 'IF'` harus jadi `WHERE kode_prodi = 'IF'`.

Pola serupa berlaku untuk `mv_statistik_dosen`:
`kode_prodi_diajar`(int[]) / `singkatan_prodi_diajar`(text[]) →
`no_prodi_diajar`(int[]) / `kode_prodi_diajar`(text[]).

---

## Tabel/View

| Lama | Baru |
|---|---|
| `analitik.mv_kelas` | `analitik.v_akademik_kelas` |
| `analitik.mv_statistik_prodi` | `analitik.v_akademik_statistik_prodi` |
| `analitik.mv_statistik_dosen` | `analitik.v_akademik_statistik_dosen` |
| `analitik.mv_komentar_mahasiswa` | `analitik.v_akademik_komentar_mahasiswa` |
| (tidak ada) | `analitik.v_akademik_jenis_dan_sifat_matkul` (baru, publik) |
| (tidak ada) | `analitik.v_info_umum_kelas_matkul` (baru, publik) |
| (tidak ada) | `analitik.v_info_umum_institusi` (baru, publik) |
| (tidak ada) | `analitik.v_info_umum_dosen` (baru, publik) |
| (tidak ada di MV) | `analitik.v_akademik_portofolio` (baru, B-view) |

---

## Kolom — `v_akademik_kelas` (eks `mv_kelas`)

| Lama | Baru | Catatan |
|---|---|---|
| `kode_mk` | `kode_matkul` | rename mk→matkul |
| `nama_mk_id` | `nama_matkul_id` | rename |
| `nama_mk_en` | `nama_matkul_en` | rename |
| `kode_prodi` (int) | `no_prodi` | lihat catatan di atas |
| `singkatan_prodi` | `kode_prodi` (varchar) | lihat catatan di atas |
| `rata_ip_akhir_mahasiswa` | `avg_ip_akhir_mahasiswa` | rename |
| `skor_q25_avg` / `skor_q26_avg` / `skor_q27_avg` | `skor_q25` / `skor_q26` / `skor_q27` | hilangkan suffix `_avg` |
| `skor_kues_dosen_q25/26/27` (jsonb) | `skor_dosen_q25/26/27` (jsonb) | rename; tetap di-mask utk role DOSEN |
| `dist_jumlah_a..e`, `dist_jumlah_pass/fail`, `dist_pct_*` | sama | **tapi WAJIB tambah `WHERE is_distribusi_nilai_sah = TRUE`** (kolom baru, gate) |
| `semua_dosen_id`, `semua_dosen_nama_gelar` | sama | tidak berubah |
| `avg_skor_capaian/pelaksanaan/sarana_prasarana/perilaku_mahasiswa/overall` | sama | tidak berubah |
| `pct_kehadiran_dosen`, `pct_kehadiran_mahasiswa` | sama | tidak berubah |
| `skor_q21..q24, q28..q30, q35, q37` | sama | tidak berubah |
| `skor_dna`, `ts_dna`, `ip_mhs_dna` | sama | tidak berubah |
| (tidak ada) | `kode_jenis_list`, `nama_jenis_list`, `nama_paket_list`, `kode_sifat_list`, `is_wajib_itb` | **kolom baru** dari join ke `v_akademik_jenis_dan_sifat_matkul` |
| (tidak ada) | `is_distribusi_nilai_sah` | **kolom baru**, gate untuk `dist_*` |

---

## Kolom — `v_akademik_statistik_prodi` (eks `mv_statistik_prodi`)

| Lama | Baru |
|---|---|
| `kode_prodi` (int) | `no_prodi` |
| `singkatan_prodi` | `kode_prodi` (varchar) |
| `avg_ip_mhs` | `avg_ip_akhir_mahasiswa` |
| sisanya (`jumlah_kelas`, `dist_pct_*`, `avg_skor_q21..q37`, `avg_skor_*`) | sama |

---

## Kolom — `v_akademik_statistik_dosen` (eks `mv_statistik_dosen`)

| Lama | Baru |
|---|---|
| `kode_prodi` (int, homebase) | `no_prodi` |
| `kode_prodi_diajar` (int[]) | `no_prodi_diajar` |
| `singkatan_prodi_diajar` (text[]) | `kode_prodi_diajar` (text[]) |
| `kode_mk_list` | `kode_matkul_list` |
| `avg_skor_q25/q26/q27` | sama (TIDAK pakai prefix `_avg` dihilangkan — sudah benar dari awal) |
| `avg_ip_mhs` | sama (TIDAK direname di view ini — beda dgn statistik_prodi) |
| sisanya | sama |

---

## Kolom — `v_akademik_komentar_mahasiswa` (eks `mv_komentar_mahasiswa`)

| Lama | Baru |
|---|---|
| `kode_mk` | `kode_matkul` |
| `nama_mk_id` / `nama_mk_en` | `nama_matkul_id` / `nama_matkul_en` |
| `kode_prodi` (int) | `no_prodi` |
| `singkatan_prodi` | `kode_prodi` (varchar) |
| sisanya | sama |

Tambahan filter row-level utk role DOSEN: `semua_dosen_id @> ARRAY[dosen_id]` (sudah ditangani SECURITY DEFINER, agen tidak perlu tambahkan).

---

## Hal lain yang perlu diperhatikan saat update prompt/few-shot

1. **`is_distribusi_nilai_sah = TRUE` wajib** setiap kali query menyentuh kolom
   `dist_jumlah_*` atau `dist_pct_*` di `v_akademik_kelas`. Tanpa ini, hasil bisa
   campur NULL (belum ada nilai sah) dengan 0 (memang 0 mahasiswa).
2. Kolom baru `kode_jenis_list`, `nama_jenis_list`, `nama_paket_list`,
   `kode_sifat_list`, `is_wajib_itb` di `v_akademik_kelas` bisa dipakai untuk
   pertanyaan ttg jenis/sifat MK (wajib/pilihan) tanpa JOIN ke
   `v_akademik_jenis_dan_sifat_matkul` secara terpisah — tapi 1 kelas bisa
   punya >1 entri di array ini (krn 1 MK bisa >1 paket).
3. Setelah rename `kode_prodi`/`no_prodi`, contoh `GROUP BY kode_prodi, singkatan_prodi, nama_prodi_id`
   (lama) menjadi `GROUP BY no_prodi, kode_prodi, nama_prodi_id` (baru) — urutan
   kolom GROUP BY berubah maknanya, bukan cuma rename string.   