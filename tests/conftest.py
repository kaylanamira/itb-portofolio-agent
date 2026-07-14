import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Type, TypeVar

import pytest
import sys
import langchain_core.messages
from _pytest.config import Config
from _pytest.nodes import Item
from pydantic import BaseModel

sys.modules["langchain.schema"] = langchain_core.messages
sys.modules["langchain.schema.messages"] = langchain_core.messages

from agent.state import AgentState, QueryType
from core.scope import UserScope, ScopeEntry, UserRole
from evals.scorer import NodeTestResult, aggregate

DATASETS_DIR = Path(__file__).parent.parent / "evals" / "datasets"
RESULTS_DIR = Path(__file__).parent.parent / "evals" / "results"

LLM_TEST_FILES = {
    "test_intent_classifier.py",
    "test_query_rewriter.py",
    "test_planner.py",
    "test_schema_linker.py",
    "test_sql_generator.py",
    "test_answer_validator.py",
    "test_step_reasoner.py",
    "test_synthesizer.py",
    "test_clarification_handler.py",
    "test_rag_retriever.py",
}

T = TypeVar("T", bound=BaseModel)


def load_cases(filename: str, schema: Type[T] | None = None) -> list:
    """Load and optionally validate a dataset JSON file from evals/datasets/."""
    path = DATASETS_DIR / filename
    with open(path) as f:
        raw = json.load(f)
    if schema is None:
        return raw
    return [schema.model_validate(item) for item in raw]


def pytest_configure(config: Config):
    config.addinivalue_line("markers", "llm_eval: requires live LLM credentials and may call external services")


def pytest_collection_modifyitems(config: Config, items: list[Item]):
    if os.getenv("RUN_LLM_EVALS") == "1":
        return
    skip_llm = pytest.mark.skip(reason="Set RUN_LLM_EVALS=1 to run live LLM evaluation tests")
    for item in items:
        if Path(str(item.fspath)).name in LLM_TEST_FILES:
            item.add_marker(skip_llm)


@pytest.fixture(scope="session")
def test_db_url():
    url = os.getenv("DATABASE_URL")
    assert url, "DATABASE_URL must be set"
    return url


@pytest.fixture(scope="session", autouse=True)
async def init_test_db_pool():
    from core.database import init_db_pool, close_db_pool
    await init_db_pool()
    yield
    await close_db_pool()


def _make_scope_entry(role: UserRole, **kwargs) -> ScopeEntry:
    return ScopeEntry(user_role_id=1, role=role, **kwargs)


@pytest.fixture
def scope_dosen():
    entry = _make_scope_entry(UserRole.DOSEN, dosen_id=556, is_prime=True)
    return UserScope(user_id=1001, active_role=entry, available_roles=[entry])


@pytest.fixture
def scope_kaprodi():
    entry = _make_scope_entry(UserRole.KAPRODI, no_ps=135, is_prime=True)
    return UserScope(user_id=1002, active_role=entry, available_roles=[entry])


@pytest.fixture
def scope_dekan():
    entry = _make_scope_entry(UserRole.DEKAN, kd_fak="STEI", is_prime=True)
    return UserScope(user_id=1003, active_role=entry, available_roles=[entry])


@pytest.fixture
def scope_admin():
    entry = _make_scope_entry(UserRole.ADMIN, is_prime=True)
    return UserScope(user_id=1004, active_role=entry, available_roles=[entry])


@pytest.fixture
def make_state(scope_admin):
    def _factory(
        query: str = "test",
        scope: UserScope | None = None,
        query_type: QueryType | None = None,
        plan: list | None = None,
        max_attempts: int = 3,
        **kwargs,
    ) -> AgentState:
        defaults = {
            "raw_query": query,
            "effective_query": query,
            "rewritten_query": None,
            "user_scope": scope or scope_admin,
            "session_id": "test-session",
            "domain": None,
            "query_type": query_type,
            "plan": plan or [],
            "current_step_index": 0,
            "steps_completed": [],
            "reasoning_history": [],
            "messages": [],
            "attempt_count": 0,
            "max_attempts": max_attempts,
            "is_aborted": False,
            "abort_reason": None,
            "error_history": [],
            "content_filter_result": None,
            "detected_entities": None,
            "relevant_tables": None,
            "schema_context": None,
            "chart_context": None,
            "generated_sql": None,
            "validation_status": None,
            "validation_errors": [],
            "sql_result": None,
            "sql_error": None,
            "sql_row_count": None,
            "formatted_response": None,
        }
        defaults.update(kwargs)
        return AgentState(**defaults)
    return _factory


_session_node_results: list[NodeTestResult] = []


@pytest.fixture(scope="session")
def node_results() -> list[NodeTestResult]:
    """Session-scoped list that accumulates NodeTestResult from all test cases."""
    return _session_node_results


def pytest_sessionfinish(session, exitstatus):
    """Aggregate NodeTestResults per node and write one JSON report per node to evals/results/."""
    if not _session_node_results:
        return

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    by_node: dict[str, list[NodeTestResult]] = {}
    for result in _session_node_results:
        by_node.setdefault(result.node_name, []).append(result)

    print(f"\n\n{'='*60}")
    print("EVALUATION METRICS REPORT")
    print(f"{'='*60}")

    for node_name, results in by_node.items():
        passed_cases = [r for r in results if r.passed]
        failed_cases = [r for r in results if not r.passed]
        metrics = aggregate(results, node_name)

        report = {
            "run_id": run_id,
            "node": node_name,
            "dataset_size": len(results),
            "passed_cases": len(passed_cases),
            "failed_cases": len(failed_cases),
            "metrics": [m.model_dump() for m in metrics],
            "failures": [
                {
                    "case_id": r.case_id,
                    "expected_value": r.expected_value,
                    "actual_value": r.actual_value,
                }
                for r in failed_cases
            ],
        }

        report_file = RESULTS_DIR / f"{node_name}_{run_id}.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\n{node_name.upper()}:")
        for metric in metrics:
            status = "PASS" if metric.passed else "FAIL"
            print(f"  {metric.metric_name}: {metric.score:.4f} (threshold={metric.threshold}) [{status}]")
        print(f"  Report: {report_file}")

    print(f"\n{'='*60}\n")
