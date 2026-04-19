import json
import os
import tempfile
import pytest
from unittest.mock import MagicMock

from memento.active_coercion import normalize_hard_rules, check_text_against_rules, HardRule


class TestActiveCoercionHook:
    def test_blocks_commit_with_violation(self, tmp_workspace):
        from memento.active_coercion_hook import run_pre_commit

        settings_dir = os.path.join(os.path.dirname(tmp_workspace), ".memento")
        os.makedirs(settings_dir, exist_ok=True)
        settings_path = os.path.join(settings_dir, "settings.json")
        with open(settings_path, "w") as f:
            json.dump({"active_coercion": {"enabled": True, "rules": [
                {"id": "test_no_print", "path_globs": ["*.py"], "kind": "regex",
                 "regex": "\\bprint\\(", "message": "No print()", "severity": "block"}
            ]}}, f)

        with tempfile.TemporaryDirectory() as repo:
            os.makedirs(os.path.join(repo, ".memento"))
            settings_repo_path = os.path.join(repo, ".memento", "settings.json")
            with open(settings_repo_path, "w") as f:
                json.dump({"active_coercion": {"enabled": True, "rules": [
                    {"id": "test_no_print", "path_globs": ["*.py"], "kind": "regex",
                     "regex": "\\bprint\\(", "message": "No print()", "severity": "block"}
                ]}}, f)

            os.system(f"cd {repo} && git init && git add . && git commit -m 'init'")

            bad_file = os.path.join(repo, "bad.py")
            with open(bad_file, "w") as f:
                f.write('print("hello")\n')

            os.system(f"cd {repo} && git add bad.py")

            exit_code = run_pre_commit(repo)
            assert exit_code == 1

    def test_allows_clean_commit(self, tmp_workspace):
        from memento.active_coercion_hook import run_pre_commit

        with tempfile.TemporaryDirectory() as repo:
            os.makedirs(os.path.join(repo, ".memento"))
            settings_repo_path = os.path.join(repo, ".memento", "settings.json")
            with open(settings_repo_path, "w") as f:
                json.dump({"active_coercion": {"enabled": True, "rules": [
                    {"id": "test_no_print", "path_globs": ["*.py"], "kind": "regex",
                     "regex": "\\bprint\\(", "message": "No print()", "severity": "block"}
                ]}}, f)

            os.system(f"cd {repo} && git init && git add . && git commit -m 'init'")

            clean_file = os.path.join(repo, "clean.py")
            with open(clean_file, "w") as f:
                f.write('import logging\nlogger.info("hello")\n')

            os.system(f"cd {repo} && git add clean.py")

            exit_code = run_pre_commit(repo)
            assert exit_code == 0

    def test_rejects_path_traversal(self, tmp_workspace):
        from memento.active_coercion_hook import run_pre_commit

        with tempfile.TemporaryDirectory() as repo:
            os.makedirs(os.path.join(repo, ".memento"))
            settings_repo_path = os.path.join(repo, ".memento", "settings.json")
            with open(settings_repo_path, "w") as f:
                json.dump({"active_coercion": {"enabled": True, "rules": [
                    {"id": "test_no_print", "path_globs": ["*.py"], "kind": "regex",
                     "regex": "\\bprint\\(", "message": "No print()", "severity": "block"}
                ]}}, f)

            os.system(f"cd {repo} && git init && git add . && git commit -m 'init'")

            exit_code = run_pre_commit(repo)
            assert exit_code == 0
