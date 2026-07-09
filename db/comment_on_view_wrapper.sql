-- ================================================================
-- COMMENT ON — Schema analitik.*
-- Konteks untuk agen text-to-SQL dan agen RAG
-- Versi ini disesuaikan dengan schema_mv_portofolio_kuesioner.sql
-- dan security_definer_function.sql terbaru.
--
-- Konvensi penamaan kolom:
--   no_prodi      = integer ID program studi (utama.program_studi.no_ps)
--   kode_prodi    = kode string singkat prodi 2 karakter (kd_ps), contoh: IF, EL
--   kode_matkul   = kode mata kuliah 6 karakter (kd_kuliah), contoh: IF2210
--   kode_fakultas = kode string fakultas/sekolah (kd_fak), contoh: STEI, SBM
--   tahun_ajaran  = format 'YYYY/YYYY', contoh: '2023/2024'
--   semester      = 1=ganjil, 2=genap, 3=pendek
--   jenjang       = S1/S2/S3/PR (dari kd_strata)
--
-- Skala kuesioner mahasiswa: 1=Sangat Tidak Setuju/Tidak Pernah,
--   2=Tidak Setuju/Jarang, 3=Setuju/Sering, 4=Sangat Setuju/Selalu.
--   Pertanyaan Q21-Q37 diisi oleh mahasiswa saat evaluasi kelas.
--   Pertanyaan Q25/Q26/Q27 bersifat per-dosen (kd_kategori='D').
--   Pertanyaan lainnya bersifat per-kelas (kd_kategori='K').
--
-- Portofolio dosen (kd_pertanyaan 12-19):
--   Diisi dosen setelah perkuliahan selesai.
--   Dikelompokkan dalam 4 grup aktif (kd_grup 6-9).
--   Teks sudah distrip HTML via analitik_mv.strip_html().
--
-- Security: semua view di schema ini difilter otomatis per user role.
-- Agen tidak perlu menambahkan filter role — sudah ditangani Security Definer Function.
-- Periode data: 2018/2019 semester 1 s.d. terkini.
-- ================================================================


-- ================================================================
-- A. VIEW PUBLIK — Informasi non-sensitif, semua role bisa akses
-- ================================================================

-- ── A1. v_akademik_jenis_dan_sifat_matkul ────────────────────────
COMMENT ON VIEW analitik.v_akademik_jenis_dan_sifat_matkul IS
    'Jenis dan sifat mata kuliah dalam struktur kurikulum. '
    'Grain: 1 baris = 1 (mata_kuliah_id, no_prodi, paket/struktur). '
    'Satu MK bisa >1 baris jika masuk ke >1 paket dalam prodi yang sama. '
    'Sumber: kur24.* (kurikulum 2024) UNION kurikulum.* (kurikulum lama). '
    'Gunakan untuk cek apakah MK wajib/pilihan, jenis paket, dan sifat kurikulum.';

COMMENT ON COLUMN analitik.v_akademik_jenis_dan_sifat_matkul.mata_kuliah_id
    IS 'ID internal mata kuliah (FK ke utama.mata_kuliah).';
COMMENT ON COLUMN analitik.v_akademik_jenis_dan_sifat_matkul.no_prodi
    IS 'ID numerik program studi penyelenggara kurikulum (FK ke utama.program_studi.no_ps).';
COMMENT ON COLUMN analitik.v_akademik_jenis_dan_sifat_matkul.kode_prodi
    IS 'Kode singkat prodi 2 karakter, contoh: IF, EL, MA. Dari utama.program_studi.kd_ps.';
COMMENT ON COLUMN analitik.v_akademik_jenis_dan_sifat_matkul.jenjang
    IS 'Jenjang program studi: S1, S2, S3, PR. Dari utama.program_studi.kd_strata.';
COMMENT ON COLUMN analitik.v_akademik_jenis_dan_sifat_matkul.nama_prodi_id
    IS 'Nama program studi Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_akademik_jenis_dan_sifat_matkul.nama_prodi_en
    IS 'Nama program studi Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_akademik_jenis_dan_sifat_matkul.kode_fakultas
    IS 'Kode fakultas/sekolah, contoh: STEI, SBM, FSRD. Dari utama.program_studi.kd_fak.';
COMMENT ON COLUMN analitik.v_akademik_jenis_dan_sifat_matkul.nama_fakultas_id
    IS 'Nama fakultas/sekolah Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_akademik_jenis_dan_sifat_matkul.nama_fakultas_en
    IS 'Nama fakultas/sekolah Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_akademik_jenis_dan_sifat_matkul.tahun_kurikulum
    IS 'Tahun berlakunya kurikulum, contoh: 2003, 2013, 2024.';
COMMENT ON COLUMN analitik.v_akademik_jenis_dan_sifat_matkul.sumber
    IS 'Asal data kurikulum: ''kurikulum_2024'' (kur24.*) atau ''kurikulum_lama'' (kurikulum.*).';
COMMENT ON COLUMN analitik.v_akademik_jenis_dan_sifat_matkul.paket_id
    IS 'ID paket kurikulum (hanya kur24, NULL untuk kurikulum lama).';
COMMENT ON COLUMN analitik.v_akademik_jenis_dan_sifat_matkul.struktur_id
    IS 'ID struktur kurikulum (hanya kurikulum lama, NULL untuk kur24).';
COMMENT ON COLUMN analitik.v_akademik_jenis_dan_sifat_matkul.kode_jenis
    IS 'Kode jenis paket (hanya kur24): A=Matakuliah Prodi, B=TPB/Wajib ITB, C=Lintas Prodi, dll. NULL untuk kurikulum lama.';
COMMENT ON COLUMN analitik.v_akademik_jenis_dan_sifat_matkul.nama_jenis
    IS 'Nama jenis paket dalam Bahasa Indonesia (hanya kur24). NULL untuk kurikulum lama.';
COMMENT ON COLUMN analitik.v_akademik_jenis_dan_sifat_matkul.nama_paket
    IS 'Nama paket kurikulum (hanya kur24), contoh: "Wajib Prodi", "Pilihan". NULL untuk kurikulum lama.';
COMMENT ON COLUMN analitik.v_akademik_jenis_dan_sifat_matkul.kode_sifat
    IS 'Sifat MK dalam struktur: C=Core/Wajib, E=Elective/Pilihan. '
       'Dinormalisasi lintas era: kurikulum lama W→C dan P→E.';
COMMENT ON COLUMN analitik.v_akademik_jenis_dan_sifat_matkul.is_wajib_itb
    IS 'TRUE jika MK termasuk matakuliah wajib ITB (lintas prodi). '
       'Hanya tersedia untuk kurikulum lama via kurikulum.struktur_wajib_itb. '
       'Untuk kur24, selalu FALSE (gunakan kode_jenis=''B'' sebagai proxy TPB).';


-- ── A2. v_info_umum_kelas_matkul ─────────────────────────────────
COMMENT ON VIEW analitik.v_info_umum_kelas_matkul IS
    'Informasi umum kelas dan mata kuliah — tanpa data nilai, kehadiran, atau skor kuesioner. '
    'Grain: 1 baris = 1 kelas. Gunakan untuk lookup kelas, matkul, dosen, prodi, dan jenis/sifat. '
    'Aman diakses semua role tanpa restriction tambahan. '
    'Periode: 2018/2019 semester 1 s.d. terkini.';

COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.kelas_id
    IS 'PK. ID kelas (FK ke kelas.kelas).';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.mata_kuliah_id
    IS 'ID mata kuliah (FK ke utama.mata_kuliah).';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.no_kelas
    IS 'Nomor urut kelas dalam satu mata kuliah per semester, contoh: 1, 2, 3.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.semester
    IS 'Semester: 1=ganjil, 2=genap, 3=pendek.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.tahun
    IS 'Tahun akademik 4 digit, contoh: 2023.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.tahun_ajaran
    IS 'Format YYYY/YYYY, contoh: 2023/2024. Semester 1 → tahun/tahun+1; semester 2/3 → tahun-1/tahun.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.kode_matkul
    IS 'Kode mata kuliah 6 karakter, contoh: IF2210, MA1101. Dari utama.mata_kuliah.kd_kuliah.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.nama_matkul_id
    IS 'Nama mata kuliah Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.nama_matkul_en
    IS 'Nama mata kuliah Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.sks
    IS 'Jumlah SKS mata kuliah.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.tahun_kurikulum
    IS 'Tahun kurikulum yang berlaku untuk mata kuliah ini.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.jenis_nilai
    IS 'Sistem penilaian kelas: ''ABCDE'' atau ''PassFail''.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.no_prodi
    IS 'ID numerik program studi penyelenggara (FK ke utama.program_studi.no_ps).';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.kode_prodi
    IS 'Kode singkat prodi 2 karakter, contoh: IF, EL, MA.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.nama_prodi_id
    IS 'Nama program studi Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.nama_prodi_en
    IS 'Nama program studi Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.jenjang
    IS 'Jenjang studi: S1, S2, S3, PR (Profesi).';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.kode_fakultas
    IS 'Kode fakultas/sekolah, contoh: STEI, SBM, FSRD, FMIPA.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.nama_fakultas_id
    IS 'Nama fakultas/sekolah Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.nama_fakultas_en
    IS 'Nama fakultas/sekolah Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.semua_dosen_id
    IS 'Array integer dosen_id semua pengajar kelas, urut dosen utama di indeks 0. '
       'Gunakan @> untuk cek dosen tertentu: WHERE semua_dosen_id @> ARRAY[123].';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.semua_dosen_nama_gelar
    IS 'Array nama lengkap dengan gelar semua pengajar, urut sama dengan semua_dosen_id.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.kode_jenis_list
    IS 'Array kode jenis MK dalam kurikulum, contoh: {A,B}. NULL jika MK tidak terdaftar di kurikulum apapun.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.nama_jenis_list
    IS 'Array nama jenis MK dalam kurikulum (Bahasa Indonesia). Paralel dengan kode_jenis_list.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.nama_paket_list
    IS 'Array nama paket kurikulum. NULL jika MK tidak terdaftar.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.kode_sifat_list
    IS 'Array sifat MK: C=Core/Wajib, E=Elective/Pilihan. NULL jika MK tidak terdaftar.';
