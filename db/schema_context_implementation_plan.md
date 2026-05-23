# Schema Context Strategy — Implementation Plan
> ITB Academic Portfolio Analytics Agent  
> Problem: Large cloud database makes unguided schema exploration unreliable and expensive.

---

## Diagnosis: What's Wrong Now

The current pipeline loads schema **dynamically** but without structure. When the agent sees a large DB with dozens of schemas (`utama`, `kelas`, `mahasiswa`, `evaluasi`, `akademik`, `keuangan`, …), it faces three compounding problems:

| Problem | Effect |
|---|---|
| Agent doesn't know which schemas are in scope for a query | Hallucinated table names, wrong joins |
| Full schema dumps are token-expensive | Less room for reasoning, slower inference |
| No cost difference between "good" and "bad" table candidates | Agent explores randomly instead of purposefully |

The answer is **not** free exploration, and **not** a rigid hardcoded whitelist. It's a **structured two-tier retrieval model** — fast and opinionated at the top, flexible at the bottom.

---

## Core Principle: MVs First, Raw Tables as Escape Hatch

Your 4–5 materialized views (`mv_kelas`, `mv_statistik_prodi`, `mv_statistik_fakultas`, `mv_statistik_dosen`, and the kuesioner MVs) are pre-flattened, pre-joined, and already scoped. They answer **~90% of real user queries** with zero join reasoning required.

Raw source tables (`utama.*`, `kelas.*`, `evaluasi.*`, `mahasiswa.*`, etc.) should only enter the agent's context when the MV layer provably cannot answer the question.

---

## Implementation: Two-Tier Schema Context

### Tier 1 — Always-Loaded Core Context (Static, Small)

A compact, always-present schema context injected into every agent run. Contains:

- Full column list + descriptions for all 4–5 MVs
- Full column list for lookup tables: `utama.dosen`, `utama.fakultas`, `utama.program_studi`, `utama.kk`, `utama.mata_kuliah`
- A short **"what lives where"** routing note (see below)

**Size target:** ≤ 2,000 tokens. This is your agent's permanent map.

```python
# agent/schema/core_context.py

CORE_SCHEMA_CONTEXT = """
## Primary Analytics Layer (use these first)

### mv_kelas
1 row = 1 class instance. Contains: kelas_id, matkul_id, kode_mk, nama_mk_id,
semester, tahun, tahun_ajaran, sks, jenis_nilai, kode_prodi, singkatan_prodi,
nama_prodi_id, kode_fakultas, semua_dosen_id[], semua_dosen_nama_gelar[],
dist_jumlah_a/ab/b/bc/c/d/e/pass/fail, total_mahasiswa,
pct_kehadiran_dosen, pct_kehadiran_mahasiswa, rata_ip_akhir_mahasiswa,
skor_q21..q30, skor_q35, skor_q37, skor_avg_capaian, skor_avg_pelaksanaan,
skor_avg_perilaku, skor_avg_sarana_prasarana.
SCOPE: {SCOPE_FILTER} on this table.

### mv_statistik_dosen
1 row = 1 lecturer × 1 semester. Contains: dosen_id, nama_dosen, kk_id,
kode_fakultas_dosen, semester, tahun, tahun_ajaran, jumlah_kelas, jumlah_matkul,
total_sks_diajar, avg_pct_kehadiran_dosen, avg_pct_kehadiran_mahasiswa,
avg_ip_mhs, avg_skor_q25/q26/q27, avg_skor_capaian/pelaksanaan/perilaku/overall,
avg_nilai_akhir, kelas_ids[], kode_mk_list[], kode_prodi_diajar[].
SCOPE: {SCOPE_FILTER} on this table.

### mv_statistik_prodi  
1 row = 1 study program × 1 semester. Contains aggregated class, student,
lecturer counts, GPA distribution, and questionnaire scores per prodi.
SCOPE: {SCOPE_FILTER} on this table.

### mv_statistik_fakultas
1 row = 1 faculty × 1 semester. Same structure as mv_statistik_prodi but at
faculty level.
SCOPE: {SCOPE_FILTER} on this table.

## Lookup / Reference Tables (no RLS, always accessible)

### utama.dosen — lecturer master: dosen_id, nama_gelar, kk_id, kd_fak, no_ps, active, nidn
### utama.fakultas — faculty master: kd_fak, nama (JSONB id/en)
### utama.program_studi — study program: no_ps, kd_ps, nama (JSONB), kd_fak
### utama.kk — research group: kk_id, nama (JSONB), kd_fak  
### utama.mata_kuliah — course master: mata_kuliah_id, kd_kuliah, nama (JSONB), sks, th_kur

## Routing Hint
- Questionnaire scores → mv_kelas (per-class) or mv_statistik_dosen (per-lecturer)
- Grade distribution → mv_kelas (dist_jumlah_* columns)
- Lecturer workload → mv_statistik_dosen
- Prodi/faculty summary → mv_statistik_prodi / mv_statistik_fakultas
- Name lookup → utama.dosen / utama.program_studi / utama.fakultas
- Raw student records, financial data, admission data → requires Tier 2 expansion
"""
```

### Tier 2 — On-Demand Table Expansion (Dynamic, Targeted)

A **semantic table registry** — a Python dict/YAML that maps schema.table → one-line description + column list. The agent requests specific tables from this registry by name; only the requested entries are loaded into the prompt.

