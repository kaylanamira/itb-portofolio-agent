from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm
from agent.prompts.faithfulness import FAITHFULNESS_SYSTEM_PROMPT, build_faithfulness_human_message
from agent.state import StepResult
from agent.tools.rag_models import FaithfulnessEvaluation
from core.config import settings
from core.utils import extract_json_from_llm

logger = logging.getLogger(__name__)


class FaithfulnessChecker:
    async def check(self, query: str, answer: str, steps: list[StepResult]) -> FaithfulnessEvaluation:
        rag_context = _rag_context(steps)
        if not rag_context:
            return FaithfulnessEvaluation(grounding_score=1.0, action="accept")

        llm = get_llm("answer_validation")
        try:
            response = await llm.ainvoke([
                SystemMessage(content=FAITHFULNESS_SYSTEM_PROMPT),
                HumanMessage(content=build_faithfulness_human_message(
                    query=query,
                    chunks=rag_context,
                    answer=answer,
                )),
            ])
            data = extract_json_from_llm(response.content)
            score = float(data.get("grounding_score", 0.0))
            return FaithfulnessEvaluation(
                grounding_score=score,
                action=_normalize_action(score, data.get("action")),
                unsupported_claims=data.get("unsupported_claims") or [],
                reasoning=data.get("reasoning", ""),
            )
        except Exception as exc:
            logger.warning("Faithfulness check failed: %s", exc)
            return FaithfulnessEvaluation(grounding_score=1.0, action="accept")


def _rag_context(steps: list[StepResult]) -> str:
    chunks: list[str] = []
    for step in steps:
        if step.action != "rag" or not isinstance(step.result, list):
            continue
        for item in step.result[:10]:
            text = item.get("chunk_text") if isinstance(item, dict) else None
            label = item.get("kelas_label", "") if isinstance(item, dict) else ""
            if text:
                chunks.append(f"{label}: {text[:800]}")
    return "\n\n".join(chunks)


def _normalize_action(score: float, action: str | None) -> str:
    if action in {"accept", "revise", "flag"}:
        return action
    if score >= settings.FAITH_ACCEPT:
        return "accept"
    if score >= settings.FAITH_REVISE:
        return "revise"
    return "flag"


faithfulness_checker = FaithfulnessChecker()
