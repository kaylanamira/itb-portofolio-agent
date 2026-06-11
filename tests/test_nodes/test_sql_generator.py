import os
import pytest
import re
import sqlglot
import sqlglot.expressions as exp
from tests.conftest import load_cases
from agent.tools.security import check_sql_security, SENSITIVE_COLUMN_PATTERNS
from agent.tools.sql.tool import SQLTool
from agent.prompts.schema_linker import PORTFOLIO_SQL_DOMAIN_RULES
from agent.tools.few_shot_retriever import retrieve_few_shots
from agent.state import QueryType
from agent.state import DetectedEntities
from core.sql_executor import PsycopgExecutor
from core.scope import UserScope, ScopeEntry, UserRole
from evals.datasets.schemas import SqlGeneratorCase
from evals.scorer import NodeTestResult, MetricFlag, _compute_soft_f1
from agent.prompts.sql_generator import BIRD_SQL_GENERATOR_PROMPT
from agent.nodes.sql_pipeline import portfolio_few_shot_examples
_itb_cases = load_cases("sql_generator_cases.json", SqlGeneratorCase)
_bird_cases = load_cases("bird_sql_generator_cases.json", SqlGeneratorCase)[:10] if os.getenv("RUN_BIRD_EVALS") else []
CASES = _itb_cases if not os.getenv("RUN_BIRD_EVALS") else _bird_cases
        
def _to_row_tuples(rows: list[dict]) -> list[tuple]:
    return [tuple(v for v in d.values()) for d in rows]

def _extract_tables_from_sql(sql: str) -> set[str]:
    try:
        statements = sqlglot.parse(sql, dialect="postgres")
        if not statements:
            return set()
        
        tables = set()
        for table in statements[0].find_all(exp.Table):
            schema = table.db.lower() if table.db else ""
            table_name = table.name.lower() if table.name else ""
            if schema and table_name:
                tables.add(f"{schema}.{table_name}")
            elif table_name:
                tables.add(table_name)
        return tables
    except Exception:
        return set()


