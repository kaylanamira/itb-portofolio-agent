-- ================================================================
-- COMMENT ON — Schema analitik.*
-- Konteks untuk agen text-to-SQL dan agen RAG
--
-- Konvensi penamaan kolom:
--   no_prodi    = integer ID program studi (dari utama.program_studi.no_ps)
--   kode_prodi  = kode string singkat prodi, 2 karakter (dari kd_ps), contoh: IF, EL
--   kode_matkul = kode mata kuliah 6 karakter (dari kd_kuliah), contoh: IF2210
--   kode_fakultas = kode string fakultas/sekolah (dari kd_fak), contoh: STEI, SBM
--   tahun_ajaran  = format 'YYYY/YYYY', contoh: '2023/2024'
--   semester      = 1=ganjil, 2=genap, 3=pendek
--   jenjang       = S1/S2/S3/PR (dari kd_strata)
--
-- Security: semua view di schema ini di-filter otomatis per user role.
-- Agen tidak perlu menambahkan filter role — sudah ditangani Security Definer Function.
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
COMMENT ON COLUMN analitik.v_akademik_jenis_dan_sifat_matkul.kode_fakultas
    IS 'Kode fakultas/sekolah, contoh: STEI, SBM, FSRD. Dari utama.program_studi.kd_fak.';
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
    'Aman diakses semua role tanpa restriction tambahan.';

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
    IS 'Array integer dosen_id semua pengajar kelas, urut dosen utama di indeks 0. ';
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
    'Tidak mengandung data nilai atau skor kuesioner. Aman diakses semua role.';

COMMENT ON COLUMN analitik.v_info_umum_institusi.no_prodi
    IS 'ID numerik program studi (FK ke utama.program_studi.no_ps).';
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
    'Tidak mengandung skor kuesioner atau kehadiran. Aman diakses semua role.';

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
COMMENT ON COLUMN analitik.v_info_umum_dosen.kode_matkul_list
    IS 'Array kode MK unik yang diajar dosen semester tersebut, contoh: {IF2210,IF3110}.';
COMMENT ON COLUMN analitik.v_info_umum_dosen.no_prodi_diajar
    IS 'Array ID numerik prodi yang kelas-kelasnya diajar dosen (bisa beda dari homebase). '
       'Gunakan untuk filter KAPRODI: WHERE no_prodi_diajar @> ARRAY[v_no_prodi].';
COMMENT ON COLUMN analitik.v_info_umum_dosen.kode_prodi_diajar
    IS 'Array kode singkat prodi yang diajar, paralel dengan no_prodi_diajar.';


-- ── A5. v_info_umum_wisuda ────────────────────────────────────────
COMMENT ON VIEW analitik.v_info_umum_wisuda IS
    'Ringkasan jumlah responden survey wisudawan per prodi per periode. '
    'Grain: 1 baris = 1 (no_prodi, periode_ijazah_id_final, periode_seremoni_id). '
    'Tidak mengandung jawaban individual. Aman diakses semua role. '
    'Filter is_seremoni_asumtif=FALSE untuk hanya melihat data seremoni final.';

COMMENT ON COLUMN analitik.v_info_umum_wisuda.no_prodi
    IS 'ID numerik program studi wisudawan.';
COMMENT ON COLUMN analitik.v_info_umum_wisuda.kode_prodi
    IS 'Kode singkat prodi wisudawan.';
COMMENT ON COLUMN analitik.v_info_umum_wisuda.nama_prodi_id
    IS 'Nama program studi Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_info_umum_wisuda.nama_prodi_en
    IS 'Nama program studi Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_info_umum_wisuda.jenjang
    IS 'Jenjang studi: S1, S2, S3, PR.';
COMMENT ON COLUMN analitik.v_info_umum_wisuda.kode_fakultas
    IS 'Kode fakultas/sekolah wisudawan.';
COMMENT ON COLUMN analitik.v_info_umum_wisuda.nama_fakultas_id
    IS 'Nama fakultas Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_info_umum_wisuda.nama_fakultas_en
    IS 'Nama fakultas Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_info_umum_wisuda.periode_ijazah_id_final
    IS 'Periode ijazah final format YYYYMM, contoh: 202502=Februari 2025. '
       'Sudah diimputasi jika data asli NULL.';
COMMENT ON COLUMN analitik.v_info_umum_wisuda.tahun_ijazah
    IS 'Tahun ijazah, diekstrak dari periode_ijazah_id_final.';
COMMENT ON COLUMN analitik.v_info_umum_wisuda.bulan_ijazah
    IS 'Bulan ijazah (1–12), diekstrak dari periode_ijazah_id_final.';
COMMENT ON COLUMN analitik.v_info_umum_wisuda.periode_seremoni_id
    IS 'ID seremoni wisuda format YYYYMM. NULL jika mapping belum tersedia.';
COMMENT ON COLUMN analitik.v_info_umum_wisuda.tahun_seremoni
    IS 'Tahun pelaksanaan seremoni wisuda.';
COMMENT ON COLUMN analitik.v_info_umum_wisuda.bulan_seremoni
    IS 'Bulan pelaksanaan seremoni wisuda (1–12).';
COMMENT ON COLUMN analitik.v_info_umum_wisuda.nama_seremoni
    IS 'Nama seremoni wisuda Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_info_umum_wisuda.is_seremoni_asumtif
    IS 'TRUE = seremoni masih dummy/asumtif (data periode belum final). '
       'Filter WHERE is_seremoni_asumtif = FALSE untuk data final saja.';
COMMENT ON COLUMN analitik.v_info_umum_wisuda.jumlah_responden
    IS 'Jumlah wisudawan unik yang mengisi survey pada prodi dan periode tersebut.';


-- ================================================================
-- B. VIEW WRAPPER — Difilter otomatis per role user
-- ================================================================

-- ── B1. v_akademik_kelas ─────────────────────────────────────────
COMMENT ON VIEW analitik.v_akademik_kelas IS
    'Data lengkap per kelas: kehadiran, distribusi nilai, skor kuesioner, dan dimensi evaluasi. '
    'Grain: 1 baris = 1 kelas. '
    'ROW SECURITY: ADMIN/DIREKTORAT=semua; DEKAN/JAJ.DEKANAT=filter kode_fakultas; '
    'KAPRODI/JAJ.PRODI/DOSEN=filter no_prodi. '
    'COLUMN SECURITY: kolom skor_dosen_q25/26/27 (JSONB) di-mask untuk role DOSEN '
    '— hanya berisi entry dosen tersebut saja, bukan skor dosen lain dalam kelas.';

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
    IS 'Persentase kehadiran mahasiswa (0–100). Sumber: evaluasi.nilai_kelas.hadir_mhs. NULL jika belum ada data evaluasi.';
COMMENT ON COLUMN analitik.v_akademik_kelas.pct_kehadiran_dosen
    IS 'Persentase kehadiran dosen (0–100). Sumber: evaluasi.nilai_kelas.hadir_dosen. NULL jika belum ada data evaluasi.';