COMMENT ON COLUMN analitik.v_info_umum_kelas_matkul.is_wajib_itb
    IS 'TRUE jika MK adalah matakuliah wajib ITB lintas prodi. NULL jika tidak terdaftar di kurikulum.';


-- ── A3. v_info_umum_institusi ─────────────────────────────────────
COMMENT ON VIEW analitik.v_info_umum_institusi IS
    'Ringkasan aktivitas institusi per prodi per semester — jumlah kelas, dosen, mahasiswa aktif. '
    'Grain: 1 baris = 1 (no_prodi, semester, tahun). '
    'Tidak mengandung data nilai atau skor kuesioner. Aman diakses semua role. '
    'Periode: 2018/2019 semester 1 s.d. terkini.';

COMMENT ON COLUMN analitik.v_info_umum_institusi.no_prodi
    IS 'ID numerik program studi (FK ke utama.program_studi.no_ps). PK bersama semester dan tahun.';
COMMENT ON COLUMN analitik.v_info_umum_institusi.kode_prodi
    IS 'Kode singkat prodi 2 karakter, contoh: IF, EL, MA.';
COMMENT ON COLUMN analitik.v_info_umum_institusi.nama_prodi_id
    IS 'Nama program studi Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_info_umum_institusi.nama_prodi_en
    IS 'Nama program studi Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_info_umum_institusi.jenjang
    IS 'Jenjang studi: S1, S2, S3, PR.';
COMMENT ON COLUMN analitik.v_info_umum_institusi.kode_fakultas
    IS 'Kode fakultas/sekolah.';
COMMENT ON COLUMN analitik.v_info_umum_institusi.nama_fakultas_id
    IS 'Nama fakultas/sekolah Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_info_umum_institusi.nama_fakultas_en
    IS 'Nama fakultas/sekolah Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_info_umum_institusi.semester
    IS 'Semester: 1=ganjil, 2=genap, 3=pendek.';
COMMENT ON COLUMN analitik.v_info_umum_institusi.tahun
    IS 'Tahun akademik 4 digit.';
COMMENT ON COLUMN analitik.v_info_umum_institusi.tahun_ajaran
    IS 'Format YYYY/YYYY, contoh: 2023/2024.';
COMMENT ON COLUMN analitik.v_info_umum_institusi.jumlah_kelas
    IS 'Jumlah kelas yang diselenggarakan prodi pada semester tersebut.';
COMMENT ON COLUMN analitik.v_info_umum_institusi.jumlah_matkul_aktif
    IS 'Jumlah mata kuliah unik yang aktif diajarkan prodi pada semester tersebut.';
COMMENT ON COLUMN analitik.v_info_umum_institusi.jumlah_dosen_aktif
    IS 'Jumlah dosen unik yang mengajar di prodi pada semester tersebut.';
COMMENT ON COLUMN analitik.v_info_umum_institusi.jumlah_mahasiswa_aktif
    IS 'Jumlah mahasiswa aktif (FRS selesai, tidak nonaktif) di prodi pada semester tersebut. '
       'Sumber: mahasiswa.status + mahasiswa.nonaktif (cuti/skorsing dikecualikan).';


-- ── A4. v_info_umum_dosen ─────────────────────────────────────────
COMMENT ON VIEW analitik.v_info_umum_dosen IS
    'Informasi umum dosen per semester — beban mengajar dan daftar prodi/MK yang diajar. '
    'Grain: 1 baris = 1 (dosen_id, semester, tahun). '
    'Tidak mengandung skor kuesioner atau kehadiran. Aman diakses semua role. '
    'Periode: 2018/2019 semester 1 s.d. terkini.';

COMMENT ON COLUMN analitik.v_info_umum_dosen.dosen_id
    IS 'ID dosen (FK ke utama.dosen). PK bersama semester dan tahun.';
COMMENT ON COLUMN analitik.v_info_umum_dosen.nama_dosen_gelar
    IS 'Nama lengkap dosen dengan gelar depan dan belakang, contoh: Prof. Dr. Budi Santoso, M.T.';
COMMENT ON COLUMN analitik.v_info_umum_dosen.nip
    IS 'Nomor Induk Pegawai dosen.';
COMMENT ON COLUMN analitik.v_info_umum_dosen.kk_id
    IS 'ID Kelompok Keahlian (FK ke utama.kk). NULL jika dosen tidak terdaftar di KK.';
COMMENT ON COLUMN analitik.v_info_umum_dosen.kode_fakultas_dosen
    IS 'Kode fakultas homebase dosen (dari utama.dosen.kd_fak). '
       'Dapat berbeda dengan kode_prodi jika dosen lintas fakultas.';
COMMENT ON COLUMN analitik.v_info_umum_dosen.no_prodi
    IS 'ID numerik program studi homebase dosen (dari utama.dosen.no_ps). '
       'NULL jika dosen tidak memiliki homebase prodi.';
COMMENT ON COLUMN analitik.v_info_umum_dosen.kode_prodi
    IS 'Kode singkat prodi homebase dosen. NULL jika no_prodi NULL.';
COMMENT ON COLUMN analitik.v_info_umum_dosen.semester
    IS 'Semester: 1=ganjil, 2=genap, 3=pendek.';
COMMENT ON COLUMN analitik.v_info_umum_dosen.tahun
    IS 'Tahun akademik 4 digit.';
COMMENT ON COLUMN analitik.v_info_umum_dosen.tahun_ajaran
    IS 'Format YYYY/YYYY.';
COMMENT ON COLUMN analitik.v_info_umum_dosen.jumlah_kelas
    IS 'Jumlah kelas yang diajar dosen pada semester tersebut (termasuk kelas paralel).';
COMMENT ON COLUMN analitik.v_info_umum_dosen.jumlah_matkul
    IS 'Jumlah mata kuliah unik yang diajar dosen pada semester tersebut.';
COMMENT ON COLUMN analitik.v_info_umum_dosen.total_sks_diajar
    IS 'Total SKS seluruh kelas yang diajar (termasuk paralel). '
       'Berbeda dari SKS unik per MK — mencerminkan beban mengajar total.';
COMMENT ON COLUMN analitik.v_info_umum_dosen.kelas_id_list
    IS 'Array kelas_id semua kelas yang diajar dosen semester ini.';
COMMENT ON COLUMN analitik.v_info_umum_dosen.kode_matkul_list
    IS 'Array kode MK unik yang diajar dosen semester tersebut, contoh: {IF2210,IF3110}.';
COMMENT ON COLUMN analitik.v_info_umum_dosen.no_prodi_diajar
    IS 'Array ID numerik prodi yang kelas-kelasnya diajar dosen (bisa beda dari homebase). '
       'Gunakan untuk filter KAPRODI: WHERE no_prodi_diajar @> ARRAY[v_no_prodi].';
COMMENT ON COLUMN analitik.v_info_umum_dosen.kode_prodi_diajar
    IS 'Array kode singkat prodi yang diajar, paralel dengan no_prodi_diajar.';


-- ================================================================
-- B. VIEW WRAPPER — Difilter otomatis per role user
-- ================================================================

-- ── B1. v_akademik_kelas ─────────────────────────────────────────
COMMENT ON VIEW analitik.v_akademik_kelas IS
    'Data lengkap per kelas: kehadiran, distribusi nilai (termasuk T/incomplete), '
    'skor kuesioner mahasiswa (Q21-Q37), dan dimensi evaluasi. '
    'Grain: 1 baris = 1 kelas. Periode: 2018/2019 semester 1 s.d. terkini. '
    'ROW SECURITY: ADMIN/DIREKTORAT=semua kelas; DEKAN/JAJ.DEKANAT=filter kode_fakultas; '
    'KAPRODI/JAJ.PRODI/DOSEN=semua kelas di prodinya (no_prodi). '
    'COLUMN SECURITY: skor_dosen_q25/26/27 (JSONB) di-mask untuk role DOSEN '
    '— hanya berisi entry dosen tersebut saja, bukan skor dosen lain.';

