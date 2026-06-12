from agent.state import AgentState
from core.scope import UserScope, ScopeEntry, UserRole


def make_state_from_case(case: dict) -> AgentState:
    role_str = case.get("scope_role", "admin").upper()
    try:
        role_enum = UserRole[role_str]
    except KeyError:
        role_enum = UserRole.ADMIN
        
    scope_value = case.get("scope_value", {})
    entry = ScopeEntry(user_role_id=1, role=role_enum, is_prime=True, **scope_value)
    scope = UserScope(user_id=1000, active_role=entry, available_roles=[entry])
    
    messages = []
    if "clarification_needed" in case.get("tags", []):
        from langchain_core.messages import HumanMessage, AIMessage
        messages = [
            HumanMessage(content="Tampilkan nilai rata-rata IF1220 semester lalu."),
            AIMessage(content="Rata-rata nilainya adalah B.")
        ]
        
    return AgentState(
        raw_query=case.get("query", ""),
        effective_query=case.get("query", ""),
        user_scope=scope,
        session_id=f"eval-{case.get('id', 'unknown')}",
        plan=[],
        current_step_index=0,
        attempt_count=0,
        max_attempts=3,
        is_aborted=False,
        error_history=[],
        steps_completed=[],
        reasoning_history=[],
        messages=messages,
    )
