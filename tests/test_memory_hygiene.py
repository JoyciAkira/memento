import argparse
import asyncio
import json
import os
from datetime import datetime, timedelta

import pytest

from memento.provider import NeuroGraphProvider


def _provider(tmp_path, monkeypatch) -> NeuroGraphProvider:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MEMENTO_EMBEDDING_BACKEND", "none")
    return NeuroGraphProvider(db_path=str(tmp_path / "memory.db"))


@pytest.mark.asyncio
async def test_add_persists_memory_tier(tmp_path, monkeypatch):
    provider = _provider(tmp_path, monkeypatch)
    episodic = await provider.add("episodic fact", metadata={"memory_tier": "episodic"})
    default = await provider.add("default fact")
    invalid = await provider.add("invalid tier", metadata={"memory_tier": "nonsense"})

    rows = {
        row["id"]: row["memory_tier"]
        for row in provider._sync_db.execute(
            "SELECT id, memory_tier FROM memories"
        ).fetchall()
    }
    assert rows[episodic["id"]] == "episodic"
    assert rows[default["id"]] == "semantic"
    assert rows[invalid["id"]] == "semantic"
    await provider.close()


@pytest.mark.asyncio
async def test_search_excludes_soft_deleted_memories(tmp_path, monkeypatch):
    provider = _provider(tmp_path, monkeypatch)
    deleted = await provider.add("alpha obsolete decision")
    kept = await provider.add("alpha current decision")

    await provider.soft_delete_memory(deleted["id"], "superseded")

    results = await provider.search("alpha")
    ids = {item["id"] for item in results}
    assert deleted["id"] not in ids
    assert kept["id"] in ids
    await provider.close()


@pytest.mark.asyncio
async def test_retrieval_pipeline_excludes_soft_deleted_memories(tmp_path, monkeypatch):
    from memento.retrieval.pipeline import retrieve_bundle

    provider = _provider(tmp_path, monkeypatch)
    deleted = await provider.add("beta obsolete architecture")
    kept = await provider.add("beta current architecture")
    await provider.soft_delete_memory(deleted["id"], "superseded")

    async def _no_embedding(_text: str) -> list[float]:
        return []

    bundle = await retrieve_bundle(
        db_path=provider.db_path,
        query="beta architecture",
        user_id="default",
        limit=10,
        filters=None,
        embed_fn=_no_embedding,
        trace=False,
    )
    ids = {item["id"] for item in bundle["results"]}
    assert deleted["id"] not in ids
    assert kept["id"] in ids
    await provider.close()


def test_decay_score_uses_last_access_and_hit_count(tmp_path, monkeypatch):
    provider = _provider(tmp_path, monkeypatch)
    now = datetime(2026, 11, 6, 12, 0, 0)
    created = (now - timedelta(days=120)).isoformat()

    stale = provider._decay_score(created, "semantic", now)
    accessed = provider._decay_score(
        created, "semantic", now, last_accessed_at=now.isoformat()
    )
    popular = provider._decay_score(
        created,
        "semantic",
        now,
        last_accessed_at=now.isoformat(),
        hit_count=25,
    )

    assert stale == pytest.approx(0.5488, rel=1e-3)
    assert accessed == pytest.approx(1.0)
    assert popular == pytest.approx(1.5)
    assert stale < accessed < popular


@pytest.mark.asyncio
async def test_forget_decayed_keeps_recently_accessed_memories(tmp_path, monkeypatch):
    provider = _provider(tmp_path, monkeypatch)
    unused = await provider.add("old unused note", metadata={"memory_tier": "working"})
    used = await provider.add("old recalled note", metadata={"memory_tier": "working"})

    stale_at = (datetime.now() - timedelta(days=120)).isoformat()
    now = datetime.now().isoformat()
    provider._sync_db.execute(
        "UPDATE memories SET created_at = ? WHERE id IN (?, ?)",
        (stale_at, unused["id"], used["id"]),
    )
    provider._sync_db.execute(
        "UPDATE memory_meta SET created_at = ?, updated_at = ? WHERE id = ?",
        (stale_at, stale_at, unused["id"]),
    )
    provider._sync_db.execute(
        "UPDATE memory_meta SET created_at = ?, updated_at = ?, "
        "last_accessed_at = ?, hit_count = 3 WHERE id = ?",
        (stale_at, stale_at, now, used["id"]),
    )
    provider._sync_db.commit()

    report = await provider.forget_decayed(min_age_days=30, decay_threshold=0.1)
    assert report["candidates"] == 1
    assert report["deleted"] == 1

    archived = await provider.list_deleted_memories()
    assert [item["id"] for item in archived] == [unused["id"]]
    await provider.close()


@pytest.mark.asyncio
async def test_tier_report_reports_distribution_and_candidates(tmp_path, monkeypatch):
    provider = _provider(tmp_path, monkeypatch)
    await provider.add("recent semantic fact")
    old = await provider.add(
        "old episodic event", metadata={"memory_tier": "episodic"}
    )
    archived = await provider.add("archived fact")
    await provider.soft_delete_memory(archived["id"], "superseded")

    stale_at = (datetime.now() - timedelta(days=400)).isoformat()
    provider._sync_db.execute(
        "UPDATE memories SET created_at = ? WHERE id = ?", (stale_at, old["id"])
    )
    provider._sync_db.execute(
        "UPDATE memory_meta SET created_at = ?, updated_at = ? WHERE id = ?",
        (stale_at, stale_at, old["id"]),
    )
    provider._sync_db.commit()

    report = await provider.tier_report(min_age_days=30, decay_threshold=0.1)
    distribution = {row["tier"]: row for row in report["distribution"]}

    assert report["user_id"] == "all"
    assert distribution["semantic"]["total"] == 2
    assert distribution["semantic"]["deleted"] == 1
    assert distribution["episodic"]["total"] == 1
    assert report["decaying"] == 1
    assert report["candidates"] == 1
    assert report["next"][0]["id"] == old["id"]
    assert report["next"][0]["tier"] == "episodic"
    await provider.close()


def test_tiers_parser_and_handler(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace

    import memento.cli as cli

    args = cli._build_parser().parse_args(["tiers", "--json", "--limit", "2"])
    assert args.command == "tiers"
    assert args.user is None
    assert args.limit == 2

    class _Provider:
        async def tier_report(self, **kwargs):
            assert kwargs["limit"] == 2
            return {
                "user_id": "all",
                "total": 3,
                "distribution": [{"tier": "semantic", "total": 3, "deleted": 0}],
                "decaying": 1,
                "candidates": 0,
                "next": [],
                "threshold": 0.1,
                "min_age_days": 30.0,
            }

    async def _fake_get_provider(workspace_root=None):
        return SimpleNamespace(provider=_Provider())

    monkeypatch.setattr(cli, "_get_provider", _fake_get_provider)
    asyncio.run(cli._handle_tiers(args))

    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 3
    assert payload["user_id"] == "all"


class TestGcCommand:
    def test_parser_accepts_prune_stale(self):
        from memento.cli import _build_parser

        args = _build_parser().parse_args(["gc", "--prune-stale"])
        assert args.prune_stale is True
        assert args.min_age_days == 30.0
        assert args.threshold == 0.1

    def test_gc_dry_run_reports_candidates(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        from memento.cli import _handle_gc

        asyncio.run(
            _handle_gc(
                argparse.Namespace(
                    prune_stale=False,
                    dry_run=True,
                    min_age_days=30.0,
                    threshold=0.1,
                    user="default",
                    json=True,
                )
            )
        )

        assert '"candidates": 0' in capsys.readouterr().out
