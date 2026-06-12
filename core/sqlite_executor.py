"""SQLite-backed query executor for BIRD benchmark evaluation."""
from __future__ import annotations

import sqlite3
import asyncio
from dataclasses import dataclass, field


@dataclass
class SqliteQueryResult:
    rows: list[dict] = field(default_factory=list)
    row_count: int = 0
    error: str | None = None


class SqliteExecutor:
    """Synchronous SQLite executor wrapped in an async interface.

    Used exclusively for BIRD benchmark evaluation, where each DB is a local
    SQLite file. It follows the same execute() contract as PsycopgExecutor
    so test code can switch transparently.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def execute(self, query: str, user_scope=None) -> SqliteQueryResult:
        """Execute a SQL query against the SQLite database.

        Args:
            query: SQL string to execute.
            user_scope: Ignored for SQLite (no RLS).

        Returns:
            SqliteQueryResult with rows, row_count, and optional error.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_execute, query)

    def _sync_execute(self, query: str) -> SqliteQueryResult:
        try:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query)
            raw_rows = cursor.fetchall()
            rows = [dict(row) for row in raw_rows]
            conn.close()
            return SqliteQueryResult(rows=rows, row_count=len(rows))
        except Exception as e:
            return SqliteQueryResult(rows=[], row_count=0, error=str(e))
