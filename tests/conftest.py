import os
import pytest


@pytest.fixture(autouse=True)
def _disable_openai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")


@pytest.fixture
def tmp_workspace(tmp_path):
    db_path = str(tmp_path / "test_memory.db")
    return db_path
