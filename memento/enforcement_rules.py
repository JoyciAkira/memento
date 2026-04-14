import re

START_DELIMITER = "<!-- memento:goal-enforcer:start -->"
END_DELIMITER = "<!-- memento:goal-enforcer:end -->"

def extract_goal_enforcer_config_from_rules_md(content: str) -> dict[str, bool]:
    """
    Extracts the goal enforcer configuration from the given markdown content.
    Returns a dictionary with keys 'level1', 'level2', 'level3' and boolean values.
    """
    config: dict[str, bool] = {"level1": False, "level2": False, "level3": False}
    
    start_idx = content.find(START_DELIMITER)
    end_idx = content.find(END_DELIMITER)
    
    if start_idx == -1 or end_idx == -1 or start_idx > end_idx:
        return config
        
    block = content[start_idx + len(START_DELIMITER):end_idx]
    
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
            
        match = re.match(r'-?\s*(level[123])\s*:\s*(true|false)', line, re.IGNORECASE)
        if match:
            key = match.group(1).lower()
            val = match.group(2).lower() == 'true'
            config[key] = val
                
    return config

def upsert_goal_enforcer_block(existing: str, config: dict[str, bool]) -> str:
    """
    Upserts the goal enforcer configuration block into the given markdown content.
    If the content is empty, generates a base structure.
    """
    block_lines = [
        START_DELIMITER,
        "- level1: " + str(config.get("level1", False)).lower(),
        "- level2: " + str(config.get("level2", False)).lower(),
        "- level3: " + str(config.get("level3", False)).lower(),
        END_DELIMITER
    ]
    block_str = "\n".join(block_lines)
    
    if not existing.strip():
        return f"# Memento Rules\n\n{block_str}\n"
        
    start_idx = existing.find(START_DELIMITER)
    end_idx = existing.find(END_DELIMITER)
    
    if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
        # Replace existing block
        return existing[:start_idx] + block_str + existing[end_idx + len(END_DELIMITER):]
    else:
        # Append block at the end
        if not existing.endswith("\n\n") and not existing.endswith("\n"):
            return existing + "\n\n" + block_str + "\n"
        elif existing.endswith("\n") and not existing.endswith("\n\n"):
            return existing + "\n" + block_str + "\n"
        else:
            return existing + block_str + "\n"
