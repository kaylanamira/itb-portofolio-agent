# Dokumentasi Materialized Views
**Sistem:** Portofolio & Kuesioner Akademik ITB  
**Database:** `dev_six` — query langsung ke schema SIX, tanpa duplikasi data (ETL)

---

## Gambaran Umum

Tiga MV ini membentuk lapisan analitik di atas database operasional SIX. Data tidak disalin ke tempat lain — MV membaca langsung dari tabel asli SIX, lalu hasilnya di-*cache* sehingga dashboard dan chatbot bisa query dengan cepat tanpa membebani sistem utama.

```
SIX Database (sumber, tidak diubah)
  kelas.*  +  utama.*  +  evaluasi.*  +  mahasiswa.*
                        ↓  REFRESH
                    mv_kelas                ← granularitas: per kelas
                        ↓
              mv_statistik_prodi            ← granularitas: per prodi per semester
              mv_statistik_dosen            ← granularitas: per dosen per semester
```

**Urutan REFRESH wajib:**
```sql
REFRESH MATERIALIZED VIEW mv_kelas;
REFRESH MATERIALIZED VIEW mv_statistik_prodi;
REFRESH MATERIALIZED VIEW mv_statistik_dosen;
```

---

## 1. `mv_kelas`

> **Granularitas:** 1 baris = 1 kelas  
> **Peran:** Sumber data utama. Semua MV lain dibaca dari sini.

Setiap kelas di ITB direpresentasikan dalam satu baris, dengan semua dimensi yang dibutuhkan sudah ter-*flatten* — tidak perlu JOIN lagi di lapisan aplikasi.

### Kelompok Atribut

#### Identitas Kelas
| Kolom | Keterangan |
|-------|-----------|
| `kelas_id` | ID unik kelas (PK) |
| `mata_kuliah_id` | FK ke mata kuliah |
| `no_kelas` | Nomor kelas paralel (1, 2, 3, ...) |
| `semester` | 1 = ganjil, 2 = genap, 3 = pendek |
| `tahun` | Tahun kalender pelaksanaan |
| `tahun_ajaran` | Format `"2023/2024"` — dihitung otomatis dari semester & tahun |

#### Mata Kuliah
| Kolom | Keterangan |
|-------|-----------|
| `kode_mk` | Kode MK (mis. `"MA1101"`) |
| `nama_mk_id` / `nama_mk_en` | Nama MK dalam Bahasa Indonesia dan Inggris |
| `sks` | Jumlah SKS |
| `tahun_kurikulum` | Kurikulum MK berasal (mis. `2019`) |
| `jenis_nilai` | `"ABCDE"` atau `"PassFail"` |

#### Prodi & Fakultas
| Kolom | Keterangan |
|-------|-----------|
| `kode_prodi` | ID numerik prodi (`no_ps`) |
| `singkatan_prodi` | Kode singkat (`"IF"`, `"EL"`, dst.) |
| `nama_prodi_id` / `nama_prodi_en` | Nama lengkap prodi |
| `jenjang` | Jenjang studi (`"S1"`, `"S2"`, `"S3"`) |
| `kode_fakultas` | Kode fakultas (`"STEI"`, `"FMIPA"`, dst.) |
| `nama_fakultas_id` / `nama_fakultas_en` | Nama lengkap fakultas |

#### Dosen
| Kolom | Keterangan |
|-------|-----------|
| `semua_dosen_id` | Array integer ID semua dosen pengampu (`INTEGER[]`) |
| `semua_dosen_nama_gelar` | Array nama lengkap + gelar semua dosen (`TEXT[]`) |

Satu kelas bisa diajar lebih dari satu dosen. Array ini memungkinkan query seperti *"tampilkan semua kelas yang pernah diajar dosen X"* tanpa JOIN tambahan.

#### Statistik Kehadiran & Nilai Mahasiswa
| Kolom | Keterangan |
|-------|-----------|
| `pct_kehadiran_dosen` | Persentase kehadiran dosen (%) |
| `pct_kehadiran_mahasiswa` | Persentase kehadiran mahasiswa (%) |
| `rata_ip_akhir_mahasiswa` | Rata-rata IP akhir mahasiswa di kelas ini |
| `jumlah_mahasiswa` | Jumlah mahasiswa yang punya nilai sah di kelas |
| `skor_dna` | Skor DNA (Dosen Nilai Akhir) — skor komposit sistem SIX |
| `ip_mhs_dna` | IP mahasiswa versi DNA |

