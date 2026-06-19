import os
import re
import logging
from typing import Optional
from core.database import get_db_connection
from agent.tools.security import ALLOWED_SCHEMAS

logger = logging.getLogger(__name__)

SCHEMA_PATH = os.getenv("AGENT_SCHEMA_PATH", "db/DB_REFERENCE.md")
SCHEMA_RETRIEVAL_MODE = os.getenv("SCHEMA_RETRIEVAL_MODE", "live").lower()
MAX_TABLE_SCHEMA_CHARS = int(os.getenv("MAX_TABLE_SCHEMA_CHARS", "1500"))


class FileSchemaRetriever:
    """Retrieves table schemas from a markdown definition file."""

    def __init__(self, schema_path: str = SCHEMA_PATH):
        self.schema_path = schema_path
        self._cache: Optional[dict[str, str]] = None

    def _load_and_parse(self) -> dict[str, str]:
        if self._cache is not None:
            return self._cache

        try:
            with open(self.schema_path, "r") as f:
                content = f.read()
        except FileNotFoundError:
            self._cache = {}
            return self._cache

        tables: dict[str, str] = {}
        current_table: Optional[str] = None
        current_content: list[str] = []

        for line in content.split("\n"):
            match = re.match(r"^###\s+([a-zA-Z0-9_\.]+)", line)
            if match:
                if current_table:
                    tables[current_table] = "\n".join(current_content).strip()
                current_table = match.group(1).lower()
                current_content = [line]
            elif current_table:
                current_content.append(line)

        if current_table:
            tables[current_table] = "\n".join(current_content).strip()

        self._cache = tables
        return self._cache

    def describe_table(self, table_name: str) -> Optional[str]:
        """Returns the schema definition for a specific table."""
        tables = self._load_and_parse()
        return tables.get(table_name.lower())

    def load_full_context(self) -> str:
        """Loads the entire schema file as a string."""
        try:
            with open(self.schema_path, "r") as f:
                return f.read()
        except FileNotFoundError:
            return f"Warning: Schema file not found at {self.schema_path}"


class DBSchemaRetriever:
    """Retrieves table schemas dynamically from the database via pg_catalog."""

    def __init__(self):
        self._cache: dict[str, str] = {}

    async def list_tables(self, schemas: Optional[set[str]] = None) -> list[str]:
        """Returns table names from allowed schemas.

        Args:
            schemas: Optional set of schema names to filter. Defaults to ALLOWED_SCHEMAS.
        """
        target_schemas = schemas or ALLOWED_SCHEMAS
        placeholders = ", ".join(["%s"] * len(target_schemas))
        query = f"""
            SELECT table_schema || '.' || table_name
            FROM information_schema.tables
            WHERE table_schema IN ({placeholders})
            ORDER BY table_schema, table_name
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(query, list(target_schemas))
                rows = await cursor.fetchall()
                return [row[0] for row in rows]
        except Exception as e:
            logger.error("Error fetching table list: %s", e)
            return []

    async def describe_table(self, table_name: str) -> Optional[str]:
        """Returns column metadata and comments for a table.

        Args:
            table_name: Fully qualified table name (schema.table).
        """
        if table_name in self._cache:
            return self._cache[table_name]

        if "." in table_name:
            nspname, relname = table_name.split(".", 1)
        else:
            nspname, relname = "public", table_name

        table_comment_query = """
            SELECT obj_description(c.oid)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = %s AND n.nspname = %s
        """

        columns_query = """
            SELECT
                a.attname as column_name,
                pg_catalog.format_type(a.atttypid, a.atttypmod) as data_type,
                col_description(a.attrelid, a.attnum) as column_comment
            FROM pg_catalog.pg_attribute a
            JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = %s AND n.nspname = %s
              AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY a.attnum
        """

        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(table_comment_query, [relname, nspname])
                t_row = await cursor.fetchone()
                table_comment = t_row[0] if t_row and t_row[0] else ""

                cursor = await conn.execute(columns_query, [relname, nspname])
                c_rows = await cursor.fetchall()

                if not c_rows:
                    return None

                lines = [f"Table: {table_name}"]
                if table_comment:
                    lines.append(f"Description: {table_comment}")
                lines.append("Columns:")
                for r in c_rows:
                    line = f"  - {r[0]} ({r[1]})"
                    if r[2]:
                        line += f": {r[2]}"
                    lines.append(line)

                result = "\n".join(lines)
                self._cache[table_name] = result
                return result

        except Exception as e:
            logger.error("Error fetching schema for %s: %s", table_name, e)
            return None


db_retriever = DBSchemaRetriever()
file_retriever = FileSchemaRetriever()


async def describe_tables(table_names: list[str]) -> str:
    """Returns concatenated schema descriptions for requested tables.

    Tries live DB first. If the live description exceeds MAX_TABLE_SCHEMA_CHARS,
    falls back to the file-based description from DB_REFERENCE.md, which is the
    curated single source of truth with semantic context, scale mappings, and examples.

    Args:
        table_names: List of table names (schema-qualified or bare).
    """
    descriptions = []
    use_live = (SCHEMA_RETRIEVAL_MODE == "live")

    for t in table_names:
        desc = None

        if use_live:
            desc = await db_retriever.describe_table(t)
            if desc and len(desc) > MAX_TABLE_SCHEMA_CHARS:
                logger.warning("Live schema for '%s' is %d chars, falling back to file.", t, len(desc))
                desc = file_retriever.describe_table(t) or desc[:MAX_TABLE_SCHEMA_CHARS]

        if not desc:
            if use_live:
                logger.warning("Live DB returned empty for '%s', falling back to file.", t)
            desc = file_retriever.describe_table(t)

        if desc:
            descriptions.append(desc)

    if not descriptions:
        return "No schema metadata found for requested tables."
    return "\n\n".join(descriptions)
