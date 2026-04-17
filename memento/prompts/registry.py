import json
from pathlib import Path
from typing import Any

_PROMPTS_DIR = Path(__file__).parent
_cache: dict[str, dict[str, Any]] = {}


def load_prompt(name: str) -> dict[str, Any]:
    """Load a prompt template by name from the prompts directory."""
    if name in _cache:
        return _cache[name]
    path = _PROMPTS_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {name}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _cache[name] = data
    return data


def clear_cache() -> None:
    """Clear the prompt cache (useful for testing)."""
    _cache.clear()
