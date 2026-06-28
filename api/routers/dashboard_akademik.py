"""
api/routers/dashboard_akademik.py

Router untuk endpoint dashboard portofolio & kuesioner akademik.
"""

import asyncio
import logging

from fastapi import APIRouter, Depends

from api.dependencies import get_user_scope
from api.schemas.dashboard_akademik import (
    AkademikFilterOptionsResponse,
    FilterOption,
    FilterOptionsLocked,
    ProdiOption,
)
from api.models.akademik import (
    build_prodi_label,
    derive_jenjang_options,
    get_tahun_ajaran_tersedia,
    get_semester_tersedia,
    get_fakultas_options,
    get_prodi_options,
)
from core.scope import UserRole, UserScope

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard-akademik"],
)


# ─── GET /akademik/filter-options ─────────────────────────────────────────────

@router.get(
    "/akademik/filter-options",
    response_model=AkademikFilterOptionsResponse,
    summary="Opsi dropdown filter dashboard akademik",
    description=(
        "Dipanggil sekali saat dashboard mount. "
        "Mengembalikan semua opsi filter yang valid untuk scope user "
        "beserta dimensi mana yang terkunci oleh role. "
        "Tidak ada nilai filter yang hardcoded di frontend."
    ),
)
async def get_akademik_filter_options(
    scope: UserScope = Depends(get_user_scope),
) -> AkademikFilterOptionsResponse:
    """
    Empat query DB dijalankan paralel (asyncio.gather).
    Jenjang diturunkan dari prodi_rows — tidak ada query DB kelima.
    """
    tahun_list, semester_rows, fak_rows, prodi_rows = await asyncio.gather(
        get_tahun_ajaran_tersedia(scope),
        get_semester_tersedia(scope),
        get_fakultas_options(scope),
        get_prodi_options(scope),
    )

    locked = _resolve_locked(scope)

    tahun_options = [FilterOption(value=t, label=t) for t in tahun_list]

    semester_options = [
        FilterOption(value=r["value"], label=r["label"])
        for r in semester_rows
    ]

    # Jenjang diturunkan dari prodi_rows — scope-aware secara otomatis,
    # tidak membutuhkan query DB tambahan
    jenjang_rows = derive_jenjang_options(prodi_rows)
    jenjang_options = [
        FilterOption(value=r["value"], label=r["label"])
        for r in jenjang_rows
    ]

    fak_options = [
        FilterOption(value=r["kd_fak"], label=r["nama_id"])
        for r in fak_rows
    ]

    # Kelompokkan prodi by kd_fak
    # value = str(no_ps) — bukan kd_ps yang tidak unik dalam satu fakultas
    prodi_by_fak: dict[str, list[ProdiOption]] = {}
    for r in prodi_rows:
        fak = r["kd_fak"]
        prodi_by_fak.setdefault(fak, []).append(
            ProdiOption(
                value     = str(r["no_ps"]),
                label     = build_prodi_label(r["nama_id"], r["kd_strata"]),
                kd_ps     = r["kd_ps"],
                kd_strata = r["kd_strata"],
            )
        )

    return AkademikFilterOptionsResponse(
        locked            = locked,
        tahun_ajaran      = tahun_options,
        semester          = semester_options,
        jenjang           = jenjang_options,
        fakultas          = fak_options,
        prodi_by_fakultas = prodi_by_fak,
    )


def _resolve_locked(scope: UserScope) -> FilterOptionsLocked:
    """
    Tentukan dimensi mana yang terkunci berdasarkan role aktif.

    locked.prodi = str(no_ps) dari scope, konsisten dengan ProdiOption.value.
    """
    role = scope.role

    if role in (UserRole.ADMIN, UserRole.DIREKTORAT):
        return FilterOptionsLocked(fakultas=None, prodi=None)

    if role in (UserRole.DEKAN, UserRole.JAJARAN_DEKANAT):
        return FilterOptionsLocked(
            fakultas = scope.active_role.kd_fak,
            prodi    = None,
        )

    # kaprodi, jajaran_prodi, dosen
    locked_prodi = (
        str(scope.active_role.no_ps)
        if scope.active_role.no_ps is not None
        else None
    )

    if locked_prodi is None:
        logger.warning(
            "_resolve_locked: no_ps is None untuk role=%s user_id=%s",
            role, scope.user_id,
        )

    return FilterOptionsLocked(
        fakultas = scope.active_role.kd_fak,
        prodi    = locked_prodi,
    )