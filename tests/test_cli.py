import pytest


class TestCLIImport:
    def test_cli_import(self):
        from memento.cli import main

        assert callable(main)


class TestCLIHelp:
    def test_cli_help(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["memento", "--help"])
        with pytest.raises(SystemExit) as exc_info:
            from memento.cli import main

            main()
        assert exc_info.value.code == 0

    def test_cli_capture_help(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["memento", "capture", "--help"])
        with pytest.raises(SystemExit) as exc_info:
            from memento.cli import main

            main()
        assert exc_info.value.code == 0

    def test_cli_search_help(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["memento", "search", "--help"])
        with pytest.raises(SystemExit) as exc_info:
            from memento.cli import main

            main()
        assert exc_info.value.code == 0

    def test_cli_capture_no_args(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["memento", "capture"])
        with pytest.raises(SystemExit) as exc_info:
            from memento.cli import main

            main()
        assert exc_info.value.code != 0


class TestCLIDoctor:
    def test_doctor_runs(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["memento", "doctor"])
        from memento.cli import main

        main()
        captured = capsys.readouterr()
        assert "Memento Doctor" in captured.out
        assert "Embedding backend" in captured.out

    def test_doctor_shows_version(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["memento", "doctor"])
        from memento.cli import main

        main()
        captured = capsys.readouterr()
        assert "Version" in captured.out


class TestCLICoerce:
    def test_coerce_list(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["memento", "coerce", "--list"])
        from memento.cli import main

        main()
        captured = capsys.readouterr()
        assert "python-dev-basics" in captured.out
        assert "typescript-strict" in captured.out
        assert "go-strict" in captured.out

    def test_coerce_apply_creates_settings(self, monkeypatch, capsys, tmp_path):
        import json

        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(
            "sys.argv", ["memento", "coerce", "--apply", "python-strict"]
        )
        from memento.cli import main

        main()
        captured = capsys.readouterr()
        assert "Applied preset" in captured.out
        settings_path = tmp_path / ".memento" / "settings.json"
        assert settings_path.exists()
        data = json.loads(settings_path.read_text())
        assert "active_coercion" in data
        rules = data["active_coercion"]["rules"]
        assert len(rules) > 0

    def test_coerce_apply_merges_by_id(self, monkeypatch, capsys, tmp_path):
        import json

        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        # Apply first preset
        monkeypatch.setattr(
            "sys.argv", ["memento", "coerce", "--apply", "python-dev-basics"]
        )
        from memento.cli import main

        main()
        # Apply second preset
        monkeypatch.setattr(
            "sys.argv", ["memento", "coerce", "--apply", "typescript-strict"]
        )
        main()
        captured = capsys.readouterr()
        settings_path = tmp_path / ".memento" / "settings.json"
        data = json.loads(settings_path.read_text())
        rules = data["active_coercion"]["rules"]
        # Should have rules from both presets, not duplicated
        rule_ids = [r["id"] for r in rules]
        assert len(rule_ids) == len(set(rule_ids)), "Duplicate rule IDs found"
        assert len(rules) >= 4, f"Expected rules from both presets, got {len(rules)}"

    def test_coerce_apply_unknown_preset_fails(self, monkeypatch, tmp_path):
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(
            "sys.argv", ["memento", "coerce", "--apply", "nonexistent"]
        )
        from memento.cli import main

        with pytest.raises(SystemExit):
            main()

    def test_coerce_status(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        # Apply first so status has something to show
        monkeypatch.setattr(
            "sys.argv", ["memento", "coerce", "--apply", "python-dev-basics"]
        )
        from memento.cli import main

        main()
        capsys.readouterr()  # clear
        # Now check status
        monkeypatch.setattr("sys.argv", ["memento", "coerce", "--status"])
        main()
        captured = capsys.readouterr()
        assert "Active Coercion" in captured.out
        assert "no_print_py" in captured.out or "rules" in captured.out