#### Distribusi Nilai
Tersedia dalam dua bentuk: **jumlah absolut** dan **persentase**.

| Kolom | Keterangan |
|-------|-----------|
| `dist_jumlah_a` .. `dist_jumlah_e` | Jumlah mahasiswa dengan nilai A, AB, B, BC, C, D, E |
| `dist_jumlah_pass` / `dist_jumlah_fail` | Jumlah P / F (khusus MK PassFail) |
| `dist_pct_a` .. `dist_pct_fail` | Persentase masing-masing nilai (2 desimal) |
| `dist_pct_lulus_A_C` | % mahasiswa lulus dengan standar ≥ C (atau Pass) |
| `dist_pct_lulus_A_D` | % mahasiswa lulus dengan standar ≥ D (atau Pass) |

> Nilai `T` (incomplete/belum selesai) **tidak dihitung** dalam distribusi.

#### Skor Kuesioner — Per Pertanyaan
Skala 1–5 dari hasil pengisian kuesioner mahasiswa.

| Pertanyaan | Kolom | Dimensi |
|-----------|-------|---------|
| Q21 | `skor_q21` | Capaian pembelajaran |
| Q22 | `skor_q22` | Capaian pembelajaran |
| Q23 | `skor_q23` | Capaian pembelajaran |
| Q24 | `skor_q24` | Pelaksanaan perkuliahan |
| Q25 | `skor_q25_avg` | Penguasaan materi dosen *(rata-rata antar dosen)* |
| Q26 | `skor_q26_avg` | Kemampuan menjelaskan dosen *(rata-rata antar dosen)* |
| Q27 | `skor_q27_avg` | Interaksi dosen–mahasiswa *(rata-rata antar dosen)* |
| Q28 | `skor_q28` | Pelaksanaan perkuliahan |
| Q29 | `skor_q29` | Sarana & prasarana |
| Q30 | `skor_q30` | Sarana & prasarana |
| Q35 | `skor_q35` | Perilaku mahasiswa |
| Q37 | `skor_q37` | Perilaku mahasiswa |

Q21–Q24, Q28–Q30, Q35, Q37 adalah skor level **kelas** (sama untuk semua dosen di kelas itu). Q25–Q27 berbeda per dosen — yang tersimpan di `mv_kelas` adalah rata-ratanya.

#### Skor Per Dosen (JSONB)
| Kolom | Format | Keterangan |
|-------|--------|-----------|
| `skor_kues_dosen_q25` | `{"123": 3.67, "456": 4.00}` | Skor Q25 tiap dosen di kelas ini |
| `skor_kues_dosen_q26` | `{"123": 3.44, "456": 2.00}` | Skor Q26 tiap dosen |
| `skor_kues_dosen_q27` | `{"123": 3.11, "456": 3.50}` | Skor Q27 tiap dosen |

Key = `dosen_id` sebagai string, Value = skor rata-rata 4 desimal. `NULL` untuk kelas yang tidak punya data kuesioner per dosen (data lama sebelum sistem baru).

#### Skor Rata-rata Per Dimensi
| Kolom | Komponen | Keterangan |
|-------|---------|-----------|
| `avg_skor_capaian` | Avg(Q21, Q22, Q23) | Seberapa baik capaian pembelajaran terpenuhi |
| `avg_skor_pelaksanaan` | Avg(Q24–Q28) | Kualitas pelaksanaan perkuliahan oleh dosen |
| `avg_skor_sarana_prasarana` | Avg(Q29, Q30) | Kondisi fasilitas dan sarana |
| `avg_skor_perilaku_mahasiswa` | Avg(Q35, Q37) | Keterlibatan dan perilaku belajar mahasiswa |
| `avg_skor_overall` | Avg semua Q yang ada | Skor keseluruhan kelas |

### Insight yang Bisa Digali
- Kelas mana yang punya skor kuesioner terendah semester ini?
- Apakah kelas dengan IP tinggi juga punya skor kuesioner tinggi?
- Distribusi nilai kelas X dibandingkan rata-rata prodi
- Dosen mana yang punya skor Q25 (penguasaan materi) terendah di kelas tertentu?
- Apakah kelas besar (banyak mahasiswa) cenderung punya kehadiran lebih rendah?

