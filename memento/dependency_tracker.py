import ast
import asyncio
import importlib.metadata
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Set, Tuple

try:
    import tomllib
except ImportError:
    tomllib = None


class ImportVisitor(ast.NodeVisitor):
    def __init__(self):
        self.imports = set()

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.add(alias.name.split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.level == 0 and node.module:
            self.imports.add(node.module.split(".")[0])
        self.generic_visit(node)


def extract_imports_from_code(code: str) -> Set[str]:
    visitor = ImportVisitor()
    try:
        tree = ast.parse(code)
        visitor.visit(tree)
    except SyntaxError:
        pass
    return visitor.imports


async def scan_file(filepath: Path) -> Tuple[Path, Set[str]]:
    def read_and_parse():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            return filepath, extract_imports_from_code(content)
        except Exception:
            return filepath, set()

    return await asyncio.to_thread(read_and_parse)


async def scan_workspace_for_imports(workspace_root: str | Path) -> Dict[str, Set[str]]:
    root_path = Path(workspace_root)
    ignore_dirs = {".git", ".venv", ".memento", "__pycache__"}
    tasks = []

    for root, dirs, files in os.walk(root_path):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for file in files:
            if file.endswith(".py"):
                tasks.append(scan_file(Path(root) / file))

    if not tasks:
        return {}

    results = await asyncio.gather(*tasks)
    
    # map import_name -> set of file paths
    import_locations = {}
    stdlib_modules = set(sys.stdlib_module_names)
    
    for filepath, imports in results:
        for imp in imports:
            if imp not in stdlib_modules:
                if imp not in import_locations:
                    import_locations[imp] = set()
                import_locations[imp].add(str(filepath.relative_to(root_path)))

    return import_locations


def parse_pyproject_dependencies(filepath: str | Path) -> Set[str]:
    path = Path(filepath)
    if not path.exists():
        return set()

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return set()

    if tomllib is not None:
        try:
            data = tomllib.loads(content)
            deps = data.get("project", {}).get("dependencies", [])
            # Also check optional dependencies? Maybe not required.
        except Exception:
            deps = []
    else:
        # Fallback to regex for basic [project] dependencies array
        deps = []
        # Find dependencies = [ ... ]
        match = re.search(r"dependencies\s*=\s*\[(.*?)\]", content, re.DOTALL)
        if match:
            dep_block = match.group(1)
            # Extract strings like "mem0ai", "watchdog>=4.0.0"
            strings = re.findall(r'["\']([^"\']+)["\']', dep_block)
            deps = strings

    # Strip version constraints to get base package name
    parsed_deps = set()
    for dep in deps:
        # e.g., "watchdog>=4.0.0", "pytest[asyncio]", "aiosqlite==0.20.0"
        base_name = re.split(r"[<>=!~\[]", dep)[0].strip()
        if base_name:
            parsed_deps.add(base_name.lower())

    return parsed_deps


def map_import_to_package(import_name: str) -> str:
    """
    Map an import name (e.g., 'yaml') to its installed package name (e.g., 'PyYAML').
    If not found in distributions, return the import name.
    """
    try:
        distributions = importlib.metadata.packages_distributions()
        # packages_distributions returns a dict like {'yaml': ['PyYAML'], ...}
        if import_name in distributions and distributions[import_name]:
            return distributions[import_name][0].lower()
    except Exception:
        pass

    # Fallback to standard conventions if metadata fails or package not installed
    # (e.g. mapping simple names back to themselves)
    return import_name.lower()


async def analyze_dependencies(
    workspace_root: str | Path, pyproject_path: str | Path
) -> Dict[str, Any]:
    """
    Returns orphans and ghosts.
    orphans: Declared in pyproject.toml but not used in code.
    ghosts: Used in code but not declared in pyproject.toml.
    """
    # 1. Get used imports
    used_imports_dict = await scan_workspace_for_imports(workspace_root)

    # Filter out local modules
    root_path = Path(workspace_root)
    local_modules = set()
    for item in root_path.iterdir():
        if item.is_dir() and (item / "__init__.py").exists():
            local_modules.add(item.name)
        elif item.is_file() and item.name.endswith(".py"):
            local_modules.add(item.stem)

    filtered_imports = {
        imp: files for imp, files in used_imports_dict.items() if imp not in local_modules
    }

    # Map to package names, preserving file locations
    used_packages = {}
    for imp, files in filtered_imports.items():
        pkg = map_import_to_package(imp)
        if pkg not in used_packages:
            used_packages[pkg] = set()
        used_packages[pkg].update(files)

    # 2. Get declared dependencies
    declared_packages = parse_pyproject_dependencies(pyproject_path)

    # Get project name to ignore
    project_name = None
    try:
        with open(pyproject_path, "r", encoding="utf-8") as f:
            content = f.read()
            if tomllib is not None:
                data = tomllib.loads(content)
                project_name = data.get("project", {}).get("name")
            else:
                match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
                if match:
                    project_name = match.group(1)
    except Exception:
        pass

    if project_name:
        used_packages.pop(project_name.lower(), None)
        normalized_name = project_name.lower().replace("-", "_")
        used_packages.pop(normalized_name, None)

    used_package_names = set(used_packages.keys())

    # 3. Calculate orphans and ghosts
    orphans = declared_packages - used_package_names
    ghosts_names = used_package_names - declared_packages
    
    ghosts = {pkg: list(used_packages[pkg]) for pkg in ghosts_names}

    return {
        "orphans": list(orphans),
        "ghosts": ghosts,
        "declared": list(declared_packages),
        "used": {pkg: list(files) for pkg, files in used_packages.items()},
    }
