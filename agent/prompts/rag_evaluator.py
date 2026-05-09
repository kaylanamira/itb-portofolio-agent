CRAG_EVALUATOR_PROMPT = """You are a retrieval quality evaluator for an academic portfolio RAG system.

Query: {query}
Retrieved chunks ({n} chunks):
{chunks_preview}

<thinking>
Evaluate each chunk: does it contain information that directly or partially addresses the query?
Consider: relevance, specificity, scope match (is it about the right kelas/prodi/dosen?).
Estimate overall confidence.
</thinking>

Reply with JSON only:
{{
  "confidence": 0.0-1.0,
  "action": "accept|refine|fallback",
  "refine_suggestion": "rewritten query or null",
  "reasoning": "..."
}}"""
