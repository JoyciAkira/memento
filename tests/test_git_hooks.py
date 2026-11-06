import os
import shlex
import subprocess
import sys


def _repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def test_install_hook_includes_ledger_and_status(tmp_path):
    from memento.git_hooks import hook_status, install_pre_commit_hook

    root = _repo(tmp_path)
    path = install_pre_commit_hook(str(root))

    assert os.path.exists(path)
    assert os.access(path, os.X_OK)
    content = open(path, "r", encoding="utf-8").read()
    assert "memento.active_coercion_hook" in content
    assert "memento.ledger_hook" in content
    assert shlex.quote(sys.executable) in content

    status = hook_status(str(root))
    assert status["installed"] is True
    assert status["coercion"] is True
    assert status["ledger"] is True


def test_ledger_hook_syncs_repository(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    (root / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    monkeypatch.chdir(root)
    monkeypatch.setenv("MEMENTO_LEDGER_QUIET", "1")

    from memento.ledger_hook import main

    assert main() == 0

    ledger_dir = root / ".memento" / "ledger"
    assert (ledger_dir / "events.jsonl").exists()
    assert (ledger_dir / ".git").exists()
    assert (root / ".memento" / "code_index.sqlite").exists()


def test_ledger_hook_is_noop_outside_git(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from memento.ledger_hook import main

    assert main() == 0
    assert not (tmp_path / ".memento").exists()
