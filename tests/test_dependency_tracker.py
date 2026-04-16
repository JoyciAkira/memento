import pytest
from memento.dependency_tracker import (
    extract_imports_from_code,
    scan_workspace_for_imports,
    parse_pyproject_dependencies,
    map_import_to_package,
    analyze_dependencies,
)


def test_extract_imports_from_code():
    code = """
import os
import sys
from pathlib import Path
from external_lib import something
import complex.module.path

# This is a comment with import not_real
fake_import = "import fake_string"
"""
    imports = extract_imports_from_code(code)
    assert "os" in imports
    assert "sys" in imports
    assert "pathlib" in imports
    assert "external_lib" in imports
    assert "complex" in imports
    assert "not_real" not in imports
    assert "fake_string" not in imports


@pytest.mark.asyncio
async def test_scan_workspace_for_imports(tmp_path):
    # Create a mock workspace
    (tmp_path / "main.py").write_text("import json\nimport mylib\n")
    (tmp_path / "utils.py").write_text("from pydantic import BaseModel\n")

    # Ignored directory
    venv_dir = tmp_path / ".venv"
    venv_dir.mkdir()
    (venv_dir / "ignored.py").write_text("import ignored_lib\n")

    import_locations = await scan_workspace_for_imports(tmp_path)
    # json is stdlib, so it should be filtered out
    assert "json" not in import_locations
    assert "mylib" in import_locations
    assert "pydantic" in import_locations
    assert "ignored_lib" not in import_locations
    assert "main.py" in import_locations["mylib"]
    assert "utils.py" in import_locations["pydantic"]


def test_parse_pyproject_dependencies(tmp_path):
    pyproject_content = """
[project]
name = "test-project"
dependencies = [
    "pytest>=7.0",
    "pydantic[email]",
    "watchdog==4.0.0"
]
"""
    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text(pyproject_content)

    deps = parse_pyproject_dependencies(pyproject_file)
    assert "pytest" in deps
    assert "pydantic" in deps
    assert "watchdog" in deps


def test_map_import_to_package():
    # standard mapping
    assert map_import_to_package("pytest") == "pytest"
    # Not installed mapping fallback
    assert map_import_to_package("unknown_lib") == "unknown_lib"


@pytest.mark.asyncio
async def test_analyze_dependencies(tmp_path):
    # Create workspace with pyproject.toml
    pyproject_content = """
[project]
name = "my-project"
dependencies = [
    "requests",
    "pydantic",
    "unused_pkg"
]
"""
    (tmp_path / "pyproject.toml").write_text(pyproject_content)

    # Create some python files
    (tmp_path / "main.py").write_text("import requests\nimport yaml\n")
    # yaml will be mapped to pyyaml if installed, but here we don't know environment.
    # It will fallback to yaml or pyyaml depending on environment.

    results = await analyze_dependencies(tmp_path, tmp_path / "pyproject.toml")

    # Declared: requests, pydantic, unused_pkg
    # Used: requests, yaml
    # orphans: pydantic, unused_pkg
    # ghosts: yaml

    assert "unused_pkg" in results["orphans"]
    assert "pydantic" in results["orphans"]

    assert "yaml" in results["ghosts"] or "pyyaml" in results["ghosts"]
    assert "requests" in results["used"]
    assert "requests" in results["declared"]
    
    # check if file location is in used
    assert "main.py" in results["used"]["requests"]
