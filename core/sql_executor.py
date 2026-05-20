from typing import Protocol, Any, Sequence, Optional
import logging
from core.database import get_db_connection
from core.scope import UserScope

logger = logging.getLogger(__name__)

class QueryResult:
    """Standardized result from a SQL execution."""
    def __init__(self, rows: list[dict], row_count: int, error: Optional[str] = None):
        self.rows = rows
        self.row_count = row_count
        self.error = error

class QueryExecutor(Protocol):
    """Protocol for executing SQL queries."""
    async def execute(
        self,
        sql: str,
        params: Sequence[Any],
        user_scope: UserScope,
    ) -> QueryResult: ...

class PsycopgExecutor:
    
    async def execute(
        self,
        sql: str,
        params: Sequence[Any],
        user_scope: UserScope,
    ) -> QueryResult:
        logger.info("Executing SQL with PsycopgExecutor:\n%s", sql)
        try:
            async with get_db_connection() as conn:
                await conn.execute(f"SET LOCAL app.user_id = '{user_scope.user_id}'")
                cursor = await conn.execute(sql, params)
                rows = await cursor.fetchall()
                
                if cursor.description:
                    columns = [desc[0] for desc in cursor.description]
                    result = [dict(zip(columns, row)) for row in rows]
                else:
                    result = []
                    
                return QueryResult(rows=result, row_count=len(result))
        except Exception as e:
            logger.error("SQL Execution Error in PsycopgExecutor: %s", e)
            return QueryResult(rows=[], row_count=0, error=str(e))