COMMENT ON COLUMN analitik.v_akademik_kelas.kelas_id
    IS 'PK. ID kelas (FK ke kelas.kelas).';
COMMENT ON COLUMN analitik.v_akademik_kelas.mata_kuliah_id
    IS 'ID mata kuliah (FK ke utama.mata_kuliah).';
COMMENT ON COLUMN analitik.v_akademik_kelas.no_kelas
    IS 'Nomor urut kelas dalam satu mata kuliah per semester.';
COMMENT ON COLUMN analitik.v_akademik_kelas.semester
    IS '1=ganjil, 2=genap, 3=pendek.';
COMMENT ON COLUMN analitik.v_akademik_kelas.tahun
    IS 'Tahun akademik 4 digit.';
COMMENT ON COLUMN analitik.v_akademik_kelas.tahun_ajaran
    IS 'Format YYYY/YYYY, contoh: 2023/2024.';
COMMENT ON COLUMN analitik.v_akademik_kelas.kode_matkul
    IS 'Kode mata kuliah 6 karakter, contoh: IF2210.';
COMMENT ON COLUMN analitik.v_akademik_kelas.nama_matkul_id
    IS 'Nama mata kuliah Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_akademik_kelas.nama_matkul_en
    IS 'Nama mata kuliah Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_akademik_kelas.sks
    IS 'Jumlah SKS mata kuliah.';
COMMENT ON COLUMN analitik.v_akademik_kelas.tahun_kurikulum
    IS 'Tahun kurikulum yang berlaku untuk mata kuliah ini.';
COMMENT ON COLUMN analitik.v_akademik_kelas.jenis_nilai
    IS 'Sistem penilaian: ''ABCDE'' atau ''PassFail''.';
COMMENT ON COLUMN analitik.v_akademik_kelas.no_prodi
    IS 'ID numerik program studi penyelenggara kelas.';
COMMENT ON COLUMN analitik.v_akademik_kelas.kode_prodi
    IS 'Kode singkat prodi 2 karakter.';
COMMENT ON COLUMN analitik.v_akademik_kelas.nama_prodi_id
    IS 'Nama program studi Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_akademik_kelas.nama_prodi_en
    IS 'Nama program studi Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_akademik_kelas.jenjang
    IS 'Jenjang studi: S1, S2, S3, PR.';
COMMENT ON COLUMN analitik.v_akademik_kelas.kode_fakultas
    IS 'Kode fakultas/sekolah.';
COMMENT ON COLUMN analitik.v_akademik_kelas.nama_fakultas_id
    IS 'Nama fakultas Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_akademik_kelas.nama_fakultas_en
    IS 'Nama fakultas Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_akademik_kelas.semua_dosen_id
    IS 'Array integer dosen_id semua pengajar kelas (urut dosen utama di indeks 0). '
       'Gunakan @> untuk cek apakah dosen tertentu mengajar: WHERE semua_dosen_id @> ARRAY[123].';
COMMENT ON COLUMN analitik.v_akademik_kelas.semua_dosen_nama_gelar
    IS 'Array nama lengkap dengan gelar semua pengajar, paralel dengan semua_dosen_id.';
COMMENT ON COLUMN analitik.v_akademik_kelas.kode_jenis_list
    IS 'Array kode jenis MK dalam struktur kurikulum. NULL jika MK tidak terdaftar.';
COMMENT ON COLUMN analitik.v_akademik_kelas.nama_jenis_list
    IS 'Array nama jenis MK (Bahasa Indonesia). NULL jika MK tidak terdaftar.';
COMMENT ON COLUMN analitik.v_akademik_kelas.nama_paket_list
    IS 'Array nama paket kurikulum. NULL jika MK tidak terdaftar.';
COMMENT ON COLUMN analitik.v_akademik_kelas.kode_sifat_list
    IS 'Array sifat MK: C=Core/Wajib, E=Elective/Pilihan.';
COMMENT ON COLUMN analitik.v_akademik_kelas.is_wajib_itb
    IS 'TRUE jika MK adalah matakuliah wajib ITB lintas prodi.';
COMMENT ON COLUMN analitik.v_akademik_kelas.pct_kehadiran_mahasiswa
    IS 'Persentase kehadiran mahasiswa (0–100). Sumber: evaluasi.nilai_kelas.hadir_mhs. '
       'NULL jika belum ada data evaluasi.';
COMMENT ON COLUMN analitik.v_akademik_kelas.pct_kehadiran_dosen
    IS 'Persentase kehadiran dosen (0–100). Sumber: evaluasi.nilai_kelas.hadir_dosen. '
       'NULL jika belum ada data evaluasi.';
COMMENT ON COLUMN analitik.v_akademik_kelas.avg_ip_akhir_mahasiswa
    IS 'Rata-rata IP akhir mahasiswa yang mengikuti kelas ini. '
       'Sumber: evaluasi.nilai_kelas.ip_mhs. NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_dna
    IS 'Skor DNA (Did Not Attend) kelas. NULL jika tidak ada.';
COMMENT ON COLUMN analitik.v_akademik_kelas.ts_dna
    IS 'Timestamp kapan data DNA dicatat.';
COMMENT ON COLUMN analitik.v_akademik_kelas.ip_mhs_dna
    IS 'IP mahasiswa yang tercatat sebagai DNA.';
COMMENT ON COLUMN analitik.v_akademik_kelas.is_distribusi_nilai_sah
    IS 'TRUE = ada nilai yang sudah disahkan (sah_nilai=true) untuk kelas ini. '
       'FALSE/NULL = belum ada nilai sah — kolom dist_jumlah_* dan dist_pct_* adalah NULL '
       '(bukan berarti semua mahasiswa tidak mendapat nilai, data belum masuk). '
       'Selalu filter WHERE is_distribusi_nilai_sah = TRUE sebelum menggunakan data distribusi nilai.';