COMMENT ON COLUMN analitik.v_akademik_kelas.avg_ip_akhir_mahasiswa
    IS 'Rata-rata IP akhir mahasiswa yang mengikuti kelas ini. Sumber: evaluasi.nilai_kelas.ip_mhs. NULL jika belum ada data.';
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
    IS 'Jumlah mahasiswa dengan nilai sah (exclude T/incomplete). NULL jika is_distribusi_nilai_sah=FALSE.';
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
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_jumlah_pass
    IS 'Jumlah mahasiswa lulus (nilai P, untuk kelas PassFail). NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_jumlah_fail
    IS 'Jumlah mahasiswa tidak lulus (nilai F, untuk kelas PassFail). NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_pct_a
    IS 'Persentase mahasiswa mendapat nilai A (0–100). NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_pct_ab
    IS 'Persentase mahasiswa mendapat nilai AB. NULL jika is_distribusi_nilai_sah=FALSE.';
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
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_pct_pass
    IS 'Persentase mahasiswa lulus (nilai P). NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_pct_fail
    IS 'Persentase mahasiswa tidak lulus (nilai F). NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_pct_lulus_a_c
    IS 'Persentase mahasiswa lulus ≥C (A+AB+B+BC+C) untuk ABCDE, atau P untuk PassFail. '
       'Metrik utama tingkat kelulusan. NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.dist_pct_lulus_a_d
    IS 'Persentase mahasiswa lulus ≥D (A+AB+B+BC+C+D) untuk ABCDE, atau P untuk PassFail. '
       'NULL jika is_distribusi_nilai_sah=FALSE.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q21
    IS 'Skor kuesioner mahasiswa Q21 (rata-rata kelas, skala 1–4): '
       '"Saya memperoleh informasi yang cukup tentang luaran matakuliah." '
       'NULL jika belum ada data kuesioner untuk kelas ini.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q22
    IS 'Skor kuesioner mahasiswa Q22 (rata-rata kelas, skala 1–4): '
       '"Pelaksanaan perkuliahan diarahkan agar mahasiswa mencapai luaran matakuliah." '
       'NULL jika belum ada data kuesioner.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q23
    IS 'Skor kuesioner mahasiswa Q23 (rata-rata kelas, skala 1–4): '
       '"Saya mencapai atau menguasai luaran matakuliah ini." '
       'NULL jika belum ada data kuesioner.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q24
    IS 'Skor kuesioner mahasiswa Q24 (rata-rata kelas, skala 1–4): '
       '"Pelaksanaan perkuliahan terorganisir dengan baik." '
       'NULL jika belum ada data kuesioner.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q25
    IS 'Skor kuesioner mahasiswa Q25 (rata-rata dari semua dosen dalam kelas, skala 1–4): '
       '"Dosen berkomunikasi dengan efektif." '
       'Rata-rata lintas dosen jika kelas tim-teaching. NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q26
    IS 'Skor kuesioner mahasiswa Q26 (rata-rata dari semua dosen, skala 1–4): '
       '"Dosen peduli terhadap pencapaian mahasiswa akan luaran matakuliah." '
       'NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q27
    IS 'Skor kuesioner mahasiswa Q27 (rata-rata dari semua dosen, skala 1–4): '
       '"Dosen berlaku adil (fair) kepada mahasiswa." '
       'NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q28
    IS 'Skor kuesioner mahasiswa Q28 (rata-rata kelas, skala 1–4): '
       '"Beban kerja untuk matakuliah ini sesuai dengan SKS-nya." '
       'NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q29
    IS 'Skor kuesioner mahasiswa Q29 (rata-rata kelas, skala 1–4): '
       '"Sarana prasarana untuk matakuliah tersedia dengan memadai." '
       'Komponen dari avg_skor_sarana_prasarana. NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q30
    IS 'Skor kuesioner mahasiswa Q30 (rata-rata kelas, skala 1–4): '
       '"Tersedia cukup fasilitas pendukung di luar kuliah." '
       'Komponen dari avg_skor_sarana_prasarana. NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q35
    IS 'Skor kuesioner mahasiswa Q35 (rata-rata kelas, skala 1–4): '
       '"Saya berusaha dengan sungguh-sungguh mengikuti matakuliah ini." '
       'Mengukur keterlibatan mahasiswa. NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_q37
    IS 'Skor kuesioner mahasiswa Q37 (rata-rata kelas, skala 1–4): '
       '"Saya memperoleh pengalaman belajar yang positif dalam matakuliah ini." '
       'Mengukur kepuasan belajar mahasiswa. NULL jika belum ada data.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_dosen_q25
    IS '[JSONB] Skor Q25 per dosen dalam kelas: {"dosen_id": skor, ...}. '
       'Contoh: {"123": 3.67, "456": 4.00}. Key = dosen_id::TEXT. '
       'SECURITY: role DOSEN hanya melihat entry miliknya sendiri; role lain melihat semua. '
       'NULL jika tidak ada data kuesioner per dosen.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_dosen_q26
    IS '[JSONB] Skor Q26 per dosen dalam kelas: {"dosen_id": skor, ...}. '
       'SECURITY: di-mask untuk role DOSEN — hanya berisi entry miliknya.';
COMMENT ON COLUMN analitik.v_akademik_kelas.skor_dosen_q27
    IS '[JSONB] Skor Q27 per dosen dalam kelas: {"dosen_id": skor, ...}. '
       'SECURITY: di-mask untuk role DOSEN — hanya berisi entry miliknya.';
COMMENT ON COLUMN analitik.v_akademik_kelas.avg_skor_capaian
    IS 'Rata-rata skor dimensi Capaian Pembelajaran dari evaluasi.nilai_dosen.skor_kues (key "1"). '
       'Rata-rata dari skor semua dosen dalam kelas. NULL jika belum ada data format baru.';
COMMENT ON COLUMN analitik.v_akademik_kelas.avg_skor_pelaksanaan
    IS 'Rata-rata skor dimensi Pelaksanaan Perkuliahan dari evaluasi.nilai_dosen.skor_kues (key "2"). '
       'NULL jika belum ada data format baru.';
COMMENT ON COLUMN analitik.v_akademik_kelas.avg_skor_sarana_prasarana
    IS 'Rata-rata skor dimensi Sarana & Prasarana, dihitung dari (skor_q29 + skor_q30) / 2. '
       'NULL jika belum ada data kuesioner.';
COMMENT ON COLUMN analitik.v_akademik_kelas.avg_skor_perilaku_mahasiswa
    IS 'Rata-rata skor dimensi Perilaku Mahasiswa dari evaluasi.nilai_dosen.skor_kues (key "3"). '
       'NULL jika belum ada data format baru.';
COMMENT ON COLUMN analitik.v_akademik_kelas.avg_skor_overall
    IS 'Rata-rata skor keseluruhan dari semua pertanyaan kuesioner yang tersedia (Q21–Q37). '
       'Hanya mempertimbangkan pertanyaan yang tidak NULL. NULL jika tidak ada data kuesioner sama sekali.';


-- ── B2. v_akademik_komentar_mahasiswa ────────────────────────────
COMMENT ON VIEW analitik.v_akademik_komentar_mahasiswa IS
    'Komentar teks bebas mahasiswa per kelas dari kuesioner (pertanyaan 103). '
    'Grain: 1 baris = 1 jawaban komentar per mahasiswa per kelas. '
    'Satu kelas bisa memiliki banyak komentar (1 per mahasiswa yang mengisi). '
    'Teks sudah distrip HTML via analitik_mv.strip_html(). '
    'ROW SECURITY: ADMIN/DIREKTORAT=semua; DEKAN/JAJ.DEKANAT=filter kode_fakultas; '
    'KAPRODI/JAJ.PRODI/DOSEN=filter no_prodi; DOSEN=hanya kelas yang ia ajarkan (semua_dosen_id).';

COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.jawaban_id
    IS 'PK. ID jawaban kuesioner (FK ke evaluasi.jwb_kuesioner).';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.kelas_id
    IS 'ID kelas (FK ke kelas.kelas).';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.tahun
    IS 'Tahun akademik.';
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
    IS 'Isi komentar teks bebas dari mahasiswa. Sudah distrip HTML. '
       'Diambil dari evaluasi.jwb_kuesioner.jawaban key ''103''. '
       'Sumber utama untuk analisis RAG/sentimen komentar mahasiswa.';
COMMENT ON COLUMN analitik.v_akademik_komentar_mahasiswa.ts_jawaban
    IS 'Timestamp saat mahasiswa mengisi kuesioner.';


