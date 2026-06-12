# View Akademik (`analitik.*`) — Referensi Cepat

Akses/security: lihat `PANDUAN_SCHEMA_ANALITIK.md`.

## Daftar View

| View | Grain | Security |
|---|---|---|
| `v_akademik_jenis_dan_sifat_matkul` | (mata_kuliah_id, no_prodi, paket) | publik |
| `v_info_umum_kelas_matkul` | 1 kelas | publik |
| `v_info_umum_institusi` | (no_prodi, semester, tahun) | publik |
| `v_info_umum_dosen` | (dosen_id, semester, tahun) | publik |
| `v_akademik_kelas` | 1 kelas | row: fakultas/prodi; col-mask: `skor_dosen_q25/26/27` utk DOSEN |
| `v_akademik_komentar_mahasiswa` | 1 komentar/mhs/kelas | row: fakultas/prodi; DOSEN: hanya kelas sendiri |
| `v_akademik_portofolio` | 1 kelas (ada portofolio) | row: fakultas/prodi |
| `v_akademik_statistik_prodi` | (no_prodi, semester, tahun) | row: fakultas/prodi |
| `v_akademik_statistik_dosen` | (dosen_id, semester, tahun) | row: fakultas/prodi diajar; col-mask: kolom evaluasi utk DOSEN lain |

---

## 1. `v_akademik_jenis_dan_sifat_matkul`

| Kolom | Isi |
|---|---|
| `mata_kuliah_id`, `no_prodi`, `kode_prodi`, `jenjang`, `kode_fakultas` | identitas MK & prodi |
| `tahun_kurikulum` | tahun berlaku kurikulum |
| `sumber` | `kurikulum_2024` / `kurikulum_lama` |
| `paket_id`, `kode_jenis`, `nama_jenis`, `nama_paket` | hanya isi jika `sumber=kurikulum_2024` |
| `struktur_id`, `is_wajib_itb` | `is_wajib_itb` hanya valid utk `kurikulum_lama`; kur24 selalu FALSE (proxy: `kode_jenis='B'`) |
| `kode_sifat` | `C`=Core/Wajib, `E`=Elective (dinormalisasi lintas era) |

⚠️ 1 MK bisa multi-baris (>1 paket).

---

## 2. `v_info_umum_kelas_matkul`

| Kolom | Isi |
|---|---|
| `kelas_id`, `mata_kuliah_id`, `no_kelas`, `semester`, `tahun`, `tahun_ajaran` | identitas kelas |
| `kode_matkul`, `nama_matkul_id/en`, `sks`, `tahun_kurikulum`, `jenis_nilai` | info MK |
| `no_prodi`, `kode_prodi`, `nama_prodi_id/en`, `jenjang` | prodi |
| `kode_fakultas`, `nama_fakultas_id/en` | fakultas |
| `semua_dosen_id`, `semua_dosen_nama_gelar` | array, `[0]`=dosen utama; cek: `semua_dosen_id @> ARRAY[id]` |
| `kode_jenis_list`, `nama_jenis_list`, `nama_paket_list`, `kode_sifat_list` | array, NULL jika MK tidak terdaftar kurikulum |
| `is_wajib_itb` | dari kurikulum lama |

Tanpa nilai/kehadiran/skor — itu di `v_akademik_kelas` (filtered).

---

## 3. `v_info_umum_institusi`

| Kolom | Isi |
|---|---|
| `no_prodi`, `kode_prodi`, `nama_prodi_id/en`, `jenjang`, `kode_fakultas`, `nama_fakultas_id/en`, `semester`, `tahun`, `tahun_ajaran` | dimensi |
| `jumlah_kelas`, `jumlah_matkul_aktif`, `jumlah_dosen_aktif`, `jumlah_mahasiswa_aktif` | agregat |

---

## 4. `v_info_umum_dosen`

