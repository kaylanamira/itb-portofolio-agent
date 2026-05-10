from __future__ import annotations

from agent.state import AgentState
from agent.utils.content_filter import filter_content
from core.config import settings


async def input_guard(state: AgentState) -> dict:
    if not settings.CONTENT_FILTER_ENABLED:
        return {"content_filter_result": "safe"}

    result = filter_content(state.get("raw_query", ""))
    if result == "safe":
        return {"content_filter_result": result}
    return {
        "content_filter_result": result,
        "domain": "out_of_scope",
        "is_aborted": True,
        "abort_reason": _abort_reason(result),
    }


def route_after_input_guard(state: AgentState) -> str:
    return "out_of_scope" if state.get("is_aborted") else "intent_classifier"


def _abort_reason(result: str) -> str:
    reasons = {
        "prompt_injection": "Permintaan mengandung instruksi yang mencoba mengubah perilaku sistem.",
        "pii": "Permintaan mengandung pola data pribadi yang tidak boleh diproses.",
        "sql_fragment": "Permintaan mengandung instruski SQL atau pola yang berisiko untuk keamanan.",
    }
    return reasons.get(result, "Permintaan tidak dapat diproses karena alasan keamanan.")
