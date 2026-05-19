-- ================================================================
-- SCHEMA : Auth, Session & Ingestion Management
-- Urutan : Jalankan SETELAH schema_portofolio_kuesioner.sql
--          (tabel pengguna_peran mereference fakultas, program_studi, dosen yang didefinisikan di file sebelumnya)
-- ================================================================
--
-- CATATAN DESAIN:
--
-- Login: SSO Microsoft ITB (mayoritas pengguna) + email/password (hanya admin). metode_auth membedakan keduanya.
--
-- Session-based auth: session_token_hash di tabel sessions.
--         Token hash (bukan token asli) disimpan di DB untuk keamanan.
--         Token asli hanya ada di cookie HttpOnly sisi client.
--
-- Multi-role: satu pengguna bisa punya lebih dari satu peran
--         di scope yang berbeda (e.g. kaprodi Fisika + dosen Teknik Kimia).
--
-- Mapping pengguna → peran dilakukan MANUAL oleh admin via menu Manajemen Akun. Tidak ada auto-provisioning dari SSO.
--
-- Ingestion (upload CSV) hanya bisa dilakukan oleh admin.
--         ingestion_batch = satu sesi upload (bisa multi-file).
--         ingestion_file_log = log per file dalam satu batch.
--
-- DEPENDENCY:
--   fn_auto_updated_at() → didefinisikan di schema_portofolio_kuesioner.sql
--   fakultas, program_studi, dosen → dari schema_portofolio_kuesioner.sql
-- ================================================================


-- ============================================================
-- SECTION 1 — ENUM TYPES (Auth & Ingestion Domain)
-- ============================================================

-- Level akses pengguna dalam aplikasi.
-- Sesuai enum schema lama (tidak ada enum user_role_enum baru).
CREATE TYPE user_role_enum AS ENUM (
    'admin',            -- Full access: kelola akun, ingestion, semua data
    'direktorat',       -- Direktorat/WRAM: read-all (scope seluruh ITB)
    'dekan',            -- Dekan: read scope seluruh fakultasnya
    'jajaran_dekanat',  -- Wakil dekan / staf dekanat: read scope seluruh fakultas
    'kaprodi',          -- Kepala prodi: read scope seluruh prodinya (nama dosen terlihat)
    'jajaran_prodi',    -- Sekretaris/staf prodi: read scope seluruh prodi
    'dosen'             -- Pengajar: hanya akses kelas sendiri, KECUALI data privat dosen lain
);

-- Metode autentikasi pengguna.
CREATE TYPE metode_auth AS ENUM (
    'sso_microsoft',    -- Login via SSO Microsoft ITB (mayoritas pengguna)
    'password'          -- Login via email + password (hanya admin)
);

-- Jenis file CSV yang dapat diunggah untuk domain portofolio & kuesioner.
-- Digunakan di kolom jenis_file pada ingestion_file_log.
-- Untuk domain wisudawan: ALTER TYPE jenis_file_porto ADD VALUE 'wisudawan_...'
CREATE TYPE jenis_file_porto AS ENUM (
    'dosen',
    'kelas',
    'mata_kuliah',
    'pengajar',
    'pertanyaan_grup_portofolio',
    'pertanyaan_portofolio',
    'pertanyaan_kuesioner',
    'nilai_kelas',
    'nilai_dosen',
    'portofolio'
);

-- Status proses ingestion file CSV.
CREATE TYPE status_ingestion AS ENUM (
    'pending',      -- File diterima, belum mulai diproses
    'processing',   -- Sedang diproses
    'success',      -- Semua baris berhasil diproses
    'partial',      -- Sebagian baris berhasil, sebagian gagal
    'failed'        -- Gagal total (error sebelum/saat proses)
);


-- ============================================================
-- SECTION 2 — USER & ACCESS MANAGEMENT TABLES
-- ============================================================

-- ── 2.1 Pengguna ─────────────────────────────────────────────────────────────
-- Semua pengguna aplikasi (admin, direktorat, dekan, kaprodi, dosen).
-- SSO Microsoft: kolom password_hash = NULL.
-- Login admin via password: password_hash wajib diisi (CHECK constraint).