| Kolom | Isi |
|---|---|
| `dosen_id`, `semester`, `tahun` (PK) | dimensi |
| `nama_dosen_gelar`, `nip`, `kk_id`, `kode_fakultas_dosen`, `no_prodi`, `kode_prodi` | identitas/homebase |
| `jumlah_kelas`, `jumlah_matkul`, `total_sks_diajar` | beban mengajar |
| `kode_matkul_list`, `no_prodi_diajar`, `kode_prodi_diajar` | array MK/prodi diajar |

Tanpa skor evaluasi — itu di `v_akademik_statistik_dosen` (filtered+masked).

---

## 5. `v_akademik_kelas`

### Dimensi
| Kolom | Isi |
|---|---|
| `kelas_id`, `mata_kuliah_id`, `no_kelas`, `semester`, `tahun`, `tahun_ajaran` | identitas |
| `kode_matkul`, `nama_matkul_id/en`, `sks`, `tahun_kurikulum`, `jenis_nilai` | MK |
| `no_prodi`, `kode_prodi`, `nama_prodi_id/en`, `jenjang` | prodi |
| `kode_fakultas`, `nama_fakultas_id/en` | fakultas |
| `semua_dosen_id`, `semua_dosen_nama_gelar`, `kode_jenis_list`, `nama_jenis_list`, `nama_paket_list`, `kode_sifat_list`, `is_wajib_itb` | sama seperti `v_info_umum_kelas_matkul` |

### Kehadiran / IP / DNA
| Kolom | Isi |
|---|---|
| `pct_kehadiran_mahasiswa`, `pct_kehadiran_dosen` | 0–100, NULL jika belum ada evaluasi |
| `avg_ip_akhir_mahasiswa` | NULL jika belum ada evaluasi |
| `skor_dna`, `ts_dna`, `ip_mhs_dna` | Did Not Attend; NULL jika tidak ada kasus DNA |

### Distribusi Nilai — gate `is_distribusi_nilai_sah`
| Kolom | Isi |
|---|---|
| `is_distribusi_nilai_sah` | TRUE = nilai sah; FALSE/NULL → semua `dist_*` di bawah NULL (bukan 0) |
| `jumlah_mahasiswa` | jumlah dgn nilai sah |
| `dist_jumlah_a/ab/b/bc/c/d/e/pass/fail` | jumlah mhs per nilai |
| `dist_pct_a/ab/b/bc/c/d/e/pass/fail` | persentase per nilai |
| `dist_pct_lulus_a_c` | lulus ≥C (atau Pass) — metrik utama kelulusan |
| `dist_pct_lulus_a_d` | lulus ≥D |

⚠️ WAJIB `WHERE is_distribusi_nilai_sah = TRUE` sebelum pakai kolom `dist_*`.

### Skor Kuesioner Mahasiswa (skala 1–4, NULL jika belum ada data)
| Kolom | Pertanyaan |
|---|---|
| `skor_q21` | Informasi cukup ttg luaran MK |
| `skor_q22` | Perkuliahan diarahkan capai luaran |
| `skor_q23` | Mahasiswa capai luaran MK |
| `skor_q24` | Perkuliahan terorganisir |
| `skor_q25` | Dosen komunikasi efektif (rata² lintas dosen) |
| `skor_q26` | Dosen peduli pencapaian mhs |
| `skor_q27` | Dosen berlaku adil |
| `skor_q28` | Beban kerja sesuai SKS |
| `skor_q29` | Sarana prasarana memadai (komponen sarpras) |
| `skor_q30` | Fasilitas luar kuliah memadai (komponen sarpras) |
| `skor_q35` | Mhs berusaha sungguh-sungguh |
| `skor_q37` | Pengalaman belajar positif |
| `avg_skor_capaian/pelaksanaan/sarana_prasarana/perilaku_mahasiswa/overall` | turunan; sarana_prasarana=(Q29+Q30)/2; overall=rata² semua Q non-NULL |

### JSONB Per-Dosen — ter-mask utk role DOSEN
| Kolom | Isi |
|---|---|
| `skor_dosen_q25/26/27` | `{"dosen_id": skor}`; DOSEN hanya lihat key miliknya (atau NULL jika tidak ada entry). Unwrap: `skor_dosen_q25->>'686'` |

