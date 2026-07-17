CHUNK_GRADER_SYSTEM_PROMPT = """You are a grader assessing relevance of a retrieved document to a user question.
If the document contains keyword(s) or semantic meaning related to the user question, grade it as relevant.
It does not need to be a stringent test. The goal is to filter out erroneous retrievals.
Return a JSON object with a single key 'score' containing a float between 0.0 and 1.0, where 1.0 means highly relevant and 0.0 means completely irrelevant.
Also provide a key 'reasoning' containing a brief explanation of the score.
"""

def build_chunk_grader_human_message(query: str, chunk_text: str) -> str:
    return f"""Retrieved document:
{chunk_text}

User question: {query}
"""

QUERY_TRANSFORMER_SYSTEM_PROMPT = """You are an AI assistant tasked with reforming queries for vector search.
Your goal is to optimize the original query based on the critique provided by the retrieval evaluator.
Return a JSON object with a single key 'refined_query' containing the optimized string.
"""

def build_query_transformer_human_message(query: str, critique: str) -> str:
    return f"""Original query: {query}
Evaluator critique: {critique}

Provide a better query for dense and sparse retrieval.
"""

ENTITY_EXTRACTION_SYSTEM_PROMPT = """You are an entity extractor for a RAG retrieval system over Indonesian
academic portfolio and student-comment data (ITB). Given a user's retrieval task, extract any
structured filters mentioned so retrieval can be narrowed precisely.

Return a JSON object with these keys (use null/omit when not mentioned, do not guess):
- "dosen_mention": string | null — a lecturer's name as mentioned (with or without honorifics like Pak/Bu/Prof/Dr).
- "kode_matkul": string | null — a course code (e.g. "IF1220"), only if explicitly given.
- "nama_matkul": string | null — a course name, only if explicitly given.
- "tahun": integer | null — a specific academic year (e.g. 2024), only if explicitly given.
- "tahun_ajaran": string | null — an academic year range like "2023/2024", only if explicitly given.
- "no_prodi": integer | null — a numeric program-of-study code, only if explicitly given.
- "kode_prodi": string | null — a 2-letter program code (e.g. "IF"), only if explicitly given.
- "semester": integer | null — 1 (ganjil), 2 (genap), or 3 (pendek), only if explicitly given.
- "sentiment_hint": "positive" | "negative" | "neutral" | null — the emotional tone the user is
  looking for in student comments (e.g. "kesal"/"kecewa" -> negative, "puas"/"senang" -> positive),
  null if the query is a neutral factual lookup.
- "is_verifikator": true | false | null — whether the user specifically wants the reviewer's
  ("verifikator"/"pemeriksa"/reviewer) assessment of the portfolio, as opposed to the dosen's own
  narrative or student comments. true if the query explicitly asks about reviewer/verifikator
  feedback or evaluation; false if it explicitly asks about the dosen's own account instead; null
  if the query doesn't distinguish (most queries — leave null, do not guess).
"""

def build_entity_extraction_human_message(task: str) -> str:
    return f"""Retrieval task: {task}

Extract the filters as JSON."""

HYDE_SYSTEM_PROMPT = """You are generating hypothetical passages for HyDE (Hypothetical Document
Embeddings) retrieval. Given a user's search query about Indonesian academic
portfolio narratives or student comments, write diverse hypothetical passages that would be
strong, DIRECT answers to the query i.e. what an ideal matching document would contain, written
in the same register as real portfolio narrative text or student comments (Indonesian, 2-4
sentences each). Each hypothesis should approach the query from a different angle so the set
covers more of the possible answer space, but do not fabricate specific names, dates, or numbers
that were not implied by the query.

Return a JSON object with a single key 'hypotheses' containing a list of strings.
"""

def build_hyde_human_message(query: str, n: int) -> str:
    return f"""Query: {query}

Generate exactly {n} diverse hypothetical passages."""

RAG_GENERATION_SYSTEM_PROMPT = """You are answering a question about Indonesian academic portfolio
data using ONLY the numbered context chunks provided. Follow these rules strictly:
1. Answer only using facts present in the numbered chunks below — never use outside knowledge.
2. Cite every factual claim with the marker(s) of the chunk(s) that support it, e.g. "Mahasiswa
   menilai perkuliahan terorganisir dengan baik [1][3]."
3. If the chunks do not contain enough information to answer the question, do not guess or
   hallucinate, instead set "insufficient_context" to true and give your best partial answer
   (or an empty string) in "answer".
4. Write the answer in Indonesian, matching the language of the source chunks.

Return a JSON object with:
- "answer": string, the answer text with inline [n] citation markers.
- "citations": list of objects, each {"marker": int, "chunk_id": string} for every [n] used in the answer.
- "insufficient_context": bool.
"""

def build_rag_generation_human_message(query: str, chunks: list[dict]) -> str:
    numbered = "\n".join(
        f"[{i}] (source: {c.get('source_type')}/{c.get('tipe_konten')}, chunk_id: {c.get('chunk_id')}):\n{c.get('chunk_text')}"
        for i, c in enumerate(chunks, 1)
    )
    return f"""Question: {query}

Context chunks:
{numbered}

Answer the question using only the chunks above, following the citation rules."""

RAG_REGENERATE_SYSTEM_PROMPT = """You previously answered a question but a faithfulness check found
that some of your claims were not actually supported by the source chunks. Rewrite the answer so
that EVERY claim is directly supported by the numbered context chunks. Where you cannot find
support for a claim, remove it or soften it rather than inventing support. Keep the same [n]
citation-marker convention as before.

Return a JSON object with the same shape as before: "answer", "citations"
(list of {"marker": int, "chunk_id": string}), "insufficient_context" (bool).
"""

def build_rag_regenerate_human_message(query: str, chunks: list[dict], previous_answer: str, unsupported_claims: list[str]) -> str:
    numbered = "\n".join(
        f"[{i}] (source: {c.get('source_type')}/{c.get('tipe_konten')}, chunk_id: {c.get('chunk_id')}):\n{c.get('chunk_text')}"
        for i, c in enumerate(chunks, 1)
    )
    unsupported = "\n".join(f"- {c}" for c in unsupported_claims) or "(none flagged, but overall score was still low — be more conservative)"
    return f"""Question: {query}

Context chunks:
{numbered}

Previous answer:
{previous_answer}

Claims that were NOT supported by the context:
{unsupported}

Rewrite the answer so every claim is supported."""

FAITHFULNESS_SYSTEM_PROMPT = """You are a faithfulness evaluator for a RAG system, following the
RAGAS methodology: decompose the given answer into atomic factual claims, then
verify each claim against the provided numbered context chunks.

Steps:
1. Break the answer down into a list of atomic, independently-checkable claims (a claim should
   express exactly one fact).
2. For each claim, determine whether it is directly supported by at least one context chunk.

Return a JSON object with a single key "claims": a list of objects, each with:
- "claim": string, the atomic claim text.
- "supported": bool, true only if the claim is directly supported by the context.
- "supporting_chunk_id": string | null, the chunk_id of the strongest supporting chunk, or null if unsupported.
"""

def build_faithfulness_human_message(answer: str, chunks: list[dict]) -> str:
    numbered = "\n".join(
        f"[{i}] (chunk_id: {c.get('chunk_id')}):\n{c.get('chunk_text')}"
        for i, c in enumerate(chunks, 1)
    )
    return f"""Answer to evaluate:
{answer}

Context chunks:
{numbered}

Decompose the answer into claims and verify each against the context."""
