import re

with open('memento/dependency_tracker.py', 'r') as f:
    content = f.read()

# Add local modules filter
old_str = """    # 1. Get used imports
    used_imports = await scan_workspace_for_imports(workspace_root)
    
    # Map to package names
    used_packages = {map_import_to_package(imp) for imp in used_imports}"""

new_str = """    # 1. Get used imports
    used_imports = await scan_workspace_for_imports(workspace_root)
    
    # Filter out local modules
    root_path = Path(workspace_root)
    local_modules = set()
    for item in root_path.iterdir():
        if item.is_dir() and (item / "__init__.py").exists():
            local_modules.add(item.name)
        elif item.is_file() and item.name.endswith(".py"):
            local_modules.add(item.stem)
            
    filtered_imports = {imp for imp in used_imports if imp not in local_modules}
    
    # Map to package names
    used_packages = {map_import_to_package(imp) for imp in filtered_imports}"""

content = content.replace(old_str, new_str)

with open('memento/dependency_tracker.py', 'w') as f:
    f.write(content)

