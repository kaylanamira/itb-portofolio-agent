from agent.state import AgentState, ValidationStatus
from agent.tools.security import check_sql_security
import sqlglot

async def sql_validator(state: AgentState) -> dict:
    sql = state.get("generated_sql", "")
    is_safe, sec_err = check_sql_security(sql)
    if not is_safe:
        error_entry = {"attempt": state.get("attempt_count", 0), "sql": sql,
                       "error": sec_err, "type": "security_violation"}
        return {
            "validation_status": ValidationStatus.FAIL,
            "validation_errors": [sec_err],
            "error_history": [error_entry],
        }
    
    try:
        parsed = sqlglot.parse_one(sql, read="postgres")
        if not isinstance(parsed, sqlglot.exp.Select):
            raise ValueError("Query must be a SELECT statement.")
    except Exception as e:
        error_msg = f"SQL Parse Error: {str(e)}"
        error_entry = {"attempt": state.get("attempt_count", 0), "sql": sql,
                       "error": error_msg, "type": "parse_error"}
        return {
            "validation_status": ValidationStatus.FAIL,
            "validation_errors": [error_msg],
            "error_history": [error_entry],
        }
        
    return {"validation_status": ValidationStatus.PASS}

def route_after_validation(state: AgentState) -> str:
    if state.get("validation_status") == ValidationStatus.PASS:
        return "sql_executor"
    return "error_handler"
