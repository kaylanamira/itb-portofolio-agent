# Perubahan Schema: `schema.sql` → `schema_portofolio_kuesioner.sql` + `schema_auth_and_ingestion.sql`

Dokumen ini menjelaskan seluruh perubahan yang dilakukan dari schema awal (`schema.sql`)
ke schema versi 2.0 yang terbagi menjadi dua file. Perubahan dilakukan berdasarkan hasil
EDA (Exploratory Data Analysis) terhadap data CSV asli dari SIX ITB dan evaluasi desain
23 poin.

---

## Mengapa Schema Dipecah Menjadi Dua File?

Schema awal (`schema.sql`) mencampur semua hal dalam satu file: tabel data akademik,
tabel pengguna, tabel upload, MV, RLS, dan trigger. Schema baru memisahkan concern:

| File | Isi |
|---|---|
| `schema_portofolio_kuesioner.sql` | Semua tabel yang berhubungan langsung dengan data akademik dari CSV SIX ITB: kelas, dosen, mata kuliah, kuesioner, portofolio, dan AI/vector |
| `schema_auth_and_ingestion.sql` | Semua tabel yang berhubungan dengan sistem: pengguna, peran, session login, dan log ingestion CSV |

Alasan pemisahan: keduanya punya lifecycle update yang berbeda. Tabel data akademik
berubah setiap kali CSV baru di-ingest. Tabel sistem berubah saat ada perubahan
konfigurasi akun atau proses upload.

---

## BAGIAN 1 — Perubahan Enum & Tipe Data

### 1.1 Enum `user_role_enum`: `wram` → `direktorat`

**Schema lama:**
```sql
CREATE TYPE user_role_enum AS ENUM (
    'admin', 'wram', 'dekan', 'jajaran_dekanat',
    'kaprodi', 'jajaran_prodi', 'dosen'
);
```

**Schema baru:**
```sql
CREATE TYPE user_role_enum AS ENUM (
    'admin', 'direktorat', 'dekan', 'jajaran_dekanat',
    'kaprodi', 'jajaran_prodi', 'dosen'
);
```

`wram` diganti `direktorat` untuk menyesuaikan istilah resmi yang lebih generik
dan tidak terikat singkatan internal satu unit. Enum ini dipindah ke
`schema_auth_session.sql` karena hanya digunakan di tabel `pengguna_peran`.

---

### 1.2 Enum `tipe_konten_enum`: Dua Nilai Diganti

**Schema lama memiliki:**
- `'tambahan_info_statistik'`
- `'analisis_capaian_kelas'` (hanya ini)

**Schema baru:**
- `'statistik_kelas'` — menggantikan `tambahan_info_statistik`
- `'analisis_capaian_kelas'` — tetap ada
- `'komentar_kuesioner'` — ditambahkan (untuk kd_pertanyaan 9 dan 16)

Penyesuaian berdasarkan teks pertanyaan aktual di `pertanyaan_portofolio.csv`:
pertanyaan nomor 14 berjudul "Statistik Kelas" (bukan "Tambahan Info Statistik")
dan pertanyaan 9/16 adalah "Komentar terhadap Hasil Kuesioner Mahasiswa" yang
sebelumnya tidak punya enum.

**Catatan penting:** `tipe_konten_enum` di schema baru hanya digunakan di tabel
`vector_chunks` sebagai metadata label filter RAG. Tabel `teks_portofolio`
tidak lagi menggunakan enum ini — diganti FK ke `pertanyaan_portofolio`
(lihat perubahan 4.5).

---

### 1.3 Pertanyaan Kuesioner Lama (Tidak Digunakan Lagi) dan Pertanyaan Kuesioner yang Aktif Digunakan

Format lama vs baru cukup diinfer dari nilai
`kd_pertanyaan` dan `kd_grup`:
- `kd_pertanyaan` 1–11 dan `kd_grup` 1–5 = format lama (is_active = FALSE)
- `kd_pertanyaan` 12–19 dan `kd_grup` 6–9 = format baru aktif (is_active = TRUE)

---

### 1.4 Enum Baru: `jenjang_prodi`, `jenis_nilai_mk`, `metode_auth`, `jenis_file_porto`, `status_ingestion`

Enum-enum ini tidak ada di schema lama. Ditambahkan untuk:
- `jenjang_prodi`: menggantikan `CHECK (jenjang IN ('S1','S2','S3','Profesi'))` di
  kolom `program_studi.jenjang` agar lebih terdefinisi di level tipe data
- `jenis_nilai_mk`: menggantikan `CHECK (jenis_nilai IN ('ABCDE', 'Pass/Fail'))` di
  `mata_kuliah`
- `metode_auth`, `jenis_file_porto`, `status_ingestion`: untuk tabel-tabel baru di
  `schema_auth_session.sql`

---

## BAGIAN 2 — Perubahan Tabel Referensi

### 2.1 Tabel `program_studi`: FK `fakultas_id` dari NOT NULL → NULLABLE

**Schema lama:**
```sql
fakultas_id UUID NOT NULL REFERENCES fakultas(fakultas_id) ON UPDATE CASCADE
```

**Schema baru:**
```sql
fakultas_id UUID REFERENCES fakultas(fakultas_id) ON DELETE SET NULL
```

