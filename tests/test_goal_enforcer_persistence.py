import os
import json
import pytest
from memento.workspace_context import get_workspace_context

@pytest.fixture
def temp_workspace(tmp_path, monkeypatch):
    return str(tmp_path)

def test_load_enforcement_config_overrides(temp_workspace):
    ctx = get_workspace_context(temp_workspace)
    # Setup settings.json with level1=True, level2=False
    settings_dir = os.path.join(temp_workspace, ".memento")
    os.makedirs(settings_dir, exist_ok=True)
    settings_path = os.path.join(settings_dir, "settings.json")
    with open(settings_path, "w") as f:
        json.dump({"enforcement_config": {"level1": True, "level2": False, "level3": False}}, f)

    # Setup .memento.rules.md with level2=True, level1=False
    rules_path = os.path.join(temp_workspace, ".memento.rules.md")
    rules_content = """# Rules
<!-- memento:goal-enforcer:start -->
- level1: false
- level2: true
- level3: false
<!-- memento:goal-enforcer:end -->
"""
    with open(rules_path, "w") as f:
        f.write(rules_content)

    ctx.enforcement_config.update({"level1": False, "level2": False, "level3": False})
    ctx.load_enforcement_config()

    assert ctx.enforcement_config["level1"] is False
    assert ctx.enforcement_config["level2"] is True
    assert ctx.enforcement_config["level3"] is False

def test_save_enforcement_config_writes_markdown(temp_workspace):
    ctx = get_workspace_context(temp_workspace)
    # Modify ENFORCEMENT_CONFIG directly
    ctx.enforcement_config["level1"] = True
    ctx.enforcement_config["level2"] = True
    ctx.enforcement_config["level3"] = True

    ctx.save_enforcement_config()

    # Check settings.json
    settings_path = os.path.join(temp_workspace, ".memento", "settings.json")
    assert os.path.exists(settings_path)
    with open(settings_path, "r") as f:
        data = json.load(f)
        assert data["enforcement_config"]["level1"] is True

    # Check .memento.rules.md
    rules_path = os.path.join(temp_workspace, ".memento.rules.md")
    assert os.path.exists(rules_path)
    with open(rules_path, "r") as f:
        content = f.read()
        assert "<!-- memento:goal-enforcer:start -->" in content
        assert "- level1: true" in content
        assert "- level2: true" in content
        assert "- level3: true" in content

def test_load_enforcement_config_legacy_path(temp_workspace):
    ctx = get_workspace_context(temp_workspace)
    # Setup legacy .memento/memento.rules.md with level3=True
    legacy_dir = os.path.join(temp_workspace, ".memento")
    os.makedirs(legacy_dir, exist_ok=True)
    legacy_rules_path = os.path.join(legacy_dir, "memento.rules.md")
    rules_content = """# Legacy Rules
<!-- memento:goal-enforcer:start -->
- level1: false
- level2: false
- level3: true
<!-- memento:goal-enforcer:end -->
"""
    with open(legacy_rules_path, "w") as f:
        f.write(rules_content)

    rules_path = os.path.join(temp_workspace, ".memento.rules.md")
    if os.path.exists(rules_path):
        os.remove(rules_path)
    ctx.enforcement_config.update({"level1": False, "level2": False, "level3": False})
    ctx.load_enforcement_config()

    assert ctx.enforcement_config["level1"] is False
    assert ctx.enforcement_config["level2"] is False
    assert ctx.enforcement_config["level3"] is True
