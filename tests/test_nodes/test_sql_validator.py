import pytest
from unittest.mock import AsyncMock, MagicMock

from agent.tools.security import check_sql_security
from agent.tools.sql.tool import SQLTool
from evals.config import SECURITY_ALLOWED_SCHEMAS, SECURITY_FORBIDDEN_TABLES, SECURITY_SENSITIVE_COLUMNS
from evals.datasets.schemas import SqlValidatorCase
from evals.scorer import NodeTestResult
from tests.conftest import load_cases

CASES = load_cases("sql_validator_cases.json", SqlValidatorCase)


def _make_validator() -> SQLTool:
    return SQLTool(
        schema_linker_prompt="unused",
        entity_resolver=AsyncMock(return_value=None),
        few_shot_examples=lambda _query_type: "",
        schema_context="unused",
        default_table="analitik.v_akademik_kelas",
        executor=MagicMock(),
    )


def _assert_blocked(sql: str, expected_error: str | None = None):
    ok, err = check_sql_security(sql)
    assert ok is False, f"Expected SQL to be blocked: {sql}"
    if expected_error:
        assert expected_error in (err or "")
    print(f"\n[CORRECTLY BLOCKED] SQL: {sql[:50]}... -> Reason: {err}")


@pytest.mark.parametrize("case", CASES)
@pytest.mark.asyncio
async def test_sql_tool_validator_matches_dataset_label(case: SqlValidatorCase, node_results):
    """Verify the SQLTool validator outcome matches the dataset expected_valid label."""
    result = await _make_validator().validate_sql(case.sql)
    actual_valid = result["validation_status"] == "pass"
    is_validation_correct = actual_valid == case.expected_valid

    node_results.append(NodeTestResult(
        case_id=case.id,
        node_name="sql_validator",
        passed=is_validation_correct,
        expected_value=case.expected_valid,
        actual_value=actual_valid,
        metric_flags={
            "is_expected_invalid": not case.expected_valid,
            "is_validation_correct": is_validation_correct,
        },
    ))

    if case.expected_valid:
        assert result["validation_status"] == "pass", f"[{case.id}] {result['error']}"
    else:
        assert result["validation_status"] == "fail", f"[{case.id}] expected validator failure"
        assert case.expected_error_type in (result["error"] or "")


@pytest.mark.parametrize("case", CASES)
def test_security_checker_matches_dataset_label(case: SqlValidatorCase):
    ok, err = check_sql_security(case.sql)
    assert ok is case.expected_valid, f"[{case.id}] {err}"
    if not case.expected_valid:
        assert case.expected_error_type in (err or "")
        print(f"\n[CORRECTLY BLOCKED] SQL: {case.sql[:50]}... -> Reason: {err}")


@pytest.mark.parametrize("keyword", ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "CREATE", "MERGE"])
def test_write_operations_are_blocked(keyword):
    sql_by_keyword = {
        "INSERT": "INSERT INTO analitik.v_akademik_kelas (kode_matkul) VALUES ('IF9999')",
        "UPDATE": "UPDATE analitik.v_akademik_kelas SET avg_ip_akhir_mahasiswa = 4.0 WHERE kode_matkul = 'IF1220'",
        "DELETE": "DELETE FROM analitik.v_akademik_kelas WHERE kode_matkul = 'IF1220'",
        "DROP": "DROP TABLE analitik.v_akademik_kelas",
        "TRUNCATE": "TRUNCATE analitik.v_akademik_kelas",
        "ALTER": "ALTER TABLE analitik.v_akademik_kelas ADD COLUMN dummy int",
        "CREATE": "CREATE TABLE analitik.eval_tmp (id int)",
        "MERGE": "MERGE INTO analitik.v_akademik_kelas USING analitik.v_akademik_kelas source ON true WHEN MATCHED THEN UPDATE SET kode_matkul = source.kode_matkul",
    }
    _assert_blocked(sql_by_keyword[keyword], "Security Violation")


@pytest.mark.parametrize("column", sorted(SECURITY_SENSITIVE_COLUMNS))
def test_sensitive_columns_are_blocked(column):
    schema_table = "users.user" if column in {"password", "token", "secret", "ip_address"} else "utama.mahasiswa"
    _assert_blocked(f"SELECT {column} FROM {schema_table} LIMIT 1")


