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
        goals = await ctx.provider.list_goals(context=context, active_only=True)
        if not goals:
            return ""
        entries = [g["goal"] for g in goals[:max_goals] if isinstance(g, dict) and "goal" in g]
        if not entries:
            return ""
        formatted = "\n- ".join(entries)
        return f"[ACTIVE GOALS]\n- {formatted}\n\n"
    except Exception:
        return ""