COMMENT ON COLUMN analitik.v_akademik_kelas.jumlah_mahasiswa
    IS 'Total mahasiswa dengan nilai apapun (termasuk T/incomplete). '
       'NULL jika is_distribusi_nilai_sah=FALSE. '
       'Gunakan dist_jumlah_t untuk mengetahui jumlah yang masih pending.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_jumlah_a
    IS 'Jumlah mahasiswa mendapat nilai A. NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_jumlah_ab
    IS 'Jumlah mahasiswa mendapat nilai AB. NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_jumlah_b
    IS 'Jumlah mahasiswa mendapat nilai B. NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_jumlah_bc
    IS 'Jumlah mahasiswa mendapat nilai BC. NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_jumlah_c
    IS 'Jumlah mahasiswa mendapat nilai C. NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_jumlah_d
    IS 'Jumlah mahasiswa mendapat nilai D. NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_jumlah_e
    IS 'Jumlah mahasiswa mendapat nilai E (tidak lulus). NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_jumlah_t
    IS 'Jumlah mahasiswa dengan nilai T (tunda/incomplete — nilai belum final). '
       'NULL jika is_distribusi_nilai_sah=FALSE. '
       'Mahasiswa T ikut dihitung di jumlah_mahasiswa dan dist_pct_*.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_jumlah_pass
    IS 'Jumlah mahasiswa lulus (nilai P, untuk kelas PassFail). NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_jumlah_fail
    IS 'Jumlah mahasiswa tidak lulus (nilai F, untuk kelas PassFail). NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_pct_a
    IS 'Persentase mahasiswa mendapat nilai A dari total mahasiswa (termasuk T). '
       'NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_pct_ab
    IS 'Persentase mahasiswa mendapat nilai AB dari total mahasiswa. NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_pct_b
    IS 'Persentase mahasiswa mendapat nilai B. NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_pct_bc
    IS 'Persentase mahasiswa mendapat nilai BC. NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_pct_c
    IS 'Persentase mahasiswa mendapat nilai C. NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_pct_d
    IS 'Persentase mahasiswa mendapat nilai D. NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_pct_e
    IS 'Persentase mahasiswa mendapat nilai E. NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_pct_t
    IS 'Persentase mahasiswa dengan nilai T (tunda/incomplete) dari total mahasiswa. '
       'Nilai tinggi menandakan banyak nilai yang belum final. NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_pct_pass
    IS 'Persentase mahasiswa lulus (nilai P). NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_pct_fail
    IS 'Persentase mahasiswa tidak lulus (nilai F). NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_pct_lulus_a_c
    IS 'Persentase mahasiswa lulus ≥C (A+AB+B+BC+C) untuk ABCDE, atau P untuk PassFail, '
       'dari total mahasiswa termasuk T. Metrik utama tingkat kelulusan. '
       'NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_pct_lulus_a_d
    IS 'Persentase mahasiswa lulus ≥D (A+AB+B+BC+C+D) untuk ABCDE, atau P untuk PassFail, '
       'dari total mahasiswa termasuk T. NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q21
    IS 'Skor kuesioner mahasiswa Q21 (rata-rata kelas, skala 1–4). '
       'Pertanyaan: "Saya memperoleh informasi yang cukup tentang hal-hal tertentu yang '
       'harus saya capai atau kuasai (luaran matakuliah) sesudah mengikuti matakuliah ini." '
       'Kelompok: Outcome (luaran) matakuliah. Kategori: K (per kelas). '
       'NULL jika belum ada data kuesioner untuk kelas ini.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q22
    IS 'Skor kuesioner mahasiswa Q22 (rata-rata kelas, skala 1–4). '
       'Pertanyaan: "Pelaksanaan perkuliahan diarahkan agar mahasiswa dapat mencapai '
       'atau menguasai luaran matakuliah ini." '
       'Kelompok: Outcome (luaran) matakuliah. Kategori: K (per kelas). '
       'NULL jika belum ada data kuesioner.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q23
    IS 'Skor kuesioner mahasiswa Q23 (rata-rata kelas, skala 1–4). '
       'Pertanyaan: "Saya mencapai atau menguasai luaran matakuliah ini." '
       'Kelompok: Outcome (luaran) matakuliah. Kategori: K (per kelas). '
       'NULL jika belum ada data kuesioner.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q24
    IS 'Skor kuesioner mahasiswa Q24 (rata-rata kelas, skala 1–4). '
       'Pertanyaan: "Pelaksanaan perkuliahan terorganisir dengan baik." '
       'Kelompok: Pelaksanaan perkuliahan. Kategori: K (per kelas). '
       'NULL jika belum ada data kuesioner.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q25
    IS 'Skor kuesioner mahasiswa Q25 (rata-rata dari semua dosen dalam kelas, skala 1–4). '
       'Pertanyaan: "Dosen berkomunikasi dengan efektif." '
       'Kelompok: Pelaksanaan perkuliahan. Kategori: D (per dosen, dirata-rata antar dosen). '
       'Rata-rata lintas dosen jika kelas tim-teaching. NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q26
    IS 'Skor kuesioner mahasiswa Q26 (rata-rata dari semua dosen dalam kelas, skala 1–4). '
       'Pertanyaan: "Dosen peduli terhadap pencapaian atau penguasaan mahasiswa '
       'akan luaran matakuliah ini." '
       'Kelompok: Pelaksanaan perkuliahan. Kategori: D (per dosen, dirata-rata antar dosen). '
       'NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q27
    IS 'Skor kuesioner mahasiswa Q27 (rata-rata dari semua dosen dalam kelas, skala 1–4). '
       'Pertanyaan: "Dosen berlaku adil (fair) kepada mahasiswa." '
       'Kelompok: Pelaksanaan perkuliahan. Kategori: D (per dosen, dirata-rata antar dosen). '
       'NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q28
    IS 'Skor kuesioner mahasiswa Q28 (rata-rata kelas, skala 1–4). '
       'Pertanyaan: "Beban kerja untuk matakuliah ini sesuai dengan SKS-nya." '
       'Kelompok: Pelaksanaan perkuliahan. Kategori: K (per kelas). '
       'NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q29
    IS 'Skor kuesioner mahasiswa Q29 (rata-rata kelas, skala 1–4). '
       'Pertanyaan: "Sarana prasarana untuk matakuliah tersedia dengan memadai." '
       'Kelompok: Pelaksanaan perkuliahan. Kategori: K (per kelas). '
       'Komponen dari avg_skor_sarana_prasarana. NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q30
    IS 'Skor kuesioner mahasiswa Q30 (rata-rata kelas, skala 1–4). '
       'Pertanyaan: "Tersedia cukup fasilitas pendukung di luar kuliah yang '
       'memungkinkan saya mengikuti matakuliah ini dengan baik." '
       'Kelompok: Pelaksanaan perkuliahan. Kategori: K (per kelas). '
       'Komponen dari avg_skor_sarana_prasarana. NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q35
    IS 'Skor kuesioner mahasiswa Q35 (rata-rata kelas, skala 1–4). '
       'Pertanyaan: "Saya berusaha dengan sungguh-sungguh mengikuti matakuliah ini." '
       'Kelompok: Perilaku mahasiswa. Kategori: K (per kelas). '
       'Mengukur keterlibatan/engagement mahasiswa. NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q37
    IS 'Skor kuesioner mahasiswa Q37 (rata-rata kelas, skala 1–4). '
       'Pertanyaan: "Saya memperoleh pengalaman belajar yang positif dalam matakuliah ini." '
       'Kelompok: Perilaku mahasiswa. Kategori: K (per kelas). '
       'Mengukur kepuasan belajar mahasiswa secara keseluruhan. NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_dosen_q25
    IS '[JSONB] Skor Q25 ("Dosen berkomunikasi dengan efektif") per dosen dalam kelas: '
       '{"dosen_id": skor, ...}. Contoh: {"123": 3.67, "456": 4.00}. Key = dosen_id::TEXT. '
       'SECURITY: role DOSEN hanya melihat entry miliknya; role lain melihat semua. '
       'NULL jika tidak ada data kuesioner per dosen.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_dosen_q26
    IS '[JSONB] Skor Q26 ("Dosen peduli terhadap pencapaian mahasiswa") per dosen: '
       '{"dosen_id": skor, ...}. '
       'SECURITY: di-mask untuk role DOSEN — hanya berisi entry miliknya.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_dosen_q27
    IS '[JSONB] Skor Q27 ("Dosen berlaku adil kepada mahasiswa") per dosen: '
       '{"dosen_id": skor, ...}. '
       'SECURITY: di-mask untuk role DOSEN — hanya berisi entry miliknya.';
COMMENT ON COLUMN analitik.v_akademik_kelas.avg_skor_capaian
    IS 'Rata-rata skor dimensi Capaian Pembelajaran dari evaluasi.nilai_dosen.skor_kues (key "1"). '
       'Rata-rata dari skor semua dosen dalam kelas. NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.avg_skor_pelaksanaan
    IS 'Rata-rata skor dimensi Pelaksanaan Perkuliahan dari evaluasi.nilai_dosen.skor_kues (key "2"). '
       'NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.avg_skor_sarana_prasarana
    IS 'Rata-rata skor dimensi Sarana & Prasarana, dihitung dari (skor_q29 + skor_q30) / 2. '
       'NULL jika belum ada data kuesioner.';
COMMENT ON COLUMN analitik.v_akademik_kelas.avg_skor_perilaku_mahasiswa
    IS 'Rata-rata skor dimensi Perilaku Mahasiswa dari evaluasi.nilai_dosen.skor_kues (key "3"). '
       'NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.avg_skor_overall
    IS 'Rata-rata skor keseluruhan dari semua pertanyaan kuesioner yang tersedia (Q21–Q37). '
       'Hanya mempertimbangkan pertanyaan yang tidak NULL. NULL jika tidak ada data kuesioner.';


-- ── B2. v_akademik_komentar_mahasiswa ────────────────────────────
COMMENT ON VIEW analitik.v_akademik_komentar_mahasiswa IS
    'Komentar teks bebas mahasiswa per kelas dari kuesioner (pertanyaan Q103). '
    'Q103: "Berikan komentar Anda tentang matakuliah ini (opsional)." '
    'Grain: 1 baris = 1 jawaban komentar per mahasiswa per kelas. '
    'Satu kelas bisa memiliki banyak komentar (1 per mahasiswa yang mengisi). '
    'Teks sudah distrip HTML via analitik_mv.strip_html(). '
    'Periode: 2018/2019 semester 1 s.d. terkini. '
    'ROW SECURITY: ADMIN/DIREKTORAT=semua; DEKAN/JAJ.DEKANAT=filter kode_fakultas; '
    'KAPRODI/JAJ.PRODI=filter no_prodi; '
    'DOSEN=hanya kelas yang ia ajarkan (filter semua_dosen_id).';

COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.jawaban_id
    IS 'PK. ID jawaban kuesioner (FK ke evaluasi.jwb_kuesioner).';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.kelas_id
    IS 'ID kelas (FK ke kelas.kelas).';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.tahun
    IS 'Tahun akademik 4 digit.';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.semester
    IS '1=ganjil, 2=genap, 3=pendek.';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.tahun_ajaran
    IS 'Format YYYY/YYYY.';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.kode_matkul
    IS 'Kode mata kuliah 6 karakter.';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.nama_matkul_id
    IS 'Nama mata kuliah Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.nama_matkul_en
    IS 'Nama mata kuliah Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.sks
    IS 'Jumlah SKS mata kuliah.';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.no_kelas
    IS 'Nomor urut kelas.';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.no_prodi
    IS 'ID numerik program studi penyelenggara kelas.';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.kode_prodi
    IS 'Kode singkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.nama_prodi_id
    IS 'Nama program studi Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.jenjang
    IS 'Jenjang studi: S1, S2, S3, PR.';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.kode_fakultas
    IS 'Kode fakultas/sekolah.';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.nama_fakultas_id
    IS 'Nama fakultas Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.semua_dosen_id
    IS 'Array dosen_id semua pengajar kelas.';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.semua_dosen_nama_gelar
    IS 'Array nama dengan gelar semua pengajar kelas.';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.komentar_teks
    IS 'Isi komentar teks bebas dari mahasiswa untuk matakuliah ini. '
       'Sudah distrip HTML via analitik_mv.strip_html(). '
       'Diambil dari evaluasi.jwb_kuesioner.jawaban key ''103''. '
       'Q103: pertanyaan terbuka opsional — mahasiswa dapat menuliskan '
       'pendapat, saran, atau masukan apapun tentang matakuliah. '
       'Sumber utama untuk analisis RAG/sentimen komentar mahasiswa.';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.ts_jawaban
    IS 'Timestamp saat mahasiswa mengisi kuesioner.';


-- ── B3. v_akademik_portofolio ─────────────────────────────────────
COMMENT ON VIEW analitik.v_akademik_portofolio IS
    'Portofolio dosen per kelas — refleksi, analisis, dan rekomendasi pengajaran. '
    'Grain: 1 baris = 1 kelas (hanya kelas yang memiliki portofolio terisi). '
    'Hanya skema pertanyaan baru (kd_pertanyaan 12–19, berlaku sejak 2017/2018 semester 2). '
    'Periode data: 2018/2019 semester 1 s.d. terkini. '
    'Semua teks sudah distrip HTML via analitik_mv.strip_html(). '
    'NULL pada kolom isian = dosen tidak mengisi pertanyaan tersebut. '
    'Gunakan kolom lengkap dan nilai_portofolio sebagai sinyal kualitas kelengkapan. '
    'ROW SECURITY: ADMIN/DIREKTORAT=semua; DEKAN/JAJ.DEKANAT=filter kode_fakultas; '
    'KAPRODI/JAJ.PRODI/DOSEN=semua portofolio di prodinya (no_prodi).';

-- Identitas kelas
COMMENT ON COLUMN analitik.v_akademik_portofolio.kelas_id
    IS 'PK. ID kelas (FK ke kelas.kelas).';
COMMENT ON COLUMN analitik.v_akademik_portofolio.kode_matkul
    IS 'Kode mata kuliah 6 karakter, contoh: MA1101.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.nama_matkul_id
    IS 'Nama mata kuliah Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.nama_matkul_en
    IS 'Nama mata kuliah Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.sks
    IS 'Jumlah SKS mata kuliah.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.no_kelas
    IS 'Nomor urut kelas dalam satu mata kuliah per semester.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.semester
    IS '1=ganjil, 2=genap, 3=pendek.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.tahun
    IS 'Tahun akademik 4 digit.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.tahun_ajaran
    IS 'Format YYYY/YYYY, contoh: 2022/2023.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.tahun_kurikulum
    IS 'Tahun kurikulum yang berlaku untuk mata kuliah ini.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.jenis_nilai
    IS 'Sistem penilaian kelas: ''ABCDE'' atau ''PassFail''.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.no_prodi
    IS 'ID numerik program studi penyelenggara kelas (no_ps).';
COMMENT ON COLUMN analitik.v_akademik_portofolio.kode_prodi
    IS 'Kode singkat prodi 2 karakter, contoh: IF, EL.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.nama_prodi_id
    IS 'Nama program studi Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.nama_prodi_en
    IS 'Nama program studi Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.jenjang
    IS 'Jenjang studi: S1, S2, S3, PR.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.kode_fakultas
    IS 'Kode fakultas/sekolah, contoh: STEI, SBM.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.nama_fakultas_id
    IS 'Nama fakultas/sekolah Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.nama_fakultas_en
    IS 'Nama fakultas/sekolah Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.semua_dosen_id
    IS 'Array dosen_id semua pengajar kelas (dari kelas.pengajar).';
COMMENT ON COLUMN analitik.v_akademik_portofolio.semua_dosen_nama_gelar
    IS 'Array nama lengkap dengan gelar semua pengajar kelas.';

-- Metadata portofolio
COMMENT ON COLUMN analitik.v_akademik_portofolio.tanggal_entri
    IS 'Tanggal dosen pertama kali mengisi/menyimpan portofolio (dari evaluasi.portofolio.tgl_entri).';
COMMENT ON COLUMN analitik.v_akademik_portofolio.lengkap
    IS 'TRUE jika portofolio sudah dinyatakan lengkap dan diverifikasi. '
       'FALSE = belum lengkap atau masih dalam pengisian. '
       'Gunakan sebagai sinyal kualitas bersama nilai_portofolio.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.nilai_portofolio
    IS 'Nilai numerik portofolio hasil verifikasi (NULL jika belum dinilai). '
       'Gunakan sebagai sinyal kualitas bersama kolom lengkap.';

-- ── Isian Portofolio Skema Baru (kd_pertanyaan 12–19) ────────────
-- Grup 6: Penyelenggaraan Perkuliahan (kd_pertanyaan 12, 13)
COMMENT ON COLUMN analitik.v_akademik_portofolio.metode_perkuliahan
    IS '[kd_pertanyaan=12 | Grup 6: Penyelenggaraan Perkuliahan] '
       'Pertanyaan: "Metode Perkuliahan" '
       'Deskripsi: Uraian metode yang digunakan dalam pembelajaran, misalnya diskusi, '
       'collaborative learning, kuliah tamu, maupun project. '
       'NULL jika dosen tidak mengisi pertanyaan ini.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.sistem_penilaian
    IS '[kd_pertanyaan=13 | Grup 6: Penyelenggaraan Perkuliahan] '
       'Pertanyaan: "Sistem Penilaian" '
       'Deskripsi: Komponen-komponen penilaian yang digunakan dalam menghasilkan nilai akhir '
       'mata kuliah (UTS, UAS, kuis, tugas, praktikum, presentasi, dll.), '
       'bobot setiap komponen, dan standar konversi nilai ke indeks. '
       'NULL jika dosen tidak mengisi pertanyaan ini.';

-- Grup 7: Ketercapaian Outcomes (kd_pertanyaan 14, 15)
COMMENT ON COLUMN analitik.v_akademik_portofolio.statistik_kelas
    IS '[kd_pertanyaan=14 | Grup 7: Ketercapaian Outcomes] '
       'Pertanyaan: "Statistik Kelas" '
       'Deskripsi: Distribusi nilai ujian, PR, kuis dan bentuk penilaian lainnya, '
       'serta data penting lainnya tentang kelas. '
       'NULL jika dosen tidak mengisi pertanyaan ini.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.analisis_terhadap_statistik_kelas_dan_ketercapaian_outcomes
    IS '[kd_pertanyaan=15 | Grup 7: Ketercapaian Outcomes] '
       'Pertanyaan: "Analisis terhadap Statistik Kelas dan Ketercapaian Outcomes" '
       'Deskripsi: Uraian tentang tingkat keberhasilan pembelajaran dan ketercapaian outcomes '
       'beserta faktor-faktor yang mempengaruhinya, berdasarkan data yang terkumpul. '
       'NULL jika dosen tidak mengisi pertanyaan ini.';

-- Grup 8: Refleksi Dosen (kd_pertanyaan 16, 17)
COMMENT ON COLUMN analitik.v_akademik_portofolio.komentar_terhadap_hasil_kuesioner_mahasiswa
    IS '[kd_pertanyaan=16 | Grup 8: Refleksi Dosen] '
       'Pertanyaan: "Komentar terhadap Hasil Kuesioner Mahasiswa" '
       'Deskripsi: Tanggapan dosen terhadap penilaian mahasiswa yang diberikan '
       'melalui pengisian kuesioner evaluasi matakuliah. '
       'NULL jika dosen tidak mengisi pertanyaan ini.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.refleksi_pelaksanaan_perkuliahan
    IS '[kd_pertanyaan=17 | Grup 8: Refleksi Dosen] '
       'Pertanyaan: "Refleksi Pelaksanaan Perkuliahan" '
       'Deskripsi: Uraian tentang pelaksanaan perkuliahan, meliputi aspek keberhasilan '
       'dan kegagalan rencana, masalah belajar mahasiswa, persoalan yang dihadapi dosen, '
       'serta temuan penting lainnya selama perkuliahan berlangsung. '
       'NULL jika dosen tidak mengisi pertanyaan ini.';

