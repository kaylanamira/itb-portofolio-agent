"""
SQL Security validator

Covers: write ops, injection patterns, dangerous functions, forbidden tables.

"""

import re
import sqlglot
import sqlglot.expressions as exp


FORBIDDEN_KEYWORDS: frozenset[str] = frozenset({
    "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER",
    "GRANT", "REVOKE", "EXECUTE", "CALL", "COPY", "VACUUM",
    "CREATE", "REPLACE", "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT",
    "LOCK", "NOTIFY", "LISTEN", "UNLISTEN", "LOAD", "IMPORT", "MERGE",
})

INJECTION_PATTERNS: list[tuple[str, str]] = [
    (r"--",          "SQL line comment"),
    (r"/\*",         "SQL block comment"),
    (r";\s*\S",      "Multiple statements"),
    (r"\bxp_",       "Extended procedure call"),
    (r"\bpg_sleep\b","Timing attack (pg_sleep)"),
]

DANGEROUS_FUNCTIONS: frozenset[str] = frozenset({
    "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_stat_file",
    "lo_read", "lo_import", "lo_export",
    "dblink", "dblink_exec",
    "file_fdw", "pg_stat_activity",
})

PG_SYSTEM_PATTERN = re.compile(r"\bpg_[a-z_]+\b", re.IGNORECASE)

FORBIDDEN_TABLES: frozenset[str] = frozenset({
    "pengguna",           # user accounts / credentials
    "user_scope",         # user permissions table
    "ingestion_log",      # system internals
    "chat_session",       # session data
    "chat_message",       # message history
    "checkpoints",        # LangGraph internals
    "checkpoint_blobs",
    "checkpoint_writes",
    "information_schema", # DB introspection
})

# Tables that belong to the RAG pipeline; the SQL agent should not touch them
RAG_ONLY_TABLES: frozenset[str] = frozenset({
    "vector_chunks",
})


def check_sql_security(sql: str) -> tuple[bool, str | None]:
    """
    Multi-layer pre-parse security check on a raw SQL string.

    Returns:
        (True, None)         — SQL passed all checks
        (False, error_msg)   — SQL failed; error_msg describes the violation
    """
    if not sql or not sql.strip():
        return False, "Security Violation: Empty SQL"

    sql_upper = sql.upper()

    # ── 1. Write-operation keyword blocklist ──────────────────────────────────
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(r"\b" + keyword + r"\b", sql_upper):
            return False, f"Security Violation: Forbidden keyword '{keyword}'"

    # ── 2. Injection patterns (raw string) ────────────────────────────────────
    for pattern, label in INJECTION_PATTERNS:
        if re.search(pattern, sql, re.IGNORECASE):
            return False, f"Security Violation: {label} detected"

    # ── 3. Dangerous function names ───────────────────────────────────────────
    for func in DANGEROUS_FUNCTIONS:
        if re.search(r"\b" + re.escape(func) + r"\b", sql, re.IGNORECASE):
            return False, f"Security Violation: Dangerous function '{func}' not allowed"

    # ── 4. Broad pg_* system function / catalog access ───────────────────────
    pg_matches = PG_SYSTEM_PATTERN.findall(sql)
    if pg_matches:
        return False, f"Security Violation: pg_* system access not allowed ({pg_matches[0]})"

    # ── 5. Vector operations (SQL agent doesn't do RAG) ──────────────────────
    if "<->" in sql or "<=>" in sql:
        return False, "Security Violation: Vector operators not allowed in SQL agent"

    # ── 6. sqlglot AST — table-level and write-op checks ─────────────────────
    try:
        statements = sqlglot.parse(sql, dialect="postgres")
    except sqlglot.errors.ParseError as e:
        return False, f"SQL Parse Error: {e}"

    if not statements:
        return False, "Security Violation: No SQL statement found"

    if len(statements) > 1:
        return False, "Security Violation: Multiple SQL statements not allowed"

    stmt = statements[0]

    # Root must be a SELECT (covers WITH...SELECT too via sqlglot)
    if not isinstance(stmt, exp.Select):
        return False, f"Security Violation: Only SELECT allowed, got {type(stmt).__name__}"

    # Check for write ops hidden in CTEs / subqueries
    for node in stmt.walk():
        if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create)):
            return False, "Security Violation: Write operation in subquery/CTE"

    # Extract all referenced table names and check against blocklists
    referenced_tables = {t.name.lower() for t in stmt.find_all(exp.Table) if t.name}

    forbidden_hit = referenced_tables & {t.lower() for t in FORBIDDEN_TABLES}
    if forbidden_hit:
        return False, f"Security Violation: Access to restricted table(s): {forbidden_hit}"

    rag_hit = referenced_tables & {t.lower() for t in RAG_ONLY_TABLES}
    if rag_hit:
        return False, f"Security Violation: RAG-only table accessed by SQL agent: {rag_hit}"

    return True, None
