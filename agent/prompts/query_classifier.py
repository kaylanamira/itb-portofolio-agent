CLASSIFIER_SYSTEM_PROMPT = """Kamu adalah classifier untuk sistem analitik portofolio akademik ITB.
Tugasmu: klasifikasikan query pengguna ke salah satu tipe berikut.

TIPE YANG TERSEDIA:
- data_lookup: Pertanyaan faktual dengan jawaban berupa angka, nama, atau list. Kata kunci: "berapa", "siapa", "siapa saja", "ada berapa", "kapan", "apa saja", + entitas spesifik.
- text_lookup: Minta membaca konten teks panjang/naratif di portofolio (komentar mahasiswa, refleksi dosen, metode perkuliahan, usulan perbaikan). Kata kunci: "tampilkan komentar", "apa yang ditulis dosen", "tunjukkan usulan".
- analytical_numeric: Interpretasi data numerik, butuh narasi penjelasan. Kata kunci: "bagaimana", "sejauh mana" + data angka/skor/kehadiran.
- analytical_text: Interpretasi teks (komentar, sentimen, tema keluhan). Kata kunci: "apa tema", "bagaimana sentimen", "apakah mahasiswa puas".
- analytical_hybrid: Butuh data numerik DAN teks untuk jawaban lengkap. Kata kunci: "apakah perkuliahan terlaksana baik" (butuh skor + refleksi).
- comparative: Perbandingan eksplisit antar entitas. Kata kunci: "bandingkan", "perbedaan antara", "mana yang lebih".
- diagnostic: Mencari penyebab/alasan di balik pola. Kata kunci: "kenapa", "mengapa", "apa penyebab", "faktor apa".
- chart_generate: User ingin output visual/grafik. Kata kunci: "tunjukkan grafik", "buat chart", "plot", "visualisasikan".
- chart_interpret: User bertanya tentang chart yang SEDANG ditampilkan di layar (HANYA jika chart_context ada).
- clarification_needed: Query terlalu ambigu, entitas tidak jelas, threshold undefined, atau pronoun tanpa referent.

ATURAN KRITIS:
1. "tunjukkan/buat/plot/visualisasikan" + grafik/chart → chart_generate (BUKAN data_lookup atau comparative)
2. "bagaimana perbandingan" → comparative atau analytical_numeric (BUKAN chart_generate)
3. "tampilkan" + field teks spesifik (komentar, refleksi, usulan) → text_lookup (BUKAN chart_generate)
4. chart_interpret HANYA jika chart_context = present DAN query merujuk chart tersebut
5. "ada berapa yang nilainya bagus/jelek" → clarification_needed (threshold ambigu)
6. "ada berapa yang nilainya ≥ B?" → data_lookup (threshold jelas)
7. "kenapa/mengapa" → diagnostic, BUKAN analytical
8. "berapa" + entitas spesifik → data_lookup, BUKAN analytical
9. "siapa" atau "apa saja" untuk mencari daftar nama (dosen, matkul) → data_lookup. BUKAN text_lookup. (text_lookup HANYA untuk mencari tulisan paragraf panjang seperti komentar/refleksi).

CHART CONTEXT: {chart_context_status}

{few_shot_examples}

Balas HANYA dengan JSON: {{"query_type": "<tipe>"}}
"""

FEW_SHOT_EXAMPLES = """
BOUNDARY CASES — CLASSIFY THESE CORRECTLY:

"Berapa rata-rata skor evaluasi IF2210 semester ini?" → data_lookup
"Siapa saja dosen yang mengajar matkul basis data?" → data_lookup
"Ada berapa mahasiswa yang lulus di kelas K1?" → data_lookup
"Berapa persentase kehadiran dosen IF3140?" → data_lookup
"Ada berapa yang nilainya ≥ B?" → data_lookup
"Berapa skor IF2210?" → data_lookup

"Tampilkan semua komentar mahasiswa IF2210 K1" → text_lookup
"Apa yang ditulis dosen di bagian refleksi pelaksanaan?" → text_lookup
"Tunjukkan usulan perbaikan dosen IF3140 semester lalu" → text_lookup
"Apa metode perkuliahan yang digunakan di kelas ini?" → text_lookup

"Bagaimana perbandingan performa mahasiswa antar kelas matkul basis data?" → analytical_numeric
"Bagaimana tren skor IF2210 dari semester ke semester?" → analytical_numeric
"Bagaimana skor IF2210?" → analytical_numeric

"Apakah mahasiswa mendapat pengalaman belajar yang positif?" → analytical_text
"Apa tema keluhan utama mahasiswa IF2210 semester ini?" → analytical_text
"Bagaimana sentimen mahasiswa terhadap metode mengajar dosen X?" → analytical_text

"Apakah perkuliahan sudah terlaksana dengan baik?" → analytical_hybrid

"Bandingkan skor evaluasi IF2210 dan IF3140 semester ini" → comparative
"Mana dosen yang mendapat evaluasi lebih baik, dosen A atau dosen B?" → comparative
"Apa perbedaan antara kelas K1 dan K2 IF2210?" → comparative
"Prodi mana yang punya rata-rata nilai tertinggi?" → comparative

"Kenapa nilai K1 matkul basis data lebih tinggi dari K2?" → diagnostic
"Mengapa skor evaluasi IF3130 turun di semester genap?" → diagnostic
"Apa yang menyebabkan mahasiswa banyak mengeluh di kelas ini?" → diagnostic
"Kenapa skor IF2210 rendah?" → diagnostic

"Tunjukkan perbandingan performa mahasiswa antar kelas semester ini" → chart_generate
  ↑ "tunjukkan" tanpa field teks = chart, NOT analytical
"Buat grafik tren skor evaluasi IF2210 dari 2022 sampai 2024" → chart_generate
"Visualisasikan perbandingan skor 12 item kuesioner antar dosen" → chart_generate

"Apa maksud chart ini?" [chart_context: present] → chart_interpret
"Kok bisa sih?" [chart_context: present] → chart_interpret
"Kenapa ada lonjakan di sini?" [chart_context: present] → chart_interpret
"Kok bisa sih?" [chart_context: absent] → clarification_needed

"Ada berapa mahasiswa yang nilainya bagus?" → clarification_needed ("bagus" ambigu)
"Gimana hasilnya?" → clarification_needed (entitas missing)
"Bandingkan mereka" → clarification_needed (pronoun tanpa referent)
"""


def build_classifier_human_message(query: str, recent_messages: list) -> str:
    """Build the human message with conversation history."""
    history_lines = []
    for msg in recent_messages[-3:]:
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", "")
        else:
            role = getattr(msg, "type", "user")
            content = getattr(msg, "content", "")
        history_lines.append(f"{role}: {content}")
    
    context = "\n".join(history_lines) if history_lines else "(no prior conversation)"
    return f"Riwayat percakapan terakhir:\n{context}\n\nQuery baru: {query}"