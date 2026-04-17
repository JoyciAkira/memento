import json
import pytest
from memento.access_manager import MementoAccessManager


def test_default_state():
    am = MementoAccessManager()
    assert am.state == "read-write"
    assert am.can_read() is True
    assert am.can_write() is True


def test_set_state_persists_to_file(tmp_path):
    state_file = str(tmp_path / "settings.json")
    am = MementoAccessManager(state_path=state_file)
    am.set_state("read-only")
    assert am.state == "read-only"
    assert am.can_read() is True
    assert am.can_write() is False
    with open(state_file) as f:
        data = json.load(f)
    assert data["access_manager"]["state"] == "read-only"


def test_state_restored_on_init(tmp_path):
    state_file = str(tmp_path / "settings.json")
    with open(state_file, "w") as f:
        json.dump({"access_manager": {"state": "lockdown", "warnings_enabled": False, "auto_tasks_enabled": True}}, f)
    am = MementoAccessManager(state_path=state_file)
    assert am.state == "lockdown"
    assert am.warnings_enabled is False
    assert am.auto_tasks_enabled is True


def test_persists_preserves_existing_settings(tmp_path):
    state_file = str(tmp_path / "settings.json")
    with open(state_file, "w") as f:
        json.dump({"enforcement_config": {"level1": True}}, f)
    am = MementoAccessManager(state_path=state_file)
    am.set_state("read-only")
    with open(state_file) as f:
        data = json.load(f)
    assert data["enforcement_config"]["level1"] is True
    assert data["access_manager"]["state"] == "read-only"


def test_invalid_state_raises():
    am = MementoAccessManager()
    with pytest.raises(ValueError, match="Invalid state"):
        am.set_state("invalid")


def test_no_path_no_persistence():
    am = MementoAccessManager()
    am.set_state("lockdown")
    assert am.state == "lockdown"
