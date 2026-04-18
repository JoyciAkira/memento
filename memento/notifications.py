"""Real-time MCP notifications — proactive alerts about relevant context changes."""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiosqlite

logger = logging.getLogger(__name__)


class NotificationManager:
    """Manages proactive notifications for the AI agent."""

    MAX_PENDING = 50
    NOTIFICATION_TTL_SECONDS = 600  # 10 minutes

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._pending: List[Dict[str, Any]] = []
        self._dismissed: set = set()
        self._config: Dict[str, Any] = {
            "enabled": True,
            "topics": ["memory_added", "consolidation", "kg_extraction", "relevance_alert"],
            "min_confidence": 0.5,
        }
        self._load_config()

    def _config_path(self) -> str:
        return os.path.join(os.path.dirname(self.db_path), "notifications.json")

    def _load_config(self):
        path = self._config_path()
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._config.update(data)
            except Exception:
                pass

    def _save_config(self):
        path = self._config_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump(self._config, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save notification config: {e}")

    def configure(self, enabled: bool = None, topics: List[str] = None, min_confidence: float = None) -> Dict[str, Any]:
        """Update notification configuration."""
        if enabled is not None:
            self._config["enabled"] = enabled
        if topics is not None:
            self._config["topics"] = topics
        if min_confidence is not None:
            self._config["min_confidence"] = min_confidence
        self._save_config()
        return self._config

    @property
    def enabled(self) -> bool:
        return self._config.get("enabled", True)

    async def notify(
        self,
        topic: str,
        title: str,
        body: str,
        confidence: float = 1.0,
        metadata: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Create a notification and add it to the pending queue."""
        if not self.enabled:
            return {"status": "disabled"}

        if topic not in self._config.get("topics", []):
            return {"status": "filtered", "topic": topic}

        if confidence < self._config.get("min_confidence", 0.0):
            return {"status": "low_confidence", "confidence": confidence}

        notification = {
            "id": f"notif_{int(time.time() * 1000)}",
            "topic": topic,
            "title": title,
            "body": body,
            "confidence": confidence,
            "metadata": metadata or {},
            "created_at": datetime.now().isoformat(),
            "timestamp": time.time(),
        }

        # Add to pending (evict oldest if over limit)
        self._pending.append(notification)
        while len(self._pending) > self.MAX_PENDING:
            self._pending.pop(0)

        logger.info(f"Notification [{topic}]: {title}")
        return {"status": "queued", "id": notification["id"]}

    def get_pending_notifications(self, include_dismissed: bool = False) -> List[Dict[str, Any]]:
        """Get all pending notifications."""
        now = time.time()
        valid = [
            n for n in self._pending
            if (now - n["timestamp"]) < self.NOTIFICATION_TTL_SECONDS
            and (include_dismissed or n["id"] not in self._dismissed)
        ]
        # Sort newest first
        valid.sort(key=lambda n: n["timestamp"], reverse=True)
        return valid

    def dismiss(self, notification_id: str) -> bool:
        """Dismiss a notification."""
        if notification_id in self._dismissed:
            return False
        self._dismissed.add(notification_id)
        return True

    def clear_all(self) -> int:
        """Clear all pending notifications. Returns count cleared."""
        count = len(self._pending)
        self._pending.clear()
        self._dismissed.clear()
        return count

    def notification_stats(self) -> Dict[str, Any]:
        """Get notification statistics."""
        return {
            "pending": len(self._pending),
            "dismissed": len(self._dismissed),
            "max_pending": self.MAX_PENDING,
            "ttl_seconds": self.NOTIFICATION_TTL_SECONDS,
            "enabled": self.enabled,
            "topics": self._config.get("topics", []),
            "config": self._config,
        }

    async def check_relevance_alert(self, text: str, top_results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Check if search results contain highly relevant memories and notify."""
        if not self.enabled or "relevance_alert" not in self._config.get("topics", []):
            return None

        # Check for very high-scoring results
        high_scoring = [r for r in top_results if r.get("score", 0) > 0.8]
        if not high_scoring:
            return None

        best = high_scoring[0]
        return await self.notify(
            topic="relevance_alert",
            title=f"Highly relevant memory found (score: {best.get('score', 0):.2f})",
            body=f"While searching, found a highly relevant memory:\n\n{best.get('memory', '')[:200]}",
            confidence=best.get("score", 0),
        )

    async def notify_memory_event(self, event: str, details: Dict[str, Any] = None) -> Dict[str, Any]:
        """Generic notification for memory events (add, delete, consolidate, etc.)."""
        topic = f"memory_{event}"
        return await self.notify(
            topic=topic,
            title=f"Memory {event}",
            body=json.dumps(details or {}, indent=2)[:500],
            confidence=1.0,
            metadata=details,
        )
