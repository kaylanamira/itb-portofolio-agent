import logging
from agent.state import AgentState

logger = logging.getLogger(__name__)

async def answer_validator(state: AgentState) -> dict:
    sql_result = state.get("sql_result")
    sql_error = state.get("sql_error")
    row_count = state.get("sql_row_count", 0)
    
    # If there was a SQL execution error, always mark as invalid
    if sql_error is not None:
        error_entry = {
            "attempt": state.get("attempt_count", 0), 
            "sql": state.get("generated_sql", ""),
            "error": sql_error, 
            "type": "execution_error",
        }
        return {
            "answer_is_valid": False,
            "error_history": [error_entry],
        }
    
    # Rule-based validation:
    # 1. Aggregation queries (COUNT, AVG, SUM) always return 1 row — even a count of 0 is valid
    # 2. Any result with rows is considered valid at this stage
    # 3. Only truly empty results (None or []) from non-aggregate queries are suspicious
    
    if sql_result is None:
        error_entry = {
            "attempt": state.get("attempt_count", 0),
            "sql": state.get("generated_sql", ""),
            "error": "SQL returned no result set",
            "type": "answer_invalid",
        }
        return {
            "answer_is_valid": False,
            "error_history": [error_entry],
        }
    
    # If we got rows back (even 1 row from COUNT), it's valid
    if row_count > 0:
        logger.info(f"Answer validated: {row_count} rows returned")
        return {"answer_is_valid": True}
    
    # 0 rows from a non-aggregate query — still valid, the data just doesn't exist
    # Let the response_formatter explain "no data found" gracefully
    logger.info("Query returned 0 rows — passing to formatter to explain")
    return {"answer_is_valid": True}

def route_after_answer_validator(state: AgentState) -> str:
    if state.get("answer_is_valid", False):
        return "response_formatter"
    return "error_handler"