-- Grup 9: Rekomendasi Tindak Lanjut (kd_pertanyaan 18, 19)
COMMENT ON COLUMN analitik.v_akademik_portofolio.usulan_perbaikan_oleh_dosen_berikutnya
    IS '[kd_pertanyaan=18 | Grup 9: Rekomendasi Tindak Lanjut] '
       'Pertanyaan: "Usulan Perbaikan oleh Dosen Berikutnya" '
       'Deskripsi: Hal-hal yang perlu dan dapat dilakukan oleh dosen pengampu pada '
       'perkuliahan mendatang untuk meningkatkan kualitas dan keberhasilan pembelajaran. '
       'NULL jika dosen tidak mengisi pertanyaan ini.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.usulan_perbaikan_oleh_itb
    IS '[kd_pertanyaan=19 | Grup 9: Rekomendasi Tindak Lanjut] '
       'Pertanyaan: "Usulan Perbaikan oleh ITB" '
       'Deskripsi: Hal-hal yang perlu dilakukan oleh ITB (institut, fakultas/sekolah, prodi) '
       'untuk mendukung keberhasilan perkuliahan, meliputi aspek kurikulum, '
       'sarana prasarana, dan fasilitas lainnya. '
       'NULL jika dosen tidak mengisi pertanyaan ini.';

-- ── Komentar Verifikator/Reviewer ────────────────────────────────
COMMENT ON COLUMN analitik.v_akademik_portofolio.verifikator_penyelenggaraan_perkuliahan
    IS '[Komentar verifikator | Grup 6: Penyelenggaraan Perkuliahan] '
       'Komentar reviewer/verifikator terhadap isian dosen pada grup Penyelenggaraan Perkuliahan, '
       'yang mencakup metode_perkuliahan (r12) dan sistem_penilaian (r13). '
       'NULL jika verifikator tidak memberikan komentar.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.verifikator_ketercapaian_outcomes
    IS '[Komentar verifikator | Grup 7: Ketercapaian Outcomes] '
       'Komentar reviewer/verifikator terhadap isian dosen pada grup Ketercapaian Outcomes, '
       'yang mencakup statistik_kelas (r14) dan '
       'analisis_terhadap_statistik_kelas_dan_ketercapaian_outcomes (r15). '
       'NULL jika verifikator tidak memberikan komentar.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.verifikator_refleksi_dosen
    IS '[Komentar verifikator | Grup 8: Refleksi Dosen] '
       'Komentar reviewer/verifikator terhadap isian dosen pada grup Refleksi Dosen, '
       'yang mencakup komentar_terhadap_hasil_kuesioner_mahasiswa (r16) dan '
       'refleksi_pelaksanaan_perkuliahan (r17). '
       'NULL jika verifikator tidak memberikan komentar.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.verifikator_rekomendasi_tindak_lanjut
    IS '[Komentar verifikator | Grup 9: Rekomendasi Tindak Lanjut] '
       'Komentar reviewer/verifikator terhadap isian dosen pada grup Rekomendasi Tindak Lanjut, '
       'yang mencakup usulan_perbaikan_oleh_dosen_berikutnya (r18) dan '
       'usulan_perbaikan_oleh_itb (r19). '
       'NULL jika verifikator tidak memberikan komentar.';


-- ── B4. v_akademik_statistik_prodi ───────────────────────────────
COMMENT ON VIEW analitik.v_akademik_statistik_prodi IS
    'Statistik agregat per program studi per semester: kehadiran, distribusi nilai, dan skor kuesioner. '
    'Grain: 1 baris = 1 (no_prodi, semester, tahun). '
    'Distribusi nilai dihitung dari akumulasi absolut (weighted by class size), '
    'bukan rata-rata persentase per kelas. '
    'Mahasiswa dengan nilai T (pending) ikut dihitung di total_mahasiswa_dinilai '
    'dan denominator dist_pct_* — konsisten dengan v_akademik_kelas. '
    'Periode: 2018/2019 semester 1 s.d. terkini. '
    'ROW SECURITY: ADMIN/DIREKTORAT=semua; DEKAN/JAJ.DEKANAT=filter kode_fakultas; '
    'KAPRODI/JAJ.PRODI/DOSEN=hanya prodinya sendiri.';

COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.no_prodi
    IS 'ID numerik program studi. PK bersama semester dan tahun.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.kode_prodi
    IS 'Kode singkat prodi 2 karakter.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.nama_prodi_id
    IS 'Nama program studi Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.nama_prodi_en
    IS 'Nama program studi Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.jenjang
    IS 'Jenjang studi: S1, S2, S3, PR.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.kode_fakultas
    IS 'Kode fakultas/sekolah.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.nama_fakultas_id
    IS 'Nama fakultas Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.nama_fakultas_en
    IS 'Nama fakultas Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.semester
    IS '1=ganjil, 2=genap, 3=pendek.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.tahun
    IS 'Tahun akademik 4 digit.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.tahun_ajaran
    IS 'Format YYYY/YYYY.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.jumlah_kelas
    IS 'Total kelas yang diselenggarakan prodi pada semester tersebut.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.jumlah_matkul_aktif
    IS 'Jumlah mata kuliah unik yang aktif diajarkan prodi pada semester tersebut.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.jumlah_dosen_aktif
    IS 'Jumlah dosen unik yang mengajar di prodi pada semester tersebut.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.jumlah_mahasiswa_aktif
    IS 'Jumlah mahasiswa aktif (FRS selesai, tidak nonaktif) di prodi pada semester tersebut.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_pct_kehadiran_dosen
    IS 'Rata-rata persentase kehadiran dosen lintas kelas (rata-rata tidak tertimbang per kelas). '
       'NULL jika belum ada data evaluasi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_pct_kehadiran_mahasiswa
    IS 'Rata-rata persentase kehadiran mahasiswa lintas kelas. NULL jika belum ada data evaluasi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_ip_akhir_mahasiswa
    IS 'Rata-rata IP akhir mahasiswa lintas kelas. NULL jika belum ada data evaluasi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_jumlah_a
    IS 'Total akumulasi mahasiswa mendapat nilai A di seluruh kelas prodi semester ini. '
       'Kelas tanpa nilai sah (NULL) tidak ikut dihitung (SUM mengabaikan NULL).';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_jumlah_ab  IS 'Total mahasiswa nilai AB di prodi semester ini.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_jumlah_b   IS 'Total mahasiswa nilai B di prodi semester ini.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_jumlah_bc  IS 'Total mahasiswa nilai BC di prodi semester ini.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_jumlah_c   IS 'Total mahasiswa nilai C di prodi semester ini.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_jumlah_d   IS 'Total mahasiswa nilai D di prodi semester ini.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_jumlah_e   IS 'Total mahasiswa nilai E (tidak lulus) di prodi semester ini.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_jumlah_t
    IS 'Total mahasiswa dengan nilai T (tunda/incomplete) di prodi semester ini. '
       'Ikut dihitung di total_mahasiswa_dinilai dan denominator dist_pct_*.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_jumlah_pass IS 'Total mahasiswa lulus (nilai P, kelas PassFail) di prodi semester ini.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_jumlah_fail IS 'Total mahasiswa tidak lulus (nilai F, kelas PassFail) di prodi semester ini.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_mahasiswa_dinilai
    IS 'Total mahasiswa yang sudah memiliki nilai sah di seluruh kelas prodi semester ini. '
       'Termasuk mahasiswa dengan nilai T. Penyebut untuk perhitungan dist_pct_* tingkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_a
    IS 'Persentase mahasiswa nilai A di tingkat prodi = total_jumlah_a / total_mahasiswa_dinilai * 100. '
       'Tertimbang berdasarkan ukuran kelas. Denominator termasuk mahasiswa nilai T.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_ab  IS 'Persentase mahasiswa nilai AB di tingkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_b   IS 'Persentase mahasiswa nilai B di tingkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_bc  IS 'Persentase mahasiswa nilai BC di tingkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_c   IS 'Persentase mahasiswa nilai C di tingkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_d   IS 'Persentase mahasiswa nilai D di tingkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_e   IS 'Persentase mahasiswa nilai E di tingkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_t
    IS 'Persentase mahasiswa dengan nilai T (tunda/incomplete) di tingkat prodi. '
       'Nilai tinggi menandakan banyak nilai yang belum final di prodi tersebut.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_pass IS 'Persentase mahasiswa lulus (P) di tingkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_fail IS 'Persentase mahasiswa tidak lulus (F) di tingkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_lulus_a_c
    IS 'Persentase lulus ≥C (A+AB+B+BC+C) di tingkat prodi. '
       'Denominator termasuk mahasiswa nilai T. Metrik utama kelulusan prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_lulus_a_d
    IS 'Persentase lulus ≥D (A+AB+B+BC+C+D) di tingkat prodi. '
       'Denominator termasuk mahasiswa nilai T.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q21
    IS 'Rata-rata skor Q21 lintas kelas prodi (skala 1–4): '
       '"Saya memperoleh informasi yang cukup tentang luaran matakuliah."';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q22
    IS 'Rata-rata skor Q22 lintas kelas prodi (skala 1–4): '
       '"Pelaksanaan perkuliahan diarahkan agar mahasiswa mencapai luaran matakuliah."';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q23
    IS 'Rata-rata skor Q23 lintas kelas prodi (skala 1–4): '
       '"Saya mencapai atau menguasai luaran matakuliah ini."';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q24
    IS 'Rata-rata skor Q24 lintas kelas prodi (skala 1–4): '
       '"Pelaksanaan perkuliahan terorganisir dengan baik."';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q25
    IS 'Rata-rata skor Q25 lintas kelas prodi (skala 1–4): '
       '"Dosen berkomunikasi dengan efektif." (rata-rata per dosen, lalu per kelas, lalu per prodi).';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q26
    IS 'Rata-rata skor Q26 lintas kelas prodi (skala 1–4): '
       '"Dosen peduli terhadap pencapaian mahasiswa akan luaran matakuliah."';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q27
    IS 'Rata-rata skor Q27 lintas kelas prodi (skala 1–4): '
       '"Dosen berlaku adil (fair) kepada mahasiswa."';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q28
    IS 'Rata-rata skor Q28 lintas kelas prodi (skala 1–4): '
       '"Beban kerja untuk matakuliah ini sesuai dengan SKS-nya."';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q29
    IS 'Rata-rata skor Q29 lintas kelas prodi (skala 1–4): '
       '"Sarana prasarana untuk matakuliah tersedia dengan memadai."';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q30
    IS 'Rata-rata skor Q30 lintas kelas prodi (skala 1–4): '
       '"Tersedia cukup fasilitas pendukung di luar kuliah yang memungkinkan '
       'saya mengikuti matakuliah ini dengan baik."';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q35
    IS 'Rata-rata skor Q35 lintas kelas prodi (skala 1–4): '
       '"Saya berusaha dengan sungguh-sungguh mengikuti matakuliah ini."';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q37
    IS 'Rata-rata skor Q37 lintas kelas prodi (skala 1–4): '
       '"Saya memperoleh pengalaman belajar yang positif dalam matakuliah ini."';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_capaian
    IS 'Rata-rata skor dimensi Capaian Pembelajaran lintas kelas prodi '
       '(dari evaluasi.nilai_dosen.skor_kues key "1"). Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_pelaksanaan
    IS 'Rata-rata skor dimensi Pelaksanaan Perkuliahan lintas kelas prodi '
       '(dari evaluasi.nilai_dosen.skor_kues key "2"). Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_sarana_prasarana
    IS 'Rata-rata skor dimensi Sarana & Prasarana lintas kelas prodi '
       '(dari rata-rata Q29 dan Q30). Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_perilaku_mahasiswa
    IS 'Rata-rata skor dimensi Perilaku Mahasiswa lintas kelas prodi '
       '(dari evaluasi.nilai_dosen.skor_kues key "3"). Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_overall
    IS 'Rata-rata skor keseluruhan (semua pertanyaan Q21-Q37) lintas kelas prodi. Skala 1–4.';


