CRAG_EVALUATOR_SYSTEM_PROMPT = """Kamu adalah Retrieval Quality Evaluator untuk sistem RAG ITB Academic Portfolio.
Tugasmu mengevaluasi apakah chunk yang diambil benar-benar relevan dengan query dan scope akademik.

KRITERIA:
1. Relevance: chunk menjawab query secara langsung atau parsial.
2. Specificity: chunk cukup spesifik, bukan hanya kata kunci umum.
3. Scope match: chunk cocok dengan kelas/prodi/dosen/semester/tahun ajaran yang diminta.
4. Evidence sufficiency: kumpulan chunk cukup untuk sintesis jawaban.

Reply with JSON only:
{{
  "confidence": 0.0-1.0,
  "action": "accept|refine|fallback",
  "refine_suggestion": "rewritten query or null",
  "reasoning": "..."
}}"""


def build_crag_evaluator_human_message(query: str, n: int, chunks_preview: str) -> str:
    return f"Query: {query}\nRetrieved chunks ({n} chunks):\n{chunks_preview}"
