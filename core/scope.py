from enum import Enum
from typing import Optional
from pydantic import BaseModel


class UserRole(str, Enum):
    ADMIN = "admin"
    DIREKTORAT = "direktorat"
    DEKAN = "dekan"
    JAJARAN_DEKANAT = "jajaran_dekanat"
    KAPRODI = "kaprodi"
    JAJARAN_PRODI = "jajaran_prodi"
    DOSEN = "dosen"


class ScopeEntry(BaseModel):
    """Role assignment from users.user_role."""
    user_role_id: int
    role: UserRole
    dosen_id: Optional[int] = None
    kk_id: Optional[int] = None
    no_ps: Optional[int] = None
    kd_fak: Optional[str] = None
    is_prime: bool = False


class UserScope(BaseModel):
    """Resolved user scope for a session.

    Args:
        user_id: The authenticated user's ID from users.user.
        active_role: The currently active ScopeEntry for this session.
        available_roles: All valid roles the user holds (for role switching).
    """
    user_id: int
    active_role: ScopeEntry
    available_roles: list[ScopeEntry] = []

    @property
    def role(self) -> UserRole:
        return self.active_role.role

    @property
    def can_see_all(self) -> bool:
        return self.role in (UserRole.ADMIN, UserRole.DIREKTORAT)

    def get_rls_vars(self) -> dict[str, str]:
        """Returns session variables for PostgreSQL RLS policies.

        These are set via SET LOCAL before query execution so the
        database can enforce row-level access control automatically.
        """
        r = self.active_role
        return {
            "app.user_id": str(self.user_id),
            "app.role": r.role.value,
            "app.dosen_id": str(r.dosen_id) if r.dosen_id else "",
            "app.kk_id": str(r.kk_id) if r.kk_id else "",
            "app.no_ps": str(r.no_ps) if r.no_ps else "",
            "app.kd_fak": r.kd_fak or "",
        }