Alasan: Data CSV tidak selalu menyertakan `fakultas_id`. Constraint NOT NULL
memaksa prodi harus punya fakultas sebelum bisa di-insert. Di schema baru, prodi
bisa di-seed lebih dulu, lalu `fakultas_id` diisi belakangan.

Selain itu, kolom `jenjang` berubah tipe dari `VARCHAR(10) CHECK (...)` menjadi
enum `jenjang_prodi`. Panjang kolom `nama_prodi` diperlebar dari `VARCHAR(150)`
→ `VARCHAR(300)`.

---

### 2.2 Tabel `mata_kuliah`: Perubahan Besar Berbasis CSV

Ini adalah salah satu perubahan terbesar yang didorong langsung oleh data CSV.

**Schema lama (desain tanpa lihat CSV):**
```sql
prodi_id   UUID NOT NULL REFERENCES program_studi ...
kode_mk    VARCHAR(20) NOT NULL
nama_mk    VARCHAR(200) NOT NULL
nama_mk_en VARCHAR(200) NOT NULL   -- nama Inggris
kategori   VARCHAR(100) NOT NULL DEFAULT 'Kuliah'
jenis_nilai VARCHAR(10) NOT NULL DEFAULT 'ABCDE'
```

**Schema baru (setelah EDA mata_kuliah.csv):**
```sql
six_matkul_id INTEGER UNIQUE  -- natural key dari CSV
prodi_id      UUID REFERENCES ... ON DELETE SET NULL  -- nullable, CSV tidak ada prodi per MK
kd_kuliah     VARCHAR(20) NOT NULL     -- rename dari kode_mk sesuai header CSV
nama_mk       VARCHAR(300) NOT NULL
nama_mk_en    VARCHAR(300)
th_kur        SMALLINT                 -- tahun kurikulum: 2019, 2024, 2026 (ada di CSV)
sks           SMALLINT NOT NULL        -- DIPINDAH dari tabel kelas ke sini (sesuai CSV)
jenis_nilai   jenis_nilai_mk           -- nullable, tidak ada di CSV
```

Perubahan kunci:
- Ditambah `six_matkul_id` sebagai natural key integer dari CSV (kolom `mata_kuliah_id`)
  untuk keperluan ETL upsert, namun dibuat null karena data dari scraping json tidak semuanya ada di CSV
- `prodi_id` jadi NULLABLE karena CSV tidak menyertakan prodi per MK. MK lintas-prodi
  (prefix WI) harus bisa `NULL`
- Dihapus: `kategori` — tidak ada di CSV
- Ditambah: `th_kur` (tahun kurikulum) — ada di CSV
- `sks` dipindah dari `kelas` ke `mata_kuliah` — karena di CSV, SKS adalah atribut `mata_kuliah`
  (ada di `mata_kuliah.csv`), bukan atribut `kelas` (tidak ada di `kelas.csv`)

---

### 2.3 Tabel `dosen`: Tambah `six_dosen_id` + Perlebar Kolom

**Schema lama:**
```sql
dosen_id    UUID PRIMARY KEY
kk_id       UUID REFERENCES kelompok_keahlian(kk_id) ON UPDATE CASCADE
nama_dosen  VARCHAR(150) NOT NULL
```

**Schema baru:**
```sql
dosen_id     UUID PRIMARY KEY
six_dosen_id INTEGER UNIQUE  -- natural key integer dari dosen.csv, nullable karena tidak semua hasil scraping json ada di csv six
kk_id        UUID REFERENCES kelompok_keahlian(kk_id) ON DELETE SET NULL  -- nullable
nama_dosen   VARCHAR(300) NOT NULL    -- diperlebar karena ada nama dosen panjang di data
```

`six_dosen_id` ditambahkan karena CSV (`dosen.csv`) menggunakan integer ID. ETL perlu
lookup `six_dosen_id → dosen_id (UUID)` saat import `pengajar.csv` dan `nilai_dosen.csv`.

`kk_id` jadi nullable karena CSV tidak menyertakan informasi KK dosen sama sekali —
relasi dosen-KK harus diisi manual oleh admin setelah import.

Ditambah index trigram GIN untuk nama dosen (fuzzy search chatbot):
```sql
CREATE INDEX idx_dosen_nama_trgm ON dosen USING GIN (nama_dosen gin_trgm_ops);
```

---

### 2.4 Tabel `kelompok_keahlian`: FK `fakultas_id` dari NOT NULL → NULLABLE + Tambah `kode_kk`

**Schema lama:** `fakultas_id NOT NULL`

**Schema baru:** `fakultas_id` nullable + tambah `kode_kk VARCHAR(30) UNIQUE`

Alasan sama seperti `program_studi`: data KK tidak ada di CSV, harus diisi manual.

---

### 2.5 Tabel Baru: `pertanyaan_kuesioner`, `pertanyaan_grup_portofolio`, `pertanyaan_portofolio`

Ketiga tabel ini **tidak ada di schema lama sama sekali**. Di schema lama, pertanyaan
kuesioner hanya direpresentasikan sebagai angka (`no_pertanyaan SMALLINT`) tanpa
tabel master.

