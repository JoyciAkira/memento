import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _summary_guard() -> str:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    matches = re.findall(
        r"^\s*(grep -Eq .*?pytest\.log)\s*$", workflow, flags=re.MULTILINE
    )
    assert len(matches) == 3, (
        "expected the pytest summary guard in Linux, Windows and macOS jobs; "
        f"found {len(matches)}"
    )
    assert len(set(matches)) == 1, "pytest summary guards differ between CI jobs"
    return matches[0]


def _run_guard(tmp_path: Path, log_text: str) -> subprocess.CompletedProcess:
    (tmp_path / "pytest.log").write_text(log_text, encoding="utf-8")
    return subprocess.run(
        ["bash", "-c", _summary_guard()],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


def test_ci_summary_guard_rejects_log_without_pytest_summary(tmp_path):
    result = _run_guard(
        tmp_path,
        "tests/test_cli.py::TestCLIDoctor::test_doctor_runs ...\n"
        "process exited with code 0\n",
    )

    assert result.returncode != 0, (
        "CI guard accepted a pytest log with no final summary; "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )


def test_ci_summary_guard_accepts_complete_pytest_summary(tmp_path):
    result = _run_guard(
        tmp_path,
        "================= 468 passed, 174 warnings in 78.80s =================\n",
    )

    assert result.returncode == 0, (
        "CI guard rejected a valid pytest summary; "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
