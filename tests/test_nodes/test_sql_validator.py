from agent.tools.security import check_sql_security


def test_security_blocks_destructive():
    ok, err = check_sql_security("DROP TABLE mv_kelas;")
    assert not ok
    assert "Security Violation" in err


def test_security_allows_select():
    ok, err = check_sql_security("SELECT * FROM analitik.mv_kelas LIMIT 10;")
    assert ok
    assert err is None


def test_security_blocks_forbidden_schema():
    ok, err = check_sql_security("SELECT * FROM wisuda.lulusan;")
    assert not ok
    assert "forbidden schema" in err.lower()


def test_security_domain_agnostic_mode():
    ok, err = check_sql_security(
        "SELECT * FROM wisuda.lulusan;",
        allowed_schemas=frozenset(),
    )
    assert ok
    assert err is None
