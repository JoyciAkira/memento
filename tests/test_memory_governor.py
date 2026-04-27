from datetime import datetime

from memento.memory.governor import MemoryGovernor


def test_memory_governor_triggers_for_strong_recent_memory():
    governor = MemoryGovernor()
    signal = governor.score(
        memory_id="m1",
        semantic_similarity=1.0,
        vsa_resonance=1.0,
        created_at=datetime.now().isoformat(),
        hit_count=10,
        surprise=1.0,
    )
    decision = governor.decide(signal)

    assert signal.strength >= 0.85
    assert decision.should_inject
    assert decision.should_consolidate


def test_memory_governor_keeps_weak_memory_quiet():
    governor = MemoryGovernor()
    signal = governor.score(memory_id="m1")
    decision = governor.decide(signal)

    assert signal.strength < 0.60
    assert not decision.should_prefetch
    assert decision.reason == "low_signal"
