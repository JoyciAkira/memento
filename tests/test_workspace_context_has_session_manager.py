def test_workspace_context_has_session_manager(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")
    from memento.workspace_context import get_workspace_context

    ctx = get_workspace_context(str(tmp_path))
    assert hasattr(ctx, "session_manager")