**Mengapa ditambahkan?** EDA menemukan bahwa:
- `pertanyaan_kuesioner.csv` berisi 36 pertanyaan dengan kd_pertanyaan tertentu
  (Q21–Q37, Q103, Q128–Q152) — bukan Q1–Q12 seperti asumsi schema lama
- `pertanyaan_portofolio.csv` berisi 19 pertanyaan dengan dua format (lama: kd 1–11,
  baru: kd 12–19)
- `pertanyaan_grup_portofolio.csv` berisi 9 grup untuk mengelompokkan pertanyaan portofolio

Tabel-tabel ini dibutuhkan agar ETL bisa melakukan lookup `kd_pertanyaan → UUID`
saat import JSON dari `nilai_kelas.csv`, `nilai_dosen.csv`, dan `portofolio.csv`.

---

## BAGIAN 3 — Perubahan Tabel Core (kelas & pengajar)

### 3.1 Tabel `kelas`: Perubahan Signifikan Berbasis CSV

**Schema lama:**
```sql
kelas_id     UUID PRIMARY KEY
matkul_id    UUID NOT NULL REFERENCES mata_kuliah
no_kelas     VARCHAR(5) NOT NULL
semester     SMALLINT NOT NULL CHECK (semester IN (1,2,3))
tahun_ajaran VARCHAR(9) NOT NULL CHECK (tahun_ajaran ~ '^\d{4}/\d{4}$')
sks          SMALLINT NOT NULL CHECK (sks BETWEEN 1 AND 6)   -- ada di tabel kelas!
-- Statistik langsung di kelas:
pct_kehadiran_dosen     NUMERIC(5,2)
pct_kehadiran_mahasiswa NUMERIC(5,2)
rata_rata_nilai         NUMERIC(4,2)
jumlah_mahasiswa        SMALLINT
nilai_portofolio        SMALLINT
sumber_file             VARCHAR(500)
is_synthetic            BOOLEAN NOT NULL DEFAULT FALSE
```

**Schema baru:**
```sql
kelas_id     UUID PRIMARY KEY
six_kelas_id INTEGER UNIQUE NOT NULL  -- natural key dari kelas.csv
matkul_id    UUID NOT NULL REFERENCES mata_kuliah
prodi_id     UUID NOT NULL REFERENCES program_studi  -- DITAMBAHKAN
no_ps        SMALLINT NOT NULL         -- natural key SIX ITB untuk traceability
tahun        SMALLINT NOT NULL         -- ganti tahun_ajaran VARCHAR → tahun SMALLINT
semester     SMALLINT NOT NULL CHECK (semester IN (1,2,3))
no_kelas     SMALLINT NOT NULL         -- ganti VARCHAR(5) → SMALLINT sesuai CSV
```

Perubahan kunci:
- **`six_kelas_id`**: natural key integer dari `kelas.csv` (kolom `kelas_id`), dibutuhkan ETL
- **`prodi_id` + `no_ps`**: dua kolom baru. `no_ps` adalah nilai asli dari CSV untuk traceability;
  `prodi_id` adalah UUID FK hasil mapping untuk JOIN efisien di aplikasi
- **`tahun_ajaran VARCHAR(9)` → `tahun SMALLINT`**: CSV hanya punya kolom `tahun` (integer
  seperti 2024), bukan format string `'2024/2025'`
- **`no_kelas VARCHAR(5)` → `no_kelas SMALLINT`**: nilai di CSV adalah integer (1, 2, 3, 41, 42)
- **Dihapus dari `kelas`**: `sks`, semua kolom statistik (`pct_kehadiran_*`, `rata_rata_nilai`,
  `jumlah_mahasiswa`, `nilai_portofolio`, `sumber_file`, `is_synthetic`)

**Mengapa statistik dipisah?**
Statistik kelas (kehadiran, IP, DNA) ada di `nilai_kelas.csv` — file terpisah dari `kelas.csv`.
Menggabungkannya dalam satu tabel berarti tabel `kelas` harus menunggu data statistik
sebelum bisa di-insert. Dengan memisahkan ke `statistik_kelas`, kelas bisa di-insert
lebih dulu dari `kelas.csv`, lalu statistiknya di-insert setelahnya dari `nilai_kelas.csv`.

**Mengapa `sks` dipindah ke `mata_kuliah`?**
Karena di CSV, kolom `sks` ada di `mata_kuliah.csv`, bukan di `kelas.csv`. Menyimpan `sks`
di tabel `kelas` adalah duplikasi yang tidak didukung data.

---

### 3.2 Tabel `pengajar` → `pengajar_kelas`

**Schema lama:**
```sql
-- PK Composite:
PRIMARY KEY (kelas_id, dosen_id)
-- Tidak ada surrogate PK
```

**Schema baru:**
```sql
pengajar_kelas_id UUID PRIMARY KEY DEFAULT gen_random_uuid()  -- surrogate UUID
kelas_id          UUID NOT NULL REFERENCES kelas
dosen_id          UUID NOT NULL REFERENCES dosen
weight            SMALLINT NOT NULL DEFAULT 100 CHECK (weight BETWEEN 0 AND 100)
is_utama          BOOLEAN NOT NULL DEFAULT TRUE  -- dari kolom 'utama' di pengajar.csv
UNIQUE (kelas_id, dosen_id)  -- natural uniqueness tetap dijaga
```

