from agent.state import AgentState, FormattedResponse

async def clarification_handler(state: AgentState) -> dict:
    """Pattern-matching clarification per QUERY_CLASSIFICATION.md spec."""
    query = state.get("effective_query", state.get("raw_query", "")).lower()
    
    # Check for ambiguous thresholds
    if any(word in query for word in ["bagus", "baik", "jelek", "buruk", "rendah", "tinggi"]):
        question = (
            "Untuk menjawab pertanyaan ini, saya perlu tahu definisi yang digunakan. "
            "Misalnya: nilai ≥ B, nilai ≥ AB, atau kriteria lain?"
        )
    # Check for unresolved pronouns
    elif any(word in query for word in ["mereka", "dia", "itu", "ini", "nya"]):
        question = (
            "Pertanyaan Anda merujuk ke entitas tertentu. "
            "Bisa sebutkan nama mata kuliah, dosen, atau kelas yang dimaksud?"
        )
    # Check for vague/short queries
    elif len(query.split()) <= 3:
        question = (
            "Pertanyaan ini terlalu singkat. "
            "Bisa sebutkan: (1) mata kuliah apa, (2) semester/tahun ajaran, "
            "dan (3) kelas atau dosen yang ingin dilihat?"
        )
    # Default: ask for more specifics
    else:
        question = (
            "Pertanyaan ini perlu informasi tambahan agar saya bisa memberikan jawaban yang tepat. "
            "Bisa sebutkan: (1) mata kuliah atau dosen yang dimaksud, "
            "(2) semester/tahun ajaran, dan (3) detail spesifik yang ingin diketahui?"
        )
    
    return {
        "formatted_response": FormattedResponse(
            response_type="clarification",
            clarification_question=question,
        )
    }
