import json
import os
import sqlite3
import subprocess

from memento.ledger import FileLedger


def _write(project, rel: str, text: str) -> str:
    path = os.path.join(str(project), rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _remove_cache(ledger: FileLedger) -> None:
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(ledger.cache_path + suffix)
        except FileNotFoundError:
            pass


def test_sync_records_events_and_builds_cache(tmp_path):
    _write(tmp_path, "a.py", "print('a')")
    _write(tmp_path, "src/b.py", "print('b')")

    ledger = FileLedger(str(tmp_path))
    report = ledger.sync()

    assert report["added"] == 2
    assert report["events_appended"] == 2
    assert report["cache_files"] == 2
    assert report["git_backed"] is True

    events = ledger.read_events()
    assert [event["path"] for event in events] == ["a.py", "src/b.py"]
    assert all(event["event"] == "upsert" for event in events)

    conn = sqlite3.connect(ledger.cache_path)
    paths = {row[0] for row in conn.execute("SELECT path FROM files")}
    conn.close()
    assert paths == {"a.py", "src/b.py"}

    log = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=ledger.ledger_dir,
        capture_output=True,
        text=True,
    )
    assert log.returncode == 0
    assert len(log.stdout.strip().splitlines()) == 1


def test_sync_appends_only_diffs_and_handles_deletes(tmp_path):
    _write(tmp_path, "a.py", "print('a')")
    b_path = _write(tmp_path, "b.py", "print('b')")

    ledger = FileLedger(str(tmp_path))
    ledger.sync()

    _write(tmp_path, "a.py", "print('changed')")
    os.remove(b_path)
    _write(tmp_path, "c.py", "print('c')")

    report = ledger.sync()

    assert (report["added"], report["modified"], report["deleted"]) == (1, 1, 1)
    assert report["events_appended"] == 3
    assert report["cache_files"] == 2
    assert set(ledger.cache_state()) == {"a.py", "c.py"}

    deletes = [event for event in ledger.read_events() if event["event"] == "delete"]
    assert len(deletes) == 1
    assert deletes[0]["path"] == "b.py"


def test_replay_only_rebuilds_cache_without_scanning(tmp_path):
    _write(tmp_path, "a.py", "a")
    ledger = FileLedger(str(tmp_path))
    ledger.sync()

    _remove_cache(ledger)
    _write(tmp_path, "later.py", "later")
    before = ledger.read_events()

    report = ledger.sync(scan=False)

    assert report["scanned"] == 0
    assert report["events_appended"] == 0
    assert report["cache_files"] == 1
    assert "later.py" not in ledger.cache_state()
    assert ledger.read_events() == before


def test_sync_is_idempotent(tmp_path):
    _write(tmp_path, "a.py", "a")
    ledger = FileLedger(str(tmp_path))

    first = ledger.sync()
    second = ledger.sync()

    assert first["events_appended"] == 1
    assert second["events_appended"] == 0
    assert second["cache_files"] == 1
    assert len(ledger.read_events()) == 1

    log = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=ledger.ledger_dir,
        capture_output=True,
        text=True,
    )
    assert len(log.stdout.strip().splitlines()) == 1


def test_compaction_folds_events_into_snapshot(tmp_path):
    _write(tmp_path, "a.py", "a")
    _write(tmp_path, "b.py", "b")
    ledger = FileLedger(str(tmp_path))
    ledger.sync()

    result = ledger.compact()

    assert result["compacted"] is True
    assert result["snapshot_files"] == 2
    assert result["events_removed"] == 2
    assert os.path.exists(ledger.snapshot_path)
    assert ledger.read_events() == []
    assert ledger.read_snapshot()["seq"] == 2

    _remove_cache(ledger)
    report = ledger.sync(scan=False)
    assert report["cache_files"] == 2
    assert report["events_total"] == 0
    assert report["snapshot_files"] == 2

    _write(tmp_path, "c.py", "c")
    ledger.sync()
    events = ledger.read_events()
    assert len(events) == 1
    assert events[0]["seq"] == 3
    assert set(ledger.cache_state()) == {"a.py", "b.py", "c.py"}


def test_sync_auto_compacts_at_threshold(tmp_path):
    _write(tmp_path, "a.py", "a")
    _write(tmp_path, "b.py", "b")
    ledger = FileLedger(str(tmp_path), compact_after=2)

    report = ledger.sync()

    assert report["compacted"] is True
    assert report["events_total"] == 0
    assert report["snapshot_files"] == 2
    assert ledger.read_events() == []


def test_compaction_without_events_is_noop(tmp_path):
    _write(tmp_path, "a.py", "a")
    ledger = FileLedger(str(tmp_path))
    ledger.sync()
    ledger.compact()

    second = ledger.compact()

    assert second["compacted"] is False
    assert second["events_removed"] == 0


def test_cli_sync_parser_and_handler(tmp_path, monkeypatch, capsys):
    from memento.cli import _build_parser, _handle_sync

    args = _build_parser().parse_args(["sync", "--replay-only", "--json"])
    assert args.command == "sync"
    assert args.replay_only is True
    assert args.json is True

    _write(tmp_path, "a.py", "a")
    FileLedger(str(tmp_path)).sync()
    monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))

    _handle_sync(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["scanned"] == 0
    assert payload["cache_files"] == 1
