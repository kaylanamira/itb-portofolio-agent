import pytest
from tests.conftest import load_cases
from agent.state import DetectedEntities
from agent.tools.security import FORBIDDEN_TABLES
from evals.datasets.schemas import SchemaLinkerCase
from evals.scorer import NodeTestResult
from core.scope import UserScope, UserRole

CASES = load_cases("schema_linker_cases.json", SchemaLinkerCase)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
@pytest.mark.asyncio
async def test_schema_linker_node(case: SchemaLinkerCase, make_state, node_results):
    """Verify entity extraction, table selection, and security constraints."""
    try:
        user_role = UserRole(case.scope_role)
    except ValueError:
        user_role = UserRole.KAPRODI

    from tests.conftest import _make_scope_entry
    entry = _make_scope_entry(user_role, **case.scope_value)
    scope = UserScope(user_id=1000, active_role=entry, available_roles=[entry])

    state = make_state(
        query=case.query,
        scope=scope,
        plan=[{"task": case.query, "tool": "sql"}],
    )
    from agent.nodes.sql_pipeline import _portfolio_sql_pipeline, _build_prior_steps_context
    plan = state.get("plan", [])
    idx = state.get("current_step_index", 0)
    plan_step = plan[idx] if idx < len(plan) else {"task": state["effective_query"]}
    query_type = state.get("query_type")
    
    sql_state = {
        "question": state["effective_query"],
        "user_scope": state["user_scope"],
        "plan_step_context": plan_step,
        "prior_steps_context": _build_prior_steps_context(state),
        "plan_context": _build_prior_steps_context(state),
        "query_type": query_type.value if query_type else None,
        "error_history": [],
        "attempt_count": 0,
        "is_aborted": False,
    }
    result = await _portfolio_sql_pipeline.nodes["schema_linker"].ainvoke(sql_state)

    entities: DetectedEntities = result.get("detected_entities")
    tables: list[str] = result.get("relevant_tables", [])

    entity_fields_total = len(case.expected_entities)
    entity_fields_matched = 0
    entity_fields_extracted = 0

    fuzzy_fields_total = len(case.expected_resolved)
    fuzzy_fields_matched = 0

    if entities is not None:
        metadata_fields = {'confidence', 'entity_candidates', 'resolved_matkul_id', 'resolved_dosen_id', 'resolved_prodi_id'}
        
        for field, expected_value in case.expected_entities.items():
            actual = getattr(entities, field, None)
            if actual is not None:
                entity_fields_extracted += 1
                if isinstance(expected_value, list):
                    if isinstance(actual, list) and set(actual) == set(expected_value):
                        entity_fields_matched += 1
                    elif str(actual) in [str(v) for v in expected_value]:
                        entity_fields_matched += 1
                else:
                    if str(actual) == str(expected_value):
                        entity_fields_matched += 1
        
        for field in DetectedEntities.model_fields:
            if field in metadata_fields:
                continue
            val = getattr(entities, field, None)
            if val is not None and field not in case.expected_entities:
                entity_fields_extracted += 1

        for field, expected_value in case.expected_resolved.items():
            actual = getattr(entities, field, None)
            if expected_value == "fuzzy_match_expected" and actual is not None:
                fuzzy_fields_matched += 1
            elif actual == expected_value or (actual is not None and expected_value is True):
                fuzzy_fields_matched += 1
    
    print(f"\n[DEBUG] {case.id}")
    print(f"  Expected entities: {case.expected_entities}")
    if entities:
        actual_entities = {k: v for k, v in entities.model_dump().items() if v is not None}
        print(f"  Actual entities: {actual_entities}")
    print(f"  Matched: {entity_fields_matched}/{entity_fields_total}" if entity_fields_total > 0 else "  Matched: N/A (no expected entities)")
    print(f"  Extracted: {entity_fields_extracted}")
    print(f"  Expected Tables: {case.expected_tables_subset}")
    print(f"  Actual Tables: {tables}")

    is_table_correct = any(
        any(expected_table in t for t in tables)
        for expected_table in case.expected_tables_subset
    )
    passed = entities is not None and is_table_correct

    node_results.append(NodeTestResult(
        case_id=case.id,
        node_name="schema_linker",
        passed=passed,
        expected_value=case.expected_tables_subset,
        actual_value=tables,
        metric_flags={
            "is_table_correct": is_table_correct,
            "entity_fields_matched_count": entity_fields_matched,
            "entity_fields_total_count": entity_fields_total,
            "entity_fields_extracted_count": entity_fields_extracted,
            "fuzzy_fields_matched_count": fuzzy_fields_matched,
            "fuzzy_fields_total_count": fuzzy_fields_total,
        },
    ))

    assert entities is not None, f"[{case.id}] detected_entities is None"
    assert len(tables) >= 1, f"[{case.id}] no tables selected"

    for expected_table in case.expected_tables_subset:
        assert any(expected_table in t for t in tables), (
            f"[{case.id}] expected table '{expected_table}' not in {tables}"
        )

    for table in tables:
        table_name = table.split(".")[-1]
        assert table_name not in FORBIDDEN_TABLES, (
            f"[{case.id}] schema linker selected forbidden table '{table}'"
        )

    schema_ctx = result.get("schema_context")
    assert schema_ctx is not None and len(schema_ctx) > 0, f"[{case.id}] schema_context is empty"
