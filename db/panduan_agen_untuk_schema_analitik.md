# Panduan Schema `analitik` untuk Agen Text-to-SQL & RAG

Dokumen ini untuk tim yang membangun: agen Text-to-SQL, agen RAG, agen domain
**wisudawan** (survei alumni), dan agen domain **ulasan/portofolio dosen**.

**Satu kalimat paling penting di seluruh dokumen ini**: agen HANYA boleh
membaca dari schema `analitik.*` (13 view), TIDAK PERNAH dari
`analitik_mv.*` atau schema lain. Semua hal lain di bawah ini menjelaskan
kenapa dan bagaimana.

---

## 1. Arsitektur — Dua Schema

```
analitik_mv.*   ← raw materialized views (TERLARANG diakses agen)
      │
      ▼  (di-wrap oleh view + security definer function)
analitik.*      ← 13 view, INI YANG DIPAKAI AGEN
```

- `analitik_mv.*` adalah data mentah, tidak ter-filter, tidak ter-mask.
  Role database aplikasi kebetulan adalah **owner** dari `analitik_mv`,
  artinya **GRANT/REVOKE tidak mencegah akses langsung** ke sana. Filtering
  per-role HANYA terjadi jika query melalui `analitik.*`.
- `analitik.*` berisi 13 view: 5 view publik (A1–A5, tidak ada filter baris)
  dan 8 view wrapper (B1–B8) yang di baliknya dipanggil
  `analitik.fn_get_*()` — function `SECURITY DEFINER` yang melakukan
  filtering baris dan masking kolom berdasarkan role user.

### Implikasi langsung untuk agen Text-to-SQL

1. **Validasi sebelum eksekusi**: setiap query yang digenerate harus
   diparse, dan SEMUA referensi tabel/view harus fully-qualified ke schema
   `analitik` (contoh: `analitik.v_akademik_kelas`). Jika ada referensi ke
   `analitik_mv.*`, schema lain, atau tabel tanpa schema prefix → **tolak
   query**, jangan dieksekusi.
2. **Hanya `SELECT`**. Tolak `INSERT/UPDATE/DELETE/DDL` apapun.
3. **Session variable wajib di-set sebelum query** (lihat §2) — tanpa ini,
   8 view B1–B8 akan selalu return 0 baris (bukan error, tapi silent empty).

---

## 2. Session Variable (Row-Level Security)

**Versi terbaru/resmi** (sumber: `core/scope.py`,
`UserScope.get_rls_vars()`) — backend men-`SET LOCAL` 6 variable berikut
sebelum query ke `analitik.*`:

```python
{
    "app.user_id": str(user_id),
    "app.role":    r.role.value,        # LOWERCASE, contoh: "admin", "dosen", "jajaran_prodi"
    "app.dosen_id": str(r.dosen_id) if r.dosen_id else "",
    "app.kk_id":    str(r.kk_id) if r.kk_id else "",
    "app.no_ps":    str(r.no_ps) if r.no_ps else "",
    "app.kd_fak":   r.kd_fak or "",
}
```

`app.role` valuenya **lowercase** (enum `UserRole`):
`admin`, `direktorat`, `dekan`, `jajaran_dekanat`, `kaprodi`,
`jajaran_prodi`, `dosen`.

| Role (`app.role`) | Efek pada 8 view B1–B8 |
|---|---|
| `admin`, `direktorat` | semua baris, semua kolom (tidak ada filter/mask) |
| `dekan`, `jajaran_dekanat` | filter `kode_fakultas = app.kd_fak` |
| `kaprodi`, `jajaran_prodi` | filter `no_prodi = app.no_ps` |
| `dosen` | filter `no_prodi = app.no_ps`, **plus** masking kolom (lihat §4) |

Tanpa session variable sama sekali (atau setelah mismatch di atas
diperbaiki tapi backend belum jalan `SET LOCAL`) → semua 8 view B1–B8
return **0 baris**. View publik A1–A5 selalu return data terlepas dari
session variable (tidak ada filtering).

---

