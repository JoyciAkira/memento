import json
import os
import subprocess
import sys

from memento.active_coercion import check_text_against_rules, normalize_hard_rules


def run_pre_commit(repo_root: str) -> int:
    settings_path = os.path.join(repo_root, ".memento", "settings.json")
    settings: dict = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    settings = data
        except Exception:
            settings = {}

    active = settings.get("active_coercion", {})
    enabled = bool(active.get("enabled", False)) if isinstance(active, dict) else False
    if not enabled:
        return 0

    rules = normalize_hard_rules(active.get("rules", []) if isinstance(active, dict) else [])
    if not rules:
        return 0

    paths = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        text=True,
        cwd=repo_root,
    ).splitlines()

    block_violations = []
    warn_violations = []

    for rel in paths:
        rel = rel.strip()
        if not rel:
            continue
        try:
            content = subprocess.check_output(["git", "show", f":{rel}"], cwd=repo_root)
        except subprocess.CalledProcessError:
            continue
        if b"\x00" in content:
            continue
        text = content.decode("utf-8", errors="replace")
        abs_path = os.path.join(repo_root, rel)
        violations = check_text_against_rules(
            workspace_root=repo_root,
            rules=rules,
            file_path=abs_path,
            content=text,
        )
        for v in violations:
            if v.severity == "warn":
                warn_violations.append(v)
            else:
                block_violations.append(v)

    if warn_violations:
        sys.stderr.write("\nMemento Active Coercion warnings:\n")
        for v in warn_violations:
            sys.stderr.write(f"- {v.rule_id}: {os.path.relpath(v.file, repo_root)}: {v.message}\n")

    if block_violations:
        sys.stderr.write("\nMemento Active Coercion BLOCKED commit:\n")
        for v in block_violations:
            sys.stderr.write(f"- {v.rule_id}: {os.path.relpath(v.file, repo_root)}: {v.message}\n")
        return 1

    return 0


def main() -> None:
    repo_root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
    raise SystemExit(run_pre_commit(repo_root))


if __name__ == "__main__":
    main()

