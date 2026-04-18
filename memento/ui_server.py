import threading
import json
import html
import asyncio
import logging
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

# We will inject these from mcp_server.py
shared_state: dict[str, Any] = {
    "enforcement_config": {},
    "active_coercion": {},
    "get_active_goals": None,
    "provider": None
}

_loop: asyncio.AbstractEventLoop | None = None

def _run_async(coro):
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(coro)

def _safe_int(value: str | None, default: int) -> int:
    if not value:
        return default
    try:
        return int(value)
    except Exception:
        return default

def render_dashboard_html(
    *,
    enforcement_config: dict,
    active_coercion: dict,
    goals: str,
    memories: list[dict],
    query: str,
) -> str:
    config_json = html.escape(json.dumps(enforcement_config, indent=2, ensure_ascii=False))
    goals_text = html.escape(goals) if goals else ""
    coercion_enabled = bool(active_coercion.get("enabled")) if isinstance(active_coercion, dict) else False
    coercion_rules = active_coercion.get("rules", []) if isinstance(active_coercion, dict) else []
    coercion_rules_count = len(coercion_rules) if isinstance(coercion_rules, list) else 0
    query_value = html.escape(query or "")
    memories_html = "".join(
        [
            f"<tr><td><code>{html.escape(str(m.get('id', '')))}</code></td><td>{html.escape(str(m.get('created_at', '')))}</td><td>{html.escape(str(m.get('memory', '')))}</td></tr>"
            for m in (memories or [])
        ]
    )
    return f"""
            <html>
            <head>
                <title>Memento Dashboard</title>
                <style>
                    :root {{
                        --bg: #0b0f14;
                        --panel: #0f1620;
                        --text: #e6edf3;
                        --muted: #9fb0c0;
                        --border: rgba(230, 237, 243, 0.12);
                        --accent: #7aa2f7;
                        --danger: #ff6b6b;
                        --ok: #2ecc71;
                    }}
                    body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji"; margin: 0; background: var(--bg); color: var(--text); }}
                    a {{ color: var(--accent); text-decoration: none; }}
                    .wrap {{ max-width: 1100px; margin: 0 auto; padding: 28px 18px 60px; }}
                    .topbar {{ display: flex; align-items: baseline; justify-content: space-between; gap: 16px; margin-bottom: 18px; }}
                    .title {{ display: flex; flex-direction: column; gap: 6px; }}
                    h1 {{ font-size: 22px; margin: 0; letter-spacing: 0.3px; }}
                    .subtitle {{ color: var(--muted); font-size: 13px; }}
                    .grid {{ display: grid; grid-template-columns: 1fr; gap: 14px; }}
                    .card {{ background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.02)); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }}
                    .card h2 {{ font-size: 14px; margin: 0 0 12px; color: var(--muted); font-weight: 600; letter-spacing: 0.4px; text-transform: uppercase; }}
                    pre {{ background: rgba(255,255,255,0.03); border: 1px solid var(--border); padding: 12px; border-radius: 10px; overflow: auto; white-space: pre-wrap; word-break: break-word; margin: 0; }}
                    .chips {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 0; padding: 0; list-style: none; }}
                    .chip {{ border: 1px solid var(--border); border-radius: 999px; padding: 6px 10px; font-size: 12px; color: var(--muted); display: inline-flex; align-items: center; gap: 8px; }}
                    .dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; background: var(--muted); }}
                    .dot.ok {{ background: var(--ok); }}
                    .dot.bad {{ background: var(--danger); }}
                    form {{ display: flex; gap: 10px; align-items: center; }}
                    input[type="text"] {{ flex: 1; background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; color: var(--text); outline: none; }}
                    button {{ background: rgba(122, 162, 247, 0.18); border: 1px solid rgba(122, 162, 247, 0.35); color: var(--text); border-radius: 10px; padding: 10px 12px; cursor: pointer; }}
                    table {{ width: 100%; border-collapse: collapse; }}
                    th, td {{ text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--border); vertical-align: top; }}
                    th {{ color: var(--muted); font-size: 12px; font-weight: 600; }}
                    code {{ color: rgba(230,237,243,0.9); }}
                </style>
            </head>
            <body>
                <div class="wrap">
                    <div class="topbar">
                        <div class="title">
                            <h1>Memento Dashboard</h1>
                            <div class="subtitle">Local-first memory, enforcement, and goal alignment</div>
                        </div>
                        <div class="subtitle"><a href="/api/status">/api/status</a></div>
                    </div>

                    <div class="card" style="margin-bottom: 14px;">
                        <form method="GET" action="/">
                            <input type="text" name="q" value="{query_value}" placeholder="Search memory…" />
                            <button type="submit">Search</button>
                        </form>
                    </div>

                    <div class="grid">
                        <div class="card">
                            <h2>System</h2>
                            <ul class="chips">
                                <li class="chip"><span class="dot {'ok' if coercion_enabled else 'bad'}"></span>Active Coercion: {'on' if coercion_enabled else 'off'}</li>
                                <li class="chip"><span class="dot"></span>Rules: {coercion_rules_count}</li>
                                <li class="chip"><span class="dot"></span>UI: localhost</li>
                            </ul>
                        </div>

                        <div class="card">
                            <h2>Active Goals</h2>
                            <pre>{goals_text if goals_text else 'No active goals.'}</pre>
                        </div>

                        <div class="card">
                            <h2>Memories</h2>
                            <table>
                                <thead>
                                    <tr><th>ID</th><th>Created</th><th>Memory</th></tr>
                                </thead>
                                <tbody>
                                    {memories_html if memories_html else '<tr><td colspan="3">No memories found.</td></tr>'}
                                </tbody>
                            </table>
                        </div>

                        <div class="card">
                            <h2>Enforcement Config</h2>
                            <pre>{config_json}</pre>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """

class MementoUIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        q = (qs.get("q") or [""])[0]

        if path == "/api/status":
            payload = {
                "enforcement_config": shared_state.get("enforcement_config") or {},
                "active_coercion": shared_state.get("active_coercion") or {},
            }
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            return

        if path == "/api/goals":
            goals = ""
            fn = shared_state.get("get_active_goals")
            if fn:
                try:
                    goals = _run_async(fn(5))
                except Exception:
                    goals = ""
            payload = {"goals": goals}
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            return

        if path == "/api/memories":
            provider = shared_state.get("provider")
            limit = _safe_int((qs.get("limit") or [None])[0], 20)
            if limit < 1:
                limit = 20
            if limit > 200:
                limit = 200

            items: list[dict] = []
            if provider:
                try:
                    if q:
                        items = _run_async(provider.search(q, user_id="default", limit=limit))
                    else:
                        items = _run_async(provider.get_all(user_id="default", limit=limit))
                except Exception:
                    items = []

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"results": items}, ensure_ascii=False).encode("utf-8"))
            return

        if path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            
            config = shared_state.get("enforcement_config") or {}
            active = shared_state.get("active_coercion") or {}
            
            goals = ""
            fn = shared_state.get("get_active_goals")
            if fn:
                try:
                    goals = _run_async(fn(5))
                except Exception:
                    goals = ""
                
            memories: list[dict] = []
            provider = shared_state.get("provider")
            if provider:
                try:
                    if q:
                        memories = _run_async(provider.search(q, user_id="default", limit=50))
                    else:
                        memories = _run_async(provider.get_all(user_id="default", limit=20))
                except Exception:
                    pass

            page = render_dashboard_html(
                enforcement_config=config,
                active_coercion=active,
                goals=str(goals or ""),
                memories=memories,
                query=q,
            )
            self.wfile.write(page.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def run_ui_server(port=8089):
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    try:
        server = HTTPServer(("localhost", port), MementoUIHandler)
        server.serve_forever()
    except Exception as e:
        logging.getLogger("memento-ui").error(f"Failed to start UI server on port {port}: {e}")
    finally:
        if _loop and not _loop.is_closed():
            _loop.close()


def start_ui_server_thread(enforcement_config, get_active_goals_fn, provider, port=8089, active_coercion=None):
    shared_state["enforcement_config"] = enforcement_config
    shared_state["active_coercion"] = active_coercion or {}
    shared_state["get_active_goals"] = get_active_goals_fn
    shared_state["provider"] = provider
    
    thread = threading.Thread(target=run_ui_server, args=(port,), daemon=True)
    thread.start()
    return thread
