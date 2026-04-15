import os
import asyncio
import sys
import os
import time
import json
import logging
from typing import Dict, Any

# Set up logging silently
logging.basicConfig(level=logging.CRITICAL)

# Import Memento tools
from memento.workspace_context import WorkspaceContext
from memento.access_manager import MementoAccessManager
from memento.tools import core, memory, coercion, cognitive

# ANSI Colors
CYAN = '\033[96m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BOLD = '\033[1m'
DIM = '\033[2m'
RESET = '\033[0m'

def type_text(text: str, speed: float = 0.03, color: str = RESET, bold: bool = False):
    """Simulate typing text in terminal."""
    prefix = ""
    if color != RESET: prefix += color
    if bold: prefix += BOLD
    
    sys.stdout.write(prefix)
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(speed)
    sys.stdout.write(RESET + "\n")

async def run_tool(registry, name: str, args: Dict[str, Any], ctx: WorkspaceContext, access_manager: MementoAccessManager) -> str:
    """Run an MCP tool and extract the text result."""
    result = await registry.execute(name, args, ctx, access_manager=access_manager)
    if isinstance(result, list) and len(result) > 0:
        if hasattr(result[0], 'text'):
            return result[0].text
        elif isinstance(result[0], dict) and 'text' in result[0]:
            return result[0]['text']
    return str(result)

async def run_demo():
    # memento-override
    sys.stdout.write("\n" + "="*60 + "\n")
    sys.stdout.write(f"{BOLD}{CYAN}🧠 MEMENTO - The Autonomous Nervous System for AI{RESET}\n")
    sys.stdout.write("="*60 + "\n\n")
    
    # Init context
    ctx = WorkspaceContext(os.getcwd())
    ctx.load_enforcement_config()
    
    from memento.mcp_server import registry as mcp_registry
    registry = mcp_registry
    access_manager = MementoAccessManager()
    
    # 1. Active Coercion Setup
    type_text("User: Protect this repository. No 'print' allowed in production code.", speed=0.04, color=CYAN, bold=True)
    time.sleep(1)
    
    type_text("\n[Agent invoking memento_add_active_coercion_rule...]", color=DIM)
    time.sleep(0.5)
    
    rule_args = {
        "id": "no_print_prod",
        "path_globs": ["**/*.py"],
        "regex": "\\bprint\\(",
        "message": "Vietato usare print(). Usa il logger strutturato.",
        "severity": "block"
    }
    
    res = await run_tool(registry, "memento_add_active_coercion_rule", rule_args, ctx, access_manager)
    type_text(f"🤖 Memento: {res}", color=GREEN)
    time.sleep(1.5)
    
    # 2. Strict Mentor Alignment
    sys.stdout.write("\n" + "-"*60 + "\n\n")
    type_text("User: Write a script that logs 'Hello World' to the console.", speed=0.04, color=CYAN, bold=True)
    time.sleep(1)
    
    bad_code = """def say_hello():\n    print("Hello World")"""  # memento-override
    type_text(f"\n[Agent generated code:]\n{DIM}{bad_code}{RESET}", speed=0.01)
    time.sleep(1)
    
    type_text("\n[Agent invoking memento_check_goal_alignment...]", color=DIM)
    
    # We mock the response for the demo to avoid hitting the real OpenAI API and waiting
    # In reality, this calls cognitive.py which uses LLM
    time.sleep(1.5)
    mentor_res = f"🛡️ [ALLINEAMENTO GOAL]\n\n❌ BOCCIATO\n\nIl codice viola la regola di Active Coercion 'no_print_prod'.\nHai usato `print()` invece di un logger strutturato."
    type_text(f"🤖 Memento Strict Mentor:\n{mentor_res}", color=RED, bold=True)
    time.sleep(2)
    
    # 3. Dependency Tracker
    sys.stdout.write("\n" + "-"*60 + "\n\n")
    type_text("User: Audit my repository dependencies.", speed=0.04, color=CYAN, bold=True)
    time.sleep(1)
    
    type_text("\n[Agent invoking memento_audit_dependencies...]", color=DIM)
    
    # Enable tracker
    ctx.dependency_tracker["enabled"] = True
    ctx.save_dependency_tracker_config()
    
    # Create a fake pyproject.toml and a fake python file for the demo to find orphans
    with open("demo_fake.py", "w") as f:
        f.write("import json\nimport sys\n")
        
    res = await run_tool(registry, "memento_audit_dependencies", {}, ctx, access_manager)
    
    # Parse the JSON response
    try:
        # Extract json part if it has text around it
        json_str = res
        if "```json" in res:
            json_str = res.split("```json")[1].split("```")[0].strip()
        elif "Dependency Audit Results:" in res:
            json_str = res.split("Dependency Audit Results:")[1].strip()
        audit_data = json.loads(json_str)
        
        type_text("\n🤖 Memento Dependency Audit:", color=YELLOW, bold=True)
        if audit_data.get("orphans"):
            type_text(f"⚠️  Orphan Dependencies Found (in pyproject.toml but never imported):", color=RED)
            for orphan in audit_data.get("orphans", []):
                type_text(f"   - {orphan}", color=RED)
                
        if audit_data.get("ghosts"):
            type_text(f"👻 Ghost Dependencies Found (imported but not in pyproject.toml):", color=YELLOW)
            for ghost in audit_data.get("ghosts", []):
                type_text(f"   - {ghost}", color=YELLOW)
                
        if not audit_data.get("orphans") and not audit_data.get("ghosts"):
             type_text(f"✅ Dependencies are perfectly synchronized.", color=GREEN)
             
    except Exception as e:
        type_text(f"🤖 Memento: {res}", color=YELLOW)
        
    # Cleanup demo file
    if os.path.exists("demo_fake.py"):
        os.remove("demo_fake.py")
        
    time.sleep(2)
    sys.stdout.write("\n" + "="*60 + "\n")
    type_text("✨ Memento is watching over your codebase. ✨", color=CYAN, bold=True)
    sys.stdout.write("="*60 + "\n\n")

if __name__ == "__main__":
    # Hide the DeprecationWarning from Pydantic inside Mem0
    import warnings
    warnings.filterwarnings("ignore")
    
    asyncio.run(run_demo())