CREATE TABLE pengguna (
    pengguna_id     UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(320)  UNIQUE NOT NULL,
    -- Untuk SSO: email ITB (format: nip@itb.ac.id atau nama@itb.ac.id).
    -- Untuk admin password: email yang digunakan sebagai username login.
    
    nama_lengkap    VARCHAR(300),
    metode_auth     metode_auth   NOT NULL DEFAULT 'sso_microsoft',

    password_hash   VARCHAR(255),
    -- NULL untuk pengguna SSO. Wajib diisi untuk pengguna metode_auth='password'.

    is_active       BOOLEAN       NOT NULL DEFAULT TRUE,
    -- FALSE = akun dinonaktifkan (tidak bisa login). Tidak dihapus permanen.
    
    last_login      TIMESTAMPTZ,
    -- NULL jika belum pernah login. Diupdate setiap kali login berhasil.
    
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_password_required CHECK (
        metode_auth <> 'password' OR password_hash IS NOT NULL
    )
);

CREATE INDEX idx_pengguna_email     ON pengguna (email);
-- idx_pengguna_email: lookup saat login — setiap request autentikasi.
CREATE INDEX idx_pengguna_is_active ON pengguna (is_active) WHERE is_active = TRUE;
-- Partial index: hanya akun aktif. Dipakai filter di halaman manajemen akun.

COMMENT ON TABLE  pengguna IS 'Semua pengguna aplikasi. SSO Microsoft = password_hash NULL. Admin password = password_hash wajib ada. last_login diupdate tiap login berhasil.';
COMMENT ON COLUMN pengguna.email IS 'Email ITB untuk SSO, atau email username untuk login password (admin). UNIQUE.';
COMMENT ON COLUMN pengguna.password_hash IS 'NULL untuk pengguna SSO. Wajib ada untuk metode_auth=password. Gunakan bcrypt/argon2. Jangan simpan plaintext.';
COMMENT ON COLUMN pengguna.last_login IS 'Timestamp login terakhir berhasil. NULL jika belum pernah login.';


-- ── 2.2 Peran Pengguna ───────────────────────────────────────────────────────
-- Multi-role: satu pengguna bisa punya lebih dari satu baris (satu per peran). 

-- Scope peran ditentukan oleh kombinasi kode_peran + fakultas_id/prodi_id:
--   admin, direktorat → fakultas_id NULL, prodi_id NULL (scope global)
--   dekan, jajaran_dekanat → fakultas_id wajib, prodi_id NULL
--   kaprodi, jajaran_prodi → prodi_id wajib, fakultas_id NULL (atau diisi untuk reference)
--   dosen → prodi_id wajib (scope prodi), dosen_ref_id wajib

-- Mapping dilakukan manual oleh admin. 
CREATE TABLE pengguna_peran (
    id              UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    pengguna_id     UUID           NOT NULL REFERENCES pengguna(pengguna_id) ON DELETE CASCADE,
    kode_peran      user_role_enum NOT NULL,
    fakultas_id     UUID           REFERENCES fakultas(fakultas_id) ON DELETE SET NULL,
    -- Wajib diisi untuk peran dekan/jajaran_dekanat.
    -- NULL untuk admin, direktorat (scope global).

    prodi_id        UUID           REFERENCES program_studi(prodi_id) ON DELETE SET NULL,
    -- Wajib diisi untuk peran kaprodi/jajaran_prodi/dosen.
    -- NULL untuk admin, direktorat, dekan (scope lebih luas).

    dosen_ref_id    UUID           REFERENCES dosen(dosen_id) ON DELETE SET NULL,
    -- Referensi ke entitas dosen (tabel dosen). Wajib diisi untuk peran 'dosen'.
    -- NULL untuk semua peran non-dosen.
    -- Digunakan RLS: fn_is_own_dosen() membandingkan app.dosen_id dengan dosen_id di nilai_dosen.

    is_active       BOOLEAN        NOT NULL DEFAULT TRUE,
    -- FALSE = peran ini dinonaktifkan sementara tanpa menghapus baris.

    created_by      UUID           REFERENCES pengguna(pengguna_id) ON DELETE SET NULL,
    -- UUID admin yang membuat/assign peran ini. NULL jika sistem yang membuat.

    created_at      TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ    NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_peran_scope CHECK (
        -- Admin & direktorat: tidak perlu scope spesifik
        (kode_peran IN ('admin', 'direktorat'))
        -- Dekanat: wajib ada fakultas_id
        OR (kode_peran IN ('dekan', 'jajaran_dekanat') AND fakultas_id IS NOT NULL)
        -- Prodi & dosen: wajib ada prodi_id
        OR (kode_peran IN ('kaprodi', 'jajaran_prodi', 'dosen') AND prodi_id IS NOT NULL)
    ),
    CONSTRAINT chk_dosen_ref CHECK (
        -- Peran dosen wajib punya dosen_ref_id
        kode_peran <> 'dosen' OR dosen_ref_id IS NOT NULL
    )
);

