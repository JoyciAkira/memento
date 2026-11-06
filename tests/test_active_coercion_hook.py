import json
import os
import subprocess
import tempfile


def _git(repo: str, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(repo: str) -> None:
    _git(repo, "init")
    _git(repo, "config", "user.email", "tests@example.com")
    _git(repo, "config", "user.name", "Memento Tests")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")


class TestActiveCoercionHook:
    def test_blocks_commit_with_violation(self, tmp_workspace):
        from memento.active_coercion_hook import run_pre_commit

        settings_dir = os.path.join(os.path.dirname(tmp_workspace), ".memento")
        os.makedirs(settings_dir, exist_ok=True)
        settings_path = os.path.join(settings_dir, "settings.json")
        with open(settings_path, "w") as f:
            json.dump(
                {
                    "active_coercion": {
                        "enabled": True,
                        "rules": [
                            {
                                "id": "test_no_print",
                                "path_globs": ["*.py"],
                                "kind": "regex",
                                "regex": "\\bprint\\(",
                                "message": "No print()",
                                "severity": "block",
                            }
                        ],
                    }
                },
                f,
            )

        with tempfile.TemporaryDirectory() as repo:
            os.makedirs(os.path.join(repo, ".memento"))
            settings_repo_path = os.path.join(repo, ".memento", "settings.json")
            with open(settings_repo_path, "w") as f:
                json.dump(
                    {
                        "active_coercion": {
                            "enabled": True,
                            "rules": [
                                {
                                    "id": "test_no_print",
                                    "path_globs": ["*.py"],
                                    "kind": "regex",
                                    "regex": "\\bprint\\(",
                                    "message": "No print()",
                                    "severity": "block",
                                }
                            ],
                        }
                    },
                    f,
                )

            _init_repo(repo)

            bad_file = os.path.join(repo, "bad.py")
            with open(bad_file, "w") as f:
                f.write('print("hello")\n')

            _git(repo, "add", "bad.py")

            exit_code = run_pre_commit(repo)
            assert exit_code == 1

    def test_allows_clean_commit(self, tmp_workspace):
        from memento.active_coercion_hook import run_pre_commit

        with tempfile.TemporaryDirectory() as repo:
            os.makedirs(os.path.join(repo, ".memento"))
            settings_repo_path = os.path.join(repo, ".memento", "settings.json")
            with open(settings_repo_path, "w") as f:
                json.dump(
                    {
                        "active_coercion": {
                            "enabled": True,
                            "rules": [
                                {
                                    "id": "test_no_print",
                                    "path_globs": ["*.py"],
                                    "kind": "regex",
                                    "regex": "\\bprint\\(",
                                    "message": "No print()",
                                    "severity": "block",
                                }
                            ],
                        }
                    },
                    f,
                )

            _init_repo(repo)

            clean_file = os.path.join(repo, "clean.py")
            with open(clean_file, "w") as f:
                f.write('import logging\nlogger.info("hello")\n')

            _git(repo, "add", "clean.py")

            exit_code = run_pre_commit(repo)
            assert exit_code == 0

    def test_rejects_path_traversal(self, tmp_workspace):
        from memento.active_coercion_hook import run_pre_commit

        with tempfile.TemporaryDirectory() as repo:
            os.makedirs(os.path.join(repo, ".memento"))
            settings_repo_path = os.path.join(repo, ".memento", "settings.json")
            with open(settings_repo_path, "w") as f:
                json.dump(
                    {
                        "active_coercion": {
                            "enabled": True,
                            "rules": [
                                {
                                    "id": "test_no_print",
                                    "path_globs": ["*.py"],
                                    "kind": "regex",
                                    "regex": "\\bprint\\(",
                                    "message": "No print()",
                                    "severity": "block",
                                }
                            ],
                        }
                    },
                    f,
                )

            _init_repo(repo)

            exit_code = run_pre_commit(repo)
            assert exit_code == 0
