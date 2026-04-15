# Pre-cognitive Intervention Checklist

- [x] Dependency `watchdog>=4.0.0` is installed and registered in `pyproject.toml`.
- [x] `PreCognitiveDaemon` is implemented in `memento/daemon.py`.
- [x] The daemon correctly debounces multiple rapid file change events (e.g. 5 seconds delay).
- [x] `CognitiveEngine` has a new method `evaluate_raw_context(raw_text)` that accepts raw file content.
- [x] `evaluate_raw_context` computes embeddings and checks for historical warnings with a strict mathematical threshold (e.g. score > 0.8).
- [x] The MCP server exposes a new tool `memento_toggle_precognition` that accepts `{"enabled": true/false}`.
- [x] Toggling the tool successfully starts and stops the background `watchdog` observer.
- [x] When a file is modified and the cognitive engine detects a high-confidence match, the MCP server attempts to send an asynchronous JSON-RPC notification (`memento/precognitive_warning`) to the connected client.
- [x] All new logic has associated failing-then-passing tests in `tests/test_daemon.py` and `tests/test_cognitive_engine.py`.