CREATE INDEX idx_pp_pengguna ON pengguna_peran (pengguna_id, is_active);
-- idx_pp_pengguna: resolve peran aktif pengguna di awal setiap request.
-- Dipakai backend untuk set session variables (app.role, app.prodi_id, dll.).

CREATE INDEX idx_pp_dosen_ref ON pengguna_peran (dosen_ref_id);
-- idx_pp_dosen_ref: lookup "akun mana yang terhubung ke dosen X?" saat setup akun dosen.

COMMENT ON TABLE  pengguna_peran IS 'Mapping pengguna → peran, multi-role (1 pengguna bisa punya beberapa baris). Dilakukan manual admin. Scope ditentukan oleh kombinasi kode_peran + fakultas_id/prodi_id/dosen_ref_id.';
COMMENT ON COLUMN pengguna_peran.dosen_ref_id IS 'FK ke dosen. Wajib untuk kode_peran=dosen. Digunakan RLS: backend set app.dosen_id dari kolom ini untuk filter data privat dosen.';
COMMENT ON COLUMN pengguna_peran.created_by IS 'Admin yang assign peran. NULL jika dibuat sistem (seed awal).';


-- ============================================================
-- SECTION 3 — SESSION STORE
-- ============================================================

-- ── 3.1 Sessions (Session-Based Auth) ────────────────────────────────────────
-- Tabel session store untuk autentikasi berbasis session. [AUTH2]
-- session_token_hash = hash dari token asli (token asli di cookie client).
-- Lookup saat setiap request: WHERE session_token_hash = $hash AND expires_at > NOW().
-- id menggunakan BIGSERIAL (bukan UUID) untuk performa tinggi pada tabel
-- yang sangat sering di-write (setiap login = INSERT, setiap logout = DELETE).
CREATE TABLE sessions (
    id                  BIGSERIAL   PRIMARY KEY,
    session_token_hash  BYTEA       NOT NULL UNIQUE,
    user_id             UUID        NOT NULL REFERENCES pengguna(pengguna_id) ON DELETE CASCADE,
    -- ON DELETE CASCADE: jika pengguna dihapus, semua sesinya ikut terhapus.

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ NOT NULL
    -- Setiap request: CHECK expires_at > NOW(). Sesi expired = login ulang.
);

CREATE INDEX idx_sessions_user_expires ON sessions (user_id, expires_at);
CREATE INDEX idx_sessions_expires      ON sessions (expires_at);

COMMENT ON TABLE  sessions IS 'Session store untuk session-based auth. session_token_hash = SHA-256(token asli). Token asli hanya ada di cookie HttpOnly sisi client, tidak pernah disimpan di DB.';
COMMENT ON COLUMN sessions.session_token_hash IS 'BYTEA bukan VARCHAR: hash biner lebih efisien untuk lookup equality dan tidak ada risiko encoding issue.';
COMMENT ON COLUMN sessions.expires_at IS 'Expiry session. Backend HARUS cek expires_at > NOW() setiap request. Job cleanup periodik: DELETE WHERE expires_at < NOW().';


-- ============================================================
-- SECTION 4 — INGESTION MANAGEMENT TABLES
-- ============================================================
-- Ingestion = proses upload dan pemrosesan file CSV oleh admin.
-- Hierarki: ingestion_batch (1 sesi upload) → ingestion_file_log (1 baris per file).
-- Hanya admin yang bisa melakukan ingestion.

-- ── 4.1 Ingestion Batch ──────────────────────────────────────────────────────
-- Satu batch = satu sesi upload yang bisa berisi beberapa file sekaligus.
-- Contoh: admin upload nilai_kelas.csv + nilai_dosen.csv + portofolio.csv
--         dalam satu sesi = satu batch.

