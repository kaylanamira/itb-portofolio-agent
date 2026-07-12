from core.config import settings

CONVERSATION_SUMMARY_PROMPT = f"""You are a conversation summarizer for ITB Academic Portfolio Analytics.
Create a summary of the conversation so far in max {settings.MEMORY_SUMMARY_MAX_WORDS} words.

MUST include if mentioned:
- Academic entities: kelas (kode_matkul + no_kelas), dosen (nama), prodi, semester, tahun_ajaran
- Last query intent (e.g., "user was investigating low scores in IF2210")
- Any unresolved comparisons or follow-up questions

EXCLUDE: greetings, system messages, clarification exchanges.
SCOPE RULE: Only name entities within the user's authorized scope.

Return ONLY the summary string. Return empty string if no meaningful content."""


def build_conversation_summary_messages(
    previous_summary: str | None,
    messages: list[dict],
) -> list[dict[str, str]]:
    previous = previous_summary.strip() if previous_summary else "(none)"
    formatted_messages = "\n".join(
        f"{message.get('role', 'user')}: {message.get('content', '')}"
        for message in messages
        if message.get("content")
    )
    return [
        {"role": "system", "content": CONVERSATION_SUMMARY_PROMPT},
        {
            "role": "user",
            "content": (
                f"Previous summary:\n{previous}\n\n"
                f"Conversation turns to merge into the summary:\n{formatted_messages}"
            ),
        },
    ]