```python
# agent/schema/table_registry.py

TABLE_REGISTRY: dict[str, dict] = {
    "mahasiswa.kuliah": {
        "description": "Per-student course enrollment and final grades. Use when individual student grades needed.",
        "columns": "kuliah_id, mahasiswa_id, kelas_id, nilai, sah_nilai, ts_hapus",
        "join_hint": "JOIN mv_kelas ON mv_kelas.kelas_id = mahasiswa.kuliah.kelas_id"
    },
    "evaluasi.portofolio": {
        "description": "Course portfolio text entries (free-form evidence). Use for RAG or text analysis.",
        "columns": "portofolio_id, kelas_id, tipe, konten, ts_entry"
    },
    "kelas.kelas": {
        "description": "Raw class table. Prefer mv_kelas. Use only if you need fields not in mv_kelas.",
        "columns": "kelas_id, mata_kuliah_id, no_kelas, semester, tahun, ..."
    },
    # ... all other tables catalogued here
}

def get_table_context(table_names: list[str]) -> str:
    """Returns schema context string for requested tables only."""
    lines = []
    for name in table_names:
        if entry := TABLE_REGISTRY.get(name):
            lines.append(f"### {name}\n{entry['description']}\nColumns: {entry['columns']}")
            if hint := entry.get("join_hint"):
                lines.append(f"Join hint: {hint}")
    return "\n\n".join(lines)
```

---

## Agent Pipeline Changes

### 1. Schema Selector Node (New Node)

Insert a lightweight node **between the planner and the SQL generator**. Its job: given the plan step and query, decide which Tier 2 tables (if any) to expand.

```
[planner] → [schema_selector] → [sql_generator] → [sql_executor]
```

The schema selector is a fast LLM call with a strict, low-token prompt:

```python
SCHEMA_SELECTOR_PROMPT = """
You are a schema router. Given a user query and the core schema context,
decide if any Tier 2 tables are needed beyond the MVs.

Return ONLY a JSON array of table names, or empty array [] if MVs suffice.
Valid Tier 2 tables: {tier2_table_list}

Query: {query}
Plan step: {step}

Rules:
- Default to [] (use MVs). Only expand if MVs provably lack the required data.
- Max 3 tables per step.
"""
```

Expected output: `["mahasiswa.kuliah"]` or `[]`

This call costs ~200–400 tokens and prevents the SQL generator from hallucinating table names.

### 2. State Contract Addition

Add two fields to `AgentState`:

```python
tier2_tables_requested: list[str] = []   # tables the selector chose
schema_context_tier2: Optional[str] = None  # expanded schema injected into SQL gen
```

### 3. SQL Generator Prompt Update

The SQL generator receives:

```
{CORE_SCHEMA_CONTEXT}          ← always present
{schema_context_tier2}         ← only if selector chose Tier 2 tables
```

The generator is explicitly instructed: **"Query the MVs unless a Tier 2 table is explicitly listed above."**

---

## Table Registry Population Strategy

Building the registry is a one-time (then periodic) maintenance task, not an agent responsibility.

**Approach — semi-automated cataloguing:**

```python
# scripts/catalogue_schema.py
# Run once against your cloud DB to generate table_registry.py skeleton

import psycopg

SCHEMAS_TO_CATALOGUE = [
    "mahasiswa", "akademik", "keuangan", "penerimaan",
    "wisuda", "evaluasi", "kelas"
    # exclude: utama (already in core), pg_catalog, information_schema
]

query = """
SELECT table_schema, table_name, column_name, data_type, col_description(
    (table_schema||'.'||table_name)::regclass::oid, ordinal_position
) AS col_comment
FROM information_schema.columns
WHERE table_schema = ANY(%s)
ORDER BY table_schema, table_name, ordinal_position
"""
```

Run this once, export to YAML, then **manually add one-line descriptions and join hints**. This is a 2–4 hour human task that unlocks reliable agent reasoning indefinitely.

---

## What This Achieves

| Concern | Before | After |
|---|---|---|
| Token usage per query | Unpredictable (dumps whole schema) | Bounded: ~2K (core) + ~300/table (Tier 2) |
| Table hallucination | Common | Eliminated — agent only sees real tables |
| Join reasoning burden | High (agent must figure out all FKs) | Low — MVs are pre-joined; Tier 2 includes join hints |
| Coverage of complex queries | Poor (agent gives up or hallucinates) | Good — escape hatch to raw tables is controlled |
| Maintenance | None (fully dynamic) | Periodic (registry refresh when schema changes) |

---

## Boundary Decision: What Stays Out

Some parts of the DB should be explicitly **excluded from agent reach**, regardless of query. Define this as a blocklist in the registry:

```python
AGENT_EXCLUDED_SCHEMAS = {
    "auth",          # user authentication internals
    "audit",         # system audit logs  
    "pg_catalog",    # postgres internals
    "information_schema",
}

AGENT_EXCLUDED_TABLES = {
    "mahasiswa.mahasiswa",   # PII — full student personal data
    "utama.user",            # user accounts
    # add sensitive tables here
}
```

The scope/RLS already enforces row-level access. This blocklist enforces **table-level** access — the agent simply never learns these tables exist.

---

## Rollout Phases

### Phase 1 — Core Context Injection (1–2 days)
- Write `core_context.py` with MV + lookup schemas
- Replace current dynamic full-dump with this static core in the SQL generator prompt
- Verify existing queries still work (they will — MVs cover the common cases)

### Phase 2 — Table Registry Skeleton (2–3 days)
- Run the cataloguing script against your cloud DB
- Export the table list with column names
- Add descriptions and join hints for the 20–30 most relevant non-MV tables

### Phase 3 — Schema Selector Node (2–3 days)
- Implement `schema_selector` LangGraph node
- Add state fields `tier2_tables_requested`, `schema_context_tier2`
- Wire into graph between planner and SQL generator
- Add the excluded schemas/tables blocklist

### Phase 4 — Eval & Tuning (ongoing)
- Log which tables the selector picks per query type
- Identify queries that still fail → add missing tables to registry
- Track token usage before/after — expect 40–60% reduction