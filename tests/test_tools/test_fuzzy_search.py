from agent.tools.fuzzy_search import (
    _is_unambiguous,
    SIMILARITY_THRESHOLD_UUID,
    AMBIGUITY_GAP,
)

def test_is_unambiguous_empty_list():
    assert _is_unambiguous([]) is False

def test_is_unambiguous_lone_match_without_uuid_resolve():
    assert _is_unambiguous([{"sim": 0.30}], uuid_resolve=False) is True

def test_is_unambiguous_lone_match_with_uuid_resolve():
    # If below threshold
    assert _is_unambiguous([{"sim": SIMILARITY_THRESHOLD_UUID - 0.05}], uuid_resolve=True) is False
    # If above threshold
    assert _is_unambiguous([{"sim": SIMILARITY_THRESHOLD_UUID + 0.05}], uuid_resolve=True) is True

def test_is_unambiguous_multiple_candidates_clear_lead():
    rows = [
        {"sim": 0.80},
        {"sim": 0.80 - AMBIGUITY_GAP - 0.05}
    ]
    # Gap is larger than AMBIGUITY_GAP, so unambiguous
    assert _is_unambiguous(rows, uuid_resolve=False) is True

def test_is_unambiguous_multiple_candidates_ambiguous():
    rows = [
        {"sim": 0.80},
        {"sim": 0.80 - AMBIGUITY_GAP + 0.05}
    ]
    # Gap is smaller than AMBIGUITY_GAP, so ambiguous
    assert _is_unambiguous(rows, uuid_resolve=False) is False