-- ── B3. v_akademik_portofolio ─────────────────────────────────────
-- (Comments dari beberapa_informasi_comment.sql — sudah di-apply ke view ini)
-- Tambahan comment pada view-level:
COMMENT ON VIEW analitik.v_akademik_portofolio IS
    'Portofolio dosen per kelas — refleksi, analisis, dan rekomendasi pengajaran. '
    'Grain: 1 baris = 1 kelas (hanya kelas yang memiliki portofolio terisi). '
    'Dua era: skema_pertanyaan=''baru'' (kd_pertanyaan 12–19, sejak 2018) dan '
    '''lama'' (kd_pertanyaan 1–11, sebelum 2018). Semua teks sudah distrip HTML. '
    'ROW SECURITY: ADMIN/DIREKTORAT=semua; DEKAN/JAJ.DEKANAT=filter kode_fakultas; '
    'KAPRODI/JAJ.PRODI=filter no_prodi; DOSEN=filter no_prodi (portofolio kelas di prodinya).';

COMMENT ON COLUMN analitik.v_akademik_portofolio.no_prodi
    IS 'ID numerik program studi penyelenggara kelas.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.nama_prodi_en
    IS 'Nama program studi Bahasa Inggris.';


-- ── B4. v_akademik_statistik_prodi ───────────────────────────────
COMMENT ON VIEW analitik.v_akademik_statistik_prodi IS
    'Statistik agregat per program studi per semester: kehadiran, distribusi nilai, dan skor kuesioner. '
    'Grain: 1 baris = 1 (no_prodi, semester, tahun). '
    'Distribusi nilai dihitung dari akumulasi absolut (weighted by class size), bukan rata-rata persentase per kelas. '
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
    IS 'Rata-rata persentase kehadiran dosen lintas kelas (rata-rata tidak tertimbang per kelas). NULL jika belum ada data evaluasi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_pct_kehadiran_mahasiswa
    IS 'Rata-rata persentase kehadiran mahasiswa lintas kelas. NULL jika belum ada data evaluasi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_ip_akhir_mahasiswa
    IS 'Rata-rata IP akhir mahasiswa lintas kelas. NULL jika belum ada data evaluasi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_jumlah_a
    IS 'Total akumulasi mahasiswa mendapat nilai A di seluruh kelas prodi semester ini. '
       'Mengabaikan kelas yang belum ada nilai sah (NULL dikecualikan dari SUM).';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_jumlah_ab IS 'Total mahasiswa nilai AB.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_jumlah_b  IS 'Total mahasiswa nilai B.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_jumlah_bc IS 'Total mahasiswa nilai BC.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_jumlah_c  IS 'Total mahasiswa nilai C.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_jumlah_d  IS 'Total mahasiswa nilai D.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_jumlah_e  IS 'Total mahasiswa nilai E (tidak lulus).';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_jumlah_pass IS 'Total mahasiswa lulus (nilai P, untuk kelas PassFail).';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_jumlah_fail IS 'Total mahasiswa tidak lulus (nilai F, untuk kelas PassFail).';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.total_mahasiswa_dinilai
    IS 'Total mahasiswa yang sudah memiliki nilai sah di seluruh kelas prodi semester ini. '
       'Penyebut untuk perhitungan dist_pct_* tingkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_a
    IS 'Persentase mahasiswa nilai A di tingkat prodi = total_jumlah_a / total_mahasiswa_dinilai * 100. '
       'Tertimbang berdasarkan ukuran kelas (kelas besar memiliki bobot lebih besar).';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_ab  IS 'Persentase mahasiswa nilai AB di tingkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_b   IS 'Persentase mahasiswa nilai B di tingkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_bc  IS 'Persentase mahasiswa nilai BC di tingkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_c   IS 'Persentase mahasiswa nilai C di tingkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_d   IS 'Persentase mahasiswa nilai D di tingkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_e   IS 'Persentase mahasiswa nilai E di tingkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_pass IS 'Persentase mahasiswa lulus (P) di tingkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_fail IS 'Persentase mahasiswa tidak lulus (F) di tingkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_lulus_a_c
    IS 'Persentase lulus ≥C (A+AB+B+BC+C) di tingkat prodi. Metrik utama kelulusan.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.dist_pct_lulus_a_d
    IS 'Persentase lulus ≥D (A+AB+B+BC+C+D) di tingkat prodi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q21
    IS 'Rata-rata skor Q21 lintas kelas prodi: "Informasi luaran matakuliah." Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q22
    IS 'Rata-rata skor Q22 lintas kelas prodi: "Perkuliahan diarahkan ke luaran." Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q23
    IS 'Rata-rata skor Q23 lintas kelas prodi: "Mahasiswa mencapai luaran matakuliah." Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q24
    IS 'Rata-rata skor Q24 lintas kelas prodi: "Perkuliahan terorganisir dengan baik." Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q25
    IS 'Rata-rata skor Q25 lintas kelas prodi: "Dosen berkomunikasi dengan efektif." Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q26
    IS 'Rata-rata skor Q26 lintas kelas prodi: "Dosen peduli terhadap pencapaian mahasiswa." Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q27
    IS 'Rata-rata skor Q27 lintas kelas prodi: "Dosen berlaku adil kepada mahasiswa." Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q28
    IS 'Rata-rata skor Q28 lintas kelas prodi: "Beban kerja sesuai SKS." Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q29
    IS 'Rata-rata skor Q29 lintas kelas prodi: "Sarana prasarana memadai." Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q30
    IS 'Rata-rata skor Q30 lintas kelas prodi: "Fasilitas pendukung di luar kuliah memadai." Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q35
    IS 'Rata-rata skor Q35 lintas kelas prodi: "Mahasiswa berusaha sungguh-sungguh." Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_q37
    IS 'Rata-rata skor Q37 lintas kelas prodi: "Mahasiswa memperoleh pengalaman belajar positif." Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_capaian
    IS 'Rata-rata skor dimensi Capaian Pembelajaran lintas kelas prodi (dari skor_kues dosen). Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_pelaksanaan
    IS 'Rata-rata skor dimensi Pelaksanaan Perkuliahan lintas kelas prodi. Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_sarana_prasarana
    IS 'Rata-rata skor dimensi Sarana & Prasarana lintas kelas prodi (dari Q29 dan Q30). Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_perilaku_mahasiswa
    IS 'Rata-rata skor dimensi Perilaku Mahasiswa lintas kelas prodi. Skala 1–4.';
COMMENT ON COLUMN analitik.v_akademik_statistik_prodi.avg_skor_overall
    IS 'Rata-rata skor keseluruhan (all questions) lintas kelas prodi. Skala 1–4.';


-- ── B5. v_akademik_statistik_dosen ───────────────────────────────
COMMENT ON VIEW analitik.v_akademik_statistik_dosen IS
    'Statistik kinerja dosen per semester: beban mengajar, kehadiran, dan skor evaluasi. '
    'Grain: 1 baris = 1 (dosen_id, semester, tahun). '
    'ROW SECURITY: ADMIN/DIREKTORAT=semua; DEKAN/JAJ.DEKANAT=filter kode_fakultas_dosen (homebase); '
    'KAPRODI/JAJ.PRODI/DOSEN=filter berdasarkan prodi yang sedang diajar (no_prodi_diajar). '
    'COLUMN SECURITY: kolom evaluasi (avg_skor_*, avg_pct_kehadiran_dosen, avg_ip_mhs, dll.) '
    'di-mask (NULL) untuk role DOSEN ketika melihat data dosen lain; '
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
       'Tidak di-mask — ini informasi tentang mahasiswa, bukan evaluasi dosen pribadi.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_ip_mhs
    IS '[SENSITIF] Rata-rata IP akhir mahasiswa di kelas yang diajar dosen ini. '
       'Di-mask (NULL) untuk role DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_skor_q25
    IS '[SENSITIF] Rata-rata skor Q25 ("Dosen berkomunikasi efektif") lintas kelas dosen ini. '
       'Dari evaluasi.nilai_dosen.kuesioner (per-dosen). Skala 1–4. '
       'Di-mask (NULL) untuk role DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_skor_q26
    IS '[SENSITIF] Rata-rata skor Q26 ("Dosen peduli terhadap pencapaian mahasiswa") lintas kelas. '
       'Skala 1–4. Di-mask untuk role DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_skor_q27
    IS '[SENSITIF] Rata-rata skor Q27 ("Dosen berlaku adil kepada mahasiswa") lintas kelas. '
       'Skala 1–4. Di-mask untuk role DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_skor_capaian
    IS '[SENSITIF] Rata-rata skor dimensi Capaian Pembelajaran dosen (dari evaluasi.nilai_dosen.skor_kues key "1"). '
       'Skala 1–4. NULL jika data format baru belum tersedia. Di-mask untuk DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_skor_pelaksanaan
    IS '[SENSITIF] Rata-rata skor dimensi Pelaksanaan Perkuliahan dosen (key "2"). '
       'Skala 1–4. Di-mask untuk DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_skor_sarana_prasarana
    IS '[SENSITIF] Rata-rata skor Sarana & Prasarana dari kelas yang diajar dosen ini (Q29+Q30)/2. '
       'Di-mask untuk DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_skor_perilaku_mahasiswa
    IS '[SENSITIF] Rata-rata skor dimensi Perilaku Mahasiswa dosen (key "3"). '
       'Skala 1–4. Di-mask untuk DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_skor_overall
    IS '[SENSITIF] Rata-rata skor keseluruhan dosen, dihitung dari (capaian + pelaksanaan + perilaku) / N-dimensi-tersedia. '
       'Di-mask untuk DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.jumlah_kelas_dengan_skor
    IS '[SENSITIF] Jumlah kelas dosen yang sudah memiliki data evaluasi (skor_kues terisi). '
       'Di-mask untuk DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.avg_nilai_akhir
    IS '[SENSITIF] Rata-rata nilai akhir dosen dari evaluasi.nilai_dosen.nilai_akhir. '
       'Sering NULL karena kolom ini tidak konsisten diisi. Di-mask untuk DOSEN ketika melihat dosen lain.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.kelas_ids
    IS 'Array kelas_id semua kelas yang diajar dosen semester ini.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.kode_matkul_list
    IS 'Array kode MK unik yang diajar dosen semester ini.';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.no_prodi_diajar
    IS 'Array ID numerik prodi yang kelas-kelasnya diajar dosen (bisa berbeda dari homebase). '
       'Digunakan sebagai filter KAPRODI/JAJ.PRODI/DOSEN: WHERE no_prodi_diajar @> ARRAY[v_no_prodi].';
COMMENT ON COLUMN analitik.v_akademik_statistik_dosen.kode_prodi_diajar
    IS 'Array kode singkat prodi yang diajar, paralel dengan no_prodi_diajar.';


-- ── B6. v_wisudawan_distribusi_jawaban ───────────────────────────
COMMENT ON VIEW analitik.v_wisudawan_distribusi_jawaban IS
    'Distribusi jawaban survey wisudawan per pertanyaan, per nilai jawaban, per prodi, per periode. '
    'Grain: 1 baris = 1 (periode_ijazah_id_final, no_prodi, kode_pertanyaan, nilai). '
    'Mencakup pertanyaan ordinal (Likert, tipe_opsi=O) dan nominal/kategoris (tipe_opsi=N). '
    'Untuk analisis statistik (rata-rata, median), gunakan v_wisudawan_statistik_pertanyaan '
    'yang hanya mencakup pertanyaan ordinal. '
    'Filter is_seremoni_asumtif=FALSE untuk hanya data seremoni final. '
    'ROW SECURITY: ADMIN/DIREKTORAT=semua; DEKAN/JAJ.DEKANAT=filter kode_fakultas; '
    'KAPRODI/JAJ.PRODI/DOSEN=filter no_prodi.';

COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.periode_ijazah_id_final
    IS 'Periode ijazah final format YYYYMM (sudah diimputasi). Gunakan kolom ini untuk filter periode.';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.tahun_ijazah
    IS 'Tahun ijazah.';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.bulan_ijazah
    IS 'Bulan ijazah (1–12).';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.periode_seremoni_id
    IS 'ID seremoni format YYYYMM. NULL jika mapping belum tersedia.';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.tahun_seremoni
    IS 'Tahun pelaksanaan seremoni wisuda.';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.bulan_seremoni
    IS 'Bulan pelaksanaan seremoni wisuda (1–12).';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.nama_seremoni
    IS 'Nama seremoni wisuda Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.is_seremoni_asumtif
    IS 'TRUE = seremoni masih dummy/asumtif. Filter FALSE untuk data final.';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.no_prodi
    IS 'ID numerik program studi wisudawan.';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.kode_prodi
    IS 'Kode singkat prodi wisudawan.';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.nama_prodi_id
    IS 'Nama program studi Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.nama_prodi_en
    IS 'Nama program studi Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.jenjang
    IS 'Jenjang studi: S1, S2, S3, PR.';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.kode_fakultas
    IS 'Kode fakultas/sekolah wisudawan.';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.nama_fakultas_id
    IS 'Nama fakultas Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.nama_fakultas_en
    IS 'Nama fakultas Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.kode_pertanyaan
    IS 'Kode pertanyaan survey wisudawan, contoh: U03_SQ001, U02, G01Q23. '
       'Format: [Section][Nomor][SQ_Subpertanyaan].';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.kode_grup_pertanyaan
    IS 'Kode grup pertanyaan (FK ke evaluasi_wisudawan.pertanyaan.kd_grup_pertanyaan). '
       'Mengelompokkan pertanyaan dalam satu section.';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.kode_grup_opsi
    IS 'Kode grup opsi jawaban (FK ke evaluasi_wisudawan.ref_grup_opsi). '
       'Menentukan skala jawaban yang digunakan.';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.tipe_opsi
    IS 'Tipe skala jawaban: O=Ordinal/Likert (bisa di-AVG), N=Nominal/Kategoris (jangan di-AVG).';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.nilai
    IS 'Nilai jawaban (sebagai teks, sudah di-decode): contoh "Setuju", "Kualitas dosen", dll. '
       'Sumber: CASE expression decode dari nilai numerik di JSONB jawaban.';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.jumlah_responden
    IS 'Jumlah wisudawan yang memilih nilai jawaban ini untuk pertanyaan ini pada prodi dan periode tersebut.';
COMMENT ON COLUMN analitik.v_wisudawan_distribusi_jawaban.persentase
    IS 'Persentase responden yang memilih nilai ini terhadap total responden yang menjawab pertanyaan ini '
       'pada prodi dan periode tersebut (0–100).';


-- ── B7. v_wisudawan_statistik_pertanyaan ─────────────────────────
COMMENT ON VIEW analitik.v_wisudawan_statistik_pertanyaan IS
    'Statistik deskriptif jawaban survey wisudawan per pertanyaan ordinal (Likert) per prodi per periode. '
    'Grain: 1 baris = 1 (periode_ijazah_id_final, no_prodi, kode_pertanyaan). '
    'HANYA mencakup pertanyaan ordinal (tipe_opsi=O, skala Likert). '
    'Pertanyaan nominal (U02 = alasan rekomendasi, dll.) TIDAK ada di sini — gunakan v_wisudawan_distribusi_jawaban. '
    'Filter is_seremoni_asumtif=FALSE untuk hanya data seremoni final. '
    'ROW SECURITY: ADMIN/DIREKTORAT=semua; DEKAN/JAJ.DEKANAT=filter kode_fakultas; '
    'KAPRODI/JAJ.PRODI/DOSEN=filter no_prodi.';

COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.periode_ijazah_id_final
    IS 'Periode ijazah final format YYYYMM. Gunakan kolom ini untuk filter periode.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.tahun_ijazah
    IS 'Tahun ijazah.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.bulan_ijazah
    IS 'Bulan ijazah (1–12).';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.periode_seremoni_id
    IS 'ID seremoni format YYYYMM.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.tahun_seremoni
    IS 'Tahun pelaksanaan seremoni wisuda.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.bulan_seremoni
    IS 'Bulan pelaksanaan seremoni wisuda (1–12).';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.nama_seremoni
    IS 'Nama seremoni wisuda Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.is_seremoni_asumtif
    IS 'TRUE = seremoni masih dummy/asumtif. Filter FALSE untuk data final.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.no_prodi
    IS 'ID numerik program studi wisudawan.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.kode_prodi
    IS 'Kode singkat prodi wisudawan.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.nama_prodi_id
    IS 'Nama program studi Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.nama_prodi_en
    IS 'Nama program studi Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.jenjang
    IS 'Jenjang studi: S1, S2, S3, PR.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.kode_fakultas
    IS 'Kode fakultas/sekolah wisudawan.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.nama_fakultas_id
    IS 'Nama fakultas Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.nama_fakultas_en
    IS 'Nama fakultas Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.kode_pertanyaan
    IS 'Kode pertanyaan ordinal (Likert), contoh: U03_SQ001, U01_SQ005. '
       'Hanya pertanyaan dengan tipe_opsi=O.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.kode_grup_pertanyaan
    IS 'Kode grup pertanyaan — mengelompokkan pertanyaan dalam satu section survey.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.kode_grup_opsi
    IS 'Kode grup opsi — menentukan skala Likert yang digunakan (1–4 atau 1–5).';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.jumlah_responden
    IS 'Jumlah wisudawan yang menjawab pertanyaan ini pada prodi dan periode tersebut.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.rata_rata
    IS 'Rata-rata nilai jawaban (valid karena hanya skala ordinal). '
       'Contoh: 3.42 pada skala 1–4 berarti "Cenderung Setuju".';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.median
    IS 'Median nilai jawaban pada pertanyaan ini.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.std_dev
    IS 'Standar deviasi jawaban — mengukur variasi/konsensus. Nilai rendah = lebih konsensus.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.skor_min
    IS 'Nilai jawaban terendah yang diberikan oleh responden.';
COMMENT ON COLUMN analitik.v_wisudawan_statistik_pertanyaan.skor_max
    IS 'Nilai jawaban tertinggi yang diberikan oleh responden.';


-- ── B8. v_wisudawan_jawaban_responden ────────────────────────────
COMMENT ON VIEW analitik.v_wisudawan_jawaban_responden IS
    'Jawaban individual setiap wisudawan — wide table dengan semua pertanyaan sebagai kolom. '
    'Grain: 1 baris = 1 responden wisudawan (response_id). '
    'Nilai jawaban sudah di-decode dari numerik ke label teks via CASE expression. '
    'Semua teks bebas sudah distrip HTML via analitik_mv.strip_html(). '
    'Kolom section-spesifik (s101, m01, d01, fsrd01, sbm01) akan NULL untuk prodi/strata yang tidak relevan. '
    'ROW SECURITY: ADMIN/DIREKTORAT=semua; DEKAN/JAJ.DEKANAT=filter kode_fakultas; '
    'KAPRODI/JAJ.PRODI/DOSEN=filter no_prodi.';


-- ================================================================
-- COMMENTS DARI beberapa_informasi_comment.sql
-- (kolom v_wisudawan_jawaban_responden + v_akademik_portofolio)
-- ================================================================


COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.response_id IS 'Surrogate primary key internal database';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.survey_platform_response_id IS 'ID response asli dari LimeSurvey (bisa NULL jika tidak tercatat)';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.periode_ijazah_id IS 'Periode wisuda format YYYYMM asli dari data sumber, contoh: 202502=Februari 2025. Nullable (66% terisi). FK ke wisuda.periode_ijazah';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.periode_ijazah_id_final IS 'periode_ijazah_id siap pakai: asli jika not null, diimputasi dari submit_date jika null. Gunakan kolom ini untuk filtering per periode';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.tahun_ijazah IS 'Tahun ijazah diekstrak dari lower(tgl_ijazah) di periode_ijazah_sementara (LEFT JOIN). NULL jika periode_ijazah_id_final belum dipetakan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.bulan_ijazah IS 'Bulan ijazah (1–12) diekstrak dari lower(tgl_ijazah) di periode_ijazah_sementara (LEFT JOIN). NULL jika periode_ijazah_id_final belum dipetakan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.periode_seremoni_id IS 'ID seremoni wisuda dari ijazah_to_seremoni (LEFT JOIN). Format YYYYMM, contoh: 202504=Seremoni April 2025. NULL jika periode belum dipetakan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.tahun_seremoni IS 'Tahun pelaksanaan seremoni wisuda, diekstrak dari lower(tgl_seremoni). NULL jika mapping belum ada atau tgl_seremoni belum diisi';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.bulan_seremoni IS 'Bulan pelaksanaan seremoni wisuda (1–12), diekstrak dari lower(tgl_seremoni). NULL jika mapping belum ada atau tgl_seremoni belum diisi';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.nama_seremoni IS 'Nama seremoni wisuda dalam Bahasa Indonesia dari periode_seremoni_sementara.nama->>''id''. NULL jika mapping belum ada';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.kd_strata IS 'Jenjang pendidikan kode: S1=Sarjana, S2=Magister, S3=Doktor, PR=Profesi';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.kd_fak IS 'Kode fakultas/sekolah singkat, contoh: STEI, SBM, FSRD. FK ke utama.fakultas';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.no_ps IS 'Kode numerik program studi, contoh: 135=Teknik Informatika S1. FK ke utama.program_studi';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.submit_date IS 'Timestamp pengisian kuesioner oleh wisudawan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.kode_prodi IS 'no_ps dari utama.program_studi (identik dengan no_ps, disediakan untuk konsistensi penamaan lintas MV)';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.singkatan_prodi IS 'Kode singkat program studi, contoh: IF, EL, MA. Dari utama.program_studi.kd_ps';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.nama_prodi_id IS 'Nama lengkap program studi dalam Bahasa Indonesia. Dari utama.program_studi.nama->>id';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.nama_prodi_en IS 'Nama lengkap program studi dalam Bahasa Inggris. Dari utama.program_studi.nama->>en';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.jenjang IS 'Jenjang program studi: S1, S2, S3, PR. Dari utama.program_studi.kd_strata';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.kode_fakultas IS 'Kode fakultas/sekolah. Dari utama.fakultas.kd_fak';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.nama_fakultas_id IS 'Nama lengkap fakultas dalam Bahasa Indonesia. Dari utama.fakultas.nama->>id';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.nama_fakultas_en IS 'Nama lengkap fakultas dalam Bahasa Inggris. Dari utama.fakultas.nama->>en';

-- Section A: Fasilitas & Kepuasan ITB (U03)
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u03_sq001 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Tersedia cukup ruang kelas';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u03_sq002 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Ruang kelas kondusif untuk pembelajaran';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u03_sq003 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Laboratorium kondusif untuk pembelajaran';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u03_sq004 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Akses internet memadai';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u03_sq005 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Fasilitas keprofesian memadai';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u03_sq006 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Akses perpustakaan memadai';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u03_sq007 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Perangkat pembelajaran up-to-date';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u03_sq008 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Fasilitas toilet memadai';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u03_sq009 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Fasilitas kantin memadai';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u03_sq010 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Fasilitas rekreasi/olahraga memadai';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u03_sq011 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Fasilitas kesehatan memadai';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u03_sq012 IS 'Section A (U03) | Fasilitas & Kepuasan ITB | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Secara keseluruhan saya puas dengan fasilitas ITB';

-- Section B: Pendidikan di Prodi (U01 + U02)
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u01_sq001 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Wali akademik selalu tersedia saat dibutuhkan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u01_sq002 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Wali akademik membantu memenuhi persyaratan akademik';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u01_sq003 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Dosen berinteraksi secara informal dengan mahasiswa';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u01_sq004 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Dosen memperhatikan proses pembelajaran mahasiswa';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u01_sq005 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Dosen memiliki kemampuan profesional yang baik';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u01_sq006 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Matakuliah wajib memberikan dasar yang baik';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u01_sq007 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Matakuliah pilihan memberikan keleluasaan eksplorasi';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u01_sq008 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Praktikum sejalan dengan teori di kelas';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u01_sq009 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Sarana program studi memadai';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u01_sq010 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Program studi memberikan gambaran dunia kerja';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u01_sq011 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Saya menikmati bidang studi saya';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u01_sq012 IS 'Section B (U01) | Pendidikan di Program Studi | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Saya akan memilih program studi yang sama lagi';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u02 IS 'Section B (U02) | Rekomendasi prodi | Populasi: semua | Nominal (REKOMENDASI_PRODI): 1=Kualitas dosen · 2=Suasana akademik · 3=Jejaring alumni · 4=Lapangan pekerjaan · 5=Fasilitas akademik · 6=Tidak merekomendasikan · 7=Other';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u02_other IS 'Section B (U02) | Teks bebas jika u02=Other. NULL jika u02 bukan Other';

-- Section C1: Softskills (U04)
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u04_sq001 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan komunikasi lisan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u04_sq002 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan komunikasi tertulis';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u04_sq003 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan berbahasa asing';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u04_sq004 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan penyelesaian masalah';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u04_sq005 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan berpikir kritis';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u04_sq006 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan introspeksi diri';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u04_sq007 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan menyampaikan pendapat';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u04_sq008 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan kerja tim';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u04_sq009 IS 'Section C1 (U04) | Kemampuan Softskills | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kemampuan kerja mandiri';

-- Section C2: Karakter (U05)
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u05_sq001 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kejujuran';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u05_sq002 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Komitmen';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u05_sq003 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kecerdasan emosi';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u05_sq004 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kepedulian terhadap sesama';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u05_sq005 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Objektivitas';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u05_sq006 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Ketidakmudahan menyerah (Perseverance)';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u05_sq007 IS 'Section C2 (U05) | Pengembangan Karakter | Populasi: semua strata & fakultas | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kepatuhan terhadap aturan';

-- Section D1: Permasalahan Studi (U06)
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u06_sq001 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah atau sama sekali tidak · 2=Jarang atau kecil · 3=Sering atau cukup · 4=Selalu atau besar | Pertanyaan: Permasalahan akademis';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u06_sq002 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah atau sama sekali tidak · 2=Jarang atau kecil · 3=Sering atau cukup · 4=Selalu atau besar | Pertanyaan: Permasalahan keuangan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u06_sq003 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah atau sama sekali tidak · 2=Jarang atau kecil · 3=Sering atau cukup · 4=Selalu atau besar | Pertanyaan: Pengaruh keuangan terhadap akademis';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u06_sq004 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah atau sama sekali tidak · 2=Jarang atau kecil · 3=Sering atau cukup · 4=Selalu atau besar | Pertanyaan: Permasalahan psikologis';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u06_sq005 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah atau sama sekali tidak · 2=Jarang atau kecil · 3=Sering atau cukup · 4=Selalu atau besar | Pertanyaan: Pengaruh psikologis terhadap studi';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u06_sq006 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah atau sama sekali tidak · 2=Jarang atau kecil · 3=Sering atau cukup · 4=Selalu atau besar | Pertanyaan: Permasalahan sosial budaya';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u06_sq007 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah atau sama sekali tidak · 2=Jarang atau kecil · 3=Sering atau cukup · 4=Selalu atau besar | Pertanyaan: Pengaruh sosial budaya terhadap studi';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u06_sq008 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah atau sama sekali tidak · 2=Jarang atau kecil · 3=Sering atau cukup · 4=Selalu atau besar | Pertanyaan: Permasalahan kesehatan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u06_sq009 IS 'Section D1 (U06) | Permasalahan Selama Studi | Populasi: semua strata & fakultas | 1=Tidak pernah atau sama sekali tidak · 2=Jarang atau kecil · 3=Sering atau cukup · 4=Selalu atau besar | Pertanyaan: Pengaruh kesehatan terhadap studi';

-- Section D2: Ketersediaan Dukungan (U07)
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u07_sq001 IS 'Section D2 (U07) | Ketersediaan Dukungan | Populasi: semua strata & fakultas | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Sepenuhnya memenuhi harapan · 5=Melampaui harapan | Pertanyaan: Ketersediaan beasiswa atau pinjaman';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u07_sq002 IS 'Section D2 (U07) | Ketersediaan Dukungan | Populasi: semua strata & fakultas | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Sepenuhnya memenuhi harapan · 5=Melampaui harapan | Pertanyaan: Bimbingan konseling';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u07_sq003 IS 'Section D2 (U07) | Ketersediaan Dukungan | Populasi: semua strata & fakultas | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Sepenuhnya memenuhi harapan · 5=Melampaui harapan | Pertanyaan: Nasehat dari wali akademik';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.u07_sq004 IS 'Section D2 (U07) | Ketersediaan Dukungan | Populasi: semua strata & fakultas | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Sepenuhnya memenuhi harapan · 5=Melampaui harapan | Pertanyaan: Nasehat dari dosen matakuliah';

-- Section E: Free-text Pengalaman Belajar
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.g10q22 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Kebiasaan belajar (cara belajar, waktu, hal-hal yang mendorong belajar)';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.g01q23 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Kesan-kesan dan prestasi dalam belajar';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.g01q24 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Pengalaman lain yang sangat berkesan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.g01q25 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Aktivitas kemahasiswaan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.g01q26 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Cita-cita dalam karier';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.g01q27 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Cita-cita dalam hidup';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.g01q28 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Motto untuk sukses studi di ITB';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.g01q29 IS 'Section E | Pengalaman Belajar | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Sifat khas diri sendiri';

-- Section F: Free-text Pandangan ITB
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.g11q30 IS 'Section F | Pandangan tentang ITB | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Suka duka menempuh studi di ITB';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.g01q31 IS 'Section F | Pandangan tentang ITB | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Segi positif studi di ITB';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.g01q32 IS 'Section F | Pandangan tentang ITB | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Segi negatif studi di ITB';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.g01q33 IS 'Section F | Pandangan tentang ITB | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Saran untuk perbaikan proses dan sarana pendidikan di ITB';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.g01q34 IS 'Section F | Pandangan tentang ITB | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Saran untuk mahasiswa lain dalam menempuh studi di ITB';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.g01q35 IS 'Section F | Pandangan tentang ITB | Populasi: semua | Free-text, NULL jika tidak diisi | Pertanyaan: Catatan atau komentar lain';

-- Section G: S1 Khusus
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.s101 IS 'Section G (S101) | Rencana melanjutkan ke pendidikan lebih tinggi | Hanya S1, NULL untuk strata lain | Nominal (YA_TIDAK): 1=Ya · 2=Tidak';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.s102 IS 'Section G (S102) | Lokasi rencana studi lanjut | Hanya S1, NULL untuk strata lain | Nominal (LOKASI_STUDI_LANJUT): 1=ITB · 2=Perguruan tinggi dalam negeri selain ITB · 3=Di luar negeri · 4=Tidak ada rencana studi lanjut';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.s103 IS 'Section G (S103) | Kelanjutan bidang studi | Hanya S1, NULL untuk strata lain | Nominal (BIDANG_STUDI_LANJUT): 1=Ya kelanjutan · 2=Tidak tapi serumpun · 3=Tidak tapi butuh pengetahuan ITB · 4=Tidak sangat berbeda · 5=Tidak ada rencana';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.s104_sq001 IS 'Section G (S104) | Penilaian Matakuliah Wajib ITB | Hanya S1, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Agama dan etika — pengaruh terhadap sikap';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.s104_sq002 IS 'Section G (S104) | Penilaian Matakuliah Wajib ITB | Hanya S1, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Pancasila dan kewarganegaraan — pengaruh terhadap sikap';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.s104_sq003 IS 'Section G (S104) | Penilaian Matakuliah Wajib ITB | Hanya S1, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Manajemen — wawasan pentingnya peranan manajemen';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.s104_sq004 IS 'Section G (S104) | Penilaian Matakuliah Wajib ITB | Hanya S1, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Lingkungan — wawasan dan perilaku ramah lingkungan';

-- Section H: S2 Khusus
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.m01 IS 'Section H (M01) | Rencana melanjutkan ke pendidikan lebih tinggi | Hanya S2, NULL untuk strata lain | Nominal (YA_TIDAK): 1=Ya · 2=Tidak';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.m02 IS 'Section H (M02) | Lokasi rencana studi lanjut | Hanya S2, NULL untuk strata lain | Nominal (LOKASI_STUDI_LANJUT): 1=ITB · 2=Perguruan tinggi dalam negeri selain ITB · 3=Di luar negeri · 4=Tidak ada rencana studi lanjut';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.m03 IS 'Section H (M03) | Kelanjutan bidang studi | Hanya S2, NULL untuk strata lain | Nominal (BIDANG_STUDI_LANJUT): 1=Ya kelanjutan · 2=Tidak tapi serumpun · 3=Tidak tapi butuh pengetahuan ITB · 4=Tidak sangat berbeda · 5=Tidak ada rencana';

-- Section I: S3 Khusus
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.d01_sq001 IS 'Section I (D01) | Penilaian Matakuliah Wajib ITB Doktor | Hanya S3, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Filsafat ilmu — wawasan pengembangan ilmu pengetahuan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.d01_sq002 IS 'Section I (D01) | Penilaian Matakuliah Wajib ITB Doktor | Hanya S3, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Metodologi penelitian — manfaat dalam penelitian';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.d01_sq003 IS 'Section I (D01) | Penilaian Matakuliah Wajib ITB Doktor | Hanya S3, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kesulitan mengambil filsafat ilmu';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.d01_sq004 IS 'Section I (D01) | Penilaian Matakuliah Wajib ITB Doktor | Hanya S3, NULL untuk strata lain | 1=Tidak Setuju · 2=Cenderung Tidak Setuju · 3=Cenderung Setuju · 4=Setuju | Pertanyaan: Kesulitan mengambil metodologi penelitian';

-- Section J: FSRD Khusus
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd01_sq001 IS 'Section J FSRD01 (TPB) | Pemahaman Prinsip Estetik | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd01_sq002 IS 'Section J FSRD01 (TPB) | Penguasaan Proses Kreatif | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd01_sq003 IS 'Section J FSRD01 (TPB) | Penguasaan menggambar dan membentuk | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd01_sq004 IS 'Section J FSRD01 (TPB) | Pengetahuan tentang program studi FSRD | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd01_sq005 IS 'Section J FSRD01 (TPB) | Kemampuan menulis secara ilmiah | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd02_sq001 IS 'Section J FSRD02 (Perwalian) | Perwalian tatap muka | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd02_sq002 IS 'Section J FSRD02 (Perwalian) | Perwalian online | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd02_sq003 IS 'Section J FSRD02 (Perwalian) | Bantuan dan respon dosen wali | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd03_sq001 IS 'Section J FSRD03 (MK Teori) | Sejarah Seni/Kria/Desain | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd03_sq002 IS 'Section J FSRD03 (MK Teori) | Perkembangan Seni/Kria/Desain di Indonesia | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd03_sq003 IS 'Section J FSRD03 (MK Teori) | Perkembangan Seni/Kria/Desain di Dunia | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd03_sq004 IS 'Section J FSRD03 (MK Teori) | Metoda dan prosedur penciptaan/perancangan | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd03_sq005 IS 'Section J FSRD03 (MK Teori) | Kemampuan analisis-kritis karya | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd03_sq006 IS 'Section J FSRD03 (MK Teori) | Kesesuaian SKS dengan jumlah dan materi tugas | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd04_sq001 IS 'Section J FSRD04 (MK Studio) | Teknik penciptaan/perancangan | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd04_sq002 IS 'Section J FSRD04 (MK Studio) | Wawasan estetik dan proses perancangan | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd04_sq003 IS 'Section J FSRD04 (MK Studio) | Kesesuaian SKS dengan tugas studio | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd04_sq004 IS 'Section J FSRD04 (MK Studio) | Proses asistensi/pembimbingan | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd04_sq005 IS 'Section J FSRD04 (MK Studio) | Kesesuaian penilaian kualitas karya | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd04_sq006 IS 'Section J FSRD04 (MK Studio) | Kesesuaian pengetahuan dengan kerja profesi/pemagangan | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd05_sq001 IS 'Section J FSRD05 (Tugas Akhir) | Pengetahuan menunjang TA | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd05_sq002 IS 'Section J FSRD05 (Tugas Akhir) | Proses pembimbingan TA | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd05_sq003 IS 'Section J FSRD05 (Tugas Akhir) | Sarana dan prasarana TA | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.fsrd05_sq004 IS 'Section J FSRD05 (Tugas Akhir) | Buku dan literatur perpustakaan untuk TA | Hanya FSRD, NULL untuk fak lain | 1=Tidak sesuai harapan · 2=Ada yang memenuhi harapan · 3=Sebagian besar memenuhi harapan · 4=Memenuhi harapan · 5=Melampaui harapan';

-- Section K: SBM Khusus
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq001 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan berkomunikasi secara lisan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq002 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan berkomunikasi dalam tulisan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq003 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menggunakan pengetahuan marketing';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq004 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menggunakan pengetahuan manajemen operasi';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq005 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menggunakan pengetahuan manajemen sumber daya manusia';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq006 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menggunakan pengetahuan keuangan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq007 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan Pengambilan Keputusan dan Negosiasi';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq008 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan kewirausahaan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq009 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan tampil di depan publik';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq010 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Pengetahuan mendalam pada sekurangnya satu konsentrasi';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq011 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Pengetahuan probabilitas dan statistik termasuk analisis data';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq012 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menginterpretasi data';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq013 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan mengidentifikasi masalah';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq014 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menyelesaikan masalah';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq015 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan melakukan riset bisnis';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq016 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan menggunakan internet untuk informasi dan berbagi pengetahuan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq017 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan membangun jejaring';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq018 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan mendirikan usaha baru';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq019 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan bekerjasama dalam tim';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq020 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan mengidentifikasi peluang bisnis';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq021 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan mengidentifikasi peluang peningkatan kondisi komunitas';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq022 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan merancang dan menciptakan produk baru';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq023 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan beradaptasi dalam kendala sosial';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq024 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan bekerja/belajar dalam kendala sumberdaya';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq025 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan bekerja/belajar dalam kendala etika';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq026 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan bekerja/belajar dalam kendala kesehatan dan keamanan';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq027 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Memahami tanggung jawab profesional';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq028 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Memahami tanggung jawab etis';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq029 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Pengakuan perlunya belajar seumur hidup';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq030 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Kemampuan terlibat dalam pembelajaran seumur hidup';
COMMENT ON COLUMN analitik.v_wisudawan_jawaban_responden.sbm01_sq031 IS 'Section K (SBM01) | Outcomes Program Studi SBM | Hanya SBM, NULL untuk fak lain | 1=Undeveloped · 2=Slightly Developed · 3=Moderately Developed · 4=Substantially Developed · 5=Highly Developed | Pertanyaan: Pengetahuan pendukung untuk studi pasca sarjana';


-- COMMENT ON VIEW analitik.v_akademik_portofolio IS  ← sudah ada di atas, skip duplikat
    'Wide table portofolio dosen — grain: 1 baris = 1 kelas. '
    'Sumber: evaluasi.portofolio JOIN analitik.mv_kelas. '
    'Era baru (skema_pertanyaan=''baru''): kd_pertanyaan 12-19, [20181,∞), ~54K baris. '
    'Era lama (skema_pertanyaan=''lama''): kd_pertanyaan 1-11, ~27K baris. '
    'Semua teks sudah distrip HTML via analitik.strip_html(). '
    'Refresh setelah analitik.mv_kelas. '
-- ================================================================
-- COMMENT ON MATERIALIZED VIEW
-- ================================================================
-- COMMENT ON VIEW analitik.v_akademik_portofolio IS  ← sudah ada di atas, skip duplikat
    'Wide table portofolio dosen — grain: 1 baris = 1 kelas. '
    'Sumber: evaluasi.portofolio JOIN analitik_mv.mv_kelas. '
    'Era baru (skema_pertanyaan=''baru''): kd_pertanyaan 12-19, [20181,∞), ~54K baris. '
    'Era lama (skema_pertanyaan=''lama''): kd_pertanyaan 1-11, ~27K baris. '
    'Semua teks sudah distrip HTML via analitik.strip_html(). '
    'Refresh setelah analitik.mv_kelas. '
    '--- '
    'CATATAN HISTORIS — Phased rollout skema evaluasi: '
    'Kuesioner mahasiswa beralih ke q21-q37 mulai 2016/semester-1, '
    'sedangkan portofolio dosen baru beralih ke q12-19 mulai 2018/semester-1. '
    'Akibatnya ~11.618 kelas (2016/1, 2016/2, 2017/1, 2017/2) '
    'memiliki skema_pertanyaan=''lama'' meski kuesioner mahasiswanya sudah era baru. '
    'Untuk kelas-kelas ini, respons dosen terhadap kuesioner mahasiswa '
    'ada di kolom lama_uraian_kuesioner_statistik (kd_pertanyaan=4) '
    'dan lama_komentar_kuesioner_mahasiswa (kd_pertanyaan=9).';

-- ================================================================
-- COMMENT ON COLUMN — DIMENSI KELAS
-- ================================================================
COMMENT ON COLUMN analitik.v_akademik_portofolio.kelas_id
    IS 'PK MV. Identitas kelas (FK ke kelas.kelas).';
COMMENT ON COLUMN analitik.v_akademik_portofolio.kode_mk
    IS 'Kode mata kuliah (6 karakter), contoh: MA1101.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.nama_mk_id
    IS 'Nama mata kuliah Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.nama_mk_en
    IS 'Nama mata kuliah Bahasa Inggris.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.sks
    IS 'Jumlah SKS mata kuliah.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.no_kelas
    IS 'Nomor urut kelas dalam satu mata kuliah per semester.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.semester
    IS '1=ganjil, 2/3=genap/pendek.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.tahun
    IS 'Tahun akademik (4 digit).';
COMMENT ON COLUMN analitik.v_akademik_portofolio.tahun_ajaran
    IS 'Format YYYY/YYYY, contoh: 2022/2023.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.tahun_kurikulum
    IS 'Tahun kurikulum yang berlaku untuk mata kuliah ini.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.jenis_nilai
    IS 'ABCDE atau PassFail.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.kode_prodi
    IS 'no_ps program studi penyelenggara.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.singkatan_prodi
    IS 'Singkatan prodi (2 karakter).';
COMMENT ON COLUMN analitik.v_akademik_portofolio.nama_prodi_id
    IS 'Nama program studi Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.jenjang
    IS 'Jenjang studi: S1, S2, S3, D3, dst.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.kode_fakultas
    IS 'Kode fakultas/sekolah (FMIPA, STEI, FTI, dst.).';
COMMENT ON COLUMN analitik.v_akademik_portofolio.nama_fakultas_id
    IS 'Nama fakultas/sekolah Bahasa Indonesia.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.semua_dosen_id
    IS 'Array dosen_id semua pengajar kelas (dari kelas.pengajar).';
COMMENT ON COLUMN analitik.v_akademik_portofolio.semua_dosen_nama_gelar
    IS 'Array nama lengkap dengan gelar semua pengajar kelas.';

-- ================================================================
-- COMMENT ON COLUMN — METADATA PORTOFOLIO
-- ================================================================
COMMENT ON COLUMN analitik.v_akademik_portofolio.tgl_entri
    IS 'Tanggal dosen menyelesaikan pengisian portofolio.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.lengkap
    IS 'TRUE jika portofolio sudah dinyatakan lengkap oleh verifikator.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.nilai_portofolio
    IS 'Nilai numerik portofolio hasil verifikasi.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.skema_pertanyaan
    IS '"baru" = kd_pertanyaan 12-19 [20181,∞) | '
       '"lama" = kd_pertanyaan 1-11 (sebelum 2018) | '
       '"kosong" = isian NULL atau {}.';

-- ================================================================
-- COMMENT ON COLUMN — ERA BARU (kd_pertanyaan 12–19)
-- ================================================================
COMMENT ON COLUMN analitik.v_akademik_portofolio.metode_perkuliahan
    IS '[ACTIVE | kd_pertanyaan=12 | kd_grup=6 Penyelenggaraan Perkuliahan] '
       'Uraian metode yang digunakan dalam pembelajaran: diskusi, '
       'collaborative learning, kuliah tamu, project, dsb.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.komponen_penilaian
    IS '[ACTIVE | kd_pertanyaan=13 | kd_grup=6 Penyelenggaraan Perkuliahan] '
       'Komponen-komponen penilaian (UTS, UAS, kuis, tugas, praktikum, presentasi, dll.) '
       'beserta bobot dan standar konversi nilai ke indeks.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.statistik_nilai_kelas
    IS '[ACTIVE | kd_pertanyaan=14 | kd_grup=7 Ketercapaian Outcomes] '
       'Distribusi nilai ujian, PR, kuis, dan bentuk penilaian lainnya, '
       'serta data statistik penting kelas lainnya.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.analisis_ketercapaian_outcomes
    IS '[ACTIVE | kd_pertanyaan=15 | kd_grup=7 Ketercapaian Outcomes] '
       'Uraian tentang tingkat keberhasilan pembelajaran dan ketercapaian outcomes '
       'beserta faktor-faktor yang mempengaruhinya berdasarkan data terkumpul.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.tanggapan_kuesioner_mahasiswa
    IS '[ACTIVE | kd_pertanyaan=16 | kd_grup=8 Refleksi Dosen] '
       'Tanggapan dosen terhadap penilaian mahasiswa melalui kuesioner.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.refleksi_perkuliahan
    IS '[ACTIVE | kd_pertanyaan=17 | kd_grup=8 Refleksi Dosen] '
       'Uraian tentang pelaksanaan perkuliahan: keberhasilan dan kegagalan rencana, '
       'masalah belajar mahasiswa, persoalan yang dihadapi dosen, temuan penting.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.usulan_perbaikan_dosen
    IS '[ACTIVE | kd_pertanyaan=18 | kd_grup=9 Rekomendasi Tindak Lanjut] '
       'Hal-hal yang perlu dilakukan oleh dosen pengampu pada perkuliahan mendatang '
       'untuk meningkatkan kualitas dan keberhasilan pembelajaran.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.rekomendasi_ke_itb
    IS '[ACTIVE | kd_pertanyaan=19 | kd_grup=9 Rekomendasi Tindak Lanjut] '
       'Hal-hal yang perlu dilakukan oleh ITB (institut, fakultas/sekolah, prodi) '
       'untuk mendukung keberhasilan perkuliahan: kurikulum, sarpras, fasilitas.';
-- ================================================================
-- COMMENT ON COLUMN — ERA LAMA (kd_pertanyaan 1–11)
-- ================================================================
COMMENT ON COLUMN analitik.v_akademik_portofolio.lama_metode_perkuliahan
    IS '[ARCHIVED | kd_pertanyaan=1 | kd_grup=2 Pelaksanaan Kuliah] '
       'Metode Perkuliahan.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.lama_statistik_kelas
    IS '[ARCHIVED | kd_pertanyaan=7 | kd_grup=2 Pelaksanaan Kuliah] '
       'Statistik Kelas.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.lama_outcomes_matakuliah
    IS '[ARCHIVED | kd_pertanyaan=2 | kd_grup=1 Pencapaian Tujuan/Outcomes] '
       'Outcomes Matakuliah.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.lama_sistem_penilaian
    IS '[ARCHIVED | kd_pertanyaan=3 | kd_grup=1 Pencapaian Tujuan/Outcomes] '
       'Sistem Penilaian.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.lama_analisis_statistik_ketercapaian
    IS '[ARCHIVED | kd_pertanyaan=8 | kd_grup=1 Pencapaian Tujuan/Outcomes] '
       'Analisis terhadap Statistik Kelas dan Ketercapaian Outcomes.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.lama_uraian_kuesioner_statistik
    IS '[ARCHIVED | kd_pertanyaan=4 | kd_grup=3 Refleksi] '
       'Uraian terhadap Hasil Kuesioner dan Statistik Kelas.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.lama_komentar_kuesioner_mahasiswa
    IS '[ARCHIVED | kd_pertanyaan=9 | kd_grup=3 Refleksi] '
       'Komentar terhadap Hasil Kuesioner Mahasiswa.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.lama_refleksi_perkuliahan
    IS '[ARCHIVED | kd_pertanyaan=5 | kd_grup=3 Refleksi] '
       'Refleksi Pelaksanaan Perkuliahan.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.lama_rencana_tindak_lanjut
    IS '[ARCHIVED | kd_pertanyaan=6 | kd_grup=4 Rencana Tindak Lanjut] '
       'Rencana Tindak Lanjut.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.lama_rekomendasi_perbaikan_dosen
    IS '[ARCHIVED | kd_pertanyaan=10 | kd_grup=5 Rekomendasi Tindak Lanjut] '
       'Rekomendasi Perbaikan oleh Dosen Berikutnya.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.lama_rekomendasi_itb
    IS '[ARCHIVED | kd_pertanyaan=11 | kd_grup=5 Rekomendasi Tindak Lanjut] '
       'Rekomendasi Perbaikan oleh ITB.';
-- ================================================================
-- COMMENT ON COLUMN — KOMENTAR VERIFIKATOR ERA BARU
-- ================================================================
COMMENT ON COLUMN analitik.v_akademik_portofolio.komentar_penyelenggaraan
    IS '[ACTIVE | kd_grup=6] '
       'Komentar verifikator untuk grup Penyelenggaraan Perkuliahan.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.komentar_ketercapaian
    IS '[ACTIVE | kd_grup=7] '
       'Komentar verifikator untuk grup Ketercapaian Outcomes.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.komentar_refleksi
    IS '[ACTIVE | kd_grup=8] '
       'Komentar verifikator untuk grup Refleksi Dosen.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.komentar_rekomendasi
    IS '[ACTIVE | kd_grup=9] '
       'Komentar verifikator untuk grup Rekomendasi Tindak Lanjut.';
-- ================================================================
-- COMMENT ON COLUMN — KOMENTAR VERIFIKATOR ERA LAMA
-- ================================================================
COMMENT ON COLUMN analitik.v_akademik_portofolio.lama_komentar_pencapaian_outcomes
    IS '[ARCHIVED | kd_grup=1] '
       'Komentar verifikator untuk grup Pencapaian Tujuan/Outcomes.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.lama_komentar_pelaksanaan_kuliah
    IS '[ARCHIVED | kd_grup=2] '
       'Komentar verifikator untuk grup Pelaksanaan Kuliah.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.lama_komentar_refleksi
    IS '[ARCHIVED | kd_grup=3] '
       'Komentar verifikator untuk grup Refleksi.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.lama_komentar_rencana_tindak_lanjut
    IS '[ARCHIVED | kd_grup=4] '
       'Komentar verifikator untuk grup Rencana Tindak Lanjut.';
COMMENT ON COLUMN analitik.v_akademik_portofolio.lama_komentar_rekomendasi
    IS '[ARCHIVED | kd_grup=5] '
       'Komentar verifikator untuk grup Rekomendasi Tindak Lanjut.';