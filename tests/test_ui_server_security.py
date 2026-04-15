from memento.ui_server import render_dashboard_html


def test_ui_escapes_memory_and_goals():
    config = {"level1": True, "note": "<b>unsafe</b>"}
    goals = "<script>alert(1)</script>"
    memories = [{"memory": "<img src=x onerror=alert(1)>"}, {"memory": "ok"}]

    page = render_dashboard_html(config, goals, memories)

    assert "<script>" not in page
    assert "<img" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "&lt;img src=x onerror=alert(1)&gt;" in page
    assert "&lt;b&gt;unsafe&lt;/b&gt;" in page

