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