CREATE TABLE ingestion_batch (
    batch_id        UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID             NOT NULL REFERENCES pengguna(pengguna_id) ON DELETE RESTRICT,
    -- Admin yang melakukan ingestion. RESTRICT: jangan hapus pengguna jika ada batch untuk audit log.

    notes           TEXT,
    -- Catatan admin tentang batch ini, e.g. "Import data semester ganjil 2024".

    status          status_ingestion NOT NULL DEFAULT 'pending',
    total_file      SMALLINT         NOT NULL DEFAULT 0,
    -- Jumlah file dalam batch ini.

    success_file    SMALLINT         NOT NULL DEFAULT 0,
    -- File yang berhasil diproses (status=success atau partial).

    failed_file     SMALLINT         NOT NULL DEFAULT 0,
    -- File yang gagal diproses (status=failed).

    started_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    -- Waktu batch mulai diproses.

    finished_at     TIMESTAMPTZ,
    -- NULL selama batch masih berjalan atau pending. Diisi saat semua file selesai.

    created_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ib_user_id    ON ingestion_batch (user_id);
CREATE INDEX idx_ib_status     ON ingestion_batch (status);
CREATE INDEX idx_ib_started_at ON ingestion_batch (started_at DESC);
-- idx_ib_started_at: tampilkan riwayat batch terbaru di halaman manajemen ingestion.

COMMENT ON TABLE  ingestion_batch IS 'Satu sesi ingestion (bisa multi-file). Dibuat admin. ingestion_file_log berisi detail per file dalam batch ini. Hanya admin yang bisa insert.';
COMMENT ON COLUMN ingestion_batch.notes IS 'Catatan admin, e.g. periode data yang diimport. Opsional.';
COMMENT ON COLUMN ingestion_batch.finished_at IS 'NULL selama masih proses. Diisi backend setelah semua file dalam batch selesai.';


-- ── 4.2 Ingestion File Log ────────────────────────────────────────────────────
-- Log detail per file CSV dalam satu batch.
-- Statistik baris (total_row, new_row, dll.) diupdate secara incremental
-- selama proses ingestion berlangsung.

CREATE TABLE ingestion_file_log (
    log_id            UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id          UUID             NOT NULL REFERENCES ingestion_batch(batch_id) ON DELETE CASCADE,
    jenis_file        jenis_file_porto NOT NULL,
    -- Jenis file CSV yang diupload. Menentukan tabel target dan logika upsert.

    original_filename VARCHAR(500)     NOT NULL,
    -- Nama file asli yang diupload oleh admin.

    -- === Konteks Periode ===
    tahun_ajaran      VARCHAR(9),
    -- Periode data yang diimport, format 'YYYY/YYYY'. e.g. '2024/2025'.
    -- NULLABLE: tidak semua file perlu periode (e.g. dosen.csv, mata_kuliah.csv).

    semester          SMALLINT         CHECK (semester IS NULL OR semester IN (1, 2, 3)),
    -- 1=Ganjil, 2=Genap, 3=Semester Pendek. NULLABLE.

    -- === Status & Hasil Pemrosesan ===
    status            status_ingestion NOT NULL DEFAULT 'pending',

    total_row         INTEGER          NOT NULL DEFAULT 0,
    -- Total baris data di file CSV (exclude header baris pertama).

    processed_row     INTEGER          NOT NULL DEFAULT 0,
    -- Baris yang sudah diproses = new_row + updated_row + skipped_row.

    new_row           INTEGER          NOT NULL DEFAULT 0,
    -- Baris INSERT baru: natural key belum ada di DB.

    updated_row       INTEGER          NOT NULL DEFAULT 0,
    -- Baris UPDATE: natural key sudah ada, data berubah (upsert hit).

    skipped_row       INTEGER          NOT NULL DEFAULT 0,
    -- Baris dilewati: natural key sudah ada, data identik (tidak perlu update).

    failed_row        INTEGER          NOT NULL DEFAULT 0,
    -- Baris gagal: error validasi, FK violation, constraint violation, dll.

    error_detail      JSONB,
    -- Detail error per baris. Format:
    -- [{"baris": 42, "pesan": "FK dosen tidak ditemukan", "data": {...}}, ...]

    notes             TEXT,
    -- Catatan sistem atau admin tentang file ini.

    started_at        TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    -- Waktu file mulai diproses.

    finished_at       TIMESTAMPTZ,
    -- NULL selama masih diproses atau pending.

    created_at        TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ      NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_processed_row_konsisten CHECK (
        -- processed_row = jumlah baris yang sudah ditangani (tanpa error)
        processed_row = new_row + updated_row + skipped_row
        OR processed_row = 0   -- masih pending, belum ada yang diproses
    )
);

CREATE INDEX idx_ifl_batch_id  ON ingestion_file_log (batch_id);
-- Lookup semua file dalam satu batch.
CREATE INDEX idx_ifl_jenis     ON ingestion_file_log (jenis_file);
CREATE INDEX idx_ifl_status    ON ingestion_file_log (status) WHERE status IN ('pending', 'processing');
-- Partial index: hanya file yang belum selesai (untuk monitoring aktif).

COMMENT ON TABLE  ingestion_file_log IS 'Log detail per file CSV per batch ingestion. Statistik baris (new_row, updated_row, dll.) diupdate incremental selama proses. error_detail JSONB berisi detail error per baris yang gagal.';
COMMENT ON COLUMN ingestion_file_log.jenis_file IS 'Enum jenis_file_porto. Menentukan tabel target dan upsert logic di ETL script.';
COMMENT ON COLUMN ingestion_file_log.processed_row IS 'Baris yang berhasil ditangani = new_row + updated_row + skipped_row. failed_row tidak masuk ke processed_row.';
COMMENT ON COLUMN ingestion_file_log.error_detail IS 'JSONB array detail error per baris. NULL jika tidak ada error. Contoh: [{"baris":42,"pesan":"FK tidak ditemukan","data":{...}}].';


-- ============================================================
-- SECTION 5 — TRIGGER: AUTO updated_at
-- ============================================================
-- fn_auto_updated_at() sudah didefinisikan di schema_portofolio_kuesioner.sql.
-- Pastikan file tersebut dijalankan lebih dulu.

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'pengguna',
        'pengguna_peran',
        'ingestion_batch',
        'ingestion_file_log'
    ] LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_updated_at_%I
             BEFORE UPDATE ON %I
             FOR EACH ROW EXECUTE FUNCTION fn_auto_updated_at()',
            t, t
        );
    END LOOP;