## 3. Cara Mendapatkan Dokumentasi Kolom (untuk RAG)

Schema sudah didokumentasikan
lengkap via `COMMENT ON VIEW` dan `COMMENT ON COLUMN` di database itu
sendiri. Agen RAG sebaiknya melakukan introspection langsung:

```sql
-- Deskripsi tiap view
SELECT obj_description('analitik.v_akademik_kelas'::regclass) AS deskripsi_view;

-- Deskripsi semua kolom suatu view
SELECT a.attname AS kolom, col_description(a.attrelid, a.attnum) AS deskripsi
FROM pg_attribute a
WHERE a.attrelid = 'analitik.v_akademik_kelas'::regclass
  AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY a.attnum;
```

Setiap comment kolom berformat konsisten dan SUDAH menjelaskan: makna
kolom, satuan/skala, kondisi NULL, dan (untuk kolom kuesioner) teks
pertanyaan asli + skala jawaban. Ini sumber kebenaran tunggal — kalau
comment di DB berubah, dokumentasi otomatis ikut update tanpa perlu sinkron
manual dengan dokumen ini.

---

## 4. Daftar 13 View — Ringkasan

### Grup A — View Publik (semua role, tanpa filter baris)

| View | Grain | Isi |
|---|---|---|
| `v_akademik_jenis_dan_sifat_matkul` | 1 baris = (mata_kuliah_id, no_prodi, paket/struktur) | Jenis MK dalam kurikulum: wajib/pilihan, paket, sifat (Core/Elective) |
| `v_info_umum_kelas_matkul` | 1 baris = 1 kelas | Lookup kelas/MK/dosen/prodi TANPA nilai/kehadiran/skor |
| `v_info_umum_institusi` | 1 baris = (no_prodi, semester, tahun) | Jumlah kelas/MK/dosen/mahasiswa aktif per prodi per semester |
| `v_info_umum_dosen` | 1 baris = (dosen_id, semester, tahun) | Beban mengajar dosen, daftar prodi/MK diajar |
| `v_info_umum_wisuda` | 1 baris = (no_prodi, periode_ijazah_id_final, periode_seremoni_id) | Jumlah **responden** survei wisudawan per prodi per periode |

### Grup B — View dengan Row/Column Security

| View | Grain | Row filter | Column masking |
|---|---|---|---|
| `v_akademik_kelas` | 1 kelas | fakultas/prodi | `skor_dosen_q25/26/27` (JSONB) untuk DOSEN |
| `v_akademik_komentar_mahasiswa` | 1 komentar/mhs/kelas | fakultas/prodi; DOSEN: hanya kelas yg ia ajar | – |
| `v_akademik_portofolio` | 1 kelas (yg punya portofolio) | fakultas/prodi | – |
| `v_akademik_statistik_prodi` | (no_prodi, semester, tahun) | fakultas/prodi sendiri | – |
| `v_akademik_statistik_dosen` | (dosen_id, semester, tahun) | fakultas homebase / prodi diajar | `avg_skor_*`, `avg_pct_kehadiran_dosen`, dll untuk dosen lain (DOSEN) |
| `v_wisudawan_distribusi_jawaban` | (periode, no_prodi, kode_pertanyaan, nilai) | fakultas/prodi | – |
| `v_wisudawan_statistik_pertanyaan` | (periode, no_prodi, kode_pertanyaan) — HANYA ordinal | fakultas/prodi | – |
| `v_wisudawan_jawaban_responden` | 1 responden (response_id) — wide table ~140 kolom | fakultas/prodi | – |

---

## Hal Wajib Diperhatikan (Lintas View)

Ini bagian paling penting. Salah satu dari ini diabaikan → hasil query
*terlihat* valid tapi **salah secara analitis**.

### 5.1 NULL ≠ 0 di kolom distribusi nilai (`v_akademik_kelas`, `v_akademik_statistik_prodi`)