-- ── B5. v_akademik_statistik_dosen ───────────────────────────────
COMMENT ON VIEW analitik.v_akademik_statistik_dosen IS
    'Statistik kinerja dosen per semester: beban mengajar, kehadiran, dan skor evaluasi. '
    'Grain: 1 baris = 1 (dosen_id, semester, tahun). '
    'Periode: 2018/2019 semester 1 s.d. terkini. '
    'ROW SECURITY: ADMIN/DIREKTORAT=semua; DEKAN/JAJ.DEKANAT=filter kode_fakultas_dosen (homebase); '
    'KAPRODI/JAJ.PRODI=filter berdasarkan prodi yang sedang diajar (no_prodi_diajar); '
    'DOSEN=hanya data dirinya sendiri (dosen_id = v_dosen_id). '
    'COLUMN SECURITY: kolom evaluasi sensitif (avg_skor_*, avg_pct_kehadiran_dosen, '
    'avg_ip_mhs, dll.) di-mask (NULL) untuk role DOSEN ketika melihat dosen lain; '
    'hanya data diri sendiri yang tampil penuh.';

COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.dosen_id
    IS 'ID dosen (FK ke utama.dosen). PK bersama semester dan tahun.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.nama_dosen_gelar
    IS 'Nama lengkap dosen dengan gelar depan dan belakang.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.nip
    IS 'Nomor Induk Pegawai dosen.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.kk_id
    IS 'ID Kelompok Keahlian dosen. NULL jika tidak terdaftar di KK.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.nama_kk_id
    IS 'Nama Kelompok Keahlian Bahasa Indonesia. NULL jika kk_id NULL.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.nama_kk_en
    IS 'Nama Kelompok Keahlian Bahasa Inggris. NULL jika kk_id NULL.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.kode_fakultas_dosen
    IS 'Kode fakultas homebase dosen (dari utama.dosen.kd_fak). '
       'Digunakan sebagai filter untuk DEKAN/JAJ.DEKANAT.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.no_prodi
    IS 'ID numerik program studi homebase dosen (dari utama.dosen.no_ps). '
       'NULL jika dosen tidak memiliki homebase prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.kode_prodi
    IS 'Kode singkat prodi homebase dosen. NULL jika no_prodi NULL.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.semester
    IS '1=ganjil, 2=genap, 3=pendek.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.tahun
    IS 'Tahun akademik 4 digit.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.tahun_ajaran
    IS 'Format YYYY/YYYY.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.jumlah_kelas
    IS 'Jumlah kelas yang diajar dosen semester ini (termasuk semua prodi yang diajar).';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.jumlah_matkul
    IS 'Jumlah mata kuliah unik yang diajar dosen semester ini.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.total_sks_diajar
    IS 'Total SKS semua kelas yang diajar (termasuk paralel). Mencerminkan beban total dosen.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_pct_kehadiran_dosen
    IS '[SENSITIF] Rata-rata persentase kehadiran dosen lintas kelas semester ini. '
       'Di-mask (NULL) untuk role DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_pct_kehadiran_mahasiswa
    IS 'Rata-rata persentase kehadiran mahasiswa di kelas-kelas yang diajar dosen ini. '
       'Tidak di-mask — informasi tentang mahasiswa, bukan evaluasi dosen pribadi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_ip_mhs
    IS '[SENSITIF] Rata-rata IP akhir mahasiswa di kelas yang diajar dosen ini. '
       'Di-mask (NULL) untuk role DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_skor_q25
    IS '[SENSITIF] Rata-rata skor Q25 ("Dosen berkomunikasi dengan efektif") '
       'lintas kelas dosen ini. Dari evaluasi.nilai_dosen.kuesioner (per-dosen). Skala 1–4. '
       'Di-mask (NULL) untuk role DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_skor_q26
    IS '[SENSITIF] Rata-rata skor Q26 ("Dosen peduli terhadap pencapaian mahasiswa") '
       'lintas kelas. Skala 1–4. Di-mask untuk role DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_skor_q27
    IS '[SENSITIF] Rata-rata skor Q27 ("Dosen berlaku adil kepada mahasiswa") '
       'lintas kelas. Skala 1–4. Di-mask untuk role DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_skor_capaian
    IS '[SENSITIF] Rata-rata skor dimensi Capaian Pembelajaran dosen '
       '(dari evaluasi.nilai_dosen.skor_kues key "1"). Skala 1–4. '
       'NULL jika data format baru belum tersedia. Di-mask untuk DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_skor_pelaksanaan
    IS '[SENSITIF] Rata-rata skor dimensi Pelaksanaan Perkuliahan dosen (key "2"). '
       '/Skala 1–4. Di-mask untuk DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_skor_sarana_prasarana
    IS '[SENSITIF] Rata-rata skor Sarana & Prasarana dari kelas yang diajar dosen ini '
       '((Q29+Q30)/2). Di-mask untuk DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_skor_perilaku_mahasiswa
    IS '[SENSITIF] Rata-rata skor dimensi Perilaku Mahasiswa dosen (key "3"). '
       'Skala 1–4. Di-mask untuk DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_skor_overall
    IS '[SENSITIF] Rata-rata skor keseluruhan dosen, dihitung dari '
       '(capaian + pelaksanaan + perilaku) / N-dimensi-tersedia. '
       'Di-mask untuk DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.jumlah_kelas_dengan_skor
    IS '[SENSITIF] Jumlah kelas dosen yang sudah memiliki data evaluasi (skor_kues terisi). '
       'Di-mask untuk DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_nilai_akhir
    IS '[SENSITIF] Rata-rata nilai akhir dosen dari evaluasi.nilai_dosen.nilai_akhir. '
       'Sering NULL karena kolom ini tidak konsisten diisi. Di-mask untuk DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.kelas_id_list
    IS 'Array kelas_id semua kelas yang diajar dosen semester ini.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.kode_matkul_list
    IS 'Array kode MK unik yang diajar dosen semester ini.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.no_prodi_diajar
    IS 'Array ID numerik prodi yang kelas-kelasnya diajar dosen (bisa berbeda dari homebase). '
       'Digunakan sebagai filter KAPRODI/JAJ.PRODI: WHERE no_prodi_diajar @> ARRAY[v_no_prodi].';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.kode_prodi_diajar
    IS 'Array kode singkat prodi yang diajar, paralel dengan no_prodi_diajar.';