Perubahan:
- Nama tabel: `pengajar` → `pengajar_kelas` (lebih eksplisit sebagai junction table)
- PK dari composite → surrogate UUID. Alasan: konsistensi dengan semua tabel lain
  yang menggunakan UUID PK
- Ditambah `weight` dan `is_utama` sesuai kolom yang ada di `pengajar.csv`

---

## BAGIAN 4 — Perubahan Tabel Assessment & Skor

### 4.1 Statistik Kelas Dipisah → Tabel `statistik_kelas` (Baru)

**Schema lama:** Statistik ada langsung di tabel `kelas` (lihat 3.1).

**Schema baru:** Tabel terpisah `statistik_kelas` dengan shared PK (PK = FK ke kelas_id).

```sql
CREATE TABLE statistik_kelas (
    kelas_id        UUID PRIMARY KEY REFERENCES kelas(kelas_id)  -- 1:1 dengan kelas
    hadir_mhs       NUMERIC(5,2)
    hadir_dosen     NUMERIC(5,2)   -- nullable, tidak ada di CSV
    ip_mhs          NUMERIC(4,2)
    jumlah_mahasiswa SMALLINT
    skor_dna        SMALLINT
    ts_dna_raw      TEXT           -- nilai ts_dna as-is dari CSV
    ts_dna          TIMESTAMPTZ    -- hasil parse (nullable sampai format dikonfirmasi)
    ip_mhs_dna      NUMERIC(4,2)
    ...
);
```

Kolom `ts_dna` disimpan dua kali (`ts_dna_raw TEXT` dan `ts_dna TIMESTAMPTZ`) karena
format timestamp dari SIX ITB belum terkonfirmasi. `ts_dna_raw` menyimpan nilai asli
untuk traceability, `ts_dna` diisi setelah format dikonfirmasi dan bisa dipakai untuk
filter periode di dashboard.

---

### 4.2 Tabel `distribusi_nilai`: Tidak Berubah Signifikan

Tabel ini sudah benar di schema lama (row-based, satu baris per grade). Hanya
penambahan index langsung di bawah tabel dan penyesuaian kecil di komentar.

---

### 4.3 Tabel Baru: `nilai_dosen`

**Tidak ada di schema lama.** Schema lama tidak memodelkan nilai akhir per dosen.

```sql
CREATE TABLE nilai_dosen (
    nilai_dosen_id UUID PRIMARY KEY
    kelas_id       UUID NOT NULL REFERENCES kelas
    dosen_id       UUID NOT NULL REFERENCES dosen
    nilai_akhir    NUMERIC(6,4)  -- dari kolom nilai_akhir di nilai_dosen.csv
    UNIQUE (kelas_id, dosen_id)
);
```

`nilai_akhir` adalah skor komposit per dosen per kelas dari SIX ITB (range 2.016–4.000
berdasarkan data aktual). Data ini bersifat **privat** — dosen tidak boleh melihat
nilai akhir dosen lain (RLS ketat).

---

### 4.4 Tabel `skor_kuesioner` → Dipecah Menjadi Tiga Tabel

Ini adalah perubahan terbesar pada domain kuesioner.

**Schema lama:**
```sql
CREATE TABLE skor_kuesioner (
    skor_id       UUID PRIMARY KEY
    kelas_id      UUID NOT NULL REFERENCES kelas
    no_pertanyaan SMALLINT NOT NULL CHECK (no_pertanyaan BETWEEN 1 AND 12)
    -- Q1-Q3  → capaian, Q4-Q8 → pelaksanaan, Q9-Q10 → sarana, Q11-Q12 → perilaku
    rata_skor     NUMERIC(4,2) NOT NULL
);
```

**Masalah yang ditemukan dari EDA:**
1. Nomor pertanyaan bukan Q1–Q12 tapi Q21–Q37, Q103, dll. (dari `pertanyaan_kuesioner.csv`)
2. Q25, Q26, Q27 terbukti berbeda nilainya per dosen dalam satu kelas team-teaching
   (terverifikasi dari data, bukan asumsi)
3. Schema lama tidak memodelkan nilai per dosen sama sekali

**Schema baru — tiga tabel terpisah:**

