from agent.state import QueryType
from agent.tools.few_shot_retriever import retrieve_few_shots


def test_data_lookup_examples_load_from_yaml():
    examples = retrieve_few_shots(QueryType.DATA_LOOKUP, n=10)

    assert "fakultas" in examples.lower()
    assert "persen dosen di STEI" in examples
    assert "COUNT(*)" in examples



def test_analytical_numeric_examples_load():
    examples = retrieve_few_shots(QueryType.ANALYTICAL_NUMERIC, n=3)
    assert len(examples) > 0
    assert "Example 1" in examples


def test_unknown_query_type_falls_back_gracefully():
    # A type with no YAML file falls back gracefully
    examples = retrieve_few_shots(QueryType.CHART_INTERPRET, n=3)
    assert isinstance(examples, str)
