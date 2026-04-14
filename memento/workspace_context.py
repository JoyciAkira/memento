import os
import json
import logging
from typing import Dict
from memento.provider import NeuroGraphProvider
from memento.cognitive_engine import CognitiveEngine
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
        
        self.enforcement_config = {
            "level1": False,
            "level2": False,
            "level3": False,
        }
        self.load_enforcement_config()
        self.daemon = None

    def toggle_daemon(self, enabled: bool, callback) -> bool:
        if enabled:
            if not self.daemon or not self.daemon.is_running:
                from memento.daemon import PreCognitiveDaemon
                self.daemon = PreCognitiveDaemon(workspace_path=self.workspace_root, callback=callback, debounce_seconds=5.0)
                self.daemon.start()
            return True
        else:
            if self.daemon and self.daemon.is_running:
                self.daemon.stop()
            return False

    def load_enforcement_config(self):
        settings_path = os.path.join(self.memento_dir, "settings.json")
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r") as f:
                    data = json.load(f)
                    config = data.get("enforcement_config", {})
                    self.enforcement_config.update(config)
            except Exception as e:
                logger.error(f"Failed to load config from {settings_path}: {e}")

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
        settings_path = os.path.join(self.memento_dir, "settings.json")
        try:
            data = {}
            if os.path.exists(settings_path):
                with open(settings_path, "r") as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        pass
            data["enforcement_config"] = self.enforcement_config
            with open(settings_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save config to {settings_path}: {e}")

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

_contexts: Dict[str, WorkspaceContext] = {}

def get_workspace_context(workspace_root: str) -> WorkspaceContext:
    if not workspace_root:
        workspace_root = os.getcwd()
    abs_root = os.path.abspath(workspace_root)
    if abs_root not in _contexts:
        _contexts[abs_root] = WorkspaceContext(abs_root)
    return _contexts[abs_root]
