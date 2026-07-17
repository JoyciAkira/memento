"""Tests for enterprise DB corruption detection + self-heal (memento.db_guard)."""
import os
import sqlite3

import pytest

from memento.db_guard import is_corrupted, backup_corrupted, ensure_healthy_db


def _make_valid_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t(v) VALUES ('hello')")
    conn.commit()
    conn.close()


def test_missing_file_is_not_corrupted():
    assert is_corrupted("/tmp/does-not-exist-xyz.db") is False


def test_valid_db_not_corrupted(tmp_path):
    p = str(tmp_path / "ok.db")
    _make_valid_db(p)
    assert is_corrupted(p) is False


def test_garbage_file_is_corrupted(tmp_path):
    p = str(tmp_path / "bad.db")
    with open(p, "wb") as f:
        f.write(b"\xef\xbf\xbd" * 500)  # U+FFFD repeated — classic text-decode corruption
    assert is_corrupted(p) is True


def test_ensure_healthy_backs_up_and_clears_corrupted(tmp_path):
    p = str(tmp_path / "bad.db")
    with open(p, "wb") as f:
        f.write(b"\xef\xbf\xbd" * 500)
    assert os.path.exists(p)
    ok = ensure_healthy_db(p, label="memory")
    assert ok is True
    # Live corrupted file removed; a timestamped backup preserved.
    assert not os.path.exists(p)
    backups = [f for f in os.listdir(tmp_path) if "corrupted-" in f]
    assert len(backups) == 1
    # Next connect recreates a fresh, valid store.
    _make_valid_db(p)
    assert is_corrupted(p) is False


def test_ensure_healthy_leaves_valid_db_untouched(tmp_path):
    p = str(tmp_path / "ok.db")
    _make_valid_db(p)
    ok = ensure_healthy_db(p, label="memory")
    assert ok is True
    assert os.path.exists(p)
    assert is_corrupted(p) is False
    # No backup created for a healthy db.
    assert not any("corrupted-" in f for f in os.listdir(tmp_path))


def test_backup_corrupted_moves_wal_and_shm(tmp_path):
    p = str(tmp_path / "bad.db")
    with open(p, "wb") as f:
        f.write(b"garbage")
    with open(p + "-wal", "wb") as f:
        f.write(b"wal")
    with open(p + "-shm", "wb") as f:
        f.write(b"shm")
    backup = backup_corrupted(p)
    assert backup is not None
    assert os.path.exists(backup)
    assert os.path.exists(backup + "-wal")
    assert os.path.exists(backup + "-shm")
    assert not os.path.exists(p)
