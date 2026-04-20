"""Tests for local embedding backend."""
import os
import pytest
from unittest.mock import MagicMock, patch


def test_is_fastembed_available_returns_bool():
    from memento.local_embeddings import is_fastembed_available
    result = is_fastembed_available()
    assert isinstance(result, bool)


def test_local_embedding_backend_import():
    from memento.local_embeddings import LocalEmbeddingBackend
    backend = LocalEmbeddingBackend()
    assert backend.dimension == 384


def test_local_embedding_backend_model_not_loaded_at_init():
    from memento.local_embeddings import LocalEmbeddingBackend
    backend = LocalEmbeddingBackend()
    assert backend._model is None


def test_settings_detects_no_backend_by_default(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MEMENTO_EMBEDDING_BACKEND", raising=False)
    monkeypatch.setattr("memento.local_embeddings.is_fastembed_available", lambda: False)
    from memento.settings import Settings
    s = Settings()
    assert s.embedding_backend == "none"


def test_settings_detects_openai_with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.delenv("MEMENTO_EMBEDDING_BACKEND", raising=False)
    from memento.settings import Settings
    s = Settings()
    assert s.embedding_backend == "openai"


def test_settings_detects_local_with_fastembed(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MEMENTO_EMBEDDING_BACKEND", raising=False)
    monkeypatch.setattr("memento.local_embeddings.is_fastembed_available", lambda: True)
    from memento.settings import Settings
    s = Settings()
    assert s.embedding_backend == "local"


def test_settings_explicit_backend_overrides(monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from memento.settings import Settings
    s = Settings()
    assert s.embedding_backend == "openai"


@pytest.mark.asyncio
async def test_provider_get_embedding_with_local_backend(monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "local")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    mock_backend = MagicMock()

    async def mock_embed(text):
        return [0.1] * 384
    mock_backend.embed = mock_embed

    from memento.provider import NeuroGraphProvider
    provider = NeuroGraphProvider.__new__(NeuroGraphProvider)
    provider.embedding_backend = "local"
    provider._local_embedder = mock_backend

    result = await provider._get_embedding("test text")
    assert len(result) == 384
    assert result[0] == pytest.approx(0.1)
