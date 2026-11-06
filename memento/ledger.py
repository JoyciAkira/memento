"""Git-backed shadow ledger for workspace file events.

The ledger is an append-only JSONL stream under ``.memento/ledger`` kept in its
own git repository, so the user's repository history is never touched and the
usual ``.memento/`` git-ignore does not matter. The SQLite database at
``.memento/ledger_cache.sqlite`` is a disposable cache rebuilt by replaying the
ledger: it can be deleted at any time and ``memento sync --replay-only``
restores it without rescanning the workspace.

Events are periodically folded into ``snapshot.json``: older events are removed
from ``events.jsonl`` and replay starts from the snapshot instead, keeping the
replay cost bounded.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional

EVENTS_FILENAME = "events.jsonl"
SNAPSHOT_FILENAME = "snapshot.json"
LEDGER_DIRNAME = "ledger"
CACHE_FILENAME = "ledger_cache.sqlite"
DEFAULT_COMPACT_AFTER = 2000

IGNORED_DIRS = {
    ".git",
    ".memento",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "dist",
    "build",
    ".next",
}
_IGNORED_DIRS = IGNORED_DIRS


class LedgerError(RuntimeError):
    """Raised when the ledger contains data that cannot be replayed."""


def find_project_root(current_dir: str) -> str:
    """Locate the workspace root without importing the MCP tool package."""
    markers = [".git", "package.json", "pyproject.toml", "cargo.toml"]
    directory = os.path.abspath(current_dir)
    original = directory
    while True:
        for marker in markers:
            if os.path.exists(os.path.join(directory, marker)):
                return directory
        parent = os.path.dirname(directory)
        if parent == directory:
            return original
        directory = parent


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FileLedger:
    """Append-only file event ledger with snapshots and a rebuildable cache."""

    def __init__(self, workspace_root: str, compact_after: Optional[int] = None):
        self.workspace_root = os.path.abspath(workspace_root)
        self.project_root = find_project_root(self.workspace_root)
        self.memento_dir = os.path.join(self.project_root, ".memento")
        self.ledger_dir = os.path.join(self.memento_dir, LEDGER_DIRNAME)
        self.events_path = os.path.join(self.ledger_dir, EVENTS_FILENAME)
        self.snapshot_path = os.path.join(self.ledger_dir, SNAPSHOT_FILENAME)
        self.cache_path = os.path.join(self.memento_dir, CACHE_FILENAME)
        if compact_after is None:
            try:
                compact_after = int(
                    os.environ.get(
                        "MEMENTO_LEDGER_COMPACT_AFTER", DEFAULT_COMPACT_AFTER
                    )
                )
            except ValueError:
                compact_after = DEFAULT_COMPACT_AFTER
        self.compact_after = compact_after

    # -- git helpers -----------------------------------------------------

    @staticmethod
    def _run_git(args: List[str], cwd: str) -> Optional[subprocess.CompletedProcess]:
        if not shutil.which("git"):
            return None
        try:
            return subprocess.run(
                ["git", *args],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return None

    def _head_info(self) -> tuple[Optional[str], Optional[str]]:
        head = self._run_git(["rev-parse", "HEAD"], self.project_root)
        branch = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"], self.project_root)
        commit = head.stdout.strip() if head and head.returncode == 0 else None
        name = branch.stdout.strip() if branch and branch.returncode == 0 else None
        return commit or None, name or None

    def _ensure_ledger_repo(self) -> bool:
        os.makedirs(self.ledger_dir, exist_ok=True)
        if os.path.exists(os.path.join(self.ledger_dir, ".git")):
            return True
        init = self._run_git(["init", "-q"], self.ledger_dir)
        return init is not None and init.returncode == 0

    def _commit_ledger(self, event_count: int, message: Optional[str] = None) -> bool:
        if not self._ensure_ledger_repo():
            return False
        paths = [EVENTS_FILENAME]
        if os.path.exists(self.snapshot_path):
            paths.append(SNAPSHOT_FILENAME)
        add = self._run_git(["add", "--", *paths], self.ledger_dir)
        if add is None or add.returncode != 0:
            return False
        staged = self._run_git(["diff", "--cached", "--quiet"], self.ledger_dir)
        if staged is not None and staged.returncode == 0:
            return False  # nothing new to commit
        commit = self._run_git(
            [
                "-c",
                "user.name=Memento",
                "-c",
                "user.email=memento@localhost",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "-q",
                "-m",
                message or f"sync: {event_count} file event(s)",
            ],
            self.ledger_dir,
        )
        return commit is not None and commit.returncode == 0

    # -- workspace scan --------------------------------------------------

    def _walk_files(self) -> List[str]:
        found: List[str] = []
        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = sorted(d for d in dirs if d not in _IGNORED_DIRS)
            for name in files:
                abs_path = os.path.join(root, name)
                if os.path.islink(abs_path):
                    continue
                found.append(os.path.relpath(abs_path, self.project_root))
        return found

    def list_files(self) -> List[str]:
        """Return workspace-relative paths, preferring git's ignore rules."""
        listing = self._run_git(
            ["ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            self.project_root,
        )
        candidates = (
            listing.stdout.split("\0")
            if listing is not None and listing.returncode == 0
            else None
        )
        if candidates is None:
            candidates = self._walk_files()

        result = []
        seen = set()
        for rel in candidates:
            rel = rel.strip().replace(os.sep, "/")
            if not rel or rel in seen:
                continue
            if rel.split("/")[0] in _IGNORED_DIRS:
                continue
            abs_path = os.path.join(self.project_root, rel)
            if not os.path.isfile(abs_path) or os.path.islink(abs_path):
                continue
            seen.add(rel)
            result.append(rel)
        return sorted(result)

    def scan(self) -> Dict[str, Dict[str, Any]]:
        state: Dict[str, Dict[str, Any]] = {}
        for rel in self.list_files():
            abs_path = os.path.join(self.project_root, rel)
            try:
                stat = os.stat(abs_path)
                state[rel] = {"sha256": _sha256(abs_path), "size": stat.st_size}
            except OSError:
                continue
        return state

    # -- ledger I/O ------------------------------------------------------

    def read_events(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.events_path):
            return []
        events: List[Dict[str, Any]] = []
        with open(self.events_path, "r", encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise LedgerError(f"invalid JSON at line {lineno}: {exc}") from exc
                if event.get("event") not in ("upsert", "delete") or not event.get(
                    "path"
                ):
                    raise LedgerError(f"invalid event at line {lineno}")
                if event["event"] == "upsert" and not event.get("sha256"):
                    raise LedgerError(f"upsert without sha256 at line {lineno}")
                events.append(event)
        return events

    def read_snapshot(self) -> Dict[str, Any]:
        if not os.path.exists(self.snapshot_path):
            return {"version": 1, "seq": 0, "files": {}}
        try:
            with open(self.snapshot_path, "r", encoding="utf-8") as handle:
                snapshot = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise LedgerError(f"invalid snapshot: {exc}") from exc
        if not isinstance(snapshot, dict) or not isinstance(
            snapshot.get("files"), dict
        ):
            raise LedgerError("invalid snapshot: missing files map")
        snapshot.setdefault("version", 1)
        snapshot.setdefault("seq", 0)
        return snapshot

    def _current_seq(self) -> int:
        return int(self.read_snapshot().get("seq") or 0) + len(self.read_events())

    def append(self, events: List[Dict[str, Any]]) -> int:
        if not events:
            return 0
        os.makedirs(self.ledger_dir, exist_ok=True)
        seq = self._current_seq()
        timestamp = datetime.now().isoformat()
        with open(self.events_path, "a", encoding="utf-8") as handle:
            for event in events:
                seq += 1
                payload = {"seq": seq, "ts": timestamp, **event}
                handle.write(
                    json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
                )
            handle.flush()
            os.fsync(handle.fileno())
        self._commit_ledger(len(events))
        return len(events)

    # -- cache -----------------------------------------------------------

    def _connect_cache(self) -> sqlite3.Connection:
        os.makedirs(self.memento_dir, exist_ok=True)
        conn = sqlite3.connect(self.cache_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    @staticmethod
    def _ensure_schema(conn: sqlite3.Connection) -> None:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS files ("
            "path TEXT PRIMARY KEY, "
            "sha256 TEXT NOT NULL, "
            "size INTEGER NOT NULL, "
            "last_event TEXT NOT NULL, "
            "last_ts TEXT NOT NULL, "
            "commit_hash TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )

    @staticmethod
    def _upsert_file(
        conn: sqlite3.Connection,
        path: str,
        sha256: str,
        size: int,
        timestamp: str,
        commit: Optional[str],
    ) -> None:
        conn.execute(
            "INSERT INTO files "
            "(path, sha256, size, last_event, last_ts, commit_hash) "
            "VALUES (?, ?, ?, 'upsert', ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET "
            "sha256=excluded.sha256, size=excluded.size, "
            "last_event=excluded.last_event, last_ts=excluded.last_ts, "
            "commit_hash=excluded.commit_hash",
            (path, sha256, size, timestamp, commit),
        )

    def replay(self) -> Dict[str, int]:
        """Rebuild the SQLite cache from the snapshot plus pending events."""
        snapshot = self.read_snapshot()
        snapshot_seq = int(snapshot.get("seq") or 0)
        events = [
            event
            for event in self.read_events()
            if int(event.get("seq") or 0) > snapshot_seq
        ]
        snapshot_files = snapshot.get("files") or {}

        conn = self._connect_cache()
        try:
            self._ensure_schema(conn)
            with conn:
                conn.execute("DELETE FROM files")
                for path, info in snapshot_files.items():
                    self._upsert_file(
                        conn,
                        path,
                        str(info.get("sha256") or ""),
                        int(info.get("size") or 0),
                        str(snapshot.get("ts") or ""),
                        info.get("commit"),
                    )
                for event in events:
                    if event["event"] == "upsert":
                        self._upsert_file(
                            conn,
                            event["path"],
                            event["sha256"],
                            int(event.get("size") or 0),
                            event.get("ts", ""),
                            event.get("commit"),
                        )
                    else:
                        conn.execute(
                            "DELETE FROM files WHERE path = ?", (event["path"],)
                        )
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES('event_count', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(len(events)),),
                )
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES('rebuilt_at', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (datetime.now().isoformat(),),
                )
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES('head_commit', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(events[-1].get("commit") or "") if events else "",),
                )
            files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        finally:
            conn.close()
        return {
            "events": len(events),
            "snapshot_files": len(snapshot_files),
            "files": files,
        }

    def cache_state(self) -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(self.cache_path):
            return {}
        conn = sqlite3.connect(self.cache_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT path, sha256, size, commit_hash FROM files"
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
        finally:
            conn.close()
        return {
            row["path"]: {
                "sha256": row["sha256"],
                "size": row["size"],
                "commit": row["commit_hash"],
            }
            for row in rows
        }

    # -- compaction ------------------------------------------------------

    def compact(self) -> Dict[str, Any]:
        """Fold all pending events into a snapshot and truncate the event log."""
        events = self.read_events()
        if not events:
            return {
                "compacted": False,
                "reason": "no pending events",
                "snapshot_files": len(self.read_snapshot().get("files") or {}),
                "events_removed": 0,
            }

        self.replay()  # guarantee the cache reflects every event before snapshotting
        state = self.cache_state()
        previous = self.read_snapshot()
        seq = int(previous.get("seq") or 0) + len(events)
        timestamp = datetime.now().isoformat()
        files = {
            path: {
                "sha256": info["sha256"],
                "size": info["size"],
                "commit": info.get("commit"),
            }
            for path, info in state.items()
        }
        payload = {"version": 1, "seq": seq, "ts": timestamp, "files": files}

        os.makedirs(self.ledger_dir, exist_ok=True)
        tmp_path = self.snapshot_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, self.snapshot_path)

        with open(self.events_path, "w", encoding="utf-8"):
            pass

        committed = self._commit_ledger(
            len(files), message=f"compact: snapshot {len(files)} file(s) at seq {seq}"
        )
        return {
            "compacted": True,
            "snapshot_files": len(files),
            "snapshot_seq": seq,
            "events_removed": len(events),
            "git_committed": committed,
        }

    # -- sync ------------------------------------------------------------

    def sync(self, scan: bool = True) -> Dict[str, Any]:
        """Diff the workspace against the cache, append events, then rebuild."""
        added = modified = deleted = 0
        scanned = 0
        appended = 0

        if scan:
            if not os.path.exists(self.cache_path):
                self.replay()
            previous = self.cache_state()
            current = self.scan()
            scanned = len(current)
            commit, branch = self._head_info()

            events: List[Dict[str, Any]] = []
            for path, info in current.items():
                prev = previous.get(path)
                if prev is None:
                    added += 1
                elif prev["sha256"] != info["sha256"] or prev["size"] != info["size"]:
                    modified += 1
                else:
                    continue
                events.append(
                    {
                        "event": "upsert",
                        "path": path,
                        "sha256": info["sha256"],
                        "size": info["size"],
                        "commit": commit,
                        "branch": branch,
                    }
                )
            for path in sorted(set(previous) - set(current)):
                deleted += 1
                events.append(
                    {
                        "event": "delete",
                        "path": path,
                        "sha256": None,
                        "size": None,
                        "commit": commit,
                        "branch": branch,
                    }
                )
            appended = self.append(events)

        replayed = self.replay()
        compacted = None
        if self.compact_after > 0 and replayed["events"] >= self.compact_after:
            compacted = self.compact()
            replayed = self.replay()

        return {
            "scanned": scanned,
            "added": added,
            "modified": modified,
            "deleted": deleted,
            "events_appended": appended,
            "events_total": replayed["events"],
            "snapshot_files": replayed["snapshot_files"],
            "cache_files": replayed["files"],
            "compacted": compacted is not None,
            "ledger_dir": self.ledger_dir,
            "cache_path": self.cache_path,
            "git_backed": os.path.exists(os.path.join(self.ledger_dir, ".git")),
        }
