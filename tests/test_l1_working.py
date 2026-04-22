import pytest
from memento.memory.l1_working import L1WorkingMemory

def test_l1_working_memory_basic_ops():
    l1 = L1WorkingMemory(max_size=3)

    l1.add("ctx1", "Task: refactor code")
    l1.add("ctx2", "File: main.py")

    assert len(l1.get_all()) == 2
    assert l1.get_all()[0]["content"] == "Task: refactor code"

    l1.add("ctx3", "Line 10")
    l1.add("ctx4", "Error 500")

    assert len(l1.get_all()) == 3
    assert not any(item["id"] == "ctx1" for item in l1.get_all())

    l1.clear()
    assert len(l1.get_all()) == 0


def test_l1_working_memory_update_existing():
    l1 = L1WorkingMemory(max_size=10)

    l1.add("ctx1", "v1")
    l1.add("ctx1", "v2")

    assert l1.get_all()[0]["content"] == "v2"


def test_l1_working_memory_metadata():
    l1 = L1WorkingMemory()

    l1.add("ctx1", "code", {"type": "file", "path": "/src/main.py"})
    meta = l1.get_all()[0]["metadata"]

    assert meta["type"] == "file"
    assert meta["path"] == "/src/main.py"
