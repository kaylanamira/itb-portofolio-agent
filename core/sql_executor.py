from __future__ import annotations

from decimal import Decimal
from typing import Protocol, Any, Optional
import logging
from psycopg import sql as psql
from core.database import get_db_connection
from core.scope import UserScope

logger = logging.getLogger(__name__)


def _coerce_value(v: Any) -> Any:
    """Coerce Decimal to float rounded to 2dp; leave everything else as-is."""
    if isinstance(v, Decimal):
        return float(round(v, 2))
    return v


class QueryResult:
    """Standardized result from SQL execution."""

    def __init__(self, rows: list[dict], row_count: int, error: Optional[str] = None):
        self.rows = rows
        self.row_count = row_count
        self.error = error


class QueryExecutor(Protocol):
    """Protocol for executing SQL queries."""
    async def execute(
        self,
        sql: str,
        user_scope: UserScope,
    ) -> QueryResult: ...


class PsycopgExecutor:
    """Executes SQL with RLS session variables via psycopg3."""

    async def execute(
        self,
        sql: str,
        user_scope: UserScope,
    ) -> QueryResult:
        """Execute SQL with RLS session vars set for the current user.

        Args:
            sql: Validated SELECT query.
            user_scope: UserScope providing RLS session variable values.

        Returns:
            QueryResult with rows (Decimal values coerced to float), row_count, and error.
        """
        logger.info("Executing SQL:\n%s", sql)
        try:
            async with get_db_connection() as conn:
                async with conn.transaction():
                    for key, value in user_scope.get_rls_vars().items():
                        await conn.execute(
                            psql.SQL("SET LOCAL {} = {}").format(
                                psql.Identifier(key),
                                psql.Literal(value),
                            )
                        )

                    cursor = await conn.execute(sql)
                    rows = await cursor.fetchall()

                    if cursor.description:
                        columns = [desc[0] for desc in cursor.description]
                        result = [
                            {col: _coerce_value(val) for col, val in zip(columns, row)}
                            for row in rows
                        ]
                    else:
                        result = []

                    return QueryResult(rows=result, row_count=len(result))

        except Exception as e:
            logger.error("SQL Execution Error: %s", e)
            return QueryResult(rows=[], row_count=0, error=str(e))
