ANSWER_VALIDATOR_PROMPT = """Given the current plan step task and the SQL query result, determine if the result adequately answers the step task.

Rules:
1. The result columns must be relevant to the step task.
2. If the step task is a catalog or prerequisite lookup (e.g. fetching question catalog, dimension groups, scale options), and the result contains rows with question codes or dimension metadata, it is VALID regardless of null columns.
3. Zero rows:
   - VALID only if the question is an existence check ("apakah ada", "adakah", "pernah ada") — zero rows is a meaningful "no".
   - INVALID if the task asks for a quantity ("berapa", "siapa", "apa nilai", "rata-rata") — zero rows means the query failed to find data.
4. Multiple rows are VALID when the task asks for a list, trend, comparison, or breakdown. Multiple rows are INVALID only when the task asks for a single total or count and the result returns unaggregated detail rows with no COUNT or SUM.
5. Extra columns alongside the relevant ones are acceptable.
6. If the result contains the correct metric columns and non-empty data (or is a valid existence check), it is VALID.

STEP TASK: {raw_query}

SQL USED: {generated_sql}

SQL RESULT ({row_count} rows):
{sql_result}

Reply with JSON only:
{{"is_valid": true|false, "reason": "brief explanation"}}
"""
