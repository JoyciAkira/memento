import json
import os
import shutil
import subprocess
import sys

from memento.active_coercion import check_text_against_rules, normalize_hard_rules


def test_rule_engine_match_and_override(tmp_path):
    workspace_root = str(tmp_path)
    rules = normalize_hard_rules(
        [
            {
                "id": "no_print_backend",
                "enabled": True,
                "path_globs": ["backend/**/*.py"],
                "regex": r"\bprint\(",
                "message": "Use logger, not print",
                "severity": "block",
                "override_token": "memento-override",
            }
        ]
    )

    file_path = os.path.join(workspace_root, "backend", "a.py")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    v1 = check_text_against_rules(
        workspace_root=workspace_root,
        rules=rules,
        file_path=file_path,
        content="print('x')\n",
    )
    assert [v.rule_id for v in v1] == ["no_print_backend"]

    v2 = check_text_against_rules(
        workspace_root=workspace_root,
        rules=rules,
        file_path=file_path,
        content="print('x')\n# memento-override\n",
    )
    assert v2 == []


def test_pre_commit_hook_logic_blocks_commit_and_allows_override(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    subprocess.check_call(["git", "init"], cwd=repo_root)
    subprocess.check_call(["git", "config", "user.email", "test@example.com"], cwd=repo_root)
    subprocess.check_call(["git", "config", "user.name", "Test"], cwd=repo_root)

    memento_dir = repo_root / "memento"
    memento_dir.mkdir()
    (memento_dir / "__init__.py").write_text("", encoding="utf-8")

    source_pkg = os.path.join(os.path.dirname(__file__), "..", "memento")
    shutil.copyfile(
        os.path.join(source_pkg, "active_coercion.py"),
        memento_dir / "active_coercion.py",
    )
    shutil.copyfile(
        os.path.join(source_pkg, "active_coercion_hook.py"),
        memento_dir / "active_coercion_hook.py",
    )

    settings_dir = repo_root / ".memento"
    settings_dir.mkdir()
    (settings_dir / "settings.json").write_text(
        json.dumps(
            {
                "active_coercion": {
                    "enabled": True,
                    "rules": [
                        {
                            "id": "no_print_backend",
                            "path_globs": ["backend/**/*.py"],
                            "regex": r"\bprint\(",
                            "message": "Use logger, not print",
                            "severity": "block",
                            "override_token": "memento-override",
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    backend_dir = repo_root / "backend"
    backend_dir.mkdir()
    target_file = backend_dir / "a.py"
    target_file.write_text("print('x')\n", encoding="utf-8")

    subprocess.check_call(["git", "add", "backend/a.py"], cwd=repo_root)

    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root)
    blocked = subprocess.run(
        [sys.executable, "-m", "memento.active_coercion_hook"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert blocked.returncode == 1
    assert "BLOCKED commit" in blocked.stderr
    assert "no_print_backend" in blocked.stderr

    target_file.write_text("print('x')\n# memento-override\n", encoding="utf-8")
    subprocess.check_call(["git", "add", "backend/a.py"], cwd=repo_root)

    allowed = subprocess.run(
        [sys.executable, "-m", "memento.active_coercion_hook"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert allowed.returncode == 0