def _check_gold_sql(case: SqlGeneratorCase, sql: str) -> list[str]:
    failures = []
    checks = case.gold_sql_checks
    sql_upper = sql.upper()

    if checks.must_be_select:
        if not sql_upper.strip().startswith("SELECT"):
            failures.append("expected SELECT statement")

    for required in checks.must_include:
        if required.upper() not in sql_upper and required not in sql:
            failures.append(f"required token '{required}' not found")

    for forbidden in checks.must_not_include:
        if re.search(r'\b' + re.escape(forbidden.upper()) + r'\b', sql_upper):
            failures.append(f"forbidden token '{forbidden}' found")

    if checks.should_have_order_by and "ORDER BY" not in sql_upper:
        failures.append("expected ORDER BY clause not found")

    if checks.should_have_limit and "LIMIT" not in sql_upper:
        failures.append("expected LIMIT clause not found")

    if checks.should_have_null_guard:
        has_null_guard = "IS NOT NULL" in sql_upper or "COALESCE" in sql_upper or "NULLS LAST" in sql_upper
        if not has_null_guard:
            failures.append("expected null guard not found")
    

    return failures


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
@pytest.mark.asyncio
async def test_sql_generator_node(case: SqlGeneratorCase, make_state, scope_kaprodi, node_results):
    entities_kwargs = {}
    for k, v in case.detected_entities.items():
        if k in DetectedEntities.model_fields:
            if k in ["no_kelas", "kode_prodi"] and isinstance(v, int):
                entities_kwargs[k] = str(v)
            else:
                entities_kwargs[k] = v
    entities = DetectedEntities(**entities_kwargs)
    is_bird = case.id.startswith("BIRD-")
    
    sqlite_sys_prompt = BIRD_SQL_GENERATOR_PROMPT

    if is_bird:
        from core.sqlite_executor import SqliteExecutor
        db_id = case.detected_entities.get("db_id", "dummy")
        db_path = f"evals/datasets/bird/MINIDEV/dev_databases/{db_id}/{db_id}.sqlite"
        executor = SqliteExecutor(db_path)
        active_scope = UserScope(user_id=999, active_role=ScopeEntry(user_role_id=999, role=UserRole.ADMIN, is_prime=True))
    else:
        executor = PsycopgExecutor()
        active_scope = UserScope(
            user_id=999,
            active_role=ScopeEntry(user_role_id=999, role=UserRole.ADMIN, is_prime=True)
        )

    from agent.tools.schema_retriever import describe_tables
    from agent.prompts.sql_generator import SQL_GENERATOR_SYSTEM

    tool = SQLTool(
        schema_linker_prompt="",
        entity_resolver=lambda _: None,
        few_shot_examples=(lambda _: "") if is_bird else portfolio_few_shot_examples,
        schema_context=case.schema_context if is_bird else describe_tables,
        default_table="",
        executor=executor,
        domain_rules="" if is_bird else PORTFOLIO_SQL_DOMAIN_RULES,
        system_prompt_template=sqlite_sys_prompt if is_bird else SQL_GENERATOR_SYSTEM,
    )
    
    output_sql = await tool.generate_sql(
        question=case.query,
        detected_entities=entities,
        user_scope=active_scope,
        relevant_tables=case.expected_tables,
        query_type=case.query_type,
        plan_step_context={"task": case.query, "tool": "sql"},
    )

    is_syntax_valid = False
    is_security_safe = False
    is_no_pii = True
    is_correct_table_used = False
    is_execution_accurate = False
    extracted_tables = set()

    if output_sql and output_sql.strip():
        try:
            statements = sqlglot.parse(output_sql, dialect="postgres")
            is_syntax_valid = statements is not None and len(statements) > 0
        except Exception:
            is_syntax_valid = False

    if is_syntax_valid:
        is_security_safe, _ = check_sql_security(output_sql)
        sql_lower = output_sql.lower()
        
        for col in SENSITIVE_COLUMN_PATTERNS:
            if re.search(r'\b' + re.escape(col) + r'\b', sql_lower):
                is_no_pii = False
                break
        
        extracted_tables = _extract_tables_from_sql(output_sql)
        if hasattr(case, 'expected_tables') and case.expected_tables:
            expected_set = {t.lower() for t in case.expected_tables}
            is_correct_table_used = expected_set <= extracted_tables
        else:
            is_correct_table_used = True

    soft_f1: float | None = None

    if is_syntax_valid and case.ground_truth_sql:
        expected_result = await executor.execute(case.ground_truth_sql, active_scope)
        generated_result = await executor.execute(output_sql, active_scope)
        if not generated_result.error and not expected_result.error:

            expected_tuples = _to_row_tuples(expected_result.rows)
            generated_tuples = _to_row_tuples(generated_result.rows)

            expected_set = {tuple(sorted(str(v) for v in t)) for t in expected_tuples}
            generated_set = {tuple(sorted(str(v) for v in t)) for t in generated_tuples}
            is_execution_accurate = generated_set == expected_set

            soft_f1 = _compute_soft_f1(generated_tuples, expected_tuples)

            if not is_execution_accurate:
                print(f"\n[DEBUG] {case.id} Execution Mismatch! (F1: {soft_f1})")
                print(f"EXPECTED SQL: {case.ground_truth_sql}")
                print(f"EXPECTED TUPLES: {expected_tuples}")
                print(f"GENERATED SQL: {output_sql.strip()}")
                print(f"GENERATED TUPLES: {generated_tuples}\n")

    metric_flags: dict = {
        MetricFlag.IS_SYNTAX_VALID: is_syntax_valid,
        MetricFlag.IS_SECURITY_SAFE: is_security_safe,
        MetricFlag.IS_NO_PII: is_no_pii,
        MetricFlag.IS_CORRECT_TABLE_USED: is_correct_table_used,
        MetricFlag.IS_EXECUTION_ACCURATE: is_execution_accurate,
    }
    if soft_f1 is not None:
        metric_flags[MetricFlag.SOFT_F1_SCORE] = soft_f1

    node_results.append(NodeTestResult(
        case_id=case.id,
        node_name="sql_generator",
        passed=is_syntax_valid and is_security_safe and is_no_pii,
        expected_value=None,
        actual_value=output_sql,
        metric_flags=metric_flags,
        complexity=case.complexity,
        query_type=case.query_type,
    ))

    assert is_syntax_valid, f"[{case.id}] sql_pipeline did not produce SQL"

    security_ok, security_err = check_sql_security(output_sql)
    assert security_ok, f"[{case.id}] generated SQL failed security check: {security_err}\nSQL: {output_sql}"

    gold_failures = _check_gold_sql(case, output_sql)
    assert not gold_failures, (
        f"[{case.id}] gold SQL checks failed:\n" + "\n".join(f"  - {f}" for f in gold_failures)
        + f"\n\nGenerated SQL:\n{output_sql}"
    )

    sql_lower = output_sql.lower()
    for col in SENSITIVE_COLUMN_PATTERNS:
        if re.search(r'\b' + re.escape(col) + r'\b', sql_lower):
            pytest.fail(f"[{case.id}] PII column '{col}' found in generated SQL:\n{output_sql}")
