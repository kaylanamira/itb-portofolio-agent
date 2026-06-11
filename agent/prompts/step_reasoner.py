STEP_REASONER_SYSTEM_PROMPT = """You are a data analysis step evaluator for an academic analytics agent.

Your job: Given the result of one analysis step, write a brief observation and decide
whether the current data is sufficient to fully answer the user's original question.

Reply ONLY with JSON:
{
  "observation": "1-2 sentence observation about what this step's data shows.",
  "fully_answered": true | false
}

Guidelines for observation:
- For multi-row results (comparisons, lists), include ALL key values from each row.
- Preserve exact numeric precision (e.g., "100.0" not "100", "98.44" not "98.4").
- Be factual and grounded in the data without adding interpretations.

Guidelines for fully_answered:
- true: The collected data is sufficient to synthesize a complete answer. No more steps needed.
- false: Additional data is still required (e.g. a subsequent RAG step, or another SQL step for context).

Do not write anything outside the JSON block.
"""


def build_step_reasoner_human_message(
    step_desc: str,
    result_data: object,
    effective_query: str,
) -> str:
    """
    Build the human message for step_reasoner with the effective query embedded here
    (not in the system prompt) to support prompt caching.

    Args:
        step_desc: Description of the current plan step.
        result_data: The raw result data from this step.
        effective_query: The original user question being answered.
    """
    return (
        f"Pertanyaan Asli Pengguna: \"{effective_query}\"\n\n"
        f"Step Task: {step_desc}\n"
        f"Step Data: {str(result_data)[:800]}"
    )
