from agent.tools.fuzzy_search import (
    _is_unambiguous,
    FuzzyConfig,
    DEFAULT_CONFIG,
)


def test_is_unambiguous_empty_list():
    assert _is_unambiguous([]) is False


def test_is_unambiguous_lone_match_without_id_resolve():
    assert _is_unambiguous([{"sim": 0.30}], require_id=False) is True


def test_is_unambiguous_lone_match_with_id_resolve():
    threshold = DEFAULT_CONFIG.id_threshold
    assert _is_unambiguous([{"sim": threshold - 0.05}], require_id=True) is False
    assert _is_unambiguous([{"sim": threshold + 0.05}], require_id=True) is True


def test_is_unambiguous_multiple_candidates_clear_lead():
    gap = DEFAULT_CONFIG.ambiguity_gap
    rows = [
        {"sim": 0.80},
        {"sim": 0.80 - gap - 0.05}
    ]
    assert _is_unambiguous(rows, require_id=False) is True


def test_is_unambiguous_multiple_candidates_ambiguous():
    gap = DEFAULT_CONFIG.ambiguity_gap
    rows = [
        {"sim": 0.80},
        {"sim": 0.80 - gap + 0.05}
    ]
    assert _is_unambiguous(rows, require_id=False) is False
