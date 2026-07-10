from core.scope import UserScope, UserRole
from api.services.akademik_constants import SEMESTER_MAP


def is_faculty_level(scope: UserScope) -> bool:
    return scope.role in (UserRole.ADMIN, UserRole.DIREKTORAT)


def period_label(tahun_ajaran: str | None, semester: int | None) -> str | None:
    if tahun_ajaran is None or semester is None:
        return None
    label = SEMESTER_MAP.get(semester, f"Semester {semester}")
    return f"{tahun_ajaran} {label}"