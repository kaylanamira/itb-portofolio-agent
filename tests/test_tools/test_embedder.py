from unittest.mock import MagicMock

import pytest

from agent.tools.rag.core import embedder


@pytest.fixture(autouse=True)
def reset_embedder_singleton(monkeypatch):
    """Each test gets a fresh mocked embedder instance instead of the real
    (heavy, network/GPU-dependent) one."""
    monkeypatch.setattr(embedder, "_embedder_instance", None)
    yield
    monkeypatch.setattr(embedder, "_embedder_instance", None)


def _install_mock_embedder(monkeypatch, mock):
    monkeypatch.setattr(embedder.EmbedderFactory, "get_embedder", staticmethod(lambda: mock))


def test_embed_query_text_applies_query_prefix(monkeypatch):
    mock = MagicMock()
    mock.embed_query.return_value = [0.1, 0.2, 0.3]
    _install_mock_embedder(monkeypatch, mock)

    result = embedder.embed_query_text("apa syarat kelulusan?")

    mock.embed_query.assert_called_once_with("query: apa syarat kelulusan?")
    assert result == [0.1, 0.2, 0.3]


def test_embed_passage_texts_applies_passage_prefix(monkeypatch):
    mock = MagicMock()
    mock.embed_documents.return_value = [[0.1] * 4, [0.2] * 4]
    _install_mock_embedder(monkeypatch, mock)

    result = embedder.embed_passage_texts(["chunk one", "chunk two"])

    mock.embed_documents.assert_called_once_with(["passage: chunk one", "passage: chunk two"])
    assert result == [[0.1] * 4, [0.2] * 4]


def test_embed_text_backcompat_dispatches_by_type(monkeypatch):
    mock = MagicMock()
    mock.embed_query.return_value = [0.5]
    mock.embed_documents.return_value = [[0.5]]
    _install_mock_embedder(monkeypatch, mock)

    assert embedder.embed_text("a query") == [0.5]
    mock.embed_query.assert_called_once_with("query: a query")

    assert embedder.embed_text(["a passage"]) == [[0.5]]
    mock.embed_documents.assert_called_once_with(["passage: a passage"])


def test_embed_text_rejects_invalid_type(monkeypatch):
    mock = MagicMock()
    _install_mock_embedder(monkeypatch, mock)
    with pytest.raises(ValueError):
        embedder.embed_text(123)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_async_wrappers_delegate_to_sync(monkeypatch):
    mock = MagicMock()
    mock.embed_query.return_value = [1.0] * 1024
    mock.embed_documents.return_value = [[1.0] * 1024]
    _install_mock_embedder(monkeypatch, mock)

    query_result = await embedder.aembed_query_text("test")
    passage_result = await embedder.aembed_passage_texts(["test"])

    assert len(query_result) == 1024
    assert len(passage_result[0]) == 1024


def test_get_embedder_unsupported_provider_raises(monkeypatch):
    monkeypatch.setattr(embedder.settings, "EMBEDDING_PROVIDER", "not-a-real-provider")
    with pytest.raises(ValueError):
        embedder.EmbedderFactory.get_embedder()