```sql
-- Tabel 1: Skor level kelas (sama untuk semua dosen dalam kelas)
-- Pertanyaan: Q21, Q22, Q23, Q24, Q28, Q29, Q30, Q35, Q37
CREATE TABLE skor_kuesioner_kelas (
    skor_kelas_id           UUID PRIMARY KEY
    kelas_id                UUID NOT NULL REFERENCES kelas
    pertanyaan_kuesioner_id UUID NOT NULL REFERENCES pertanyaan_kuesioner
    skor                    NUMERIC(5,4) NOT NULL CHECK (skor BETWEEN 1 AND 4)
    UNIQUE (kelas_id, pertanyaan_kuesioner_id)
);

-- Tabel 2: Skor per dosen (berbeda per dosen dalam team-teaching)
-- Pertanyaan: Q25, Q26, Q27 (terbukti dari data)
CREATE TABLE skor_kuesioner_dosen (
    skor_dosen_id           UUID PRIMARY KEY
    kelas_id                UUID NOT NULL REFERENCES kelas
    dosen_id                UUID NOT NULL REFERENCES dosen  -- kunci perbedaannya
    pertanyaan_kuesioner_id UUID NOT NULL REFERENCES pertanyaan_kuesioner
    skor                    NUMERIC(5,4) NOT NULL
    UNIQUE (kelas_id, dosen_id, pertanyaan_kuesioner_id)
);

-- Tabel 3: Skor dimensi agregat per dosen (key 1, 2, 3 dari nilai_dosen.csv)
CREATE TABLE skor_dimensi_dosen (
    skor_dimensi_id UUID PRIMARY KEY
    kelas_id        UUID NOT NULL REFERENCES kelas
    dosen_id        UUID NOT NULL REFERENCES dosen
    dimensi_key     SMALLINT NOT NULL CHECK (dimensi_key IN (1, 2, 3))
    -- key 1 = avg(Q21,22,23), key 2 = avg(Q24,25,26,27,28), key 3 = avg(Q35,37)
    -- TERVERIFIKASI 100% pada 1.960 baris nilai_dosen.csv
    dimensi_nama    VARCHAR(60)   -- nullable: label resmi belum dikonfirmasi SIX ITB
    skor            NUMERIC(5,4) NOT NULL
    UNIQUE (kelas_id, dosen_id, dimensi_key)
);
```

**Pembuktian dari data** (cross-check `nilai_kelas.csv` × `nilai_dosen.csv`):
```
kelas team-teaching (2 dosen):
  dosen_A: Q25=3.84, key2=3.775
  dosen_B: Q25=3.76, key2=3.748
  → key2 berbeda karena Q25,26,27 berbeda per dosen
  → key1 identik (Q21,22,23 = level kelas)
```

---

### 4.5 Tabel `teks_portofolio`: Perubahan Cara Identifikasi Konten

**Schema lama:**
```sql
CREATE TABLE teks_portofolio (
    teks_id     UUID PRIMARY KEY
    kelas_id    UUID NOT NULL REFERENCES kelas
    tipe_konten tipe_konten_enum NOT NULL  -- enum untuk identifikasi jenis teks
    konten      TEXT
    is_embedded BOOLEAN NOT NULL DEFAULT FALSE
    embedded_at TIMESTAMPTZ
);
```

**Schema baru:**
```sql
CREATE TABLE teks_portofolio (
    teks_portofolio_id       UUID PRIMARY KEY
    kelas_id                 UUID NOT NULL REFERENCES kelas
    pertanyaan_portofolio_id UUID NOT NULL REFERENCES pertanyaan_portofolio  -- FK, bukan enum
    teks_raw                 TEXT      -- rename dari 'konten', simpan as-is dari CSV
    teks_bersih              TEXT GENERATED ALWAYS AS (  -- HTML strip via regex
        regexp_replace(COALESCE(teks_raw, ''), E'<[^>]*>', '', 'g')
    ) STORED
    is_embedded BOOLEAN NOT NULL DEFAULT FALSE
    embedded_at TIMESTAMPTZ
);
```

Perubahan kunci:
- **`tipe_konten enum` → FK ke `pertanyaan_portofolio`**: lebih scalable. Jika ada
  pertanyaan baru, tidak perlu `ALTER TYPE` — cukup insert baris di tabel master
- **`konten TEXT` → `teks_raw TEXT` + `teks_bersih TEXT GENERATED`**: data CSV dari
  SIX ITB mengandung HTML tags (`<p>`, `<br>`, `&nbsp;`). `teks_raw` menyimpan konten
  asli as-is; `teks_bersih` adalah generated column yang strip HTML via regex,
  digunakan untuk full-text search dan input pipeline embedding

Ditambah index FTS:
```sql
CREATE INDEX idx_tp_fts ON teks_portofolio
    USING GIN (to_tsvector('indonesian', COALESCE(teks_bersih, '')));
```

---

### 4.6 Tabel `komentar_mahasiswa`: Perubahan Identifikasi + HTML Strip

**Schema lama:**
```sql
CREATE TABLE komentar_mahasiswa (
    komentar_id   UUID PRIMARY KEY
    kelas_id      UUID NOT NULL REFERENCES kelas
    no_komentar   SMALLINT NOT NULL   -- urutan komentar di dalam kelas
    teks_komentar TEXT NOT NULL
    is_embedded   BOOLEAN NOT NULL DEFAULT FALSE
    embedded_at   TIMESTAMPTZ
);
```

**Schema baru:**
```sql
CREATE TABLE komentar_mahasiswa (
    komentar_mahasiswa_id   UUID PRIMARY KEY
    kelas_id                UUID NOT NULL REFERENCES kelas
    pertanyaan_kuesioner_id UUID NOT NULL REFERENCES pertanyaan_kuesioner  -- FK ke Q103
    komentar_raw            TEXT
    komentar_bersih         TEXT GENERATED ALWAYS AS (
        regexp_replace(COALESCE(komentar_raw, ''), E'<[^>]*>', '', 'g')
    ) STORED
    is_embedded BOOLEAN NOT NULL DEFAULT FALSE
    embedded_at TIMESTAMPTZ
    UNIQUE (kelas_id, pertanyaan_kuesioner_id)
);
```

