"""
Error taxonomy for SQL generation retries.
"""

from __future__ import annotations
import re
from enum import Enum

class ErrorCategory(str, Enum):
    """
    Taxonomy of common SQL generation error modes.
    """
    WRONG_TABLE        = "wrong_table"        # Relation does not exist
    WRONG_COLUMN       = "wrong_column"       # Column does not exist in table
    TYPE_MISMATCH      = "type_mismatch"      # Operator/type incompatibility
    WRONG_AGGREGATION  = "wrong_aggregation"  # GROUP BY missing non-aggregate columns
    JOIN_INCONSISTENCY = "join_inconsistency" # Ambiguous column ref across joined tables
    NULL_HANDLING      = "null_handling"      # Unexpected NULL breaks aggregation/comparison
    NO_RESULTS         = "no_results"         # Query valid but returned 0 rows (over-filtered)
    SECURITY_VIOLATION = "security_violation" # Blocked by security check
    PARSE_ERROR        = "parse_error"        # SQL syntax error
    ANSWER_INVALID     = "answer_invalid"     # Result doesn't answer the question
    UNKNOWN            = "unknown"            # Could not classify


_PATTERNS: list[tuple[str, ErrorCategory, str]] = [
    # Wrong column
    (
        r'column "([^"]+)" (does not exist|of relation)',
        ErrorCategory.WRONG_COLUMN,
        "Check exact column name in DATABASE SCHEMA. Use table alias prefix to avoid ambiguity. "
    ),
    # Wrong table / relation
    (
        r'relation "([^"]+)" does not exist',
        ErrorCategory.WRONG_TABLE,
        "Verify table name against DATABASE SCHEMA.",
    ),
    # Type mismatch — UUID
    (
        r"operator does not exist: uuid (=|<|>) (text|character varying)",
        ErrorCategory.TYPE_MISMATCH,
        "UUID comparisons need explicit cast. Use: 'value'::uuid = column, or column = 'value'::uuid. "
        "For array membership: 'uuid_value'::uuid = ANY(semua_dosen_id).",
    ),
    # Type mismatch — general
    (
        r"operator does not exist|cannot be used|invalid input syntax for type",
        ErrorCategory.TYPE_MISMATCH,
        "Add explicit type cast (::uuid, ::text, ::integer, ::numeric). "
        "Check that WHERE conditions compare compatible types.",
    ),
    # GROUP BY / aggregation
    (
        r"(must appear in the GROUP BY|aggregate functions are not allowed"
        r"|is not in GROUP BY clause|non-aggregate)",
        ErrorCategory.WRONG_AGGREGATION,
        "GROUP BY must include ALL non-aggregate columns in SELECT. "
        "Every column not inside COUNT/AVG/SUM/MAX/MIN must appear in GROUP BY. "
        "For HAVING, filter on the aggregate expression (e.g. HAVING AVG(col) > 3.0).",
    ),
    # Ambiguous column (join inconsistency)
    (
        r"column reference \"([^\"]+)\" is ambiguous",
        ErrorCategory.JOIN_INCONSISTENCY,
        "Prefix all columns with their table alias. "
        "Never use bare column names when joining multiple tables.",
    ),
    # NULL / division by zero
    (
        r"division by zero",
        ErrorCategory.NULL_HANDLING,
        "Wrap denominator in NULLIF(..., 0) to avoid division by zero. "
        "Example: COUNT(*) * 100.0 / NULLIF(total, 0).",
    ),
    # Security
    (
        r"Security Violation",
        ErrorCategory.SECURITY_VIOLATION,
        "SQL was rejected by security check. Ensure: only SELECT statements, "
        "no forbidden schemas, no PII columns in SELECT, no pg_* system calls.",
    ),
    # Syntax / parse
    (
        r"(syntax error|unterminated|unexpected|parse error|missing FROM)",
        ErrorCategory.PARSE_ERROR,
        "Fix SQL syntax. Common causes: missing closing parenthesis, missing comma, "
        "incorrect use of aliases, or invalid keyword placement.",
    ),
    # Answer invalid (from answer validator)
    (
        r"Answer (relevance )?validation failed|result (is )?empty|0 rows",
        ErrorCategory.NO_RESULTS,
        "The query returned 0 rows. Try loosening filters: "
        "(1) remove or widen time-period filter, "
        "(2) use ILIKE '%%keyword%%' instead of exact match, "
        "(3) check that the entity value matches the canonical DB value.",
    ),
]


def classify_sql_error(error_str: str) -> tuple[ErrorCategory, str]:
    """
    Classifies a PostgreSQL error string into a structured ErrorCategory
    and returns a correction_hint for the SQL generator.

    Args:
        error_str: Raw error message string from PostgreSQL or the security checker.

    Returns:
        Tuple of (ErrorCategory, correction_hint: str).
        Falls back to (UNKNOWN, generic advice) if no pattern matches.
    """
    if not error_str:
        return ErrorCategory.UNKNOWN, "No error message available. Inspect the query logic carefully."

    for pattern, category, hint in _PATTERNS:
        if re.search(pattern, error_str, re.IGNORECASE):
            return category, hint

    return (
        ErrorCategory.UNKNOWN,
        "Unknown error. Carefully re-read the DATABASE SCHEMA, verify all table and column names, "
        "and check that the query logic matches the question intent.",
    )