-- ================================================================
-- COMMENT ON — analitik.v_akademik_komponen_evaluasi_kelas
-- Konteks untuk agen text-to-SQL dan agen RAG
-- ================================================================


-- ── VIEW ─────────────────────────────────────────────────────────

COMMENT ON VIEW analitik.v_akademik_komponen_evaluasi_kelas IS
    'Komposisi bobot komponen penilaian (UTS/UAS/Tugas/Kuis/Praktikum/Projek/Partisipatif) per kelas. '
    'Grain: 1 baris = 1 kelas yang memiliki minimal satu komponen penilaian aktif (bobot > 0). '
    'Kelas tanpa data komponen penilaian di evaluasi.komponen_evaluasi TIDAK muncul di view ini. '
    'Sumber: evaluasi.komponen_evaluasi (bobot per entri) JOIN analitik_mv.mv_akademik_kelas (dimensi). '
    'Periode: 2018/2019 semester 1 s.d. terkini. '
    ''
    'PENTING : cara baca kolom bobot_*: '
    'Satu kelas bisa punya banyak entri komponen yang sama, contoh "Tugas 1" (25%) + '
    '"Tugas 2" (25%) = bobot_tugas 50. Kolom bobot_* sudah berisi SUM seluruh entri '
    'per tipe komponen, sehingga 1 baris langsung mencerminkan porsi total per komponen. '
    'Nilai 0 = komponen tidak digunakan di kelas ini. '
    ''
    'CARA AGGREGASI KE PRODI/FAKULTAS: '
    'Gunakan AVG(bobot_*) GROUP BY (no_prodi|kode_fakultas), tahun_ajaran, semester. '
    'Contoh: SELECT kode_fakultas, AVG(bobot_uts) AS rata_uts '
    'FROM analitik.v_akademik_komponen_evaluasi_kelas '
    'WHERE tahun_ajaran = ''2024/2025'' AND semester = 1 '
    'GROUP BY kode_fakultas. '
    ''
    'CARA FILTER KOMPONEN YANG DIPAKAI: '
    'Komponen dianggap "digunakan" jika avg_bobot_* > 0 setelah aggregasi. '
    'Frontend/output hanya menampilkan bucket yang AVG > 0 agar stacked bar tidak penuh slot kosong. '
    ''
    'INDIKATOR KUALITAS DATA: '
    'total_bobot_kelas idealnya mendekati 100. Nilai jauh di bawah 100 mengindikasikan '
    'dosen belum selesai mengisi komponen penilaian (data tidak lengkap).';


-- ── Identitas kelas ───────────────────────────────────────────────

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.kelas_id
    IS 'PK. ID kelas (FK ke kelas.kelas dan analitik_mv.mv_akademik_kelas). '
       'Unik di view ini karena grain per kelas.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.no_kelas
    IS 'Nomor urut kelas dalam satu mata kuliah per semester, contoh: 1, 2, 3. '
       'Kelas paralel dari MK yang sama dibedakan oleh no_kelas.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.kode_matkul
    IS 'Kode mata kuliah 6 karakter, contoh: IF2210, MA1101. Dari utama.mata_kuliah.kd_kuliah.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.nama_matkul_id
    IS 'Nama mata kuliah Bahasa Indonesia.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.nama_matkul_en
    IS 'Nama mata kuliah Bahasa Inggris.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.sks
    IS 'Jumlah SKS mata kuliah.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.tahun_kurikulum
    IS 'Tahun kurikulum yang berlaku untuk mata kuliah ini, contoh: 2024.';


-- ── Dimensi prodi & fakultas ──────────────────────────────────────

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.no_prodi
    IS 'ID numerik program studi penyelenggara kelas (FK ke utama.program_studi.no_ps). ';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.kode_prodi
    IS 'Kode singkat prodi 2 karakter, contoh: IF, EL, MA. Dari utama.program_studi.kd_ps.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.nama_prodi_id
    IS 'Nama program studi Bahasa Indonesia.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.nama_prodi_en
    IS 'Nama program studi Bahasa Inggris.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.jenjang
    IS 'Jenjang program studi: S1, S2, S3, PR (Profesi). Dari utama.program_studi.kd_strata.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.kode_fakultas
    IS 'Kode fakultas/sekolah, contoh: STEI, SBM, FSRD. Dari utama.program_studi.kd_fak. ';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.nama_fakultas_id
    IS 'Nama fakultas/sekolah Bahasa Indonesia.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.nama_fakultas_en
    IS 'Nama fakultas/sekolah Bahasa Inggris.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.semua_dosen_id
    IS 'Array integer ID semua dosen yang mengajar kelas ini. '
       'Gunakan operator @> untuk cek apakah dosen tertentu mengajar kelas ini: '
       'WHERE semua_dosen_id @> ARRAY[<dosen_id>].';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.semua_dosen_nama_gelar
    IS 'Array nama lengkap dengan gelar dari semua dosen pengampu kelas, '
       'berurutan paralel dengan semua_dosen_id.';


-- ── Dimensi waktu ─────────────────────────────────────────────────

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.tahun
    IS '4 digit tahun akademik diselenggarakannnya kelas, contoh: 2023.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.semester
    IS 'Semester: 1=ganjil, 2=genap, 3=pendek.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.tahun_ajaran
    IS 'Format YYYY/YYYY, contoh: 2023/2024. '
       'Semester 1 → tahun/tahun+1; semester 2/3 → tahun-1/tahun.';


-- ── Bobot komponen penilaian ──────────────────────────────────────

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.bobot_uts
    IS 'Total bobot Ujian Tengah Semester (kd_komponen_evaluasi_mk=''UTS'') di kelas ini. '
       'SUM semua entri UTS dengan bobot > 0. Skala 0–100. '
       '0 = kelas ini tidak menggunakan UTS sebagai komponen penilaian.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.bobot_uas
    IS 'Total bobot Ujian Akhir Semester (kd_komponen_evaluasi_mk=''UAS'') di kelas ini. '
       'SUM semua entri UAS dengan bobot > 0. Skala 0–100. '
       '0 = kelas ini tidak menggunakan UAS sebagai komponen penilaian.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.bobot_tugas
    IS 'Total bobot semua Tugas (kd_komponen_evaluasi_mk=''TGS'') di kelas ini. '
       'SUM semua entri tugas dengan bobot > 0 — termasuk "Tugas 1", "Tugas 2", dst. yang semuanya ber-kode TGS. '
       'Contoh: Tugas 1 (25%) + Tugas 2 (25%) = bobot_tugas 50. '
       '0 = kelas ini tidak menggunakan tugas sebagai komponen penilaian.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.bobot_kuis
    IS 'Total bobot Kuis (kd_komponen_evaluasi_mk=''QIZ'') di kelas ini. '
       'SUM semua entri kuis dengan bobot > 0. Skala 0–100. '
       '0 = kelas ini tidak menggunakan kuis.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.bobot_praktikum
    IS 'Total bobot Praktikum (kd_komponen_evaluasi_mk=''PRK'') di kelas ini. '
       'SUM semua entri praktikum dengan bobot > 0. Skala 0–100. '
       '0 = kelas ini tidak memiliki komponen praktikum.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.bobot_projek
    IS 'Total bobot Hasil Projek (kd_komponen_evaluasi_mk=''PRO'') di kelas ini. '
       'SUM semua entri projek dengan bobot > 0. Skala 0–100. '
       '0 = kelas ini tidak menggunakan komponen projek.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.bobot_partisipatif
    IS 'Total bobot Aktivitas Partisipatif (kd_komponen_evaluasi_mk=''PAR'') di kelas ini. '
       'Mencakup partisipasi aktif, diskusi, presentasi singkat, dan sejenisnya. '
       'SUM semua entri partisipatif dengan bobot > 0. Skala 0–100. '
       '0 = kelas ini tidak menggunakan komponen partisipatif.';

COMMENT ON COLUMN analitik.v_akademik_komponen_evaluasi_kelas.total_bobot_kelas
    IS 'Jumlah total semua bobot komponen aktif di kelas ini (SUM bobot_uts + bobot_uas + '
       'bobot_tugas + bobot_kuis + bobot_praktikum + bobot_projek + bobot_partisipatif). '
       'Idealnya = 100 untuk kelas yang sudah mengisi komponen penilaian dengan lengkap. '
       'Nilai < 100: dosen belum selesai mengisi, data tidak lengkap, interpretasi hati-hati. '
       'Nilai > 100: kemungkinan entry error di sistem. ';