from agent.state import QueryType
from agent.tools.few_shot_retriever import retrieve_few_shots


def test_data_lookup_examples_include_count_and_ratio_patterns():
    examples = retrieve_few_shots(QueryType.DATA_LOOKUP, n=10)

    assert "Ada berapa fakultas di ITB?" in examples
    assert "Brp persen dosen di STEI" in examples
    assert "COUNT(*) FILTER" in examples
