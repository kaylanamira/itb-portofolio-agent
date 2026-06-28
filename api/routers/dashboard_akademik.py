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
    get_tahun_ajaran_tersedia,
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
        "Mengembalikan opsi filter yang valid untuk scope user "
        "beserta dimensi mana yang terkunci oleh role."
    ),
)
async def get_akademik_filter_options(
    scope: UserScope = Depends(get_user_scope),
) -> AkademikFilterOptionsResponse:
    """
    Tiga query dijalankan paralel — tidak saling bergantung,
    masing-masing mengambil koneksi sendiri dari pool.
    """
    tahun_list, fak_rows, prodi_rows = await asyncio.gather(
        get_tahun_ajaran_tersedia(scope),
        get_fakultas_options(scope),
        get_prodi_options(scope),
    )

    locked = _resolve_locked(scope)

    tahun_options = [FilterOption(value=t, label=t) for t in tahun_list]

    fak_options = [
        FilterOption(value=r["kd_fak"], label=r["nama_id"])
        for r in fak_rows
    ]

    # Kelompokkan prodi by kd_fak
    # value = str(no_ps) — bukan kd_ps, karena kd_ps tidak unik dalam satu fakultas
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
        fakultas          = fak_options,
        prodi_by_fakultas = prodi_by_fak,
    )


def _resolve_locked(scope: UserScope) -> FilterOptionsLocked:
    """
    Tentukan dimensi mana yang terkunci berdasarkan role aktif.

    Nilai locked untuk prodi = str(no_ps) dari scope — konsisten dengan
    ProdiOption.value yang juga str(no_ps). Frontend dapat langsung
    membandingkan locked.prodi dengan option.value untuk menentukan
    prodi mana yang dipilih secara otomatis.

    Berbeda dengan versi sebelumnya yang mengambil kd_ps dari prodi_rows,
    versi ini mengambil no_ps langsung dari scope — lebih andal dan
    tidak bergantung pada hasil query prodi.
    """
    role = scope.role

    if role in (UserRole.ADMIN, UserRole.DIREKTORAT):
        return FilterOptionsLocked(fakultas=None, prodi=None)

    if role in (UserRole.DEKAN, UserRole.JAJARAN_DEKANAT):
        return FilterOptionsLocked(
            fakultas = scope.active_role.kd_fak,
            prodi    = None,  # dekan masih bisa memilih prodi dalam fakultasnya
        )

    # kaprodi, jajaran_prodi, dosen — keduanya terkunci
    # no_ps dari scope adalah PK yang tepat (bukan kd_ps yang ambigu)
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