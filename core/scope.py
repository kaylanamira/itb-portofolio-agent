from enum import Enum
from typing import Optional, ClassVar
from uuid import UUID
from pydantic import BaseModel

class UserRole(str, Enum):
    ADMIN = "admin"
    WRAM = "wram"
    DEKAN = "dekan"
    JAJARAN_DEKANAT = "jajaran_dekanat"
    KAPRODI = "kaprodi"
    JAJARAN_PRODI = "jajaran_prodi"
    DOSEN = "dosen"

class UserScope(BaseModel):
    """Populated from user_scope table. Determines what data the user can see.
    
    SCOPE SEMANTICS:
    - Lookup/reference tables (fakultas, program_studi, dosen, etc.) are institution-wide
      and have NO row-level security. ALL roles — including dosen — can query them freely.
      This allows lower level role to ask general questions like "ada berapa prodi di ITB?" or
      "siapa saja dosen di STEI?" without seeing other people's portfolio data.
    
    - Portfolio analytics tables (mv_kelas, mv_statistik_*, teks_portofolio,
      komentar_mahasiswa) ARE scope-restricted. A dosen only sees their own classes.
    
    - The {SCOPE_FILTER} placeholder resolves to 'TRUE' for lookup tables and to
      a scoped WHERE fragment for analytics tables.
    """
    user_id: UUID
    role: UserRole
    dosen_id: Optional[UUID] = None
    kk_id: Optional[UUID] = None
    prodi_id: Optional[UUID] = None
    fakultas_id: Optional[UUID] = None
    
    # Derived helpers
    can_see_all: bool = False          # True for admin, wram
    can_see_fakultas: bool = False     # True for dekan, jajaran_dekanat
    can_see_prodi: bool = False        # True for kaprodi, jajaran_prodi
    can_see_own_kelas_only: bool = False  # True for dosen
    
    # Lookup/reference tables are institution-wide with no RLS — any role can see all rows
    LOOKUP_TABLES: ClassVar[set] = {"fakultas", "program_studi", "dosen", "kelompok_keahlian", "mata_kuliah"}
    
    def scope_where(self, table: str = "mv_kelas") -> tuple[str, list]:
        """Returns (where_clause, params_list) for the given table.
        
        Uses %s positional placeholders compatible with psycopg.
        Returns a ready-to-inject WHERE fragment and a flat params list.
        """
        # everyone can query institution-wide data
        if table in self.LOOKUP_TABLES:
            return "TRUE", []
        
        match self.role:
            case UserRole.ADMIN | UserRole.WRAM:
                return "TRUE", []
            case UserRole.DOSEN:
                if table == "mv_statistik_dosen":
                    return "dosen_id = %s::uuid", [str(self.dosen_id)]
                elif table in ("teks_portofolio", "komentar_mahasiswa"):
                    # Text tables are joined via kelas_id; filter via subquery
                    return ("kelas_id IN (SELECT kelas_id FROM mv_kelas WHERE %s::uuid = ANY(semua_dosen_id))", 
                            [str(self.dosen_id)])
                else:
                    # mv_kelas or any other MV
                    return "%s::uuid = ANY(semua_dosen_id)", [str(self.dosen_id)]
            case UserRole.KAPRODI | UserRole.JAJARAN_PRODI:
                if table == "mv_statistik_dosen":
                    return ("dosen_id IN (SELECT DISTINCT unnest(semua_dosen_id) FROM mv_kelas WHERE prodi_id = %s::uuid)",
                            [str(self.prodi_id)])
                elif table == "mv_statistik_prodi":
                    return "prodi_id = %s::uuid", [str(self.prodi_id)]
                elif table in ("teks_portofolio", "komentar_mahasiswa"):
                    return ("kelas_id IN (SELECT kelas_id FROM mv_kelas WHERE prodi_id = %s::uuid)", 
                            [str(self.prodi_id)])
                else:
                    return "prodi_id = %s::uuid", [str(self.prodi_id)]
            case UserRole.DEKAN | UserRole.JAJARAN_DEKANAT:
                if table == "mv_statistik_dosen":
                    return "fakultas_id_dosen = %s::uuid", [str(self.fakultas_id)]
                elif table == "mv_statistik_prodi":
                    return "fakultas_id = %s::uuid", [str(self.fakultas_id)]
                elif table in ("teks_portofolio", "komentar_mahasiswa"):
                    return ("kelas_id IN (SELECT kelas_id FROM mv_kelas WHERE fakultas_id = %s::uuid)",
                            [str(self.fakultas_id)])
                else:
                    return "fakultas_id = %s::uuid", [str(self.fakultas_id)]
            case _:
                return "FALSE", []

    def mv_kelas_where(self) -> tuple[str, list]:
        return self.scope_where("mv_kelas")
