import os
import logging
from typing import Dict
from memento.provider import NeuroGraphProvider
from memento.cognitive_engine import CognitiveEngine
from memento.access_manager import MementoAccessManager
from memento.config_store import WorkspaceConfigStore

logger = logging.getLogger("memento-workspace")

class WorkspaceContext:
    def __init__(self, workspace_root: str):
        self.workspace_root = os.path.abspath(workspace_root)
        self.memento_dir = os.path.join(self.workspace_root, ".memento")
        os.makedirs(self.memento_dir, exist_ok=True)

        self.db_path = os.path.join(self.memento_dir, "neurograph_memory.db")
        self.provider = NeuroGraphProvider(db_path=self.db_path)
        self.cognitive_engine = CognitiveEngine(self.provider, workspace_root=self.workspace_root)
        settings_path = os.path.join(self.memento_dir, "settings.json")
        self.access_manager = MementoAccessManager(state_path=settings_path)

        self.config = WorkspaceConfigStore(self.memento_dir, self.workspace_root)
        self.config.load()

        self.daemon = None
        self.consolidation_scheduler = None
        self.kg_extraction_scheduler = None
        self.relevance_tracker = None
        self.predictive_cache = None
        self.notification_manager = None

    @property
    def enforcement_config(self):
        return self.config.enforcement_config

    @enforcement_config.setter
    def enforcement_config(self, value):
        self.config.enforcement_config = value

    @property
    def active_coercion(self):
        return self.config.active_coercion

    @active_coercion.setter
    def active_coercion(self, value):
        self.config.active_coercion = value

    @property
    def dependency_tracker(self):
        return self.config.dependency_tracker

    @dependency_tracker.setter
    def dependency_tracker(self, value):
        self.config.dependency_tracker = value

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
        self.config.load()

    def save_enforcement_config(self):
        self.config.save()

    def save_active_coercion_config(self):
        self.config.save()

    def save_dependency_tracker_config(self):
        self.config.save()

_contexts: Dict[str, WorkspaceContext] = {}

def get_workspace_context(workspace_root: str) -> WorkspaceContext:
    if not workspace_root:
        workspace_root = os.getcwd()
    abs_root = os.path.abspath(workspace_root)
    if abs_root not in _contexts:
        _contexts[abs_root] = WorkspaceContext(abs_root)
    return _contexts[abs_root]
