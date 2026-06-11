ANSWER_VALIDATOR_PROMPT = """Given the user's question and the SQL query result, determine if the result adequately answers the question.

Rules:
1. The result columns must be relevant to what was asked. If the question asks about kehadiran but the result only has jumlah_peserta, it is INVALID.
2. Zero rows:
   - VALID only if the question is an existence check ("apakah ada", "adakah", "pernah ada") — zero rows is a meaningful "no".
   - INVALID if the question asks for a quantity ("berapa", "siapa", "apa nilai", "rata-rata") — zero rows means the query failed to find data.
3. Multiple rows are VALID when the question asks for a list, trend, comparison, or breakdown (e.g. "tren", "bandingkan", "per kelas", "per semester", "siapa saja"). Multiple rows are INVALID only when the question asks for a single total or count ("berapa total", "berapa jumlah") and the result returns unaggregated detail rows with no COUNT or SUM.
4. Extra columns alongside the relevant ones are acceptable.
5. If the result contains the correct metric columns and non-empty data (or is a valid existence check), it is VALID.

QUESTION: {raw_query}

SQL USED: {generated_sql}

SQL RESULT ({row_count} rows):
{sql_result}

Reply with JSON only:
{{"is_valid": true|false, "reason": "brief explanation"}}
"""