Perubahan kunci:
- `no_komentar SMALLINT` → FK ke `pertanyaan_kuesioner` (Q103 = pertanyaan saran mahasiswa).
  Lebih eksplisit daripada urutan angka.
- Tambah `komentar_bersih` generated column untuk HTML stripping, sama seperti
  `teks_portofolio`

---

### 4.7 Tabel Baru: `komentar_verifikator`

**Tidak ada di schema lama.**

Ditemukan dari EDA `portofolio.csv`: kolom `komentar` berisi JSON
`{kd_grup: teks}`. Ini adalah komentar dari verifikator portofolio, berbeda dari
komentar mahasiswa.

```sql
CREATE TABLE komentar_verifikator (
    komentar_verifikator_id UUID PRIMARY KEY
    kelas_id                UUID NOT NULL REFERENCES kelas
    pertanyaan_grup_id      UUID NOT NULL REFERENCES pertanyaan_grup_portofolio
    komentar_raw            TEXT
    komentar_bersih         TEXT GENERATED ALWAYS AS (
        regexp_replace(COALESCE(komentar_raw, ''), E'<[^>]*>', '', 'g')
    ) STORED
    UNIQUE (kelas_id, pertanyaan_grup_id)
);
```

---

## BAGIAN 5 — Tabel Auth & Session (Pindah ke schema_auth_session.sql)

### 5.1 Tabel `pengguna`: Refactor Besar

**Schema lama:**
```sql
CREATE TABLE pengguna (
    user_id      UUID PRIMARY KEY
    username     VARCHAR(100) UNIQUE NOT NULL
    email        VARCHAR(200) UNIQUE NOT NULL
    nama_lengkap VARCHAR(200) NOT NULL
    role         user_role_enum NOT NULL  -- single role per user
    is_active    BOOLEAN NOT NULL DEFAULT TRUE
    last_login   TIMESTAMPTZ
);
```

**Schema baru:**
```sql
CREATE TABLE pengguna (
    pengguna_id   UUID PRIMARY KEY        -- rename dari user_id
    email         VARCHAR(320) UNIQUE NOT NULL
    nama_lengkap  VARCHAR(300)
    metode_auth   metode_auth NOT NULL DEFAULT 'sso_microsoft'
    password_hash VARCHAR(255)            -- nullable untuk SSO, wajib untuk password
    is_active     BOOLEAN NOT NULL DEFAULT TRUE
    last_login    TIMESTAMPTZ
);
```

Perubahan kunci:
- Dihapus `username` — login ITB berbasis email
- Dihapus `role` langsung dari tabel `pengguna` — dipindah ke tabel terpisah
  `pengguna_peran` untuk mendukung multi-role
- Ditambah `metode_auth` (sso_microsoft / password) dan `password_hash`
- `pengguna_id` menggantikan `user_id` (konsistensi penamaan Bahasa Indonesia)

---

### 5.2 Tabel `user_scope` → Diganti `pengguna_peran`

**Schema lama:** Satu tabel `user_scope` per user (UNIQUE user_id → hanya satu scope).

**Schema baru:** Tabel `pengguna_peran` — satu user bisa punya **banyak baris** (multi-role).

```sql
CREATE TABLE pengguna_peran (
    id            UUID PRIMARY KEY
    pengguna_id   UUID NOT NULL REFERENCES pengguna
    kode_peran    user_role_enum NOT NULL
    fakultas_id   UUID REFERENCES fakultas   -- untuk dekan/jajaran_dekanat
    prodi_id      UUID REFERENCES program_studi  -- untuk kaprodi/jajaran_prodi/dosen
    dosen_ref_id  UUID REFERENCES dosen      -- wajib untuk kode_peran='dosen'
    is_active     BOOLEAN NOT NULL DEFAULT TRUE
    created_by    UUID REFERENCES pengguna
    CONSTRAINT chk_peran_scope CHECK (...)   -- validasi scope sesuai peran
    CONSTRAINT chk_dosen_ref  CHECK (...)    -- dosen wajib ada dosen_ref_id
);
```

Perubahan kunci:
- Mendukung multi-role: satu pengguna bisa jadi kaprodi di prodi A sekaligus dosen di prodi B
- Scope (prodi/fakultas) divalidasi berdasarkan `kode_peran` via CHECK constraint
- `dosen_ref_id` menghubungkan akun pengguna ke entitas dosen di tabel `dosen`
- `kk_id` dihilangkan — scope KK tidak digunakan dalam aplikasi ini

---

### 5.3 Tabel Baru: `sessions`

**Tidak ada di schema lama.** Sistem session-based auth membutuhkan tabel penyimpan session.

```sql
CREATE TABLE sessions (
    id                  BIGSERIAL PRIMARY KEY  -- bukan UUID, lebih efisien untuk tulis
    session_token_hash  BYTEA NOT NULL UNIQUE  -- hash SHA-256 dari token asli
    user_id             UUID NOT NULL REFERENCES pengguna ON DELETE CASCADE
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    expires_at          TIMESTAMPTZ NOT NULL
);
```

Token asli disimpan di cookie HttpOnly sisi client, tidak pernah disimpan di database.
Yang disimpan hanya hash-nya untuk keamanan.

---

### 5.4 Tabel `ingestion_log` → Diganti Dua Tabel: `ingestion_batch` + `ingestion_file_log`

