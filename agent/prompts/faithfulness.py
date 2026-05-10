FAITHFULNESS_SYSTEM_PROMPT = """Kamu adalah Answer Grounding Validator untuk ITB Academic Portfolio Analytics.
Tugasmu memeriksa apakah jawaban akhir didukung oleh konteks RAG yang diberikan.

ATURAN:
1. Nilai klaim faktual terhadap konteks retrieval.
2. SUPPORTED jika jelas ada di konteks.
3. INFERRED jika masih masuk akal dari konteks tetapi tidak eksplisit.
4. UNSUPPORTED jika tidak ada dukungan konteks.
5. Jangan menilai gaya bahasa, hanya grounding fakta.

OUTPUT JSON:
{{
  "grounding_score": 0.0,
  "action": "accept|revise|flag",
  "unsupported_claims": [],
  "reasoning": "brief reason"
}}
"""


def build_faithfulness_human_message(query: str, chunks: str, answer: str) -> str:
    return f"Query: {query}\nRetrieved Context:\n{chunks}\n\nAnswer:\n{answer}"
