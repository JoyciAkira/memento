import os
from pathlib import Path

import pytest

from memento.git_context import (
    build_auto_context,
    get_current_branch,
    get_recent_commits,
    get_staged_diff_stat,
    get_unstaged_diff_stat,
    is_git_repo,
)

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)


class TestIsGitRepo:
    def test_is_git_repo_true(self):
        assert is_git_repo(PROJECT_ROOT) is True

    def test_is_git_repo_false(self, tmp_path):
        assert is_git_repo(str(tmp_path)) is False


class TestGetCurrentBranch:
    def test_get_current_branch(self):
        result = get_current_branch(PROJECT_ROOT)
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0


class TestGetRecentCommits:
    def test_get_recent_commits(self):
        commits = get_recent_commits(PROJECT_ROOT, count=3)
        assert isinstance(commits, list)
        assert len(commits) <= 3
        for line in commits:
            assert isinstance(line, str)
            assert " " in line

    def test_get_recent_commits_default_count(self):
        commits = get_recent_commits(PROJECT_ROOT)
        assert isinstance(commits, list)
        assert len(commits) <= 5


class TestDiffStats:
    def test_get_staged_diff_stat(self):
        result = get_staged_diff_stat(PROJECT_ROOT)
        assert isinstance(result, str)

    def test_get_unstaged_diff_stat(self):
        result = get_unstaged_diff_stat(PROJECT_ROOT)
        assert isinstance(result, str)


class TestBuildAutoContext:
    def test_build_auto_context(self):
        result = build_auto_context(PROJECT_ROOT)
        assert "[Memento Auto-Capture]" in result
        assert "Branch:" in result
        assert "Recent commits:" in result

    def test_build_auto_context_not_git_repo(self, tmp_path):
        result = build_auto_context(str(tmp_path))
        assert result == ""
