# View Wisudawan (`analitik.*`) — Referensi Cepat

Akses/security: lihat `PANDUAN_SCHEMA_ANALITIK.md`. Sumber mentah:
`evaluasi_wisudawan.*` (LimeSurvey, 7535 respons, 137 pertanyaan).

## Daftar View

| View | Grain | Security |
|---|---|---|
| `v_info_umum_wisuda` | (no_prodi, periode_ijazah_id_final, periode_seremoni_id) | publik |
| `v_wisudawan_distribusi_jawaban` | (periode, no_prodi, kode_pertanyaan, nilai) | row: fakultas/prodi |
| `v_wisudawan_statistik_pertanyaan` | (periode, no_prodi, kode_pertanyaan) — HANYA ordinal | row: fakultas/prodi |
| `v_wisudawan_jawaban_responden` | 1 responden (response_id), ~140 kolom | row: fakultas/prodi |

---

## ⚠️ Dua Sumbu Waktu

| Kolom | Makna | Catatan |
|---|---|---|
| `periode_ijazah_id` | periode ijazah ASLI, format YYYYMM | 66% NULL by design (PR 0%, S1 81.7%, S2 51.8%, S3 43.6% NULL) |
| `periode_ijazah_id_final`, `tahun_ijazah`, `bulan_ijazah` | versi siap pakai (asli atau diimputasi dari `submit_date`) | **PAKAI INI** utk filter/group periode kelulusan |
| `periode_seremoni_id`, `tahun_seremoni`, `bulan_seremoni`, `nama_seremoni` | kapan ACARA seremoni wisuda | beda dari periode ijazah |
| `is_seremoni_asumtif` | TRUE = data seremoni dummy/placeholder | **SAAT INI SEMUA BARIS = TRUE** (data riil belum ada). Jangan default-filter `=FALSE` (akan kosong). Sebutkan ke user kalau bahas seremoni spesifik. |

Default: pakai `tahun_ijazah`/`periode_ijazah_id_final` sebagai sumbu waktu utama.

---

## ⚠️ Ordinal vs Nominal

| `tipe_opsi` | Arti | Tampil di |
|---|---|---|
| `O` (Ordinal/Likert) | mean/median valid | `v_wisudawan_statistik_pertanyaan` + `v_wisudawan_distribusi_jawaban` |
| `N` (Nominal/Kategoris) | hanya distribusi/frekuensi, JANGAN `AVG` | hanya `v_wisudawan_distribusi_jawaban` |

### Skala Likert per `kd_grup_opsi` — JANGAN dicampur tanpa normalisasi

| `kd_grup_opsi` | Skala | Section |
|---|---|---|
| `SETUJU` | 1=Tidak Setuju … 4=Setuju | A, B, C1, C2 (U03, U01, U04, U05) |
| `FREKUENSI` | 1=Tidak pernah … 4=Selalu/besar | D1 (U06) |
| `HARAPAN` | 1=Tidak sesuai harapan … 5=Sepenuhnya memenuhi harapan | D2 (U07) |
| `HARAPAN_FSRD` | 1=Tidak sesuai harapan … 5=Memenuhi harapan (label beda dgn HARAPAN di titik 4) | J (FSRD01–05) |
| `PERKEMBANGAN_SBM` | 1=Undeveloped … 5=Highly Developed | K (SBM01) |

---

## 1. `v_info_umum_wisuda`

| Kolom | Isi |
|---|---|
| `no_prodi`, `kode_prodi`, `nama_prodi_id/en`, `jenjang`, `kode_fakultas`, `nama_fakultas_id/en` | prodi/fakultas |
| `periode_ijazah_id_final`, `tahun_ijazah`, `bulan_ijazah` | periode ijazah |
| `periode_seremoni_id`, `tahun_seremoni`, `bulan_seremoni`, `nama_seremoni`, `is_seremoni_asumtif` | periode seremoni |
| `jumlah_responden` | `COUNT(DISTINCT response_id)` — jumlah PENGISI SURVEI, BUKAN jumlah lulusan riil |

---

## 2. `v_wisudawan_distribusi_jawaban`

1 baris = (periode×prodi×pertanyaan×nilai) → distribusi frekuensi.

