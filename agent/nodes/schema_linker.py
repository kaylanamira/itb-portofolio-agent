from core.utils import extract_json_from_llm
import json
from agent.state import AgentState, DetectedEntities
from agent.prompts.schema_linker import SCHEMA_LINKER_SYSTEM_PROMPT, build_schema_linker_human_message
from agent.llm import get_llm
from agent.tools.schema_loader import load_schema_context
from agent.tools.fuzzy_search import fuzzy_resolve_entities
from langchain_core.messages import SystemMessage, HumanMessage
from agent.tools.academic_calendar import get_current_academic_period

async def schema_linker(state: AgentState) -> dict:
    """LangGraph node: Extract entities and select relevant tables from the query."""
    llm = get_llm("schema_linking")

    user_scope = state.get("user_scope")
    user_role = user_scope.role.value if user_scope else "unknown"

    current_semester, current_tahun_ajaran = get_current_academic_period()
    plan = state.get("plan", [])
    idx = state.get("current_step_index", 0)
    current_task = plan[idx].get("task") if plan and idx < len(plan) else state["effective_query"]

    human_content = build_schema_linker_human_message(
        query=current_task,
        current_semester=current_semester,
        current_tahun_ajaran=current_tahun_ajaran,
        user_role=user_role,
    )

    messages = [
        SystemMessage(content=SCHEMA_LINKER_SYSTEM_PROMPT),
        HumanMessage(content=human_content),
    ]
    response = await llm.ainvoke(messages)

    schema_context = load_schema_context()

    try:
        content = extract_json_from_llm(response.content)
        entities_dict = content.get("detected_entities") or {}
        relevant_tables = content.get("relevant_tables") or ["mv_kelas"]
        valid_fields = DetectedEntities.model_fields.keys()
        filtered = {k: v for k, v in entities_dict.items() if k in valid_fields and v is not None}
        entities = DetectedEntities(**filtered)
    except Exception:
        entities = DetectedEntities()
        relevant_tables = ["mv_kelas"]

    resolved_entities = await fuzzy_resolve_entities(entities)

    return {
        "detected_entities": resolved_entities,
        "relevant_tables": relevant_tables,
        "schema_context": schema_context,
    }
