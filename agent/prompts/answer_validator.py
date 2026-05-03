ANSWER_VALIDATOR_PROMPT = """Given the user's question and the SQL query result, determine if the result adequately answers the question.

Consider:
1. Does the result contain the data needed to answer the question?
2. If the result has 0 rows, is it because the data genuinely doesn't exist, or because the query was too restrictive?
3. Are the columns in the result relevant to what was asked?

QUESTION: {raw_query}

SQL USED: {generated_sql}

SQL RESULT ({row_count} rows):
{sql_result}

Reply with JSON only:
{{"is_valid": true|false, "reason": "brief explanation"}}

- "is_valid": true → result answers the question
- "is_valid": false → result is empty/irrelevant, retry with different SQL
"""
