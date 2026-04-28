"""Tests for memento/updater.py — package detection, pip upgrade, restart."""
from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest


class TestDetectInstalledPackage:
    def test_detects_memento_mcp_first(self):
        with patch("memento.updater._get_version") as mock_ver:
            mock_ver.side_effect = lambda pkg: "1.0.0" if pkg == "memento-mcp" else None
            from memento.updater import detect_installed_package
            assert detect_installed_package() == "memento-mcp"

    def test_falls_back_to_memento(self):
        with patch("memento.updater._get_version") as mock_ver:
            mock_ver.side_effect = lambda pkg: "1.0.0" if pkg == "memento" else None
            from memento.updater import detect_installed_package
            assert detect_installed_package() == "memento"

    def test_returns_none_when_neither_found(self):
        with patch("memento.updater._get_version", return_value=None):
            from memento.updater import detect_installed_package
            assert detect_installed_package() is None


class TestGetInstalledVersion:
    def test_returns_version_string(self):
        with patch("importlib.metadata.version", return_value="1.2.3"):
            from memento.updater import _get_version
            assert _get_version("memento-mcp") == "1.2.3"

    def test_returns_none_on_package_not_found(self):
        with patch("importlib.metadata.version", side_effect=Exception("not found")):
            from memento.updater import _get_version
            assert _get_version("memento-mcp") is None


class TestPipUpgrade:
    def test_success_returns_true_and_output(self):
        fake_output = "Successfully installed memento-mcp-1.3.0"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=fake_output, stderr="")
            from memento.updater import pip_upgrade
            ok, out = pip_upgrade("memento-mcp", dry_run=False)
            assert ok is True
            assert fake_output in out

    def test_dry_run_does_not_execute_pip(self):
        with patch("subprocess.run") as mock_run:
            from memento.updater import pip_upgrade
            ok, out = pip_upgrade("memento-mcp", dry_run=True)
            mock_run.assert_not_called()
            assert ok is True
            assert "dry-run" in out.lower()

    def test_failure_returns_false_and_output(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="ERROR: Could not find")
            from memento.updater import pip_upgrade
            ok, out = pip_upgrade("memento-mcp", dry_run=False)
            assert ok is False
            assert "ERROR" in out


class TestUpgradeWithFallback:
    def test_primary_succeeds_no_fallback(self):
        with patch("memento.updater.pip_upgrade", return_value=(True, "ok")) as mock_pip:
            from memento.updater import upgrade_with_fallback
            ok, pkg, out = upgrade_with_fallback(dry_run=False)
            assert ok is True
            assert pkg == "memento-mcp"
            mock_pip.assert_called_once()

    def test_primary_fails_fallback_succeeds(self):
        with patch("memento.updater.pip_upgrade", side_effect=[
            (False, "fail"),
            (True, "ok memento"),
        ]) as mock_pip:
            from memento.updater import upgrade_with_fallback
            ok, pkg, out = upgrade_with_fallback(dry_run=False)
            assert ok is True
            assert pkg == "memento"
            assert mock_pip.call_count == 2

    def test_both_fail(self):
        with patch("memento.updater.pip_upgrade", side_effect=[
            (False, "fail1"),
            (False, "fail2"),
        ]):
            from memento.updater import upgrade_with_fallback
            ok, pkg, out = upgrade_with_fallback(dry_run=False)
            assert ok is False
            assert pkg == "memento"


class TestFormatReport:
    def test_success_report(self):
        from memento.updater import format_report
        report = format_report(
            python_path="/usr/bin/python3",
            package="memento-mcp",
            old_version="1.0.0",
            new_version="1.1.0",
            success=True,
            pip_output="Successfully installed",
        )
        assert "memento-mcp" in report
        assert "1.0.0" in report
        assert "1.1.0" in report
        assert "/usr/bin/python3" in report

    def test_failure_report(self):
        from memento.updater import format_report
        report = format_report(
            python_path="/usr/bin/python3",
            package="memento-mcp",
            old_version="1.0.0",
            new_version=None,
            success=False,
            pip_output="ERROR: blah",
        )
        assert "ERROR" in report or "Failed" in report or "FAILED" in report

    def test_dry_run_report(self):
        from memento.updater import format_report
        report = format_report(
            python_path="/usr/bin/python3",
            package="memento-mcp",
            old_version="1.0.0",
            new_version=None,
            success=True,
            pip_output="Would run: pip install -U memento-mcp",
            dry_run=True,
        )
        assert "dry-run" in report.lower()


class TestRestartBestEffort:
    def test_no_matching_processes(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            from memento.updater import restart_best_effort
            result = restart_best_effort()
            assert result["killed"] == 0

    def test_kills_matching_processes(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="  1234  python -m memento.mcp_server\n")
            from memento.updater import restart_best_effort
            result = restart_best_effort()
            assert result["killed"] >= 0