END;
$$;
-- Catatan: tabel sessions tidak memiliki kolom updated_at
-- (session tidak pernah di-UPDATE, hanya INSERT dan DELETE).


-- ============================================================
-- SECTION 6 — RLS UNTUK TABEL AUTH
-- ============================================================
-- Tabel auth tidak menggunakan RLS berbasis row (karena akses dikontrol
-- di application layer). Namun, pengguna hanya boleh melihat data sendiri
-- kecuali admin.
--
-- Strategi: gunakan GRANT dan application-layer authorization,
-- bukan RLS, untuk tabel auth — karena pattern aksesnya lebih sederhana
-- dan tidak perlu row-level filtering berdasarkan prodi/fakultas.
--
-- Rekomendasi implementasi di backend:
--   - GET /api/pengguna       → hanya admin yang bisa akses semua
--   - GET /api/pengguna/:id   → admin atau pengguna itu sendiri
--   - GET /api/sessions       → admin atau pengguna itu sendiri
--   - GET /api/ingestion      → hanya admin
-- ============================================================


-- ============================================================
-- SECTION 7 — RINGKASAN SCHEMA
-- ============================================================
-- TOTAL: 5 TABEL
--
-- [USER]  pengguna, pengguna_peran
-- [SESS]  sessions
-- [ING]   ingestion_batch, ingestion_file_log
--
-- ENUM TYPES (4):
--   user_role_enum    → peran pengguna (admin, direktorat, dekan, dll.)
--   metode_auth       → sso_microsoft | password
--   jenis_file_porto  → 10 jenis file CSV domain portofolio
--   status_ingestion  → pending | processing | success | partial | failed
--
-- DEPENDENCY ORDER (jalankan berurutan):
--   1. schema_portofolio_kuesioner.sql  (ekstensi, enum domain, 21 tabel, RLS)
--   2. schema_auth_and_ingestion.sql          (file ini: 4 enum, 5 tabel)
-- ============================================================
-- END: schema_auth_and_ingestion.sql