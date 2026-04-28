"""Tests for memento/autonomous.py — autonomous agent loop, levels, decisions."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from memento.autonomous import (
    AutonomousAgent,
    AutonomyLevel,
    AutonomousDecision,
    LEVEL_DESCRIPTIONS,
    DEFAULT_INTERVALS,
)


def _make_agent() -> AutonomousAgent:
    provider = AsyncMock()
    cognitive_engine = AsyncMock()
    return AutonomousAgent(
        provider=provider,
        cognitive_engine=cognitive_engine,
        workspace_root="/tmp/test_workspace",
    )


class TestAutonomyLevel:
    def test_valid_levels(self):
        assert AutonomyLevel.OFF == "off"
        assert AutonomyLevel.PASSIVE == "passive"
        assert AutonomyLevel.ACTIVE == "active"
        assert AutonomyLevel.AUTONOMOUS == "autonomous"

    def test_from_string(self):
        assert AutonomyLevel("off") == AutonomyLevel.OFF
        assert AutonomyLevel("passive") == AutonomyLevel.PASSIVE
        assert AutonomyLevel("active") == AutonomyLevel.ACTIVE
        assert AutonomyLevel("autonomous") == AutonomyLevel.AUTONOMOUS

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            AutonomyLevel("invalid")

    def test_descriptions_exist_for_all_levels(self):
        for level in AutonomyLevel:
            assert level in LEVEL_DESCRIPTIONS
            assert isinstance(LEVEL_DESCRIPTIONS[level], str)
            assert len(LEVEL_DESCRIPTIONS[level]) > 10

    def test_default_intervals(self):
        assert DEFAULT_INTERVALS[AutonomyLevel.OFF] == 0
        assert DEFAULT_INTERVALS[AutonomyLevel.PASSIVE] > 0
        assert DEFAULT_INTERVALS[AutonomyLevel.ACTIVE] > 0
        assert DEFAULT_INTERVALS[AutonomyLevel.AUTONOMOUS] > 0


class TestAutonomousAgentInit:
    def test_default_state(self):
        agent = _make_agent()
        assert agent.level == AutonomyLevel.OFF
        assert agent.is_running is False
        assert agent.get_status()["cycle_count"] == 0

    def test_set_level_string(self):
        agent = _make_agent()
        agent.set_level("active")
        assert agent.level == AutonomyLevel.ACTIVE

    def test_set_level_enum(self):
        agent = _make_agent()
        agent.set_level(AutonomyLevel.AUTONOMOUS)
        assert agent.level == AutonomyLevel.AUTONOMOUS


class TestAutonomousAgentStartStop:
    def test_start_when_off(self):
        agent = _make_agent()
        agent.set_level(AutonomyLevel.OFF)
        result = agent.start()
        assert result is False

    @pytest.mark.asyncio
    async def test_start_when_level_set(self):
        agent = _make_agent()
        agent.set_level(AutonomyLevel.PASSIVE)
        result = agent.start()
        assert result is True
        assert agent.is_running is True
        agent.stop()

    @pytest.mark.asyncio
    async def test_stop(self):
        agent = _make_agent()
        agent.set_level(AutonomyLevel.PASSIVE)
        agent.start()
        result = agent.stop()
        assert result is True
        assert agent.is_running is False

    @pytest.mark.asyncio
    async def test_double_start(self):
        agent = _make_agent()
        agent.set_level(AutonomyLevel.PASSIVE)
        agent.start()
        result = agent.start()
        assert result is False
        agent.stop()


class TestDecisionLog:
    def test_log_decision(self):
        agent = _make_agent()
        agent._log_decision(
            action="test_action",
            reason="test reason",
            outcome="test outcome",
            confidence=0.9,
        )
        log = agent.get_decision_log()
        assert len(log) == 1
        assert log[0]["action"] == "test_action"
        assert log[0]["reason"] == "test reason"
        assert log[0]["confidence"] == 0.9

    def test_log_truncation(self):
        agent = _make_agent()
        for i in range(250):
            agent._log_decision(
                action=f"action_{i}",
                reason="reason",
                outcome="outcome",
                confidence=0.5,
            )
        log = agent.get_decision_log()
        assert len(log) <= AutonomousAgent.MAX_DECISION_LOG

    def test_decision_log_limit_param(self):
        agent = _make_agent()
        for i in range(20):
            agent._log_decision(action=f"a{i}", reason="r", outcome="o")
        log = agent.get_decision_log(limit=5)
        assert len(log) == 5


class TestGetStatus:
    def test_status_structure(self):
        agent = _make_agent()
        agent.set_level(AutonomyLevel.ACTIVE)
        status = agent.get_status()
        assert "level" in status
        assert "level_description" in status
        assert "running" in status
        assert "interval_seconds" in status
        assert "cycle_count" in status
        assert "stats" in status
        assert "recent_decisions" in status
        assert status["level"] == "active"
        assert status["running"] is False

    def test_status_after_decisions(self):
        agent = _make_agent()
        agent._log_decision(action="test", reason="r", outcome="o")
        status = agent.get_status()
        assert len(status["recent_decisions"]) == 1


class TestPassiveCycle:
    @pytest.mark.asyncio
    async def test_observe_health(self):
        agent = _make_agent()
        agent.provider.get_all = AsyncMock(return_value=[{"id": "1", "memory": "test"}])
        await agent._observe_health()
        log = agent.get_decision_log()
        assert any(d["action"] == "observe_health" for d in log)

    @pytest.mark.asyncio
    async def test_observe_patterns(self):
        agent = _make_agent()
        agent.provider.search = AsyncMock(return_value={
            "results": [{"memory": "a"}, {"memory": "b"}, {"memory": "c"}]
        })
        await agent._observe_patterns()
        log = agent.get_decision_log()
        assert any(d["action"] == "observe_patterns" for d in log)


class TestActiveCycle:
    @pytest.mark.asyncio
    async def test_auto_consolidate_with_results(self):
        agent = _make_agent()
        agent.provider.consolidate = AsyncMock(return_value={"merged": 3})
        await agent._auto_consolidate()
        log = agent.get_decision_log()
        assert any(d["action"] == "consolidate" for d in log)

    @pytest.mark.asyncio
    async def test_auto_consolidate_nothing_to_merge(self):
        agent = _make_agent()
        agent.provider.consolidate = AsyncMock(return_value={"merged": 0})
        await agent._auto_consolidate()
        log = agent.get_decision_log()
        assert not any(d["action"] == "consolidate" for d in log)

    @pytest.mark.asyncio
    async def test_auto_kg_extract(self):
        agent = _make_agent()
        agent.provider.extract_kg = AsyncMock(return_value={"triples_extracted": 5})
        await agent._auto_kg_extract()
        log = agent.get_decision_log()
        assert any(d["action"] == "kg_extract" for d in log)

    @pytest.mark.asyncio
    async def test_detect_anomalies(self):
        agent = _make_agent()
        agent.provider.search = AsyncMock(return_value={
            "results": [{"score": 0.05, "memory": "orphan"}, {"score": 0.9, "memory": "good"}]
        })
        from memento.memory.governor import MemoryGovernor
        agent.governor = MemoryGovernor()
        await agent._detect_anomalies()
        log = agent.get_decision_log()
        assert any(d["action"] == "anomaly_detect" for d in log)


class TestAutonomousCycle:
    @pytest.mark.asyncio
    async def test_auto_dream_skips_non_multiple(self):
        agent = _make_agent()
        agent._cycle_count = 3
        await agent._auto_dream()
        agent.cognitive_engine.synthesize_dreams.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_dream_on_multiple(self):
        agent = _make_agent()
        agent._cycle_count = 5
        agent.cognitive_engine.synthesize_dreams = AsyncMock(
            return_value="[DRAFT_INSIGHT] Some interesting pattern found"
        )
        await agent._auto_dream()
        agent.cognitive_engine.synthesize_dreams.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_goal_drift_check(self):
        agent = _make_agent()
        agent._cycle_count = 3
        agent.provider.list_goals = AsyncMock(return_value=[
            {"goal": "Build fast API"}
        ])
        agent.provider.search = AsyncMock(return_value={
            "results": [{"memory": "refactoring database layer"}]
        })
        agent.cognitive_engine.check_goal_alignment = AsyncMock(
            return_value="MISALIGNED: the work doesn't align with goals"
        )
        await agent._auto_goal_drift_check()
        log = agent.get_decision_log()
        assert any(d["action"] == "goal_drift" for d in log)

    @pytest.mark.asyncio
    async def test_auto_generate_tasks_skips_non_multiple(self):
        agent = _make_agent()
        agent._cycle_count = 7
        await agent._auto_generate_tasks()
        agent.cognitive_engine.generate_tasks.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_health_report(self):
        agent = _make_agent()
        agent._cycle_count = 7
        agent.provider.add = AsyncMock(return_value="ok")
        await agent._auto_health_report()
        log = agent.get_decision_log()
        assert any(d["action"] == "health_report" for d in log)


class TestFullCycle:
    @pytest.mark.asyncio
    async def test_run_cycle_passive(self):
        agent = _make_agent()
        agent.set_level(AutonomyLevel.PASSIVE)
        agent.provider.get_all = AsyncMock(return_value=[])
        agent.provider.search = AsyncMock(return_value={"results": []})
        await agent._run_cycle()
        assert agent.get_status()["cycle_count"] == 0  # cycle_count is incremented by _loop

    @pytest.mark.asyncio
    async def test_run_cycle_active(self):
        agent = _make_agent()
        agent.set_level(AutonomyLevel.ACTIVE)
        agent.provider.get_all = AsyncMock(return_value=[])
        agent.provider.search = AsyncMock(return_value={"results": []})
        agent.provider.consolidate = AsyncMock(return_value={"merged": 0})
        agent.provider.extract_kg = AsyncMock(return_value={"triples_extracted": 0})
        agent.provider.warm_predictive_cache = AsyncMock()
        await agent._run_cycle()

    @pytest.mark.asyncio
    async def test_run_cycle_autonomous(self):
        agent = _make_agent()
        agent.set_level(AutonomyLevel.AUTONOMOUS)
        agent.provider.get_all = AsyncMock(return_value=[])
        agent.provider.search = AsyncMock(return_value={"results": []})
        agent.provider.consolidate = AsyncMock(return_value={"merged": 0})
        agent.provider.extract_kg = AsyncMock(return_value={"triples_extracted": 0})
        agent.provider.warm_predictive_cache = AsyncMock()
        agent.provider.list_goals = AsyncMock(return_value=[])
        agent.provider.add = AsyncMock(return_value="ok")
        agent.cognitive_engine.synthesize_dreams = AsyncMock(return_value="")
        agent.cognitive_engine.generate_tasks = AsyncMock(return_value="")
        await agent._run_cycle()


class TestConfigStoreIntegration:
    def test_autonomy_config_default(self, tmp_path):
        from memento.config_store import WorkspaceConfigStore
        store = WorkspaceConfigStore(str(tmp_path), str(tmp_path))
        store.load()
        assert store.autonomy["level"] == "off"

    def test_autonomy_config_save_load(self, tmp_path):
        from memento.config_store import WorkspaceConfigStore
        store = WorkspaceConfigStore(str(tmp_path), str(tmp_path))
        store.load()
        store.autonomy["level"] = "active"
        store.save()

        store2 = WorkspaceConfigStore(str(tmp_path), str(tmp_path))
        store2.load()
        assert store2.autonomy["level"] == "active"

    def test_autonomy_config_rejects_invalid(self, tmp_path):
        from memento.config_store import WorkspaceConfigStore
        import json
        settings = tmp_path / "settings.json"
        settings.write_text(json.dumps({"autonomy": {"level": "invalid_value"}}))
        store = WorkspaceConfigStore(str(tmp_path), str(tmp_path))
        store.load()
        assert store.autonomy["level"] == "off"
