from __future__ import annotations

from agent.state import AgentState
from agent.tools.faithfulness_checker import faithfulness_checker
from core.config import settings


async def faithfulness_checker(state: AgentState) -> dict:
    response = state.get("formatted_response")
    steps = state.get("steps_completed", [])
    has_rag = any(step.action == "rag" for step in steps)
    if response is None or not has_rag:
        return {}

    evaluation = await faithfulness_checker.check(
        query=state.get("effective_query", ""),
        answer=response.narrative,
        steps=steps,
    )

    if evaluation.action in {"revise", "flag"}:
        response = response.model_copy(update={
            "disclaimer": response.disclaimer or settings.FAITH_DISCLAIMER,
        })

    return {
        "formatted_response": response,
        "faithfulness_score": evaluation.grounding_score,
        "faithfulness_action": evaluation.action,
    }
