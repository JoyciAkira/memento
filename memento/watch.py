"""Polling sync watcher with debounce for `memento sync --watch`.

The watcher fingerprints file metadata instead of using OS notifications:
it is deterministic, needs no extra dependency, and detects changes made by
any tool (editor, git checkout, formatter). A change is only synced after the
workspace has been quiet for ``debounce`` seconds. New memories are grounded
against the code index on a separate, slower cadence.
"""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from memento.code_grounding import MemoryGrounder
from memento.code_index import CodeIndex
from memento.kg_storage import resolve_kg_db_path
from memento.ledger import IGNORED_DIRS, FileLedger


class SyncWatcher:
    """Keep the ledger, code index, and memory grounding up to date."""

    def __init__(
        self,
        workspace_root: str,
        interval: float = 0.5,
        debounce: float = 0.8,
        compact_after: Optional[int] = None,
        ground: bool = True,
        ground_interval: float = 5.0,
    ):
        self.workspace_root = os.path.abspath(workspace_root)
        self.ledger = FileLedger(workspace_root, compact_after=compact_after)
        self.project_root = self.ledger.project_root
        self.interval = max(0.01, float(interval))
        self.debounce = max(0.0, float(debounce))
        self.ground = bool(ground)
        self.ground_interval = max(1.0, float(ground_interval))
        self.memory_db_path = os.path.join(
            self.ledger.memento_dir, "neurograph_memory.db"
        )
        self._last_memory_at = datetime.now().isoformat()
        self._index: Optional[CodeIndex] = None
        self._grounder: Optional[MemoryGrounder] = None
        self._kg: Any = None

    def _code_index(self) -> CodeIndex:
        if self._index is None:
            self._index = CodeIndex(self.project_root, ledger=self.ledger)
        return self._index

    def _grounder_instance(self) -> MemoryGrounder:
        if self._grounder is None:
            self._grounder = MemoryGrounder(self.project_root)
        return self._grounder

    def _knowledge_graph(self) -> Any:
        if self._kg is None:
            from memento.knowledge_graph import KnowledgeGraph

            self._kg = KnowledgeGraph(resolve_kg_db_path(self.memory_db_path))
        return self._kg

    def fingerprint(self) -> tuple:
        entries = []
        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS)
            for name in files:
                abs_path = os.path.join(root, name)
                if os.path.islink(abs_path):
                    continue
                try:
                    stat = os.stat(abs_path)
                except OSError:
                    continue
                rel = os.path.relpath(abs_path, self.project_root).replace(os.sep, "/")
                entries.append((rel, stat.st_mtime_ns, stat.st_size))
        entries.sort()
        return tuple(entries)

    def ground_new_memories(self, limit: int = 200) -> Dict[str, Any]:
        """Link memories created after the watcher started, newest last."""
        empty = {
            "memories_scanned": 0,
            "memories_linked": 0,
            "links": 0,
            "kg_triples": 0,
        }
        if not self.ground or not os.path.exists(self.memory_db_path):
            return empty
        try:
            conn = sqlite3.connect(self.memory_db_path, timeout=10)
            try:
                rows = conn.execute(
                    "SELECT id, text, created_at FROM memories "
                    "WHERE created_at > ? ORDER BY created_at LIMIT ?",
                    (self._last_memory_at, max(1, int(limit))),
                ).fetchall()
            finally:
                conn.close()
        except sqlite3.OperationalError:
            return empty
        if not rows:
            return empty

        self._last_memory_at = max((row[2] or self._last_memory_at) for row in rows)
        report = self._grounder_instance().link_all(
            [(row[0], row[1]) for row in rows],
            kg=self._knowledge_graph(),
            kg_limit=max(1, int(limit)),
        )
        report["newest_memory_at"] = self._last_memory_at
        return report

    def sync_once(
        self,
        scan: bool = True,
        compact: bool = False,
        index: bool = True,
    ) -> Dict[str, Any]:
        report = self.ledger.sync(scan=scan)
        if compact:
            report["compaction"] = self.ledger.compact()
        if index:
            report["index"] = self._code_index().update()
        report["trigger"] = "sync"
        if self.ground:
            report["grounding"] = self.ground_new_memories()
        return report

    def run(
        self,
        max_cycles: int = 0,
        on_report: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> int:
        """Watch until interrupted, or until ``max_cycles`` syncs happened."""
        baseline = self.fingerprint()
        cycles = 0
        last_ground = time.monotonic()
        while True:
            time.sleep(self.interval)

            if self.ground and time.monotonic() - last_ground >= self.ground_interval:
                grounding = self.ground_new_memories()
                last_ground = time.monotonic()
                if grounding.get("memories_scanned") and on_report is not None:
                    on_report({"trigger": "grounding", "grounding": grounding})

            current = self.fingerprint()
            if current == baseline:
                continue
            baseline = current

            while True:
                time.sleep(self.debounce)
                newer = self.fingerprint()
                if newer == baseline:
                    break
                baseline = newer

            report = self.sync_once()
            baseline = self.fingerprint()
            last_ground = time.monotonic()
            cycles += 1
            if on_report is not None:
                on_report(report)
            if max_cycles and cycles >= max_cycles:
                return cycles
