"""Tests for notification system."""

import json
import os

import pytest

from memento.notifications import NotificationManager


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")
    return NotificationManager(db_path=str(tmp_path / "test.db"))


def test_configure_notifications(manager):
    config = manager.configure(enabled=False)
    assert config["enabled"] is False
    assert manager.enabled is False


def test_configure_topics(manager):
    custom_topics = ["memory_added", "quality_alert"]
    config = manager.configure(topics=custom_topics)
    assert config["topics"] == custom_topics


@pytest.mark.asyncio
async def test_notify_creates_pending(manager):
    result = await manager.notify(
        topic="memory_added",
        title="Test notification",
        body="Something happened",
        confidence=0.9,
    )
    assert result["status"] == "queued"
    assert result["id"].startswith("notif_")

    pending = manager.get_pending_notifications()
    assert len(pending) == 1
    assert pending[0]["title"] == "Test notification"
    assert pending[0]["topic"] == "memory_added"


@pytest.mark.asyncio
async def test_notify_filtered_by_topic(manager):
    result = await manager.notify(
        topic="unknown_topic",
        title="Should be filtered",
        body="nope",
        confidence=1.0,
    )
    assert result["status"] == "filtered"
    assert result["topic"] == "unknown_topic"
    assert len(manager.get_pending_notifications()) == 0


@pytest.mark.asyncio
async def test_notify_low_confidence(manager):
    result = await manager.notify(
        topic="memory_added",
        title="Low confidence",
        body="nope",
        confidence=0.1,
    )
    assert result["status"] == "low_confidence"
    assert result["confidence"] == 0.1
    assert len(manager.get_pending_notifications()) == 0


@pytest.mark.asyncio
async def test_get_pending_notifications(manager):
    await manager.notify(topic="memory_added", title="First", body="b1", confidence=1.0)
    await manager.notify(topic="memory_added", title="Second", body="b2", confidence=1.0)

    pending = manager.get_pending_notifications()
    assert len(pending) == 2
    assert pending[0]["title"] == "Second"
    assert pending[1]["title"] == "First"


@pytest.mark.asyncio
async def test_dismiss_notification(manager):
    await manager.notify(topic="memory_added", title="Dismiss me", body="b", confidence=1.0)

    pending = manager.get_pending_notifications()
    notif_id = pending[0]["id"]

    dismissed = manager.dismiss(notif_id)
    assert dismissed is True

    remaining = manager.get_pending_notifications()
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_clear_all(manager):
    await manager.notify(topic="memory_added", title="A", body="b", confidence=1.0)
    await manager.notify(topic="memory_added", title="B", body="b", confidence=1.0)

    cleared = manager.clear_all()
    assert cleared == 2
    assert len(manager.get_pending_notifications()) == 0


def test_notification_stats(manager):
    stats = manager.notification_stats()
    assert "pending" in stats
    assert "dismissed" in stats
    assert "max_pending" in stats
    assert "ttl_seconds" in stats
    assert "enabled" in stats
    assert "topics" in stats
    assert stats["enabled"] is True
    assert "memory_added" in stats["topics"]


@pytest.mark.asyncio
async def test_check_relevance_alert_high_score(manager):
    result = await manager.check_relevance_alert(
        text="test query",
        top_results=[{"score": 0.95, "memory": "very relevant memory content here"}],
    )
    assert result is not None
    assert result["status"] == "queued"

    pending = manager.get_pending_notifications()
    assert len(pending) == 1
    assert pending[0]["topic"] == "relevance_alert"


@pytest.mark.asyncio
async def test_check_relevance_alert_low_score(manager):
    result = await manager.check_relevance_alert(
        text="test query",
        top_results=[{"score": 0.3, "memory": "low relevance"}],
    )
    assert result is None
    assert len(manager.get_pending_notifications()) == 0


@pytest.mark.asyncio
async def test_notify_memory_event(manager):
    result = await manager.notify_memory_event("added", details={"key": "value"})
    assert result["status"] == "queued"

    pending = manager.get_pending_notifications()
    assert len(pending) == 1
    assert pending[0]["topic"] == "memory_added"
    assert pending[0]["title"] == "Memory added"


def test_config_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")

    db_path = str(tmp_path / "persist.db")
    manager1 = NotificationManager(db_path=db_path)
    manager1.configure(enabled=False, topics=["quality_alert"], min_confidence=0.9)

    config_path = tmp_path / "notifications.json"
    assert config_path.exists()

    manager2 = NotificationManager(db_path=db_path)
    assert manager2.enabled is False
    assert manager2._config["topics"] == ["quality_alert"]
    assert manager2._config["min_confidence"] == 0.9