| Kolom | Isi |
|---|---|
| `periode_ijazah_id_final`, `tahun_ijazah`, `bulan_ijazah`, `periode_seremoni_id`, `tahun_seremoni`, `bulan_seremoni`, `nama_seremoni`, `is_seremoni_asumtif` | dimensi waktu |
| `no_prodi`, `kode_prodi`, `nama_prodi_id/en`, `jenjang`, `kode_fakultas`, `nama_fakultas_id/en` | dimensi prodi/fakultas |
| `kode_pertanyaan` | contoh `U03_SQ001`, `U02`, `G01Q23` |
| `kode_grup_pertanyaan` | section |
| `kode_grup_opsi`, `tipe_opsi` | skala & `O`/`N` |
| `nilai` | label teks hasil decode (contoh "Setuju", "Kualitas dosen") |
| `jumlah_responden` | jumlah yg pilih nilai ini |
| `persentase` | 0–100, terhadap total yg jawab pertanyaan ini di prodi+periode tsb |

Pakai untuk: distribusi/persentase per kategori, termasuk pertanyaan nominal (U02, dll.)

---

## 3. `v_wisudawan_statistik_pertanyaan`

1 baris = (periode×prodi×pertanyaan ordinal saja).

| Kolom | Isi |
|---|---|
| dimensi waktu & prodi/fakultas | sama dgn `v_wisudawan_distribusi_jawaban` |
| `kode_pertanyaan`, `kode_grup_pertanyaan`, `kode_grup_opsi` | hanya `tipe_opsi='O'` |
| `jumlah_responden` | jumlah yg jawab pertanyaan ini |
| `rata_rata`, `median`, `std_dev`, `skor_min`, `skor_max` | statistik deskriptif |

`std_dev` rendah=konsensus, tinggi=terpolarisasi. Skala beda per `kd_grup_opsi` (lihat tabel di atas) — jangan bandingkan nilai mentah antar section dgn skala berbeda.

---

## 4. `v_wisudawan_jawaban_responden` (wide table, 1 baris = 1 responden)

### Identitas & Dimensi
| Kolom | Isi |
|---|---|
| `response_id` (PK), `survey_platform_response_id` | ID internal / ID LimeSurvey asli (bisa NULL) |
| `submit_date` | waktu pengisian |
| `kd_strata`/`jenjang` | S1/S2/S3/PR |
| `kd_fak`/`kode_fakultas`, `nama_fakultas_id/en` | fakultas |
| `no_ps`/`no_prodi`/`kode_prodi`, `nama_prodi_id/en` | prodi |
| kolom periode (lihat tabel "Dua Sumbu Waktu") | |

### Section A — Fasilitas & Kepuasan ITB (skala `SETUJU`, semua populasi)
| Kolom | Topik |
|---|---|
| `u03_sq001`–`sq012` | ruang kelas, lab, internet, fasilitas keprofesian, perpustakaan, perangkat ajar, toilet, kantin, rekreasi, kesehatan, kepuasan keseluruhan (`sq012`) |

### Section B — Pendidikan di Prodi
| Kolom | Topik |
|---|---|
| `u01_sq001`–`sq012` (skala `SETUJU`) | wali akademik, interaksi dosen, kualitas MK wajib/pilihan, praktikum, sarana prodi, kesiapan kerja, kepuasan bidang studi |
| `u02` (NOMINAL) | alasan rekomendasi prodi: 1=Kualitas dosen, 2=Suasana akademik, 3=Jejaring alumni, 4=Lapangan pekerjaan, 5=Fasilitas akademik, 6=Tidak merekomendasikan, 7=Other |
| `u02_other` | free-text, isi hanya jika `u02='Other'` |

### Section C1 — Softskills (skala `SETUJU`)
| Kolom | Topik |
|---|---|
| `u04_sq001`–`sq009` | komunikasi lisan/tertulis, bahasa asing, problem solving, critical thinking, introspeksi, sampaikan pendapat, kerja tim/mandiri |

### Section C2 — Karakter (skala `SETUJU`)
| Kolom | Topik |
|---|---|
| `u05_sq001`–`sq007` | kejujuran, komitmen, kecerdasan emosi, kepedulian, objektivitas, perseverance, kepatuhan aturan |

### Section D1 — Permasalahan Studi (skala `FREKUENSI`)
| Kolom | Topik |
|---|---|
| `u06_sq001`–`sq009` | akademis, keuangan (+pengaruh), psikologis (+pengaruh), sosial budaya (+pengaruh), kesehatan (+pengaruh) |

### Section D2 — Dukungan (skala `HARAPAN`)
| Kolom | Topik |
|---|---|
| `u07_sq001`–`sq004` | beasiswa/pinjaman, bimbingan konseling, nasehat wali akademik, nasehat dosen MK |

