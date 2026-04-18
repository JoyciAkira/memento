"""Tests for predictive cache."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from memento.predictive_cache import PredictiveCache


def _make_cache(**overrides) -> PredictiveCache:
    defaults = {"db_path": "/tmp/test.db", "provider": None}
    defaults.update(overrides)
    return PredictiveCache(**defaults)


@pytest.mark.asyncio
async def test_warm_for_context_no_provider(monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")
    cache = _make_cache(provider=None)
    result = await cache.warm_for_context("hello world")
    assert result["results"] == []
    assert result["cached_at"] is None


@pytest.mark.asyncio
async def test_warm_for_context_with_mock_provider(monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")
    provider = MagicMock()
    provider.search = AsyncMock(
        return_value=[{"id": "mem-1", "memory": "test", "score": 0.9}]
    )
    cache = _make_cache(provider=provider)

    result = await cache.warm_for_context("hello world", limit=5)
    assert len(result["results"]) == 1
    assert result["results"][0]["id"] == "mem-1"
    assert result["results"][0]["memory"] == "test"
    assert result["cached_at"] is not None
    provider.search.assert_called_once_with("hello world", limit=5)

    cached = cache.get_cached_context("hello world")
    assert cached is not None
    assert cached["results"][0]["id"] == "mem-1"


@pytest.mark.asyncio
async def test_get_cached_context_hit(monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")
    provider = MagicMock()
    provider.search = AsyncMock(
        return_value=[{"id": "mem-1", "memory": "test", "score": 0.9}]
    )
    cache = _make_cache(provider=provider)

    await cache.warm_for_context("hello world")
    cached = cache.get_cached_context("hello world")
    assert cached is not None
    assert cached["results"][0]["id"] == "mem-1"


@pytest.mark.asyncio
async def test_get_cached_context_miss(monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")
    cache = _make_cache()
    assert cache.get_cached_context("nonexistent") is None


def test_cache_stats():
    cache = _make_cache()
    cache._hits = 7
    cache._misses = 3
    key = PredictiveCache._make_key("stats-test")
    cache._cache[key] = {
        "key": key,
        "results": [],
        "cached_at": None,
        "timestamp": time.time(),
    }
    stats = cache.cache_stats()
    assert stats["total_entries"] == 1
    assert stats["active_entries"] == 1
    assert stats["stale_entries"] == 0
    assert stats["hits"] == 7
    assert stats["misses"] == 3
    assert stats["hit_rate"] == 0.7


def test_invalidate_all():
    cache = _make_cache()
    for i in range(5):
        key = PredictiveCache._make_key(f"text-{i}")
        cache._cache[key] = {
            "key": key,
            "results": [],
            "cached_at": None,
            "timestamp": time.time(),
        }
    assert len(cache._cache) == 5
    evicted = cache.invalidate()
    assert evicted == 5
    assert len(cache._cache) == 0


def test_invalidate_by_key():
    cache = _make_cache()
    key_a = PredictiveCache._make_key("text-a")
    key_b = PredictiveCache._make_key("text-b")
    cache._cache[key_a] = {
        "key": key_a,
        "results": [],
        "cached_at": None,
        "timestamp": time.time(),
    }
    cache._cache[key_b] = {
        "key": key_b,
        "results": [],
        "cached_at": None,
        "timestamp": time.time(),
    }
    evicted = cache.invalidate(key=key_a)
    assert evicted == 1
    assert key_a not in cache._cache
    assert key_b in cache._cache


@pytest.mark.asyncio
async def test_cache_ttl_expiry(monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")
    cache = _make_cache()
    key = PredictiveCache._make_key("old text")
    cache._cache[key] = {
        "key": key,
        "results": [{"id": "m1", "memory": "old", "score": 0.8}],
        "cached_at": "2020-01-01T00:00:00",
        "timestamp": time.time() - 600,
    }
    result = cache.get_cached_context("old text")
    assert result is None
    assert key not in cache._cache


@pytest.mark.asyncio
async def test_cache_eviction(monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")
    provider = MagicMock()
    provider.search = AsyncMock(return_value=[])
    cache = _make_cache(provider=provider)
    cache.MAX_CACHE_SIZE = 3

    for i in range(5):
        await cache.warm_for_context(f"text-{i}", limit=1)

    assert len(cache._cache) == 3
    assert "text-0" not in cache._cache
    assert "text-1" not in cache._cache
    assert "text-2" in cache._cache
    assert "text-3" in cache._cache
    assert "text-4" in cache._cache


@pytest.mark.asyncio
async def test_warm_for_context_empty_text(monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")
    provider = MagicMock()
    provider.search = AsyncMock(return_value=[])
    cache = _make_cache(provider=provider)

    result = await cache.warm_for_context("")
    assert result["results"] == []
    provider.search.assert_called_once_with("", limit=5)