---

## 6. `v_akademik_komentar_mahasiswa`

| Kolom | Isi |
|---|---|
| `jawaban_id` (PK), `kelas_id` | identitas |
| `tahun`, `semester`, `tahun_ajaran`, `kode_matkul`, `nama_matkul_id/en`, `sks`, `no_kelas` | dimensi kelas |
| `no_prodi`, `kode_prodi`, `nama_prodi_id`, `jenjang`, `kode_fakultas`, `nama_fakultas_id` | prodi/fakultas |
| `semua_dosen_id`, `semua_dosen_nama_gelar` | array dosen |
| `komentar_teks` | free-text, sudah strip HTML — sumber utama RAG/sentimen |
| `ts_jawaban` | timestamp pengisian |

⚠️ 1 kelas → banyak baris (1/mahasiswa pengisi). Role DOSEN: filter tambahan `semua_dosen_id @> ARRAY[dosen_id]`.

---

## 7. `v_akademik_portofolio`

1 baris = 1 kelas yang **punya portofolio**. Semua teks strip HTML.

| Kolom | Isi |
|---|---|
| `kelas_id`, `kode_mk`, `nama_mk_id/en`, `sks`, `no_kelas`, `semester`, `tahun`, `tahun_ajaran`, `tahun_kurikulum`, `jenis_nilai` | identitas |
| `kode_prodi`, `singkatan_prodi`, `nama_prodi_id`, `jenjang`, `kode_fakultas`, `nama_fakultas_id`, `no_prodi`, `nama_prodi_en` | prodi/fakultas |
| `semua_dosen_id`, `semua_dosen_nama_gelar` | array dosen |
| `tgl_entri`, `lengkap`, `nilai_portofolio`, `skema_pertanyaan` | metadata; `skema_pertanyaan`: `baru`/`lama`/`kosong` |

### Era Baru (`skema_pertanyaan='baru'`, kd_pertanyaan 12–19, sejak 2018, ~54K baris)
| Kolom | kd_pertanyaan / kd_grup |
|---|---|
| `metode_perkuliahan` | 12 / grup 6 (Penyelenggaraan) |
| `komponen_penilaian` | 13 / grup 6 |
| `statistik_nilai_kelas` | 14 / grup 7 (Ketercapaian) |
| `analisis_ketercapaian_outcomes` | 15 / grup 7 |
| `tanggapan_kuesioner_mahasiswa` | 16 / grup 8 (Refleksi) |
| `refleksi_perkuliahan` | 17 / grup 8 |
| `usulan_perbaikan_dosen` | 18 / grup 9 (Rekomendasi) |
| `rekomendasi_ke_itb` | 19 / grup 9 |
| `komentar_penyelenggaraan/ketercapaian/refleksi/rekomendasi` | komentar verifikator, grup 6/7/8/9 |

### Era Lama (`skema_pertanyaan='lama'`, kd_pertanyaan 1–11, sebelum 2018, ~27K baris)
| Kolom | kd_pertanyaan / kd_grup |
|---|---|
| `lama_metode_perkuliahan` | 1 / grup 2 |
| `lama_outcomes_matakuliah` | 2 / grup 1 |
| `lama_sistem_penilaian` | 3 / grup 1 |
| `lama_uraian_kuesioner_statistik` | 4 / grup 3 |
| `lama_refleksi_perkuliahan` | 5 / grup 3 |
| `lama_rencana_tindak_lanjut` | 6 / grup 4 |
| `lama_statistik_kelas` | 7 / grup 2 |
| `lama_analisis_statistik_ketercapaian` | 8 / grup 1 |
| `lama_komentar_kuesioner_mahasiswa` | 9 / grup 3 |
| `lama_rekomendasi_perbaikan_dosen` | 10 / grup 5 |
| `lama_rekomendasi_itb` | 11 / grup 5 |
| `lama_komentar_pencapaian_outcomes/pelaksanaan_kuliah/refleksi/rencana_tindak_lanjut/rekomendasi` | komentar verifikator, grup 1–5 |