### Section E — Free-text Pengalaman Belajar (NULL jika tidak diisi)
| Kolom | Topik |
|---|---|
| `g10q22`, `g01q23`–`g01q29` | kebiasaan belajar, kesan/prestasi, pengalaman berkesan, aktivitas kemahasiswaan, cita-cita karier/hidup, motto, sifat khas diri |

### Section F — Free-text Pandangan ITB
| Kolom | Topik |
|---|---|
| `g11q30`, `g01q31`–`g01q35` | suka duka, segi positif/negatif, saran perbaikan, saran ke mahasiswa lain, catatan lain |

### Section G — Khusus S1 (NULL utk strata lain)
| Kolom | Topik |
|---|---|
| `s101` (NOMINAL, YA_TIDAK) | rencana studi lanjut |
| `s102` (NOMINAL) | lokasi studi lanjut |
| `s103` (NOMINAL) | kelanjutan bidang studi |
| `s104_sq001`–`sq004` (skala `SETUJU`) | penilaian MK wajib ITB: agama, pancasila/kewarganegaraan, manajemen, lingkungan |

### Section H — Khusus S2 (NULL utk strata lain)
| Kolom | Topik |
|---|---|
| `m01`, `m02`, `m03` (semua NOMINAL) | rencana lanjut, lokasi, kelanjutan bidang — pola sama dgn S101–103 |

### Section I — Khusus S3 (NULL utk strata lain, skala `SETUJU`)
| Kolom | Topik |
|---|---|
| `d01_sq001`–`sq004` | filsafat ilmu, metodologi penelitian, kesulitan filsafat ilmu, kesulitan metodologi penelitian |

### Section J — Khusus FSRD (NULL utk fakultas lain, skala `HARAPAN_FSRD`)
| Kolom | Topik |
|---|---|
| `fsrd01_sq001`–`sq005` | pemahaman estetik, proses kreatif, menggambar/membentuk, pengetahuan prodi FSRD, menulis ilmiah |
| `fsrd02_sq001`–`sq003` | perwalian tatap muka/online, bantuan dosen wali |
| `fsrd03_sq001`–`sq006` | sejarah & perkembangan seni/kria/desain (lokal/global), metoda penciptaan, analisis-kritis karya, kesesuaian SKS |
| `fsrd04_sq001`–`sq006` | teknik penciptaan, wawasan estetik, kesesuaian SKS studio, asistensi, penilaian karya, kesesuaian dgn profesi |
| `fsrd05_sq001`–`sq004` | pengetahuan TA, proses pembimbingan TA, sarpras TA, literatur TA |

### Section K — Khusus SBM (NULL utk fakultas lain, skala `PERKEMBANGAN_SBM`)
| Kolom | Topik |
|---|---|
| `sbm01_sq001`–`sq031` | outcomes prodi SBM: komunikasi lisan/tulisan, marketing, manajemen operasi/SDM/keuangan, pengambilan keputusan & negosiasi, kewirausahaan, public speaking, riset bisnis, internet/jejaring, identifikasi peluang, problem solving, kerja tim, adaptasi sosial/etika/kesehatan, tanggung jawab profesional/etis, lifelong learning, pengetahuan pasca sarjana |

⚠️ `AVG()` pada kolom Section G–K otomatis exclude NULL, tapi populasi efektif HANYA strata/fakultas terkait — sebutkan ini di jawaban (jangan tampil seolah representasi seluruh ITB).

---

## Pemilihan View per Pertanyaan

| Pertanyaan user | View |
|---|---|
| Jumlah wisudawan prodi X tahun Y | `v_info_umum_wisuda` |
| % wisudawan setuju fasilitas Y memadai | `v_wisudawan_distribusi_jawaban` |
| Alasan rekomendasi prodi (U02) | `v_wisudawan_distribusi_jawaban` (nominal) |
| Rata-rata kepuasan thd dosen di prodi X | `v_wisudawan_statistik_pertanyaan` |
| Kualitatif: pengalaman belajar | `v_wisudawan_jawaban_responden`, Section E/F |
| Persepsi wisudawan FSRD ttg studio | `v_wisudawan_jawaban_responden`, `fsrd04_sq*` + filter `kode_fakultas='FSRD'` |
| Rencana studi lanjut S1 | `v_wisudawan_jawaban_responden`, `s101/s102/s103` + filter `jenjang='S1'` |