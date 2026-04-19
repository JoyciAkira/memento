import json
import os
import logging
from typing import Any

from memento.enforcement_rules import (
    extract_goal_enforcer_config_from_rules_md,
    upsert_goal_enforcer_block,
)

logger = logging.getLogger(__name__)


class WorkspaceConfigStore:
    """Owns all workspace-level settings I/O. Single source of truth for settings.json."""

    def __init__(self, memento_dir: str, workspace_root: str):
        self._memento_dir = memento_dir
        self._workspace_root = workspace_root
        self._settings_path = os.path.join(memento_dir, "settings.json")
        self._rules_path = os.path.join(workspace_root, ".memento.rules.md")
        self._legacy_rules_path = os.path.join(memento_dir, "memento.rules.md")

        self.enforcement_config: dict[str, Any] = {"level1": False, "level2": False, "level3": False}
        self.active_coercion: dict[str, Any] = {"enabled": False, "rules": []}
        self.dependency_tracker: dict[str, Any] = {"enabled": False}

    def load(self) -> None:
        data = self._read_settings()

        config = data.get("enforcement_config", {})
        if isinstance(config, dict):
            self.enforcement_config.update(config)

        active = data.get("active_coercion", {})
        if isinstance(active, dict):
            enabled = active.get("enabled", False)
            rules = active.get("rules", [])
            if isinstance(enabled, bool):
                self.active_coercion["enabled"] = enabled
            if isinstance(rules, list):
                self.active_coercion["rules"] = rules

        dependency = data.get("dependency_tracker", {})
        if isinstance(dependency, dict):
            enabled = dependency.get("enabled", False)
            if isinstance(enabled, bool):
                self.dependency_tracker["enabled"] = enabled

        rules_content = self._read_rules_file()
        if rules_content is not None:
            try:
                extracted = extract_goal_enforcer_config_from_rules_md(rules_content)
                self.enforcement_config.update(extracted)
            except Exception as e:
                logger.error(f"Failed to parse rules: {e}")

    def save(self) -> None:
        data = self._read_settings()
        data["enforcement_config"] = self.enforcement_config
        data["active_coercion"] = {
            "enabled": bool(self.active_coercion.get("enabled", False)),
            "rules": self.active_coercion.get("rules", [])
            if isinstance(self.active_coercion.get("rules", []), list)
            else [],
        }
        data["dependency_tracker"] = {
            "enabled": bool(self.dependency_tracker.get("enabled", False)),
        }
        self._write_settings(data)

        try:
            rules_content = ""
            if os.path.exists(self._rules_path):
                with open(self._rules_path, "r") as f:
                    rules_content = f.read()
            new_content = upsert_goal_enforcer_block(rules_content, self.enforcement_config)
            with open(self._rules_path, "w") as f:
                f.write(new_content)
        except Exception as e:
            logger.error(f"Failed to save rules to {self._rules_path}: {e}")

    def _read_settings(self) -> dict[str, Any]:
        if not os.path.exists(self._settings_path):
            return {}
        try:
            with open(self._settings_path, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.error(f"Failed to load config from {self._settings_path}: {e}")
        return {}

    def _write_settings(self, data: dict[str, Any]) -> None:
        try:
            with open(self._settings_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save config to {self._settings_path}: {e}")

    def _read_rules_file(self) -> str | None:
        for path in (self._rules_path, self._legacy_rules_path):
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        return f.read()
                except Exception as e:
                    logger.error(f"Failed to load rules from {path}: {e}")
        return None
