import os
import re
import logging
from typing import Optional
from core.database import get_db_connection

logger = logging.getLogger(__name__)

SCHEMA_PATH = os.getenv("AGENT_SCHEMA_PATH", "db/legacy/schema_for_agent.md")
SCHEMA_RETRIEVAL_MODE = os.getenv("SCHEMA_RETRIEVAL_MODE", "live").lower()  # 'live' or 'file'

class FileSchemaRetriever:
    """Retrieves table schemas statically from a markdown definition file."""
    
    def __init__(self, schema_path: str = SCHEMA_PATH):
        self.schema_path = schema_path
        self._cache = None
        
    def _load_and_parse(self):
        if self._cache is not None:
            return self._cache
            
        try:
            with open(self.schema_path, "r") as f:
                content = f.read()
        except FileNotFoundError:
            self._cache = {}
            return self._cache
            
        tables = {}
        current_table = None
        current_content = []
        
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


class DBSchemaRetriever:
    """Dynamically retrieves table schemas and PostgreSQL comments from the database."""
    
    def __init__(self):
        self._cache = {}
        
    async def list_tables(self) -> list[str]:
        """Returns a list of all public table and view names."""
        query = """
            SELECT table_schema || '.' || table_name 
            FROM information_schema.tables 
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
        """
        try:
            async with get_db_connection() as conn:
                cursor = await conn.execute(query)
                rows = await cursor.fetchall()
                return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Error fetching table list: {e}")
            return []
            
    async def describe_table(self, table_name: str) -> Optional[str]:
        """Returns the schema definition and semantic comments for a specific table."""
        if table_name in self._cache:
            return self._cache[table_name]
            
        # Parse schema and table name
        if "." in table_name:
            nspname, relname = table_name.split(".", 1)
        else:
            nspname, relname = "public", table_name
            
        # Query pg_description for table comment
        table_comment_query = """
            SELECT obj_description(c.oid)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = %s AND n.nspname = %s
        """
        
        # Query pg_attribute and pg_description for columns
        columns_query = """
            SELECT 
                a.attname as column_name,
                pg_catalog.format_type(a.atttypid, a.atttypmod) as data_type,
                col_description(a.attrelid, a.attnum) as column_comment
            FROM pg_catalog.pg_attribute a
            JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = %s AND n.nspname = %s AND a.attnum > 0 AND NOT a.attisdropped
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
                    col_name = r[0]
                    data_type = r[1]
                    col_comment = r[2]
                    
                    line = f"  - {col_name} ({data_type})"
                    if col_comment:
                        line += f": {col_comment}"
                    lines.append(line)
                    
                result = "\n".join(lines)
                self._cache[table_name] = result
                return result
        except Exception as e:
            logger.error(f"Error fetching schema for {table_name}: {e}")
            return None

db_retriever = DBSchemaRetriever()
file_retriever = FileSchemaRetriever()

async def describe_tables(table_names: list[str]) -> str:
    """Returns a concatenated string of schema definitions for the requested tables.
    """
    descriptions = []
    use_live = (SCHEMA_RETRIEVAL_MODE == "live")
    
    for t in table_names:
        desc = None
        
        if use_live:
            desc = await db_retriever.describe_table(t)
            
        if not desc:
            if use_live:
                logger.warning(f"Live DB retrieval returned empty for '{t}'. Falling back to file schema.")
            desc = file_retriever.describe_table(t)
            
        if desc:
            descriptions.append(desc)
    
    if not descriptions:
        return "No schema metadata found for requested tables."
    return "\n\n".join(descriptions)