**Schema lama:**
```sql
CREATE TABLE ingestion_log (
    log_id        UUID PRIMARY KEY
    kelas_id      UUID REFERENCES kelas   -- hanya track satu kelas
    sumber_file   VARCHAR(500) NOT NULL
    status        VARCHAR(20) CHECK (status IN ('success','partial','failed','skipped'))
    rows_inserted JSONB
    error_message TEXT
    started_at    TIMESTAMPTZ
    finished_at   TIMESTAMPTZ
);
```

**Schema baru — dua tabel:**

```sql
-- Tabel 1: Satu sesi upload (bisa multi-file)
CREATE TABLE ingestion_batch (
    batch_id     UUID PRIMARY KEY
    user_id      UUID NOT NULL REFERENCES pengguna  -- siapa yang upload
    notes        TEXT
    status       status_ingestion NOT NULL DEFAULT 'pending'
    total_file   SMALLINT NOT NULL DEFAULT 0
    success_file SMALLINT NOT NULL DEFAULT 0
    failed_file  SMALLINT NOT NULL DEFAULT 0
    started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    finished_at  TIMESTAMPTZ
);

-- Tabel 2: Log per file dalam satu batch
CREATE TABLE ingestion_file_log (
    log_id          UUID PRIMARY KEY
    batch_id        UUID NOT NULL REFERENCES ingestion_batch
    jenis_file      jenis_file_porto NOT NULL  -- enum 10 jenis file CSV
    original_filename VARCHAR(500) NOT NULL
    tahun_ajaran    VARCHAR(9)
    semester        SMALLINT
    status          status_ingestion NOT NULL DEFAULT 'pending'
    total_row       INTEGER NOT NULL DEFAULT 0
    processed_row   INTEGER NOT NULL DEFAULT 0  -- new + updated + skipped
    new_row         INTEGER NOT NULL DEFAULT 0
    updated_row     INTEGER NOT NULL DEFAULT 0
    skipped_row     INTEGER NOT NULL DEFAULT 0
    failed_row      INTEGER NOT NULL DEFAULT 0
    error_detail    JSONB    -- detail error per baris [{baris, pesan, data}]
    notes           TEXT
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    finished_at     TIMESTAMPTZ
    CONSTRAINT chk_processed_row_konsisten CHECK (
        processed_row = new_row + updated_row + skipped_row
        OR processed_row = 0
    )
);
```

Perubahan kunci:
- Satu batch bisa track banyak file (1:N batch → file_log)
- Statistik per file lebih detail: `new_row`, `updated_row`, `skipped_row`, `failed_row`
- `error_detail JSONB` per baris (bukan satu string `error_message`)
- Menggunakan `status_ingestion` enum: `pending | processing | success | partial | failed`
- Istilah `upload` diganti `ingestion` di semua nama tabel dan kolom

---

## BAGIAN 6 — Perubahan RLS

### Schema Lama: RLS Berbasis Tabel `user_scope` + Fungsi `user_can_see_kelas()`

```sql
-- Schema lama: policy besar dengan banyak EXISTS subquery
CREATE POLICY rls_kelas_all_roles ON kelas FOR SELECT USING (
    EXISTS (SELECT 1 FROM pengguna p WHERE p.user_id = ... AND p.role IN ('admin','wram'))
    OR EXISTS (SELECT 1 FROM pengajar_kelas pk JOIN user_scope us ...)
    OR EXISTS (SELECT 1 FROM mata_kuliah mk JOIN user_scope us ...)
    OR EXISTS (SELECT 1 FROM mata_kuliah mk JOIN program_studi ps JOIN user_scope us ...)
);
```

### Schema Baru: RLS Berbasis Session Variables + Helper Functions

```sql
-- Backend set sebelum setiap query:
SET LOCAL app.role        = 'kaprodi';
SET LOCAL app.prodi_id    = '<UUID>';
SET LOCAL app.dosen_id    = '<UUID>';
SET LOCAL app.fakultas_id = '<UUID>';

-- Helper functions kecil dan fokus:
CREATE FUNCTION fn_is_global_reader() ...   -- admin, direktorat
CREATE FUNCTION fn_is_dekanat_scope() ...   -- dekan, jajaran_dekanat, filter by fakultas
CREATE FUNCTION fn_is_prodi_scope() ...     -- kaprodi, jajaran_prodi, dosen
CREATE FUNCTION fn_is_own_dosen() ...       -- hanya untuk dosen, filter by dosen_id
```

**Perubahan RLS untuk `kelas` dan `pengajar_kelas`:**

Schema lama membatasi akses `kelas` hanya untuk user yang relevan.
Schema baru membuat `kelas` dan `pengajar_kelas` **terbuka untuk semua pengguna**:

```sql
CREATE POLICY pol_kelas_open ON kelas FOR SELECT USING (true);
CREATE POLICY pol_pengajar_kelas_open ON pengajar_kelas FOR SELECT USING (true);
```

Alasan: Metadata kelas (MK apa, semester berapa, dosen siapa) bukan data sensitif.
Yang sensitif adalah data assessment (skor kuesioner dosen, nilai akhir) — itulah
yang diproteksi ketat. Dekan STEI yang ingin tahu berapa kelas yang berjalan di FTTM
tetap bisa mendapat jawaban dari chatbot.