`dist_jumlah_*`, `dist_pct_*` adalah **NULL** (bukan 0) jika
`is_distribusi_nilai_sah = FALSE`/NULL — artinya nilai belum disahkan,
BUKAN "0 mahasiswa mendapat nilai tersebut". **Selalu**
`WHERE is_distribusi_nilai_sah = TRUE` sebelum agregasi/analisis distribusi
nilai. Mengabaikan ini akan membuat agen menyimpulkan "0% mahasiswa lulus"
untuk kelas yang datanya belum masuk, bukan kelas yang benar-benar gagal
total.

### 5.2 `skor_dosen_q25/26/27` adalah JSONB, bukan numerik

Format: `{"686": 3.25, "4571": 3.43}` — key adalah `dosen_id::TEXT`, value
adalah skor. Untuk role DOSEN, JSONB ini di-mask sehingga hanya berisi key
miliknya sendiri (atau `NULL` jika dosen tersebut tidak punya skor). Agen
yang melakukan agregasi numerik pada kolom ini **harus** unwrap JSONB
terlebih dahulu (`jsonb_each`, `->>`, dll), tidak bisa `AVG()` langsung.

### 5.3 `periode_ijazah_id` vs `periode_ijazah_id_final`
(`v_wisudawan_jawaban_responden`, view wisudawan lainnya)

- `periode_ijazah_id`: nilai ASLI dari data sumber, **66% NULL** (bukan
  anomali — by design).
- `periode_ijazah_id_final`: versi siap-pakai (asli jika ada, diimputasi
  dari `submit_date` jika NULL).
- **Selalu gunakan `periode_ijazah_id_final`** untuk filtering/grouping per
  periode. `periode_ijazah_id` mentah hampir tidak pernah relevan untuk
  agen kecuali secara eksplisit ditanya soal data sumber/data quality.

### 5.4 `is_seremoni_asumtif`

Saat ini **SELURUH data seremoni wisuda adalah data dummy/placeholder**
(`is_seremoni_asumtif = TRUE` untuk semua baris) — data seremoni riil belum
tersedia. Jika user bertanya soal "seremoni wisuda" secara spesifik (bukan
sekadar "wisuda" secara umum), agen sebaiknya menyebutkan bahwa data
seremoni masih bersifat sementara/asumtif. Kolom ini ada di
`v_info_umum_wisuda`, `v_wisudawan_distribusi_jawaban`,
`v_wisudawan_statistik_pertanyaan`, `v_wisudawan_jawaban_responden`.

### 5.5 Kolom section-spesifik di `v_wisudawan_jawaban_responden` akan NULL
secara sistematis

View ini wide table (~140 kolom) menggabungkan pertanyaan universal +
pertanyaan khusus per strata/fakultas. NULL pada kolom-kolom ini **bukan
missing data**, tapi karena pertanyaan tersebut **tidak ditanyakan** ke
responden tersebut:

| Prefix kolom | Hanya terisi untuk |
|---|---|
| `s101`, `s102`, `s103`, `s104_sq*` | `jenjang = 'S1'` |
| `m01`, `m02`, `m03` | `jenjang = 'S2'` |
| `d01_sq*` | `jenjang = 'S3'` |
| `fsrd01_sq*` … `fsrd05_sq*` | `kode_fakultas = 'FSRD'` |
| `sbm01_sq*` | `kode_fakultas = 'SBM'` |

Jika agen menghitung "rata-rata skor `fsrd01_sq001`", **harus**
`WHERE kode_fakultas = 'FSRD'` (atau biarkan NULL ter-exclude otomatis oleh
`AVG()` — tapi tetap perlu disadari bahwa populasi efektifnya hanya FSRD,
bukan "semua wisudawan").

### 5.6 Ordinal vs Nominal — jangan `AVG()` kolom nominal

`v_wisudawan_statistik_pertanyaan` HANYA berisi pertanyaan **ordinal**
(skala Likert, `tipe_opsi='O'`, mean/median valid). Pertanyaan **nominal**
(kategorikal, contoh `U02` = alasan rekomendasi prodi: 1=Kualitas dosen,
2=Suasana akademik, dst.) TIDAK ADA di view ini — gunakan
`v_wisudawan_distribusi_jawaban` (distribusi frekuensi per nilai) dan
JANGAN hitung rata-rata dari nilai numeriknya (rata-rata dari kode kategori
tidak bermakna).

