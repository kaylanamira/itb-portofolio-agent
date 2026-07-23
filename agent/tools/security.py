"""SQL security validator.

Validates generated SQL against:
- Write operation blocklist
- Injection patterns
- Dangerous functions
- Schema and table access control (allowed/forbidden)
- PII column detection in SELECT clauses
"""

import re
from typing import Optional
import sqlglot
import sqlglot.expressions as exp

ALLOWED_SCHEMAS: frozenset[str] = frozenset({
    "utama", "kelas", "evaluasi", "evaluasi_wisudawan", "mahasiswa", "users",
    "kur24", "analitik", "referensi", "kurikulum",
})

FORBIDDEN_SCHEMA_PREFIXES: tuple[str, ...] = ("x_", "__")

FORBIDDEN_TABLES: frozenset[str] = frozenset({
    "checkpoints", "checkpoint_blobs", "checkpoint_writes",
    "chat_session", "chat_message", "ingestion_log",
    "information_schema",
    "vector_chunks",
})

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

SENSITIVE_COLUMN_PATTERNS: frozenset[str] = frozenset({
    "nim", "nip", "tgl_lahir", "tanggal_lahir", "tempat_lahir",
    "email", "no_hp", "no_telp", "alamat", "id_dikti", "no_ktp",
    "nik", "ip_address", "password", "token", "secret",
    "ms365_upn", "ina_id",
})

SENSITIVE_VALUE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b\d{8,}\b"),                    # NIM-like (8+ digits)
    re.compile(r"\b[\w.-]+@[\w.-]+\.\w+\b"),      # Email
    re.compile(r"\b\d{1,3}(\.\d{1,3}){3}\b"),     # IP address
]

def _is_schema_forbidden(schema_name: str, allowed_schemas: frozenset[str] = ALLOWED_SCHEMAS) -> bool:
    """Check if a schema is forbidden based on name or prefix patterns."""
    if not schema_name:
        return False
    lower = schema_name.lower()
    if lower not in allowed_schemas:
        return True
    for prefix in FORBIDDEN_SCHEMA_PREFIXES:
        if lower.startswith(prefix):
            return True
    return False


def _check_pii_columns(stmt: exp.Expression) -> Optional[str]:
    """Walk SELECT columns and flag any that match PII patterns."""
    for col in stmt.find_all(exp.Column):
        col_name = col.name.lower() if col.name else ""
        if col_name in SENSITIVE_COLUMN_PATTERNS:
            return f"PII Violation: SELECT includes sensitive column '{col.name}'"
    return None


def check_sql_security(
    sql: str,
    allowed_schemas: frozenset[str] | None = None,
) -> tuple[bool, str | None]:
    """Multi-layer security check on generated SQL.

    Args:
        sql: Raw SQL string to validate.
        allowed_schemas: Schema allowlist override. None uses the module default
            (ALLOWED_SCHEMAS). Pass an empty frozenset to skip schema enforcement
            entirely (e.g., for domain-agnostic benchmark evaluation).

    Returns:
        (True, None) if SQL passes all checks.
        (False, error_msg) if SQL fails validation.
    """
    _allowed = ALLOWED_SCHEMAS if allowed_schemas is None else allowed_schemas

    if not sql or not sql.strip():
        return False, "Security Violation: Empty SQL"

    sql_upper = sql.upper()

    # 1. Write-operation keyword
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(r"\b" + keyword + r"\b", sql_upper):
            return False, f"Security Violation: Forbidden keyword '{keyword}'"

    # 2. Injection patterns
    for pattern, label in INJECTION_PATTERNS:
        if re.search(pattern, sql, re.IGNORECASE):
            return False, f"Security Violation: {label} detected"

    # 3. Dangerous function names
    for func in DANGEROUS_FUNCTIONS:
        if re.search(r"\b" + re.escape(func) + r"\b", sql, re.IGNORECASE):
            return False, f"Security Violation: Dangerous function '{func}'"

    # 4. pg_* system access
    pg_matches = PG_SYSTEM_PATTERN.findall(sql)
    if pg_matches:
        return False, f"Security Violation: pg_* system access ({pg_matches[0]})"

    # 5. Vector operators
    if "<->" in sql or "<=>" in sql:
        return False, "Security Violation: Vector operators not allowed in SQL agent"

    # 6. AST-level checks via sqlglot
    try:
        statements = sqlglot.parse(sql, dialect="postgres")
    except sqlglot.errors.ParseError as e:
        return False, f"SQL Parse Error: {e}"

    if not statements:
        return False, "Security Violation: No SQL statement found"

    if len(statements) > 1:
        return False, "Security Violation: Multiple SQL statements not allowed"

    stmt = statements[0]

    if not isinstance(stmt, (exp.Query, exp.Subquery)):
        return False, f"Security Violation: Only read-only queries allowed, got {type(stmt).__name__}"

    # Check for write ops in subqueries/CTEs
    for node in stmt.walk():
        if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create)):
            return False, "Security Violation: Write operation in subquery/CTE"

    # 7. Schema and table access control
    if _allowed: 
        for table in stmt.find_all(exp.Table):
            table_name = table.name.lower() if table.name else ""
            schema_name = table.db.lower() if table.db else ""

            if table_name in FORBIDDEN_TABLES:
                return False, f"Security Violation: Access to restricted table '{table_name}'"

            if schema_name and _is_schema_forbidden(schema_name, _allowed):
                return False, f"Security Violation: Access to forbidden schema '{schema_name}'"

    # 8. PII column check
    pii_error = _check_pii_columns(stmt)
    if pii_error:
        return False, pii_error

    return True, None