### Sumber Tabel
| Tabel SIX | Alasan |
|-----------|--------|
| `kelas.kelas` | Basis utama — setiap baris MV = satu kelas |
| `kelas.pengajar` | Relasi kelas ↔ dosen, untuk membangun array `semua_dosen_id` |
| `utama.dosen` | Nama dosen lengkap dengan gelar |
| `utama.mata_kuliah` | Nama, SKS, jenis penilaian (ABCDE/PassFail) |
| `utama.program_studi` | Nama, jenjang, kode prodi |
| `utama.fakultas` | Nama dan kode fakultas |
| `mahasiswa.kuliah` | Distribusi nilai nyata per kelas — sumber ground truth nilai mahasiswa |
| `evaluasi.nilai_kelas` | Skor kuesioner level kelas (Q21–Q24, Q28–Q30, Q35, Q37) + kehadiran + IP |
| `evaluasi.nilai_dosen` | Skor Q25/Q26/Q27 per dosen, skor dimensi agregat (`skor_kues`) |

---

## 2. `mv_statistik_prodi`

> **Granularitas:** 1 baris = 1 program studi × 1 semester × 1 tahun  
> **Sumber:** Agregasi dari `mv_kelas` + hitung mahasiswa aktif dari `mahasiswa.status`

MV ini menjawab pertanyaan di level program studi: bagaimana performa satu prodi dalam satu semester, dari sisi nilai mahasiswa, kuesioner, kehadiran, dan jumlah sumber daya aktif.

### Kelompok Atribut

#### Identitas Prodi & Periode
| Kolom | Keterangan |
|-------|-----------|
| `kode_prodi`, `singkatan_prodi` | ID dan kode singkat prodi |
| `nama_prodi_id` / `nama_prodi_en` | Nama prodi dua bahasa |
| `jenjang` | S1 / S2 / S3 |
| `kode_fakultas`, `nama_fakultas_id`, `nama_fakultas_en` | Identitas fakultas induk |
| `semester`, `tahun`, `tahun_ajaran` | Periode evaluasi |

#### Ringkasan Aktivitas
| Kolom | Keterangan |
|-------|-----------|
| `jumlah_kelas` | Jumlah kelas yang diselenggarakan prodi semester ini |
| `jumlah_matkul_aktif` | Jumlah mata kuliah unik yang berjalan |
| `jumlah_dosen_aktif` | Jumlah dosen unik yang mengajar di prodi ini semester ini |
| `jumlah_mahasiswa_aktif` | Jumlah mahasiswa **aktif** prodi ini semester ini *(lihat catatan)* |

> **Catatan `jumlah_mahasiswa_aktif`:** Dihitung dari `mahasiswa.status` (bukan dari jumlah kursi kelas). Mahasiswa dianggap aktif jika `ts_daftar IS NOT NULL` (FRS selesai disetujui) **dan tidak ada** di `mahasiswa.nonaktif` semester yang sama (tidak sedang cuti/skorsing). Dikelompokkan berdasarkan **prodi asal mahasiswa**, bukan prodi penyelenggara kelas — sehingga mahasiswa lintas prodi tidak ikut terhitung.

#### Kehadiran & IP
| Kolom | Keterangan |
|-------|-----------|
| `avg_pct_kehadiran_dosen` | Rata-rata kehadiran dosen di semua kelas prodi (%) |
| `avg_pct_kehadiran_mahasiswa` | Rata-rata kehadiran mahasiswa (%) |
| `avg_ip_mhs` | Rata-rata IP mahasiswa lintas kelas prodi |

#### Distribusi Nilai (Akumulasi Seluruh Kelas Prodi)
| Kolom | Keterangan |
|-------|-----------|
| `total_jumlah_a` .. `total_jumlah_fail` | Jumlah absolut tiap grade, SUM dari semua kelas |
| `total_mahasiswa_dinilai` | Total mahasiswa yang sudah punya nilai sah (penyebut persentase) |
| `dist_pct_a` .. `dist_pct_fail` | Persentase tiap grade dari total mahasiswa dinilai |
| `dist_pct_lulus_A_C` | % mahasiswa lulus dengan standar ≥ C atau Pass |
| `dist_pct_lulus_A_D` | % mahasiswa lulus dengan standar ≥ D atau Pass |

> Persentase dihitung dari **akumulasi absolut**, bukan rata-rata persentase per kelas. Ini memastikan kelas besar punya bobot lebih besar dari kelas kecil — secara statistik lebih akurat.