Di `v_wisudawan_jawaban_responden`, kolom nominal sudah di-decode ke label
teks (via CASE), jadi relatif aman — tapi tetap perhatikan komentar kolom
untuk tahu mana yang ordinal (skala 1–4/1–5, bisa di-`AVG`) vs nominal
(kategori, hanya untuk `GROUP BY`/`COUNT`).

### 5.7 Dua era portofolio dosen (`v_akademik_portofolio`)

`skema_pertanyaan` menentukan kolom mana yang terisi:

- **`'baru'`** (kd_pertanyaan 12–19, sejak 2018/sem-1, ~54K baris): kolom
  `metode_perkuliahan`, `komponen_penilaian`, `statistik_nilai_kelas`,
  `analisis_ketercapaian_outcomes`, `tanggapan_kuesioner_mahasiswa`,
  `refleksi_perkuliahan`, `usulan_perbaikan_dosen`, `rekomendasi_ke_itb`, +
  `komentar_*` (verifikator era baru).
- **`'lama'`** (kd_pertanyaan 1–11, sebelum 2018, ~27K baris): kolom
  `lama_metode_perkuliahan`, `lama_statistik_kelas`, ... `lama_komentar_*`.
- **`'kosong'`**: belum diisi sama sekali.

**Jangan pernah `COALESCE`/gabung kolom era baru dan era lama menjadi satu
kolom "universal"** tanpa flag — keduanya punya cakupan pertanyaan yang
tidak 1:1. Selalu cek `skema_pertanyaan` dulu. Kasus edge: ~11.618 kelas
(2016/1–2017/2) punya `skema_pertanyaan='lama'` meski kuesioner
**mahasiswa**-nya sudah pakai skema baru (Q21–Q37) — untuk kelas ini,
respons dosen terhadap kuesioner mahasiswa ada di
`lama_uraian_kuesioner_statistik` dan `lama_komentar_kuesioner_mahasiswa`,
bukan di kolom era-baru.

### 5.8 Semua teks bebas sudah distrip HTML

Kolom komentar/free-text (baik di portofolio maupun
`v_wisudawan_jawaban_responden`) sudah melalui `strip_html()` — agen tidak
perlu (dan tidak boleh) menambahkan pembersihan HTML lagi.

---

## 6. Mapping Pertanyaan Kuesioner Mahasiswa (Q21–Q30, Q35, Q37)

Dipakai di `v_akademik_kelas.skor_q*` /`skor_dosen_q*`,
`v_akademik_statistik_prodi.avg_skor_q*`, dan kolom turunan
`avg_skor_capaian/pelaksanaan/sarana_prasarana/perilaku_mahasiswa/overall`.
Skala selalu **1–4** (Tidak Setuju → Setuju).

| Kolom | Pertanyaan (ID) |
|---|---|
| `q21` | Memperoleh informasi cukup tentang luaran matakuliah |
| `q22` | Perkuliahan diarahkan agar mahasiswa mencapai luaran matakuliah |
| `q23` | Mahasiswa mencapai/menguasai luaran matakuliah |
| `q24` | Pelaksanaan perkuliahan terorganisir dengan baik |
| `q25` | Dosen berkomunikasi dengan efektif *(per-dosen via `skor_dosen_q25`)* |
| `q26` | Dosen peduli terhadap pencapaian mahasiswa *(per-dosen via `skor_dosen_q26`)* |
| `q27` | Dosen berlaku adil/fair *(per-dosen via `skor_dosen_q27`)* |
| `q28` | Beban kerja sesuai SKS |
| `q29` | Sarana prasarana memadai *(komponen `avg_skor_sarana_prasarana`)* |
| `q30` | Fasilitas pendukung di luar kuliah memadai *(komponen `avg_skor_sarana_prasarana`)* |
| `q35` | Mahasiswa berusaha sungguh-sungguh mengikuti matakuliah |
| `q37` | Mahasiswa memperoleh pengalaman belajar positif |