⚠️ **Edge case ~11.618 kelas (2016/1–2017/2)**: `skema_pertanyaan='lama'` meski kuesioner mahasiswanya sudah era baru (Q21–Q37) → respons dosen ttg kuesioner mhs ada di `lama_uraian_kuesioner_statistik`(4) & `lama_komentar_kuesioner_mahasiswa`(9), bukan kolom era-baru.

⚠️ Jangan `COALESCE` kolom baru+lama — cakupan tidak 1:1. Selalu cek `skema_pertanyaan` dulu.

---

## 8. `v_akademik_statistik_prodi`

| Kolom | Isi |
|---|---|
| `no_prodi`, `kode_prodi`, `nama_prodi_id/en`, `jenjang`, `kode_fakultas`, `nama_fakultas_id/en`, `semester`, `tahun`, `tahun_ajaran` | dimensi (PK: no_prodi+semester+tahun) |
| `jumlah_kelas`, `jumlah_matkul_aktif`, `jumlah_dosen_aktif`, `jumlah_mahasiswa_aktif` | agregat aktivitas |
| `avg_pct_kehadiran_dosen/mahasiswa`, `avg_ip_akhir_mahasiswa` | rata² TIDAK tertimbang per kelas; NULL jika belum ada evaluasi |
| `total_jumlah_a/ab/b/bc/c/d/e/pass/fail`, `total_mahasiswa_dinilai` | akumulasi absolut lintas kelas (exclude kelas `dist_*` NULL) |
| `dist_pct_a/ab/b/bc/c/d/e/pass/fail/lulus_a_c/lulus_a_d` | **tertimbang** ukuran kelas = `total_jumlah_x/total_mahasiswa_dinilai*100`. BEDA dgn `AVG(v_akademik_kelas.dist_pct_*)` (unweighted) |
| `avg_skor_q21..q30/q35/q37` | rata² lintas kelas prodi, skala 1–4 (mapping sama dgn `v_akademik_kelas`) |
| `avg_skor_capaian/pelaksanaan/sarana_prasarana/perilaku_mahasiswa/overall` | turunan |

---

## 9. `v_akademik_statistik_dosen`

### Selalu tampil
| Kolom | Isi |
|---|---|
| `dosen_id`, `semester`, `tahun` (PK) | dimensi |
| `nama_dosen_gelar`, `nip`, `kk_id`, `nama_kk_id/en` | identitas |
| `kode_fakultas_dosen` | homebase, basis filter DEKAN |
| `no_prodi`, `kode_prodi` | homebase prodi (bisa NULL) |
| `jumlah_kelas`, `jumlah_matkul`, `total_sks_diajar`, `kelas_ids`, `kode_matkul_list` | beban mengajar |
| `no_prodi_diajar`, `kode_prodi_diajar` | array prodi yg kelasnya diajar (bisa ≠ homebase); basis filter KAPRODI/JAJ.PRODI/DOSEN |
| `avg_pct_kehadiran_mahasiswa` | TIDAK di-mask (info ttg mhs, bukan dosen) |

### ⚠️ `[SENSITIF]` — NULL utk dosen lain jika role=DOSEN
| Kolom | Isi |
|---|---|
| `avg_pct_kehadiran_dosen` | kehadiran dosen |
| `avg_ip_mhs` | rata² IP mhs di kelasnya |
| `avg_skor_q25/q26/q27` | per-dosen, skala 1–4 |
| `avg_skor_capaian/pelaksanaan/sarana_prasarana/perilaku_mahasiswa/overall` | dimensi evaluasi dosen |
| `jumlah_kelas_dengan_skor` | jumlah kelas dgn data evaluasi |
| `avg_nilai_akhir` | sering NULL (tidak konsisten diisi) |

⚠️ Role DOSEN: baris diri sendiri terisi penuh, baris dosen lain → kolom di atas NULL meski raw ada isi. Agregasi lintas-dosen oleh role DOSEN akan bias (hanya 1 baris non-NULL = dirinya).