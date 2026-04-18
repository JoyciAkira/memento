import pytest
from memento.dependency_tracker import (
    extract_imports_from_code,
    scan_workspace_for_imports,
    parse_pyproject_dependencies,
    parse_package_json_dependencies,
    parse_cargo_toml_dependencies,
    parse_go_mod_dependencies,
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

    results = await analyze_dependencies(tmp_path)

    # Declared: requests, pydantic, unused_pkg
    # Used: requests, yaml
    # orphans: pydantic, unused_pkg
    # ghosts: yaml

    assert "unused_pkg" in results["orphans"]
    assert "pydantic" in results["orphans"]

    assert "yaml" in results["ghosts"] or "pyyaml" in results["ghosts"]
    assert "requests" in results["used"]
    assert "requests" in results["declared"]

    assert "main.py" in results["used"]["requests"]


def test_parse_package_json_dependencies(tmp_path):
    package_json_content = """{
    "name": "my-app",
    "dependencies": {
        "express": "^4.18.0",
        "lodash": "^4.17.21"
    },
    "devDependencies": {
        "jest": "^29.0.0",
        "TypeScript": "^5.0.0"
    }
}"""
    (tmp_path / "package.json").write_text(package_json_content)

    deps = parse_package_json_dependencies(tmp_path / "package.json")
    assert "express" in deps
    assert "lodash" in deps
    assert "jest" in deps
    assert "typescript" in deps
    assert len(deps) == 4


def test_parse_cargo_toml_dependencies(tmp_path):
    cargo_content = """[package]
name = "my-crate"
version = "0.1.0"

[dependencies]
serde = { version = "1.0", features = ["derive"] }
tokio = "1.0"
clap = "4.0"

[dev-dependencies]
"""
    (tmp_path / "Cargo.toml").write_text(cargo_content)

    deps = parse_cargo_toml_dependencies(tmp_path / "Cargo.toml")
    assert "serde" in deps
    assert "tokio" in deps
    assert "clap" in deps
    assert len(deps) == 3


def test_parse_go_mod_dependencies(tmp_path):
    go_mod_content = """module github.com/example/myapp

go 1.21

require (
\tgithub.com/gin-gonic/gin v1.9.0
\tgithub.com/stretchr/testify v1.8.0
)

require github.com/google/uuid v1.3.0
"""
    (tmp_path / "go.mod").write_text(go_mod_content)

    deps = parse_go_mod_dependencies(tmp_path / "go.mod")
    assert "github.com/gin-gonic/gin" in deps
    assert "github.com/stretchr/testify" in deps
    assert "github.com/google/uuid" in deps
    assert len(deps) == 3


def test_parse_missing_files_returns_empty(tmp_path):
    assert parse_pyproject_dependencies(tmp_path / "nonexistent" / "pyproject.toml") == set()
    assert parse_package_json_dependencies(tmp_path / "nonexistent" / "package.json") == set()
    assert parse_cargo_toml_dependencies(tmp_path / "nonexistent" / "Cargo.toml") == set()
    assert parse_go_mod_dependencies(tmp_path / "nonexistent" / "go.mod") == set()