**Tabel yang tetap diproteksi ketat (dosen hanya bisa akses data sendiri):**
- `nilai_dosen` — nilai akhir komposit per dosen
- `skor_kuesioner_dosen` — skor Q25/26/27 per dosen
- `skor_dimensi_dosen` — skor dimensi per dosen

---

## BAGIAN 7 — Tabel yang Dihapus

| Tabel | Alasan Dihapus |
|---|---|
| `user_scope` | Digantikan `pengguna_peran` yang lebih fleksibel (multi-role) |
| `ingestion_log` | Digantikan `ingestion_batch` + `ingestion_file_log` |
| `skor_kuesioner` (lama) | Digantikan tiga tabel baru yang mencerminkan struktur data aktual |

---

## BAGIAN 8 — Ringkasan Seluruh Tabel

### schema_portofolio_kuesioner.sql (21 tabel)

| Kelompok | Tabel | Status vs Schema Lama |
|---|---|---|
| Referensi | `fakultas` | Dipertahankan, minor update |
| Referensi | `kelompok_keahlian` | Dipertahankan, FK jadi nullable |
| Referensi | `program_studi` | Dipertahankan, FK jadi nullable |
| Referensi | `dosen` | Dipertahankan, tambah `six_dosen_id` |
| Referensi | `mata_kuliah` | Refactor besar, tambah `six_matkul_id` + `th_kur`, hapus `nama_mk_en` |
| Referensi | `pertanyaan_kuesioner` | **BARU** |
| Referensi | `pertanyaan_grup_portofolio` | **BARU** |
| Referensi | `pertanyaan_portofolio` | **BARU** |
| Core | `kelas` | Refactor besar, tambah `six_kelas_id` + `prodi_id` + `no_ps`, hapus statistik |
| Core | `pengajar_kelas` | Rename dari `pengajar`, ganti composite PK → UUID PK |
| Assessment | `statistik_kelas` | **BARU** (pisah dari `kelas`) |
| Assessment | `distribusi_nilai` | Dipertahankan |
| Assessment | `nilai_dosen` | **BARU** |
| Kuesioner | `skor_kuesioner_kelas` | **BARU** (refactor dari `skor_kuesioner`) |
| Kuesioner | `skor_kuesioner_dosen` | **BARU** |
| Kuesioner | `skor_dimensi_dosen` | **BARU** |
| Portofolio | `teks_portofolio` | Refactor, ganti enum → FK, tambah HTML strip |
| Portofolio | `komentar_verifikator` | **BARU** |
| Portofolio | `komentar_mahasiswa` | Refactor, ganti `no_komentar` → FK pertanyaan |
| AI | `vector_chunks` | Dipertahankan, minor update tipe kolom |
| AI | `llm_analysis_cache` | Dipertahankan |

### schema_auth_session.sql (5 tabel + 4 enum)

| Tabel | Status vs Schema Lama |
|---|---|
| `pengguna` | Refactor, hapus `username` + `role`, tambah `metode_auth` |
| `pengguna_peran` | **BARU** (menggantikan `user_scope`, mendukung multi-role) |
| `sessions` | **BARU** |
| `ingestion_batch` | **BARU** (menggantikan `ingestion_log`) |
| `ingestion_file_log` | **BARU** |

---

## SUMBER PERUBAHAN

Seluruh perubahan berasal dari hasil EDA pada 10 file CSV SIX ITB:

| File CSV | Temuan Utama |
|---|---|
| `dosen.csv` | Integer `dosen_id`, tidak ada info KK/prodi per dosen |
| `mata_kuliah.csv` | `sks` ada di sini (bukan di kelas), ada kolom `th_kur`, prefix kd_kuliah FI/TK/WI |
| `kelas.csv` | Kolom `tahun` integer (bukan string tahun ajaran), `no_kelas` integer, ada `no_ps` |
| `pengajar.csv` | Ada kolom `weight` dan `utama` |
| `nilai_kelas.csv` | JSON kuesioner hanya berisi Q21,22,23,24,28,29,30,35,37 |
| `nilai_dosen.csv` | JSON kuesioner berisi Q21-30,35,37; JSON skor_kues berisi key 1,2,3 |
| `portofolio.csv` | JSON `isian` berisi kd_pertanyaan 12-19; JSON `komentar` berisi kd_grup 6-9 |
| `pertanyaan_kuesioner.csv` | 36 pertanyaan dengan kode Q21-Q152, bukan Q1-Q12 |
| `pertanyaan_portofolio.csv` | 19 pertanyaan, dua format (kd 1-11 lama, 12-19 baru) |
| `pertanyaan_grup_portofolio.csv` | 9 grup, dua format (kd_grup 1-5 lama, 6-9 baru) |

**Verifikasi kritis dari data (bukan asumsi):**
- Q25, Q26, Q27 berbeda nilainya per dosen dalam team-teaching → dibuktikan dari
  cross-tabulation data kelas dengan lebih dari 1 dosen
- Key 1 = avg(Q21,22,23), Key 2 = avg(Q24,25,26,27,28), Key 3 = avg(Q35,37) →
  dibuktikan 100% match pada 1.960 baris `nilai_dosen.csv`