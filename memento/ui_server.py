import threading
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

# We will inject these from mcp_server.py
shared_state: dict[str, Any] = {
    "enforcement_config": {},
    "get_active_goals": None,
    "provider": None
}

class MementoUIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            
            config = shared_state["enforcement_config"]
            
            goals = ""
            if shared_state["get_active_goals"]:
                goals = shared_state["get_active_goals"](5)
                
            recent_memories = []
            if shared_state["provider"]:
                try:
                    # fetch recent 10 memories
                    recent_memories = shared_state["provider"].get_all(user_id="default", limit=10)
                except Exception:
                    pass
            
            memories_html = "".join([f"<li>{m.get('memory')}</li>" for m in recent_memories])
            
            html = f"""
            <html>
            <head>
                <title>Memento Dashboard</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 2rem; background: #f4f4f9; color: #333; }}
                    h1 {{ color: #2c3e50; }}
                    .card {{ background: white; padding: 1.5rem; margin-bottom: 1.5rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                    pre {{ background: #eee; padding: 1rem; border-radius: 4px; white-space: pre-wrap; }}
                </style>
            </head>
            <body>
                <h1>🧠 Memento Dashboard</h1>
                
                <div class="card">
                    <h2>Enforcement Config</h2>
                    <pre>{json.dumps(config, indent=2)}</pre>
                </div>
                
                <div class="card">
                    <h2>Active Goals</h2>
                    <pre>{goals if goals else 'No active goals.'}</pre>
                </div>
                
                <div class="card">
                    <h2>Recent Memories</h2>
                    <ul>
                        {memories_html if memories_html else '<li>No memories found.</li>'}
                    </ul>
                </div>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def run_ui_server(port=8089):
    try:
        server = HTTPServer(("localhost", port), MementoUIHandler)
        server.serve_forever()
    except Exception as e:
        import logging
        logging.getLogger("memento-ui").error(f"Failed to start UI server on port {port}: {e}")


def start_ui_server_thread(enforcement_config, get_active_goals_fn, provider, port=8089):
    shared_state["enforcement_config"] = enforcement_config
    shared_state["get_active_goals"] = get_active_goals_fn
    shared_state["provider"] = provider
    
    thread = threading.Thread(target=run_ui_server, args=(port,), daemon=True)
    thread.start()
    return thread
