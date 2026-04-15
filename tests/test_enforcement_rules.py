from memento.enforcement_rules import (
    extract_goal_enforcer_config_from_rules_md,
    upsert_goal_enforcer_block,
    START_DELIMITER,
    END_DELIMITER
)

def test_extract_empty_string():
    config = extract_goal_enforcer_config_from_rules_md("")
    assert config == {"level1": False, "level2": False, "level3": False}

def test_extract_valid_block():
    content = f"""# Some Rules
{START_DELIMITER}
- level1: true
- level2: false
- level3: true
{END_DELIMITER}
"""
    config = extract_goal_enforcer_config_from_rules_md(content)
    assert config == {"level1": True, "level2": False, "level3": True}

def test_extract_invalid_block_missing_delimiters():
    content = """# Some Rules
- level1: true
- level2: false
- level3: true
"""
    config = extract_goal_enforcer_config_from_rules_md(content)
    assert config == {"level1": False, "level2": False, "level3": False}

def test_upsert_empty_string():
    config = {"level1": True, "level2": False, "level3": True}
    result = upsert_goal_enforcer_block("", config)
    assert "# Memento Rules" in result
    assert START_DELIMITER in result
    assert "- level1: true" in result
    assert "- level2: false" in result
    assert "- level3: true" in result
    assert END_DELIMITER in result

def test_upsert_missing_block_preserving_notes():
    content = "# Memento Rules\n\nSome user notes here.\n"
    config = {"level1": True, "level2": True, "level3": False}
    result = upsert_goal_enforcer_block(content, config)
    assert "Some user notes here." in result
    assert START_DELIMITER in result
    assert "- level1: true" in result
    assert "- level2: true" in result
    assert "- level3: false" in result
    assert END_DELIMITER in result
    assert result.startswith("# Memento Rules\n\nSome user notes here.\n\n")

def test_upsert_update_existing_block():
    content = f"""# Memento Rules
{START_DELIMITER}
- level1: false
- level2: false
- level3: false
{END_DELIMITER}
More notes below.
"""
    config = {"level1": True, "level2": True, "level3": True}
    result = upsert_goal_enforcer_block(content, config)
    assert "More notes below." in result
    assert "- level1: true" in result
    assert "- level2: true" in result
    assert "- level3: true" in result
    assert "- level1: false" not in result
