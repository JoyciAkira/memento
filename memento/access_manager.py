import logging

logger = logging.getLogger(__name__)

class MementoAccessManager:
    VALID_STATES = ["read-write", "read-only", "lockdown"]

    def __init__(self):
        self._state = "read-write"
        self.warnings_enabled = True
        self.auto_tasks_enabled = True

    @property
    def state(self) -> str:
        return self._state

    def set_state(self, new_state: str):
        if new_state not in self.VALID_STATES:
            raise ValueError(f"Invalid state: {new_state}. Valid states are: {self.VALID_STATES}")
        self._state = new_state
        logger.info(f"Access state changed to: {self._state}")

    def can_read(self) -> bool:
        return self._state in ["read-write", "read-only"]

    def can_write(self) -> bool:
        return self._state == "read-write"

    def toggle_superpowers(self, warnings: bool, auto_tasks: bool):
        self.warnings_enabled = warnings
        self.auto_tasks_enabled = auto_tasks
        logger.info(f"Superpowers toggled - Warnings: {warnings}, Auto Tasks: {auto_tasks}")
