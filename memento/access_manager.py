import json
import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class MementoAccessManager:
    VALID_STATES = ["read-write", "read-only", "lockdown"]

    def __init__(self, state_path: Optional[str] = None):
        self._state_path = state_path
        self._state = "read-write"
        self.warnings_enabled = True
        self.auto_tasks_enabled = True
        self._lock = threading.Lock()
        if self._state_path:
            self._load_state()

    def _load_state(self) -> None:
        if not self._state_path or not os.path.exists(self._state_path):
            return
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
            access_data = data.get("access_manager", data)
            if isinstance(access_data, dict):
                if access_data.get("state") in self.VALID_STATES:
                    self._state = access_data["state"]
                if isinstance(access_data.get("warnings_enabled"), bool):
                    self.warnings_enabled = access_data["warnings_enabled"]
                if isinstance(access_data.get("auto_tasks_enabled"), bool):
                    self.auto_tasks_enabled = access_data["auto_tasks_enabled"]
        except Exception:
            logger.warning("Failed to load access manager state")

    def _save_state(self) -> None:
        if not self._state_path:
            return
        try:
            os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
            existing: dict = {}
            if os.path.exists(self._state_path):
                with open(self._state_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            if not isinstance(existing, dict):
                existing = {}
            existing["access_manager"] = {
                "state": self._state,
                "warnings_enabled": self.warnings_enabled,
                "auto_tasks_enabled": self.auto_tasks_enabled,
            }
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
        except Exception:
            logger.warning("Failed to save access manager state")

    @property
    def state(self) -> str:
        return self._state

    def set_state(self, new_state: str) -> None:
        if new_state not in self.VALID_STATES:
            raise ValueError(f"Invalid state: {new_state}. Valid states are: {self.VALID_STATES}")
        with self._lock:
            self._state = new_state
            logger.info(f"Access state changed to: {self._state}")
            self._save_state()

    def can_read(self) -> bool:
        return self._state in ["read-write", "read-only"]

    def can_write(self) -> bool:
        return self._state == "read-write"

    def toggle_superpowers(self, warnings: bool, auto_tasks: bool) -> None:
        with self._lock:
            self.warnings_enabled = warnings
            self.auto_tasks_enabled = auto_tasks
            logger.info(f"Superpowers toggled - Warnings: {warnings}, Auto Tasks: {auto_tasks}")
            self._save_state()
