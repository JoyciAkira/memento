import json

import pytest


@pytest.mark.asyncio
async def test_memento_search_basic_honors_limit(tmp_path):
    from memento.mcp_server import call_tool

    workspace = str(tmp_path)
    for i in range(12):
        await call_tool(
            "memento_remember",
            {
                "workspace_root": workspace,
                "action": "add",
                "text": f"limit probe alpha {i}",
            },
        )

    result = await call_tool(
        "memento_search",
        {
            "workspace_root": workspace,
            "query": "limit probe",
            "mode": "basic",
            "limit": 5,
        },
    )

    payload = result[0].text.rsplit("Results:\n", 1)[1]
    assert len(json.loads(payload)) == 5


@pytest.mark.asyncio
async def test_orchestrator_search_honors_limit(tmp_path):
    from memento.provider import NeuroGraphProvider

    provider = NeuroGraphProvider(
        db_path=str(tmp_path / "orchestrator.db"), workspace_root=str(tmp_path)
    )
    await provider.initialize()
    try:
        for i in range(30):
            provider.orchestrator.add(f"limit probe alpha {i}", tier="semantic")

        results = provider.orchestrator.search("limit probe alpha", limit=5)
        assert len(results) == 5
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_provider_search_honors_limit(tmp_path):
    from memento.provider import NeuroGraphProvider

    provider = NeuroGraphProvider(
        db_path=str(tmp_path / "provider.db"), workspace_root=str(tmp_path)
    )
    await provider.initialize()
    try:
        for i in range(30):
            await provider.add(f"limit probe omega {i}", user_id="default")

        results = await provider.search("limit probe omega", limit=5)
        assert len(results) == 5
    finally:
        await provider.close()
