from agent.state import AgentState, AgentDomain
from core.database import get_db_connection


async def catalog_lookup(state: AgentState) -> dict:
    domain = state.get("domain")
    plan = state.get("plan", [])
    idx = state.get("current_step_index", 0)
    step = plan[idx] if idx < len(plan) else {}

    if domain == AgentDomain.PORTFOLIO:
        dimension = step.get("catalog_dimension")
        if dimension:
            sql = """
                SELECT pk.kd_pertanyaan, pk.pertanyaan->>'id' AS teks_pertanyaan,
                       kk.kelompok->>'id' AS kelompok
                FROM evaluasi.pertanyaan_kuesioner pk
                JOIN evaluasi.kelompok_kuesioner kk ON kk.kd_kelompok = pk.kd_kelompok
                WHERE pk.active = TRUE AND kk.kelompok->>'id' = %s
                ORDER BY pk.kd_pertanyaan
            """
            params = (dimension,)
        else:
            sql = """
                SELECT pk.kd_pertanyaan, pk.pertanyaan->>'id' AS teks_pertanyaan,
                       kk.kelompok->>'id' AS kelompok
                FROM evaluasi.pertanyaan_kuesioner pk
                JOIN evaluasi.kelompok_kuesioner kk ON kk.kd_kelompok = pk.kd_kelompok
                WHERE pk.active = TRUE AND pk.batasan IS NULL
                ORDER BY kk.kd_kelompok, pk.kd_pertanyaan
            """
            params = ()

    elif domain == AgentDomain.WISUDAWAN:
        kd_grup = step.get("kd_grup_pertanyaan")
        if kd_grup:
            sql = """
                SELECT p.kd_pertanyaan, p.kd_grup_pertanyaan, p.kd_grup_opsi,
                       p.pertanyaan->>'id' AS teks_pertanyaan,
                       o.nilai, o.label->>'id' AS label_id, o.label->>'en' AS label_en
                FROM evaluasi_wisudawan.pertanyaan p
                LEFT JOIN evaluasi_wisudawan.ref_opsi o ON o.kd_grup_opsi = p.kd_grup_opsi
                WHERE p.active = TRUE AND p.kd_grup_pertanyaan = %s
                ORDER BY p.kd_pertanyaan, o.nilai
            """
            params = (kd_grup,)
        else:
            sql = """
                SELECT p.kd_pertanyaan, p.kd_grup_pertanyaan, p.kd_grup_opsi,
                       p.pertanyaan->>'id' AS teks_pertanyaan,
                       o.nilai, o.label->>'id' AS label_id, o.label->>'en' AS label_en
                FROM evaluasi_wisudawan.pertanyaan p
                LEFT JOIN evaluasi_wisudawan.ref_opsi o ON o.kd_grup_opsi = p.kd_grup_opsi
                WHERE p.active = TRUE
                ORDER BY p.kd_grup_pertanyaan, p.kd_pertanyaan, o.nilai
            """
            params = ()
    else:
        return {}

    async with get_db_connection() as conn:
        cursor = await conn.execute(sql, params)
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in await cursor.fetchall()]

    return {
        "sql_result": rows,
        "sql_row_count": len(rows),
        "generated_sql": (sql % params).strip() if params else sql.strip(),
    }
