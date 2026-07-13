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