`avg_skor_overall` = rata-rata semua Q yang tidak NULL (Q21–Q30, Q35, Q37).
Q25/26/27 di tingkat kelas (`skor_q25/26/27`) adalah rata-rata lintas dosen
(jika tim-teaching); versi per-dosen ada di `skor_dosen_q25/26/27` (JSONB,
ter-mask untuk DOSEN — lihat §5.2).

---

## 7. Catatan Khusus per Domain Agen

### 7.1 Agen Domain Wisudawan

- Sumber data mentah: `evaluasi_wisudawan.respons` (JSONB `jawaban`, key =
  `kd_pertanyaan` seperti `U03_SQ001`), semua sudah di-flatten jadi kolom di
  `v_wisudawan_jawaban_responden`.
- 137 pertanyaan total, terbagi section A–K. Lihat comment kolom untuk
  section, populasi (semua/S1/S2/S3/FSRD/SBM), skala jawaban, dan teks
  pertanyaan asli — semua sudah dalam satu string comment per kolom,
  format: `Section X (KODE) | Topik | Populasi: ... | Skala: ... |
  Pertanyaan: ...`.
- Section U02 (rekomendasi prodi) adalah **nominal**, punya kolom
  pendamping `u02_other` (free-text, terisi hanya jika `u02` = "Other").

### 7.2 Agen Domain Ulasan/Portofolio Dosen

- Lihat §5.7 — cek `skema_pertanyaan` SEBELUM membaca kolom manapun.
- `v_akademik_portofolio` hanya berisi kelas **yang portofolionya sudah
  diisi** (bukan semua kelas) — untuk daftar lengkap kelas pakai
  `v_info_umum_kelas_matkul` atau `v_akademik_kelas`.
- `lengkap` (boolean) = status verifikasi, `nilai_portofolio` = nilai hasil
  verifikasi. Keduanya independen dari `skema_pertanyaan`.
- Untuk pertanyaan "apa kata dosen tentang kelas X", field yang relevan
  tergantung era: era baru → `refleksi_perkuliahan`,
  `tanggapan_kuesioner_mahasiswa`, `usulan_perbaikan_dosen`,
  `rekomendasi_ke_itb`; era lama → `lama_refleksi_perkuliahan`,
  `lama_komentar_kuesioner_mahasiswa`, `lama_rencana_tindak_lanjut`,
  `lama_rekomendasi_*`.

### 7.3 Agen Text-to-SQL (umum, semua domain)

- Konvensi nama kolom across semua view: `no_prodi` (integer
  `utama.program_studi.no_ps`), `kode_prodi` (string 2 karakter),
  `kode_matkul` (6 karakter), `kode_fakultas` (string, contoh STEI/SBM),
  `tahun_ajaran` (`'YYYY/YYYY'`), `semester` (1=ganjil, 2=genap, 3=pendek),
  `jenjang` (S1/S2/S3/PR).

---

## 8. Checklist Singkat Sebelum Eksekusi Query Agen

1. ✅ Semua referensi tabel di-prefix `analitik.` — tidak ada
   `analitik_mv`, tidak ada schema lain, tidak ada tabel tanpa prefix.
2. ✅ Statement adalah `SELECT` murni (tidak ada INSERT/UPDATE/DELETE/DDL/
   `;`-chained multi-statement berbahaya).
3. ✅ Session variable `app.role`, `app.no_ps`, `app.kd_fak`,
   `app.dosen_id`, `app.user_id`, `app.kk_id` sudah di-`SET LOCAL` sesuai
   role/scope user yang sedang login, dalam transaksi yang sama dengan
   query — DAN `fn_get_*()` sudah disesuaikan untuk membaca nama+casing ini
   (lihat peringatan mismatch di §2).
4. ✅ Koneksi DB untuk agen idealnya `default_transaction_read_only = on`
   sebagai safety net tambahan.