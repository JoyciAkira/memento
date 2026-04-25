from memento.memory.l1_working import L1WorkingMemory


def test_l1_dump_roundtrip_restores_order_and_content():
    l1 = L1WorkingMemory(max_size=10)
    l1.add("a", "A", {"x": 1})
    l1.add("b", "B", {"x": 2})

    dump = l1.dump()
    assert len(dump) == 2

    l1_new = L1WorkingMemory(max_size=10)
    l1_new.restore(dump)
    restored = l1_new.get_all()

    assert [r["id"] for r in restored] == ["a", "b"]
    assert restored[0]["content"] == "A"
    assert restored[0]["metadata"] == {"x": 1}