#### Skor Kuesioner Per Pertanyaan (Tingkat Prodi)
`avg_skor_q21` hingga `avg_skor_q37` — rata-rata skor tiap pertanyaan dari seluruh kelas prodi. Kelas tanpa data kuesioner tidak ikut dihitung (NULL diabaikan AVG).

#### Skor Per Dimensi (Tingkat Prodi)
| Kolom | Keterangan |
|-------|-----------|
| `avg_skor_capaian` | Rata-rata skor dimensi capaian pembelajaran |
| `avg_skor_pelaksanaan` | Rata-rata skor dimensi pelaksanaan perkuliahan |
| `avg_skor_sarana_prasarana` | Rata-rata skor dimensi sarana prasarana |
| `avg_skor_perilaku_mahasiswa` | Rata-rata skor dimensi perilaku mahasiswa |
| `avg_skor_overall` | Rata-rata skor keseluruhan |

### Insight yang Bisa Digali
- Prodi mana di STEI yang punya pass rate terendah semester ini?
- Tren jumlah mahasiswa aktif prodi X dari 2018 sampai sekarang
- Apakah prodi dengan lebih banyak dosen punya skor kuesioner lebih tinggi?
- Perbandingan skor kuesioner antar prodi S1 di FMIPA
- Prodi mana yang distribusi nilainya paling banyak A dan AB?
- Untuk level institusi: `GROUP BY kode_fakultas` → statistik tingkat fakultas

### Sumber Tabel
| Tabel | Alasan |
|-------|--------|
| `mv_kelas` | Semua data kelas, nilai, kuesioner — sudah ter-flatten |
| `mahasiswa.status` | Dasar penghitungan mahasiswa aktif: `ts_daftar IS NOT NULL` = FRS selesai |
| `mahasiswa.nonaktif` | Filter exclude mahasiswa cuti, skorsing, outbound resmi |
| `utama.mahasiswa` | Mendapatkan `no_ps` asal mahasiswa (bukan prodi kelas) |

---

## 3. `mv_statistik_dosen`

> **Granularitas:** 1 baris = 1 dosen × 1 semester × 1 tahun  
> **Sumber:** `mv_kelas` + `evaluasi.nilai_dosen` + `utama.dosen` + `utama.kk`

MV ini adalah profil kinerja dosen per semester — menggabungkan beban mengajar, kehadiran, dan skor kuesioner yang spesifik untuk menilai dosen.

### Kelompok Atribut

#### Identitas Dosen
| Kolom | Keterangan |
|-------|-----------|
| `dosen_id` | ID dosen (PK bersama semester & tahun) |
| `nama_dosen_gelar` | Nama lengkap + gelar akademik |
| `nip` | Nomor Induk Pegawai |
| `kk_id`, `nama_kk_id`, `nama_kk_en` | Kelompok Keahlian dosen (nama dalam dua bahasa) |
| `kode_fakultas_dosen` | Fakultas langsung dari `utama.dosen.kd_fak`|
| `kode_prodi` | Home prodi dosen — berbeda dari prodi tempat mengajar |

#### Periode
| Kolom | Keterangan |
|-------|-----------|
| `semester`, `tahun`, `tahun_ajaran` | Periode evaluasi |

#### Beban Mengajar
| Kolom | Keterangan |
|-------|-----------|
| `jumlah_kelas` | Total kelas unik yang diajar semester ini |
| `jumlah_matkul` | Total mata kuliah unik yang diajar |
| `total_sks_diajar` | Total SKS dari semua kelas (termasuk kelas paralel) |

> `total_sks_diajar` adalah beban total, bukan SKS unik per MK. Dosen yang mengajar 3 kelas paralel MK 3 SKS akan tercatat 9 SKS.

#### Kehadiran & IP Mahasiswa
| Kolom | Keterangan |
|-------|-----------|
| `avg_pct_kehadiran_dosen` | Rata-rata kehadiran dosen di kelas yang diajar (%) |
| `avg_pct_kehadiran_mahasiswa` | Rata-rata kehadiran mahasiswa di kelas yang diajar (%) |
| `avg_ip_mhs` | Rata-rata IP akhir mahasiswa di kelas yang diajar |

#### Skor Kuesioner Spesifik Dosen
Tiga pertanyaan ini paling langsung menilai kualitas dosen secara individual:

