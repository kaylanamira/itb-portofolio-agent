from agent.state import AgentState, FormattedResponse
from core.config import settings

async def error_handler(state: AgentState) -> dict:
    new_attempt = state.get("attempt_count", 0) + 1
    max_attempts = state.get("max_attempts", settings.MAX_SQL_ATTEMPTS)
    
    if new_attempt <= max_attempts:
        return {
            "attempt_count": new_attempt,
            "generated_sql": None, 
            "sql_result": None,
            "sql_error": None      
        }
        
    last_error = state.get("error_history", [])[-1] if state.get("error_history") else {}
    error_type = last_error.get("type", "unknown")
    
    messages = {
        "execution_error":  "Maaf, terjadi kesalahan saat mengambil data. Coba ulangi atau persempit pertanyaan.",
        "security_violation": "Permintaan tidak dapat diproses karena alasan keamanan.",
        "answer_invalid":   "Maaf, tidak dapat menemukan jawaban yang sesuai. Coba pertanyaan yang lebih spesifik.",
    }
    narrative = messages.get(error_type, "Maaf, terjadi kesalahan yang tidak terduga.")
    
    return {
        "attempt_count": new_attempt,
        "formatted_response": FormattedResponse(
            response_type="error",
            narrative=narrative,
        ),
        "is_aborted": True,
        "abort_reason": "MAX_RETRIES_EXCEEDED"
    }

def route_after_error_handler(state: AgentState) -> str:
    if state.get("is_aborted", False) or state.get("attempt_count", 0) >= state.get("max_attempts", 3):
        return "response_formatter" 
    return "sql_generator"
