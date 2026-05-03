INTENT_SYSTEM_PROMPT = """
You are an intent classifier for ITB Academic Portfolio Analytics system.

Classify the user query into exactly one domain.

DOMAINS:
- portfolio: Questions about portofolio perkuliahan ITB — nilai mahasiswa, kehadiran dosen/mahasiswa, kuesioner evaluasi, refleksi dosen, usulan perbaikan, statistik kelas, performa prodi/fakultas, perbandingan antar kelas/dosen/matkul, analisis capaian pembelajaran. This ALSO includes general reference queries like daftar fakultas, daftar prodi, daftar dosen, and daftar mata kuliah di ITB.
- wisudawan: Questions about survei wisudawan ITB — kepuasan alumni, relevansi kurikulum dengan karir, feedback pasca kelulusan, wisudawan, alumni, lulusan, feedback after graduation.
- out_of_scope: Anything not related to ITB academic portfolio or graduate data.

Consider the conversation history to classify domain.

Respond with JSON only:
{"domain": "portfolio"|"wisudawan"|"out_of_scope", "confidence": 0.0-1.0, "reason": "..."}
""" 

def build_intent_human_message(query: str, recent_messages: list, chart_context=None) -> str:
    """Build the human message with conversation context."""
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
    
    chart_note = ""
    if chart_context:
        title = chart_context.title if hasattr(chart_context, "title") else chart_context.get("title", "unknown")
        chart_note = f"\nUser is currently viewing chart: {title}"

    return f"Recent conversation:\n{context}{chart_note}\n\nQuery: {query}"