| Kolom | Pertanyaan | Keterangan |
|-------|-----------|-----------|
| `avg_skor_q25` | Q25 | Penguasaan materi oleh dosen |
| `avg_skor_q26` | Q26 | Kemampuan menjelaskan |
| `avg_skor_q27` | Q27 | Interaksi dosen dengan mahasiswa |

Dihitung sebagai rata-rata dari semua kelas yang diajar dosen semester itu. `NULL` = tidak ada data kuesioner per dosen (data historis sebelum sistem baru).

#### Skor Dimensi Evaluasi Dosen
| Kolom | Keterangan |
|-------|-----------|
| `avg_skor_capaian` | Rata-rata skor dimensi capaian di kelas yang diajar |
| `avg_skor_pelaksanaan` | Rata-rata skor dimensi pelaksanaan |
| `avg_skor_sarana_prasarana` | Konteks saja — bukan evaluasi dosen, tapi fasilitas kelas |
| `avg_skor_perilaku_mahasiswa` | Rata-rata skor perilaku mahasiswa di kelas yang diajar |
| `avg_skor_overall` | Rata-rata dari capaian + pelaksanaan + perilaku *(sarana tidak ikut)* |
| `jumlah_kelas_dengan_skor` | Berapa kelas yang punya data skor kuesioner |

> **Kenapa sarana tidak masuk overall dosen?** Sarana prasarana (Q29/Q30) adalah penilaian terhadap fasilitas fisik kampus, bukan terhadap dosen. Memasukkannya ke overall dosen akan mendistorsi penilaian.

#### Nilai Akhir & Daftar Mengajar
| Kolom | Keterangan |
|-------|-----------|
| `avg_nilai_akhir` | Rata-rata nilai akhir dosen dari `evaluasi.nilai_dosen.nilai_akhir` *(sering NULL)* |
| `kelas_ids` | Array semua `kelas_id` yang diajar semester ini |
| `kode_mk_list` | Array kode MK unik yang diajar |
| `kode_prodi_diajar` | Array `no_ps` prodi tempat dosen mengajar *(bisa ≠ `kode_prodi`)* |
| `singkatan_prodi_diajar` | Array kode singkat prodi tersebut |

### Insight yang Bisa Digali
- Dosen mana di KK X yang punya skor Q25 (penguasaan materi) terendah?
- Apakah dosen dengan beban mengajar tinggi (SKS banyak) punya skor lebih rendah?
- Dosen yang mengajar di luar home prodi mereka — bagaimana skor kuesionernya?
- Tren skor kuesioner dosen X dari semester ke semester
- Dosen yang mengajar paling banyak prodi berbeda semester ini
- Perbandingan kehadiran dosen antar KK di STEI

### Sumber Tabel
| Tabel | Alasan |
|-------|--------|
| `mv_kelas` | Data kelas yang diajar, kehadiran, IP mahasiswa, skor dimensi kelas |
| `utama.dosen` | Identitas dosen: `nip`, `nama_gelar`, `kk_id`, `kd_fak`, `no_ps` |
| `utama.kk` | Nama kelompok keahlian dan fakultas via KK |
| `evaluasi.nilai_dosen` | Skor kuesioner spesifik dosen: `kuesioner` (Q25/26/27) dan `skor_kues` (dimensi) |
| `kelas.kelas` | JOIN untuk dapat `semester` & `tahun` dari `nilai_dosen` |

---

## Catatan Penting

### Kolom `nilai_akhir`
`evaluasi.nilai_dosen.nilai_akhir` tidak konsisten diisi di database SIX. `avg_nilai_akhir` di `mv_statistik_dosen` kemungkinan besar `NULL` untuk sebagian besar baris.

### Fakultas via GROUP BY
Untuk mendapatkan statistik tingkat **fakultas**, tidak perlu MV terpisah. Cukup agregasi dari `mv_statistik_prodi`:
```sql
SELECT kode_fakultas, nama_fakultas_id, semester, tahun,
       SUM(jumlah_mahasiswa_aktif)   AS total_mahasiswa,
       SUM(total_jumlah_a)           AS total_nilai_a,
       AVG(avg_skor_overall)         AS avg_skor_overall
FROM mv_statistik_prodi
WHERE semester = 1 AND tahun = 2023
GROUP BY kode_fakultas, nama_fakultas_id, semester, tahun;
```
