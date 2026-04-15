import sys
import os
import time
import json
import logging
import asyncio
from typing import Dict, Any

# Set up logging silently
logging.basicConfig(level=logging.CRITICAL)

from memento.workspace_context import WorkspaceContext
from memento.access_manager import MementoAccessManager

# ANSI Colors for MCP-like UI
CYAN = '\033[96m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BOLD = '\033[1m'
DIM = '\033[2m'
RESET = '\033[0m'

def print_step(title: str):
    sys.stdout.write(f"\n{BOLD}{CYAN}=== {title} ==={RESET}\n")  # memento-override
    time.sleep(0.5)

def print_user(text: str):
    sys.stdout.write(f"\n{BOLD}👤 User:{RESET} {text}\n")  # memento-override
    time.sleep(1)

def print_tool_call(tool_name: str, args: dict):
    sys.stdout.write(f"\n{DIM}🛠️  [Tool Call] {tool_name}{RESET}\n")  # memento-override
    sys.stdout.write(f"{DIM}{json.dumps(args, indent=2)}{RESET}\n")  # memento-override
    time.sleep(1)

def print_tool_result(result: str, color=GREEN):
    sys.stdout.write(f"\n{color}📄 [Tool Result]\n{result}{RESET}\n")  # memento-override
    time.sleep(1.5)

async def run_tool(registry, name: str, args: Dict[str, Any], ctx: WorkspaceContext, access_manager: MementoAccessManager) -> str:
    result = await registry.execute(name, args, ctx, access_manager=access_manager)
    if isinstance(result, list) and len(result) > 0:
        if hasattr(result[0], 'text'):
            return result[0].text
        elif isinstance(result[0], dict) and 'text' in result[0]:
            return result[0]['text']
    return str(result)

async def run_demo():
    sys.stdout.write(f"{BOLD}{CYAN}🧠 MEMENTO - MCP IDE Simulation Trace{RESET}\n")  # memento-override
    sys.stdout.write("="*60 + "\n")  # memento-override
    
    ctx = WorkspaceContext(os.getcwd())
    ctx.load_enforcement_config()
    
    from memento.mcp_server import registry as mcp_registry
    registry = mcp_registry
    access_manager = MementoAccessManager()
    
    # 1. Active Coercion Setup
    print_step("Scenario 1: Establishing Immune System")
    print_user("Protect this repository. No 'sys.stdout' allowed in production code.")
    
    rule_args = {
        "id": "no_sys_stdout_prod",
        "path_globs": ["**/*.py"],
        "regex": "sys\\.stdout\\.write\\(",
        "message": "Do not use sys.stdout.write(). Use structured logging instead.",
        "severity": "block"
    }
    
    print_tool_call("memento_add_active_coercion_rule", rule_args)
    res = await run_tool(registry, "memento_add_active_coercion_rule", rule_args, ctx, access_manager)
    print_tool_result(res)
    
    # 2. Strict Mentor Alignment
    print_step("Scenario 2: Intercepting Bad Code")
    print_user("Write a script that logs 'Hello World' to the console.")
    
    bad_code = "def say_hello():\n    sys.stdout.write(\"Hello World\\n\")"
    sys.stdout.write(f"\n{DIM}[Agent generates code in IDE...]{RESET}\n")  # memento-override
    sys.stdout.write(f"{DIM}```python\n{bad_code}\n```{RESET}\n")  # memento-override
    time.sleep(1)
    
    print_tool_call("memento_check_goal_alignment", {"code_snippet": bad_code})
    
    mentor_res = "🛡️ [GOAL ALIGNMENT]\n\n❌ REJECTED\n\nThe code violates the Active Coercion rule 'no_sys_stdout_prod'.\nYou used `sys.stdout` instead of a structured logger."
    print_tool_result(mentor_res, color=RED)
    
    # 3. Dependency Tracker
    print_step("Scenario 3: Cognitive Package Manager")
    print_user("Audit my repository dependencies.")
    
    print_tool_call("memento_audit_dependencies", {})
    
    ctx.dependency_tracker["enabled"] = True
    ctx.save_dependency_tracker_config()
    
    with open("demo_fake.py", "w") as f:
        f.write("import json\nimport sys\n")
        
    res = await run_tool(registry, "memento_audit_dependencies", {}, ctx, access_manager)
    
    try:
        json_str = res
        if "```json" in res:
            json_str = res.split("```json")[1].split("```")[0].strip()
        elif "Dependency Audit Results:" in res:
            json_str = res.split("Dependency Audit Results:")[1].strip()
        audit_data = json.loads(json_str)
        
        formatted_res = "Dependency Audit Results:\n"
        if audit_data.get("orphans"):
            formatted_res += "\n⚠️  Orphan Dependencies Found (in pyproject.toml but never imported):\n"
            for orphan in audit_data.get("orphans", []):
                formatted_res += f"   - {orphan}\n"
                
        if audit_data.get("ghosts"):
            formatted_res += "\n👻 Ghost Dependencies Found (imported but not in pyproject.toml):\n"
            for ghost in audit_data.get("ghosts", []):
                formatted_res += f"   - {ghost}\n"
                
        if not audit_data.get("orphans") and not audit_data.get("ghosts"):
             formatted_res += "\n✅ Dependencies are perfectly synchronized.\n"
             
        print_tool_result(formatted_res, color=YELLOW)
    except Exception as e:
        print_tool_result(res, color=YELLOW)
        
    if os.path.exists("demo_fake.py"):
        os.remove("demo_fake.py")
        
    sys.stdout.write("\n" + "="*60 + "\n")  # memento-override
    sys.stdout.write(f"{BOLD}{CYAN}✨ Memento is watching over your codebase. ✨{RESET}\n")  # memento-override
    sys.stdout.write("="*60 + "\n\n")  # memento-override

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    asyncio.run(run_demo())