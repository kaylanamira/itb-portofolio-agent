import logging
from agent.state import AgentState
from core.database import get_db_connection
from psycopg import sql
import sqlglot
from sqlglot import exp

logger = logging.getLogger(__name__)

async def sql_executor(state: AgentState) -> dict:
    raw_sql = state.get("generated_sql", "")
    scope = state["user_scope"]
    
    try:
        parsed = sqlglot.parse_one(raw_sql, read="postgres")
        tables = [t.name.lower() for t in parsed.find_all(exp.Table) if t.name]
        target_table = tables[0] if tables else "mv_kelas"
        for t in tables:
            if t.startswith("mv_") or t in ("teks_portofolio", "komentar_mahasiswa"):
                target_table = t
                break
    except Exception:
        relevant_tables = state.get("relevant_tables", ["mv_kelas"])
        target_table = relevant_tables[0] if relevant_tables else "mv_kelas"
    
    # Get the correct scope filter for this table
    scope_where, scope_params = scope.scope_where(target_table)
    
    # First escape all literal % in the LLM SQL (e.g. from ILIKE '%keyword%')
    # psycopg interprets % as a placeholder prefix, so %i in ILIKE causes an error.
    # We double them to %% first, then inject scope_where (which legitimately uses %s).
    escaped_sql = raw_sql.replace('%', '%%')
    
    # Replace the {SCOPE_FILTER} placeholder with scope filter (may contain %s)
    sql_with_scope = escaped_sql.replace('{SCOPE_FILTER}', f'({scope_where})')
    
    logger.info(f"Executing SQL (table={target_table}):\n{sql_with_scope}")
    logger.info(f"Scope params: {scope_params}")
    
    try:
        async with get_db_connection() as conn:
            # Execute within a transaction for SET LOCAL
            async with conn.transaction():
                await conn.execute(
                    sql.SQL("SET LOCAL app.user_id = {}").format(
                        sql.Literal(str(scope.user_id))
                    )
                )
                cursor = await conn.execute(sql_with_scope, scope_params)
                rows = await cursor.fetchall()
                
                if cursor.description:
                    columns = [desc[0] for desc in cursor.description]
                    result = [dict(zip(columns, row)) for row in rows]
                else:
                    result = []
                    
                return {
                    "sql_with_scope": sql_with_scope,
                    "sql_result": result,
                    "sql_error": None,
                    "sql_row_count": len(result),
                }
    except Exception as e:
        logger.error(f"SQL Execution Error: {e}")
        error_entry = {
            "attempt": state.get("attempt_count", 0),
            "sql": sql_with_scope,
            "error": str(e),
            "type": "execution_error",
        }
        return {
            "sql_with_scope": sql_with_scope,
            "sql_result": None,
            "sql_error": str(e),
            "error_history": [error_entry],
        }

def route_after_executor(state: AgentState) -> str:
    if state.get("sql_error") is None:
        return "answer_validator"
    return "error_handler"
