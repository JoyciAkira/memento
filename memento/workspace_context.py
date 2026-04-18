import os
import json
import logging
from typing import Any, Dict
from memento.provider import NeuroGraphProvider
from memento.cognitive_engine import CognitiveEngine
from memento.access_manager import MementoAccessManager
from memento.enforcement_rules import extract_goal_enforcer_config_from_rules_md, upsert_goal_enforcer_block

logger = logging.getLogger("memento-workspace")

class WorkspaceContext:
    def __init__(self, workspace_root: str):
        self.workspace_root = os.path.abspath(workspace_root)
        
        # Ensure .memento directory exists
        self.memento_dir = os.path.join(self.workspace_root, ".memento")
        os.makedirs(self.memento_dir, exist_ok=True)
        
        self.db_path = os.path.join(self.memento_dir, "neurograph_memory.db")
        self.provider = NeuroGraphProvider(db_path=self.db_path)
        self.cognitive_engine = CognitiveEngine(self.provider)
        settings_path = os.path.join(self.memento_dir, "settings.json")
        self.access_manager = MementoAccessManager(state_path=settings_path)
        
        self.enforcement_config = {
            "level1": False,
            "level2": False,
            "level3": False,
        }
        self.active_coercion = {
            "enabled": False,
            "rules": [],
        }
        self.dependency_tracker = {
            "enabled": False,
        }
        self.load_enforcement_config()
        self.daemon = None
        self.consolidation_scheduler = None
        self.kg_extraction_scheduler = None
        self.relevance_tracker = None
        self.predictive_cache = None
        self.notification_manager = None

    def _read_settings_json(self) -> dict[str, Any]:
        settings_path = os.path.join(self.memento_dir, "settings.json")
        if not os.path.exists(settings_path):
            return {}
        try:
            with open(settings_path, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.error(f"Failed to load config from {settings_path}: {e}")
        return {}

    def _write_settings_json(self, data: dict[str, Any]) -> None:
        settings_path = os.path.join(self.memento_dir, "settings.json")
        try:
            with open(settings_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save config to {settings_path}: {e}")

    def toggle_daemon(self, enabled: bool, callback) -> bool:
        if enabled:
            if not self.daemon or not self.daemon.is_running:
                from memento.daemon import PreCognitiveDaemon

                async def retrieval_callback(filepath: str):
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()
                        await self.provider.search_vnext_bundle(
                            query=content[:500],
                            user_id="default",
                            limit=5,
                            trace=True,
                        )
                    except Exception:
                        pass

                self.daemon = PreCognitiveDaemon(
                    workspace_path=self.workspace_root,
                    callback=callback,
                    debounce_seconds=5.0,
                    retrieval_pipeline=retrieval_callback,
                )
                self.daemon.start()
            return True
        else:
            if self.daemon and self.daemon.is_running:
                self.daemon.stop()
            return False

    def load_enforcement_config(self):
        data = self._read_settings_json()
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

        rules_path = os.path.join(self.workspace_root, ".memento.rules.md")
        if os.path.exists(rules_path):
            try:
                with open(rules_path, "r") as f:
                    rules_content = f.read()
                extracted = extract_goal_enforcer_config_from_rules_md(rules_content)
                self.enforcement_config.update(extracted)
            except Exception as e:
                logger.error(f"Failed to load rules from {rules_path}: {e}")
        else:
            legacy_rules_path = os.path.join(self.memento_dir, "memento.rules.md")
            if os.path.exists(legacy_rules_path):
                try:
                    with open(legacy_rules_path, "r") as f:
                        rules_content = f.read()
                    extracted = extract_goal_enforcer_config_from_rules_md(rules_content)
                    self.enforcement_config.update(extracted)
                except Exception as e:
                    logger.error(f"Failed to load legacy rules from {legacy_rules_path}: {e}")

    def save_enforcement_config(self):
        data = self._read_settings_json()
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
        self._write_settings_json(data)

        rules_path = os.path.join(self.workspace_root, ".memento.rules.md")
        try:
            rules_content = ""
            if os.path.exists(rules_path):
                with open(rules_path, "r") as f:
                    rules_content = f.read()
            new_content = upsert_goal_enforcer_block(rules_content, self.enforcement_config)
            with open(rules_path, "w") as f:
                f.write(new_content)
        except Exception as e:
            logger.error(f"Failed to save rules to {rules_path}: {e}")

    def save_active_coercion_config(self) -> None:
        data = self._read_settings_json()
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
        self._write_settings_json(data)

    def save_dependency_tracker_config(self) -> None:
        data = self._read_settings_json()
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
        self._write_settings_json(data)

_contexts: Dict[str, WorkspaceContext] = {}

def get_workspace_context(workspace_root: str) -> WorkspaceContext:
    if not workspace_root:
        workspace_root = os.getcwd()
    abs_root = os.path.abspath(workspace_root)
    if abs_root not in _contexts:
        _contexts[abs_root] = WorkspaceContext(abs_root)
    return _contexts[abs_root]
