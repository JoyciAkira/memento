import os

def find_project_root(current_dir: str) -> str:
    markers = [".git", "package.json", "pyproject.toml", "cargo.toml"]
    d = os.path.abspath(current_dir)
    original_dir = d
    while True:
        for marker in markers:
            if os.path.exists(os.path.join(d, marker)):
                return d
        parent = os.path.dirname(d)
        if parent == d:
            return original_dir
        d = parent

async def get_active_goals(ctx, max_goals: int = 3, context: str = None) -> str:
    try:
        search_query = f"obiettivo goal per il contesto: {context}" if context else "obiettivo goal"
        res = await ctx.provider.search(search_query, user_id="default")
        results = res.get("results", []) if isinstance(res, dict) else res
        if not isinstance(results, list):
            return ""
        goals = []
        for r in results[:max_goals]:
            if not isinstance(r, dict):
                continue
            memory = r.get("memory")
            if isinstance(memory, str) and memory.strip():
                goals.append(memory.strip())
        if not goals:
            return ""
        formatted = "\n- ".join(goals)
        return f"[ACTIVE GOALS]\n- {formatted}\n\n"
    except Exception:
        return ""
