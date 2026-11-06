import threading
import time


def test_sync_watcher_detects_and_syncs(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")

    from memento.watch import SyncWatcher

    watcher = SyncWatcher(str(tmp_path), interval=0.01, debounce=0.01)
    watcher.sync_once()
    reports = []
    thread = threading.Thread(
        target=lambda: watcher.run(max_cycles=1, on_report=reports.append)
    )
    thread.start()
    time.sleep(0.1)
    (tmp_path / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    thread.join(timeout=10)

    assert not thread.is_alive()
    assert reports
    assert reports[0]["added"] == 1
    assert reports[0]["index"]["indexed"] == 1
    assert (tmp_path / ".memento" / "ledger" / "events.jsonl").exists()
    assert (tmp_path / ".memento" / "code_index.sqlite").exists()


def test_watcher_grounds_new_memories(tmp_path):
    import sqlite3
    from datetime import datetime

    (tmp_path / ".git").mkdir()
    (tmp_path / "a.py").write_text("def helper(x):\n    return x\n", encoding="utf-8")

    from memento.watch import SyncWatcher

    watcher = SyncWatcher(str(tmp_path), interval=0.01, debounce=0.01)
    watcher.sync_once()

    db_path = tmp_path / ".memento" / "neurograph_memory.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE memories (id TEXT PRIMARY KEY, text TEXT, created_at TEXT)"
    )
    conn.execute(
        "INSERT INTO memories VALUES (?, ?, ?)",
        ("m1", "helper is used here", datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    report = watcher.ground_new_memories()

    assert report["memories_linked"] == 1
    from memento.code_grounding import MemoryGrounder

    links = MemoryGrounder(str(tmp_path)).links_for_memories(["m1"])["m1"]
    assert any(link["symbol"] == "helper" for link in links)


def test_sync_watch_flags_are_wired():
    from memento.cli import _build_parser

    args = _build_parser().parse_args(
        [
            "sync",
            "--watch",
            "--interval",
            "0.1",
            "--debounce",
            "0.2",
            "--max-cycles",
            "1",
            "--quiet",
            "--no-ground",
            "--ground-interval",
            "2.5",
        ]
    )
    assert args.watch is True
    assert args.interval == 0.1
    assert args.debounce == 0.2
    assert args.max_cycles == 1
    assert args.quiet is True
    assert args.no_ground is True
    assert args.ground_interval == 2.5


def test_graph_and_ground_commands_are_wired():
    from memento.cli import _build_parser

    graph = _build_parser().parse_args(["graph", "--symbol", "helper", "--json"])
    assert graph.command == "graph"
    assert graph.symbol == "helper"
    assert graph.json is True

    ground = _build_parser().parse_args(["ground", "--rebuild", "--limit", "10"])
    assert ground.command == "ground"
    assert ground.rebuild is True
    assert ground.limit == 10