@pytest.mark.parametrize("sql", [
    "SELECT * FROM analitik.v_akademik_kelas -- WHERE 1=1",
    "SELECT * FROM analitik.v_akademik_kelas /* comment */",
    "SELECT 1; SELECT 2",
    "SELECT pg_sleep(5)",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT * FROM dblink('host=x','SELECT 1') AS t(id int)",
    "SELECT embedding <-> '[0.1,0.2]' FROM analitik.vector_chunks LIMIT 5",
    "SELECT embedding <=> '[0.1,0.2]' FROM analitik.vector_chunks LIMIT 5",
])
def test_injection_and_dangerous_access_are_blocked(sql):
    _assert_blocked(sql, "Security Violation")


@pytest.mark.parametrize("schema", ["pg_catalog", "wisuda", "keuangan", "kemahasiswaan", "presensi", "x_hris", "v_myitb", "logs", "tmp", "kesehatan"])
@pytest.mark.asyncio
async def test_forbidden_schema(schema):
    sql = f"SELECT * FROM {schema}.sample_table LIMIT 1"
    result = await _make_validator().validate_sql(sql)
    assert result["validation_status"] == "fail", f"Expected schema {schema} to be blocked"
    assert "Security Violation" in result["error"]
    print(f"\n[CORRECTLY BLOCKED] SQL: {sql[:50]}... -> Reason: {result['error']}")


@pytest.mark.parametrize("table", sorted(SECURITY_FORBIDDEN_TABLES))
def test_forbidden_tables_are_blocked(table):
    sql = f"SELECT * FROM analitik.{table} LIMIT 1" if table == "vector_chunks" else f"SELECT * FROM {table} LIMIT 1"
    _assert_blocked(sql, "Security Violation")


@pytest.mark.parametrize("sql", [
    "",
    "   \n\t  ",
    "1+1",
    "SELECT FROM WHERE",
])
@pytest.mark.asyncio
async def test_empty_non_select_and_invalid_syntax_are_blocked(sql):
    result = await _make_validator().validate_sql(sql)
    assert result["validation_status"] == "fail"


@pytest.mark.parametrize("sql", [
    "SELECT dist_jumlah_a FROM analitik.v_akademik_kelas WHERE kode_matkul = 'IF1220' AND semester = 1 AND tahun = 2024",
    "SELECT COALESCE(AVG(avg_ip_akhir_mahasiswa), 0) AS avg_ip FROM analitik.v_akademik_kelas WHERE no_prodi = 135 AND avg_ip_akhir_mahasiswa IS NOT NULL",
    "SELECT nama_prodi_id, avg_ip_akhir_mahasiswa FROM analitik.v_akademik_statistik_prodi WHERE kode_fakultas = 'STEI' ORDER BY avg_ip_akhir_mahasiswa DESC NULLS LAST",
    "SELECT nama_dosen_gelar, avg_skor_pelaksanaan FROM analitik.v_akademik_statistik_dosen WHERE kode_fakultas_dosen = 'STEI' LIMIT 3",
    "SELECT komentar_teks FROM analitik.v_akademik_komentar_mahasiswa WHERE kode_matkul = 'IF1220'",
    "SELECT c.nama->>'id' AS cpmk FROM kur24.cpmk c JOIN utama.mata_kuliah mk ON mk.mata_kuliah_id = c.mata_kuliah_id WHERE mk.kd_kuliah = 'IF1220' AND c.active = true ORDER BY c.weight",
    "WITH top_mk AS (SELECT kode_matkul, AVG(avg_ip_akhir_mahasiswa) AS avg_ip FROM analitik.v_akademik_kelas WHERE no_prodi = 135 GROUP BY kode_matkul) SELECT kode_matkul, avg_ip FROM top_mk ORDER BY avg_ip DESC NULLS LAST LIMIT 5",
])
@pytest.mark.asyncio
async def test_valid_analytics_queries_pass(sql):
    result = await _make_validator().validate_sql(sql)
    assert result["validation_status"] == "pass", result["error"]


def test_security_config_reuses_application_allowlists():
    required = {"utama", "kelas", "evaluasi", "mahasiswa", "users", "kur24", "analitik", "referensi", "kurikulum"}
    assert required.issubset(SECURITY_ALLOWED_SCHEMAS)
    assert {"checkpoints", "chat_session", "chat_message", "vector_chunks", "information_schema"}.issubset(SECURITY_FORBIDDEN_TABLES)


@pytest.mark.parametrize("sql", [
    "SELECT dist_jumlah_a FROM analitik.v_akademik_kelas WHERE kode_matkul = 'IF1220'",
    "SELECT nama->>'id' AS nama_prodi FROM utama.program_studi WHERE kd_fak = 'STEI' AND active = true",
])
def test_scope_placeholder_is_not_required_because_rls_is_executor_managed(sql):
    ok, err = check_sql_security(sql)
    assert ok is True, err