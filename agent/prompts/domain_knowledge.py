PORTFOLIO_CATALOG_DIMENSIONS = """
Pre-aggregated dimension scores in v_akademik_statistik_prodi:

| Column | Questions | Semantic scope |
|---|---|---|
| avg_skor_capaian | Q21–23 | capaian pembelajaran, luaran matakuliah |
| avg_skor_pelaksanaan | Q24–30 | pelaksanaan perkuliahan, dosen, sarana |
| avg_skor_sarana_prasarana | Q29–30 | fasilitas, sarana prasarana |
| avg_skor_perilaku_mahasiswa | Q35, 37 | kesungguhan dan pengalaman belajar mahasiswa |
| avg_skor_overall | all | kepuasan keseluruhan |

catalog_dimension valid values and scope (for catalog lookup steps):

| catalog_dimension (exact value) | Semantic scope | Questions |
|---|---|---|
| Outcome (luaran) matakuliah | capaian pembelajaran, luaran matkul, kompetensi, tujuan kuliah | Q21–23, 128–129 |
| Pelaksanaan perkuliahan | dosen, komunikasi, kehadiran, beban kuliah, SKS, sarana, fasilitas, pustaka | Q24–30, 130–139 |
| Pengalaman mahasiswa | pengalaman belajar, kepuasan belajar, manfaat kuliah, suasana akademik | Q35, 37, 140–145 |
| Masukan | saran, komentar bebas, praktikum, jam belajar mandiri | Q103, 146–149, 152 |

kd_pertanyaan → skor_q{N} column mapping (N = integer value):

| kd_pertanyaan | teks_pertanyaan | skor_q column |
|---|---|---|
| 25 | Dosen berkomunikasi dengan efektif | skor_q25 |
| 26 | Dosen peduli terhadap pencapaian mahasiswa | skor_q26 |
| 27 | Dosen berlaku adil (fair) | skor_q27 |
| 28 | Beban kerja sesuai SKS | skor_q28 |
| 29 | Sarana prasarana memadai | skor_q29 |
| 30 | Fasilitas pendukung memadai | skor_q30 |
| 37 | Pengalaman belajar positif | skor_q37 |
"""

WISUDAWAN_CATALOG_GROUPS = """
| kd_grup_pertanyaan | Topik | tipe_opsi | Scale | Common user intent |
|---|---|---|---|---|
| U01 | Pendidikan di prodi/dosen | O | SETUJU 1–4 | kepuasan dosen, merekomendasikan prodi, memilih prodi yang sama |
| U02 | Aspek rekomendasi prodi (bukan apakah merekomendasikan) | N | Nominal 1–7 | alasan merekomendasikan prodi |
| U03 | Fasilitas ITB | O | SETUJU 1–4 | kepuasan fasilitas ITB |
| U04 | Softskill | O | SETUJU 1–4 | softskill, kemampuan komunikasi, kerja tim |
| U05 | Karakter | O | SETUJU 1–4 | karakter, kejujuran, komitmen |
| U06 | Masalah studi (nilai tinggi = lebih sering masalah) | O | FREKUENSI 1–4 | masalah psikologis, masalah keuangan, masalah akademis |
| U07 | Ketersediaan dukungan | O | HARAPAN 1–5 | dukungan konseling, dukungan wali akademik |
| S1 | Rencana studi lanjut (S1 only) | N | YA_TIDAK | rencana studi lanjut, lanjut S2 |
| M | Rencana studi lanjut S2 (S2 only) | N | Nominal | rencana studi lanjut S2 |
| D01 | MKU untuk S3 (S3 only) | O | SETUJU 1–4 | MKU doktor |
"""

