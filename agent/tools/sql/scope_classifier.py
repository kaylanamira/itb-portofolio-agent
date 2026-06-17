from __future__ import annotations

from typing import Any, Optional

from core.scope import UserScope

OUT_OF_SCOPE = "OUT_OF_SCOPE"
LEGITIMATE_NO_DATA = "LEGITIMATE_NO_DATA"


def _first(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else value


def _scope_checks(user_scope: UserScope, detected_entities: Any) -> list[tuple[Any, Any]]:
    role = user_scope.active_role
    checks = []
    if role.no_ps is not None:
        raw = getattr(detected_entities, "no_prodi", None) or getattr(detected_entities, "resolved_prodi_id", None)
        if raw is not None:
            try:
                checks.append((int(_first(raw)), role.no_ps))
            except (ValueError, TypeError):
                pass
    if role.kd_fak is not None:
        raw = getattr(detected_entities, "kode_fakultas", None)
        if raw is not None:
            checks.append((str(raw).upper(), str(role.kd_fak).upper()))
    if role.dosen_id is not None:
        raw = getattr(detected_entities, "resolved_dosen_id", None)
        if raw is not None:
            checks.append((int(raw), role.dosen_id))
    return checks


def classify_empty_result(
    user_scope: UserScope,
    detected_entities: Optional[Any],
) -> str:

    if user_scope.can_see_all or detected_entities is None:
        return LEGITIMATE_NO_DATA

    for requested, allowed in _scope_checks(user_scope, detected_entities):
        if requested != allowed:
            return OUT_OF_SCOPE

    return LEGITIMATE_NO_DATA
