import aiosqlite
import sqlite3
import uuid
import json
import math
import asyncio
import re
from datetime import datetime
from openai import AsyncOpenAI
from memento.redaction import redact_secrets
from memento.math_utils import cosine_similarity
from memento.goal_store import GoalStore
from memento.kg_storage import migrate_kg_tables_if_needed, resolve_kg_db_path
import logging
import os
from typing import List, Dict, Any, Optional
from memento.knowledge_graph import KnowledgeGraph
from memento.workspace_paths import resolve_workspace_root

logger = logging.getLogger(__name__)

VALID_MEMORY_TIERS = frozenset({"working", "episodic", "semantic"})
_NOT_DELETED_SQL = "id NOT IN (SELECT id FROM memory_meta WHERE is_deleted = 1)"
_NOT_DELETED_M_SQL = "m.id NOT IN (SELECT id FROM memory_meta WHERE is_deleted = 1)"
_HIT_BOOST_WEIGHT = 0.2
_MAX_HIT_BOOST = 1.5
_ACCESS_TRACK_LIMIT = 10


class MementoGraphProvider:
    """
    A GraphStore provider for mem0ai that uses Memento's local SQLite KnowledgeGraph.
    This allows Mem0 to use a local, zero-cost, PageRank-optimized graph database.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        db_path = self.config.get("db_path")
        self.kg = KnowledgeGraph(db_path=db_path)
        logger.info(f"Initialized MementoGraphProvider at {self.kg.db_path}")

    def add(self, *args, **kwargs) -> None:
        edges = args[0] if len(args) > 0 else kwargs.get("edges", [])
        if not edges and len(args) > 1:
            edges = args[1]

        for edge in edges:
            if not isinstance(edge, dict):
                continue
            source = edge.get("source")
            target = edge.get("target")
            relationship = edge.get("relationship")

            if not all([source, target, relationship]):
                logger.warning(f"Skipping invalid edge: {edge}")
                continue

            self.kg.add_triple(
                subject=str(source),
                predicate=str(relationship),
                obj=str(target),
                source_file="mem0_integration",
            )

    def get_all(self, **kwargs) -> List[Dict[str, Any]]:
        """Get all edges in Mem0 format."""
        triples = self.kg.timeline()
        mem0_edges = []
        for t in triples:
            if t["current"]:
                mem0_edges.append(
                    {
                        "source": t["subject"],
                        "relationship": t["predicate"],
                        "target": t["object"],
                    }
                )
        return mem0_edges

    def search(self, *args, **kwargs) -> List[Dict[str, Any]]:
        query = args[0] if len(args) > 0 else kwargs.get("query", "")
        limit = kwargs.get("limit", 100)

        results = self.kg.query_entity(str(query), direction="both")

        mem0_edges = []
        for r in results:
            if not r["current"]:
                continue

            mem0_edges.append(
                {
                    "source": r["subject"],
                    "relationship": r["predicate"],
                    "target": r["object"],
                }
            )

        return mem0_edges[:limit]

    def delete(self, edges: List[Dict[str, Any]], **kwargs) -> None:
        """Delete specific edges (in Memento this means invalidating them)."""
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            relationship = edge.get("relationship")

            if source and target and relationship:
                self.kg.invalidate(subject=source, predicate=relationship, obj=target)

    def close(self) -> None:
        """Release the persistent knowledge-graph connection."""
        self.kg.close()


class NeuroGraphProvider:
    """
    A native, concurrent, lightweight hybrid memory provider replacing Mem0.
    Uses SQLite FTS5 + WAL. Due connessioni aiosqlite (write / read) riducono contesa:
    scritture serializzate su `_write_lock`, letture su `_read_lock` (compatibile WAL con
    INSERT concorrenti). I/O trace e query KG non tengono lock SQLite.
    """

    def __init__(self, db_path: str | None = None, workspace_root: str | None = None):
        self.workspace_root = resolve_workspace_root(workspace_root)
        if not db_path:
            memento_dir = os.path.join(self.workspace_root, ".memento")
            os.makedirs(memento_dir, exist_ok=True, mode=0o700)
            try:
                os.chmod(memento_dir, 0o700)
            except Exception:
                pass
            db_path = os.path.join(memento_dir, "neurograph_memory.db")

        self.db_path: str = db_path
        # Use shared KG if MEMENTO_SHARED_KG_PATH is set (federation)
        from memento.settings import settings as _s_init

        self.kg_db_path = (
            _s_init.shared_kg_path
            if _s_init.shared_kg_path
            else resolve_kg_db_path(db_path)
        )
        self.kg = MementoGraphProvider({"db_path": self.kg_db_path})
        self._goal_store = GoalStore(db_path)

        # Code grounding is optional: it only reads the code index DB and does
        # nothing when the workspace has never been synced.
        self.code_grounder = None
        if db_path and str(db_path) != ":memory:":
            try:
                from memento.code_grounding import MemoryGrounder

                db_dir = os.path.dirname(os.path.abspath(str(db_path)))
                project_root = (
                    os.path.dirname(db_dir)
                    if os.path.basename(db_dir) == ".memento"
                    else db_dir
                )
                self.code_grounder = MemoryGrounder(project_root)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(f"Code grounding disabled: {exc}")

        from memento.settings import settings as _s

        self.embedding_backend = _s.embedding_backend
        self.embed_model = _s.embedding_model

        self.llm_client = None
        if self.embedding_backend == "openai":
            if not _s.openai_api_key:
                logger.warning("OPENAI_API_KEY not set; embedding backend disabled.")
                self.embedding_backend = "none"
                self.embed_model = "none"
            else:
                self.embed_model = _s.embedding_model
                self.llm_client = AsyncOpenAI(
                    api_key=_s.openai_api_key, base_url=_s.openai_base_url
                )
        else:
            self.embed_model = _s.embedding_model
        self._local_embedder = None
        if self.embedding_backend == "local":
            try:
                from memento.local_embeddings import LocalEmbeddingBackend

                self._local_embedder = LocalEmbeddingBackend()
                self.embed_model = "BAAI/bge-small-en-v1.5"
            except ImportError:
                logger.warning("fastembed not installed. Local embeddings disabled.")
                self.embedding_backend = "none"
                self.embed_model = "none"
        self._initialized = False
        self._db: aiosqlite.Connection | None = None
        self._db_read: aiosqlite.Connection | None = None
        self._sync_db: sqlite3.Connection | None = None
        self._write_lock = asyncio.Lock()
        self._read_lock = asyncio.Lock()
        from memento.settings import settings as _settings

        self._decay_lambda = _settings.decay_lambda
        self._last_external_write_at: str | None = None
        self._watcher_task: asyncio.Task | None = None

    async def initialize(self):
        if self._initialized:
            return
        async with self._write_lock:
            if self._initialized:
                return
            # Enterprise self-heal: detect a corrupted DB, back it up, and let the
            # subsequent connect recreate a fresh store instead of crashing.
            from memento.db_guard import ensure_healthy_db

            ensure_healthy_db(self.db_path, label="memory")
            if getattr(self, "kg_db_path", None):
                ensure_healthy_db(self.kg_db_path, label="kg")

            from memento.migrations.runner import MigrationRunner
            from memento.migrations.versions import get_all_migrations

            runner = MigrationRunner(self.db_path)
            for version, name, fn in get_all_migrations():
                runner.register(version, name, fn)

            await asyncio.to_thread(runner.run)
            await asyncio.to_thread(
                migrate_kg_tables_if_needed, self.db_path, self.kg_db_path
            )

            self._db = await aiosqlite.connect(self.db_path)
            self._db.row_factory = aiosqlite.Row
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA busy_timeout=8000")
            await self._db.execute("PRAGMA synchronous=NORMAL")
            await self._db.commit()

            self._db_read = await aiosqlite.connect(self.db_path)
            self._db_read.row_factory = aiosqlite.Row
            await self._db_read.execute("PRAGMA journal_mode=WAL")
            await self._db_read.execute("PRAGMA busy_timeout=8000")
            try:
                await self._db_read.execute("PRAGMA query_only=ON")
            except Exception:
                pass
            await self._db_read.commit()

            self._initialized = True

            from memento.memory.orchestrator import MemoryOrchestrator

            self._sync_db = sqlite3.connect(self.db_path)
            self._sync_db.row_factory = sqlite3.Row
            self.orchestrator = MemoryOrchestrator(self._sync_db)
            self.orchestrator.enable_vsa_index(self.db_path)
            await asyncio.to_thread(self._ensure_vsa_backfilled)

            # Start cross-agent WAL watcher (30s poll) — store task for clean shutdown
            if self._watcher_task is None or self._watcher_task.done():
                self._watcher_task = asyncio.ensure_future(
                    self._watch_external_writes()
                )

            # Federation: start server or connect as client based on socket existence
            from memento.settings import settings as _sfed

            if _sfed.federation_socket:
                await self._start_federation(_sfed.federation_socket)

    async def close(self) -> None:
        """Cancel background tasks and close DB connections."""
        if self._watcher_task and not self._watcher_task.done():
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass
        # Federation cleanup
        if hasattr(self, "_fed_server") and self._fed_server:
            try:
                await self._fed_server.stop()
            except Exception:
                pass
        if hasattr(self, "_fed_client") and self._fed_client:
            try:
                await self._fed_client.stop()
            except Exception:
                pass
        if self._db:
            try:
                await self._db.close()
            except Exception:
                pass
            self._db = None
        if self._db_read:
            try:
                await self._db_read.close()
            except Exception:
                pass
            self._db_read = None
        if self._sync_db is not None:
            try:
                self._sync_db.close()
            except Exception:
                pass
            self._sync_db = None
        if self.kg:
            try:
                self.kg.close()
            except Exception:
                pass

    async def _start_federation(self, socket_path: str) -> None:
        """Start federation server (if socket free) or client (if server already running)."""
        from memento.federation import FederationServer, FederationClient

        self._fed_server = None
        self._fed_client = None
        if os.path.exists(socket_path):
            # Another instance is already the server — connect as client
            async def _on_write(event: dict) -> None:
                try:
                    self.orchestrator.l1.clear()
                    logger.info(
                        f"Federation push received ({event.get('type')}), L1 invalidated"
                    )
                    self._last_external_write_at = event.get("ts", "")
                except Exception:
                    pass

            self._fed_client = FederationClient(socket_path, _on_write)
            self._fed_client.start()
            logger.info(f"Federation client started → {socket_path}")
        else:
            # First instance — become the server
            self._fed_server = FederationServer(socket_path)
            try:
                await self._fed_server.start()
                logger.info(f"Federation server started ← {socket_path}")
            except Exception as e:
                logger.warning(f"Federation server failed to start: {e}")
                self._fed_server = None

    async def _watch_external_writes(self) -> None:
        """Poll every 30s for writes by other processes sharing the same DB (cross-agent WAL)."""
        while True:
            try:
                await asyncio.sleep(30)
                if not self._initialized or self._db_read is None:
                    continue
                async with self._read_lock:
                    cursor = await self._db_read.execute(
                        "SELECT MAX(created_at) as latest FROM memory_meta"
                    )
                    row = await cursor.fetchone()
                latest = row["latest"] if row else None
                if latest and latest != self._last_external_write_at:
                    if self._last_external_write_at is not None:
                        # Another process wrote — invalidate L1 so next search re-fetches
                        try:
                            self.orchestrator.l1.clear()
                            logger.info(
                                f"Cross-agent write detected ({latest}), L1 cache invalidated"
                            )
                        except Exception:
                            pass
                    self._last_external_write_at = latest
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"_watch_external_writes error: {e}")

    def _ensure_vsa_backfilled(self) -> None:
        try:
            from memento.memory.vsa_index import VSAIndex

            idx = VSAIndex(self.db_path)
            idx.load_from_db()
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, text, metadata, memory_tier
                FROM memories
                WHERE id NOT IN (SELECT memory_id FROM _vsa_entities)
                LIMIT 1000
                """
            ).fetchall()
            conn.close()
            for row in rows:
                try:
                    metadata = json.loads(row["metadata"] or "{}")
                except Exception:
                    metadata = {}
                if row["memory_tier"]:
                    metadata.setdefault("memory_tier", row["memory_tier"])
                idx.index_memory(row["id"], row["text"] or "", metadata)
        except Exception as e:
            logger.debug(f"VSA backfill skipped: {e}")

    def _write_search_trace_file(self, trace: dict) -> None:
        # Trace is written by default so memento_explain_search has a trace to
        # read after a search; set MEMENTO_WRITE_SEARCH_TRACE=0 to opt out.
        v = os.environ.get("MEMENTO_WRITE_SEARCH_TRACE", "1").strip().lower()
        if v in ("0", "false", "no", "off"):
            return
        try:
            traces_dir = os.path.join(os.path.dirname(self.db_path), "traces")
            os.makedirs(traces_dir, exist_ok=True)
            trace_path = os.path.join(traces_dir, "last_search.json")
            with open(trace_path, "w", encoding="utf-8") as f:
                json.dump(trace, f, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            pass

    async def _get_embedding(self, text: str) -> List[float]:
        if self.embedding_backend == "local" and self._local_embedder is not None:
            try:
                return await self._local_embedder.embed(text)
            except Exception as e:
                logger.error(f"Error getting local embedding: {e}")
                return []
        if self.embedding_backend != "openai" or self.llm_client is None:
            return []
        try:
            response = await self.llm_client.embeddings.create(
                input=text, model=self.embed_model
            )
            return response.data[0].embedding
        except Exception as e:
            # Suppress noisy logs for the dummy token error in tests
            if "sk-dummy" not in str(e):
                logger.error(f"Error getting embedding: {e}")
            return []

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        if not vec1 or not vec2:
            return 0.0
        if len(vec1) != len(vec2):
            return 0.0
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm_a = math.sqrt(sum(a * a for a in vec1))
        norm_b = math.sqrt(sum(b * b for b in vec2))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    def _decay_score(
        self,
        created_at: str,
        tier: str = "semantic",
        now: datetime | None = None,
        last_accessed_at: str | None = None,
        hit_count: int = 0,
    ) -> float:
        """Exponential temporal decay weighted by the last real access.

        Age is measured from the most recent of ``created_at`` and
        ``last_accessed_at`` so memories that keep being recalled stay
        relevant. ``hit_count`` adds a bounded logarithmic boost (max 1.5x)
        that rewards frequently retrieved memories without letting popularity
        override recency.
        """
        try:
            reference = datetime.fromisoformat(created_at)
            if last_accessed_at:
                try:
                    accessed = datetime.fromisoformat(last_accessed_at)
                    if accessed > reference:
                        reference = accessed
                except (TypeError, ValueError):
                    pass
            _now = now or datetime.now()
            age_days = max(0.0, (_now - reference).total_seconds() / 86400)
            lam = self._decay_lambda.get(
                tier, self._decay_lambda.get("semantic", 0.005)
            )
            score = math.exp(-lam * age_days)
            boost = min(
                _MAX_HIT_BOOST,
                1.0 + _HIT_BOOST_WEIGHT * math.log1p(max(0, int(hit_count))),
            )
            return score * boost
        except Exception:
            return 1.0

    async def add(
        self, text: str, user_id: str = "default", metadata: dict | None = None
    ) -> Dict[str, Any]:
        if not self._initialized:
            await self.initialize()

        # Redact secrets before embedding
        redacted_text = redact_secrets(text)
        memory_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()

        meta = dict(metadata) if isinstance(metadata, dict) else {}
        meta.setdefault("workspace_root", self.workspace_root)
        meta.setdefault("workspace_name", os.path.basename(self.workspace_root))

        memory_tier = str(meta.get("memory_tier", "semantic")).strip().lower()
        if memory_tier not in VALID_MEMORY_TIERS:
            memory_tier = "semantic"

        meta_str = json.dumps(meta) if meta else "{}"

        embedding = await self._get_embedding(redacted_text)
        emb_str = json.dumps(embedding) if embedding else "[]"

        async with self._write_lock:
            db = self._db
            assert db is not None
            await db.execute(
                "INSERT INTO memories (id, user_id, text, created_at, metadata, memory_tier) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (memory_id, user_id, redacted_text, created_at, meta_str, memory_tier),
            )
            await db.execute(
                "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?)",
                (memory_id, emb_str),
            )
            await db.commit()

        try:
            await asyncio.to_thread(
                self.orchestrator._vsa_index.index_memory,
                memory_id,
                redacted_text,
                {**meta, "memory_tier": memory_tier},
            )
        except Exception as e:
            logger.debug(f"VSA indexing skipped for {memory_id}: {e}")

        # Wire importance from MemoryGovernor into L1 working memory
        try:
            from memento.memory.governor import MemoryGovernor

            _gov = MemoryGovernor()
            _surprise = float(
                meta.get("prediction_error", meta.get("surprise_score", 0.0)) or 0.0
            )
            _signal = _gov.score(
                memory_id=memory_id,
                semantic_similarity=1.0,
                vsa_resonance=1.0,
                created_at=created_at,
                hit_count=0,
                surprise=_surprise,
            )
            _importance = float(_signal.strength)
            if memory_tier == "working":
                self.orchestrator.l1.add(
                    memory_id, redacted_text, meta, importance=_importance
                )
        except Exception as e:
            logger.debug(f"L1 importance wiring skipped: {e}")

        try:
            await self._record_autonomous_memory_signal(memory_id, redacted_text, meta)
        except Exception as e:
            logger.debug(f"Autonomous memory signal skipped for {memory_id}: {e}")

        if self.kg:
            try:
                await asyncio.to_thread(self.kg.add, redacted_text)
            except Exception as e:
                logger.warning(f"Failed to add to KG: {e}")

        if self.code_grounder is not None:
            try:
                knowledge_graph = self.kg.kg if self.kg else None
                await asyncio.to_thread(
                    self.code_grounder.link_memory,
                    memory_id,
                    redacted_text,
                    knowledge_graph,
                )
            except Exception as e:
                logger.debug(f"Code grounding skipped for {memory_id}: {e}")

        # Federation: broadcast write event to all connected agents
        try:
            if hasattr(self, "_fed_server") and self._fed_server:
                await self._fed_server.broadcast(
                    "write", {"ts": created_at, "id": memory_id}
                )
        except Exception:
            pass

        return {"id": memory_id, "memory": redacted_text, "event": "ADD"}

    async def _record_autonomous_memory_signal(
        self,
        memory_id: str,
        text: str,
        metadata: dict[str, Any],
    ) -> None:
        from memento.memory.governor import MemoryGovernor

        governor = MemoryGovernor()
        surprise = float(
            metadata.get("prediction_error", metadata.get("surprise_score", 0.0)) or 0.0
        )
        signal = governor.score(
            memory_id=memory_id,
            semantic_similarity=1.0,
            vsa_resonance=1.0,
            created_at=datetime.now().isoformat(),
            hit_count=0,
            surprise=surprise,
        )
        decision = governor.decide(
            signal, novelty=1.0 if metadata.get("source") == "daemon" else 0.0
        )
        now = datetime.now().isoformat()
        async with self._write_lock:
            db = self._db
            assert db is not None
            await db.execute(
                """
                INSERT OR IGNORE INTO memory_meta (id, created_at, updated_at, is_deleted)
                VALUES (?, ?, ?, 0)
                """,
                (memory_id, now, now),
            )
            await db.execute(
                """
                UPDATE memory_meta
                SET updated_at = ?,
                    hit_count = COALESCE(hit_count, 0) + ?,
                    last_accessed_at = CASE WHEN ? THEN ? ELSE last_accessed_at END
                WHERE id = ?
                """,
                (
                    now,
                    1 if decision.should_prefetch else 0,
                    1 if decision.should_inject else 0,
                    now,
                    memory_id,
                ),
            )
            await db.commit()

    async def _record_accesses(self, memory_ids: list[str]) -> None:
        """Best-effort hit tracking for the memories actually surfaced.

        Decay is measured from ``last_accessed_at``, so memories that keep being
        retrieved must have that timestamp refreshed. Only the top results count
        as accesses: a long result list should not mark every candidate as used.
        """
        if not memory_ids:
            return
        ids = list(dict.fromkeys(memory_ids))[:_ACCESS_TRACK_LIMIT]
        if not ids:
            return
        now = datetime.now().isoformat()
        placeholders = ",".join(["?"] * len(ids))
        async with self._write_lock:
            db = self._db
            assert db is not None
            await db.execute(
                f"UPDATE memory_meta SET hit_count = COALESCE(hit_count, 0) + 1, "
                f"last_accessed_at = ? WHERE id IN ({placeholders})",
                (now, *ids),
            )
            await db.commit()

    async def search(
        self,
        query: str,
        user_id: str = "default",
        limit: int = 100,
        filters: dict | None = None,
    ) -> List[Dict[str, Any]]:
        if not self._initialized:
            await self.initialize()

        query_emb = await self._get_embedding(query)
        has_query_embedding = bool(query_emb)

        async with self._read_lock:
            db = self._db_read
            assert db is not None
            db.row_factory = aiosqlite.Row
            terms = re.findall(r"[A-Za-z0-9_]{3,}", query or "")
            fts_query = (
                " OR ".join([f"{t}*" for t in terms])
                if terms
                else (query or "").strip()
            )
            if not fts_query:
                fts_query = "*"

            allowed_filter_keys = {
                "workspace_root",
                "workspace_name",
                "room",
                "module",
                "type",
            }
            filter_clauses: list[str] = []
            filter_params: list[Any] = []
            if isinstance(filters, dict):
                for k, v in filters.items():
                    if k not in allowed_filter_keys:
                        continue
                    filter_clauses.append("json_extract(metadata, ?) = ?")
                    filter_params.extend([f"$.{k}", v])

            filter_sql = (
                f" AND {' AND '.join(filter_clauses)}" if filter_clauses else ""
            )

            try:
                cursor = await db.execute(
                    f"SELECT id, text, created_at, bm25(memories) as fts_score FROM memories "
                    f"WHERE user_id IN (?, 'system') AND memories MATCH ? {filter_sql} "
                    f"AND {_NOT_DELETED_SQL} LIMIT 200",
                    (user_id, fts_query, *filter_params),
                )
                fts_rows = await cursor.fetchall()
            except Exception as e:
                logger.warning(f"FTS MATCH failed: {e}. Fallback to LIKE.")
                cursor = await db.execute(
                    f"SELECT id, text, created_at, 1000000 as fts_score FROM memories "
                    f"WHERE user_id IN (?, 'system') AND text LIKE ? {filter_sql} "
                    f"AND {_NOT_DELETED_SQL} LIMIT 200",
                    (user_id, f"%{query}%", *filter_params),
                )
                fts_rows = await cursor.fetchall()

            cursor = await db.execute(
                f"SELECT id, text, created_at FROM memories WHERE user_id IN (?, 'system') "
                f"{filter_sql} AND {_NOT_DELETED_SQL} ORDER BY created_at DESC LIMIT 200",
                (user_id, *filter_params),
            )
            recent_rows = await cursor.fetchall()

            candidate_ids: list[str] = []
            seen: set[str] = set()
            code_memory_ids: list[str] = []
            if self.code_grounder is not None and query:
                try:
                    code_memory_ids = await asyncio.to_thread(
                        self.code_grounder.memory_ids_for_query, query, 40
                    )
                except Exception as exc:
                    logger.debug(f"Code grounding candidates skipped: {exc}")
            for row_id in list(code_memory_ids) + [
                row["id"] for row in list(fts_rows) + list(recent_rows)
            ]:
                if row_id in seen:
                    continue
                seen.add(row_id)
                candidate_ids.append(row_id)
                if len(candidate_ids) >= 400:
                    break

            candidate_rows: list[aiosqlite.Row] = []
            if candidate_ids:
                placeholders = ",".join(["?"] * len(candidate_ids))
                if has_query_embedding:
                    cursor = await db.execute(
                        f"SELECT m.id, m.text, m.created_at, m.memory_tier, e.embedding, "
                        f"mm.hit_count AS hit_count, mm.last_accessed_at AS last_accessed_at "
                        f"FROM memories m "
                        f"LEFT JOIN memory_embeddings e ON m.id = e.id "
                        f"LEFT JOIN memory_meta mm ON mm.id = m.id "
                        f"WHERE m.user_id IN (?, 'system') {filter_sql} AND {_NOT_DELETED_M_SQL} "
                        f"AND m.id IN ({placeholders})",
                        (user_id, *filter_params, *candidate_ids),
                    )
                else:
                    cursor = await db.execute(
                        f"SELECT m.id, m.text, m.created_at, m.memory_tier, "
                        f"mm.hit_count AS hit_count, mm.last_accessed_at AS last_accessed_at "
                        f"FROM memories m "
                        f"LEFT JOIN memory_meta mm ON mm.id = m.id "
                        f"WHERE m.user_id IN (?, 'system') {filter_sql} AND {_NOT_DELETED_M_SQL} "
                        f"AND m.id IN ({placeholders})",
                        (user_id, *filter_params, *candidate_ids),
                    )
                candidate_rows = list(await cursor.fetchall())

            semantic_scores: dict[str, float] = {}
            row_map: dict[str, aiosqlite.Row] = {}
            tier_map: dict[str, str] = {}
            for row in candidate_rows:
                row_id = row["id"]
                row_map[row_id] = row
                tier_map[row_id] = row["memory_tier"] or "semantic"
                if not has_query_embedding:
                    semantic_scores[row_id] = 0.0
                    continue
                emb_str = row["embedding"]
                if emb_str and query_emb:
                    try:
                        vec = json.loads(emb_str)
                        semantic_scores[row_id] = cosine_similarity(query_emb, vec)
                    except Exception:
                        logger.debug("Failed to decode embedding JSON", exc_info=True)
                        semantic_scores[row_id] = 0.0
                else:
                    semantic_scores[row_id] = 0.0

            k_rrf = 60
            rrf_scores: dict[str, float] = {}

            fts_sorted = sorted(fts_rows, key=lambda x: x["fts_score"])
            for rank, row in enumerate(fts_sorted, 1):
                rrf_scores[row["id"]] = rrf_scores.get(row["id"], 0) + 1.0 / (
                    k_rrf + rank
                )

            semantic_sorted = sorted(
                semantic_scores.items(), key=lambda x: x[1], reverse=True
            )
            for rank, (row_id, score) in enumerate(semantic_sorted, 1):
                rrf_scores[row_id] = rrf_scores.get(row_id, 0) + 1.0 / (k_rrf + rank)

            recent_sorted = sorted(
                recent_rows, key=lambda x: x["created_at"], reverse=True
            )
            for rank, row in enumerate(recent_sorted, 1):
                rrf_scores[row["id"]] = rrf_scores.get(row["id"], 0) + 0.5 / (
                    k_rrf + rank
                )

            # Fifth RRF lane: KG entity match — memories cited by KG triples for query entities
            try:
                kg_entity_ids: list[str] = []
                if self.kg and query:
                    _kg_triples = await asyncio.to_thread(
                        self.kg.kg.query_entity, query, direction="both"
                    )
                    for triple in _kg_triples[:20]:
                        src = triple.get("source_closet") or triple.get("source_file")
                        if src and len(src) == 36:  # UUID format → memory ID
                            kg_entity_ids.append(src)
                for rank, row_id in enumerate(kg_entity_ids, 1):
                    rrf_scores[row_id] = rrf_scores.get(row_id, 0) + 0.8 / (
                        k_rrf + rank
                    )
            except Exception:
                pass

            # Code-grounding lane: memories explicitly linked to the symbols
            # named in the query, ignoring links whose file hash is stale.
            for rank, row_id in enumerate(code_memory_ids, 1):
                rrf_scores[row_id] = rrf_scores.get(row_id, 0) + 0.9 / (k_rrf + rank)

            # Apply temporal decay: score *= e^(-lambda * age_days) per tier
            # Hoist datetime.now() to avoid calling it once per candidate row
            _now = datetime.now()
            for row_id in list(rrf_scores.keys()):
                row_snap = row_map.get(row_id)
                if row_snap is not None:
                    tier = tier_map.get(row_id, "semantic")
                    rrf_scores[row_id] *= self._decay_score(
                        row_snap["created_at"],
                        tier,
                        _now,
                        last_accessed_at=row_snap["last_accessed_at"],
                        hit_count=row_snap["hit_count"] or 0,
                    )

            final_sorted = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[
                :limit
            ]

            trace = {
                "query": query,
                "filters": filters or {},
                "lanes": {
                    "fts": [
                        {"id": row["id"], "score": float(1.0 / (k_rrf + rank))}
                        for rank, row in enumerate(fts_sorted[:20], 1)
                    ],
                    "dense": [
                        {"id": row_id, "score": float(1.0 / (k_rrf + rank))}
                        for rank, (row_id, _score) in enumerate(semantic_sorted[:20], 1)
                    ],
                    "recency": [
                        {"id": row["id"], "score": float(0.5 / (k_rrf + rank))}
                        for rank, row in enumerate(recent_sorted[:20], 1)
                    ],
                    "code": [
                        {"id": row_id, "score": float(0.9 / (k_rrf + rank))}
                        for rank, row_id in enumerate(code_memory_ids[:20], 1)
                    ],
                },
                "final": [
                    {"id": row_id, "score": float(score)}
                    for row_id, score in final_sorted[:50]
                ],
            }
            rows_snapshot: dict[str, dict[str, Any]] = {
                rid: {
                    "id": r["id"],
                    "text": r["text"],
                    "created_at": r["created_at"],
                    "memory_tier": r["memory_tier"] or "semantic",
                }
                for rid, r in row_map.items()
            }

        await asyncio.to_thread(self._write_search_trace_file, trace)

        results: list[Dict[str, Any]] = []
        if self.kg:
            try:
                all_names = [
                    rows_snapshot[row_id]["text"]
                    for row_id, _ in final_sorted
                    if row_id in rows_snapshot
                ]
                batch_relations = await asyncio.to_thread(
                    self.kg.kg.query_entities_batch, all_names
                )
                for row_id, score in final_sorted:
                    snap = rows_snapshot.get(row_id)
                    if not snap:
                        continue
                    res = {
                        "id": snap["id"],
                        "memory": snap["text"],
                        "created_at": snap["created_at"],
                        "score": score,
                    }
                    entity_id = self.kg.kg._entity_id(snap["text"])
                    if entity_id in batch_relations:
                        res["relations"] = batch_relations[entity_id]
                    results.append(res)
            except Exception:
                logger.debug(
                    "KG batch query failed, returning results without relations"
                )
                for row_id, score in final_sorted:
                    snap = rows_snapshot.get(row_id)
                    if not snap:
                        continue
                    results.append(
                        {
                            "id": snap["id"],
                            "memory": snap["text"],
                            "created_at": snap["created_at"],
                            "score": score,
                        }
                    )
        else:
            for row_id, score in final_sorted:
                snap = rows_snapshot.get(row_id)
                if not snap:
                    continue
                results.append(
                    {
                        "id": snap["id"],
                        "memory": snap["text"],
                        "created_at": snap["created_at"],
                        "score": score,
                    }
                )

        if self.code_grounder is not None and results:
            try:
                links = await asyncio.to_thread(
                    self.code_grounder.links_for_memories,
                    [r["id"] for r in results],
                )
                for result in results:
                    own = links.get(result["id"])
                    if own:
                        result["code_links"] = own
            except Exception as e:
                logger.debug(f"Code grounding lookup skipped: {e}")

        try:
            await self._record_accesses(
                [r["id"] for r in results[:_ACCESS_TRACK_LIMIT]]
            )
        except Exception as e:
            logger.debug(f"Access tracking skipped: {e}")

        return results

    async def forget_decayed(
        self,
        min_age_days: float = 30.0,
        decay_threshold: float = 0.1,
        user_id: str = "default",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Soft-delete memories whose decay score has fallen below threshold."""
        if not self._initialized:
            await self.initialize()

        async with self._read_lock:
            db = self._db_read
            assert db is not None
            cursor = await db.execute(
                "SELECT m.id, m.created_at, m.memory_tier, "
                "mm.hit_count AS hit_count, mm.last_accessed_at AS last_accessed_at, "
                "mm.is_deleted AS is_deleted "
                "FROM memories m LEFT JOIN memory_meta mm ON mm.id = m.id "
                "WHERE m.user_id = ?",
                (user_id,),
            )
            rows = await cursor.fetchall()

        now = datetime.now()
        to_delete: list[str] = []
        for row in rows:
            try:
                age = (now - datetime.fromisoformat(row["created_at"])).days
            except Exception:
                continue
            if age < min_age_days:
                continue
            if row["is_deleted"]:
                continue
            tier = row["memory_tier"] or "semantic"
            score = self._decay_score(
                row["created_at"],
                tier,
                now,
                last_accessed_at=row["last_accessed_at"],
                hit_count=row["hit_count"] or 0,
            )
            if score < decay_threshold:
                to_delete.append(row["id"])

        if not dry_run and to_delete:
            reason = f"decay_score<{decay_threshold} after {min_age_days}d"
            deleted_at = now.isoformat()
            async with self._write_lock:
                db = self._db
                assert db is not None
                for mid in to_delete:
                    await db.execute(
                        "UPDATE memory_meta SET is_deleted=1, deleted_at=?, delete_reason=? WHERE id=?",
                        (deleted_at, reason, mid),
                    )
                await db.commit()

        return {
            "candidates": len(to_delete),
            "deleted": len(to_delete) if not dry_run else 0,
            "dry_run": dry_run,
            "threshold": decay_threshold,
            "min_age_days": min_age_days,
        }

    async def tier_report(
        self,
        user_id: Optional[str] = None,
        min_age_days: float = 30.0,
        decay_threshold: float = 0.1,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Summarize tier distribution, decay state, and the next GC candidates."""
        if not self._initialized:
            await self.initialize()

        where = "WHERE m.user_id = ?" if user_id else ""
        params = (user_id,) if user_id else ()
        async with self._read_lock:
            db = self._db_read
            assert db is not None
            cursor = await db.execute(
                "SELECT COALESCE(NULLIF(TRIM(m.memory_tier), ''), 'unset') AS tier, "
                "COUNT(*) AS total, "
                "SUM(CASE WHEN mm.is_deleted = 1 THEN 1 ELSE 0 END) AS deleted "
                "FROM memories m LEFT JOIN memory_meta mm ON mm.id = m.id "
                f"{where} GROUP BY 1 ORDER BY 2 DESC",
                params,
            )
            tier_rows = await cursor.fetchall()
            cursor = await db.execute(
                "SELECT m.id, m.created_at, m.memory_tier, mm.hit_count AS hit_count, "
                "mm.last_accessed_at AS last_accessed_at, mm.is_deleted AS is_deleted "
                "FROM memories m LEFT JOIN memory_meta mm ON mm.id = m.id "
                f"{where}",
                params,
            )
            rows = await cursor.fetchall()

        now = datetime.now()
        decaying = 0
        candidates: List[Dict[str, Any]] = []
        for row in rows:
            if row["is_deleted"]:
                continue
            try:
                created = datetime.fromisoformat(row["created_at"])
            except Exception:
                continue
            tier = row["memory_tier"] or "semantic"
            score = self._decay_score(
                row["created_at"],
                tier,
                now,
                last_accessed_at=row["last_accessed_at"],
                hit_count=row["hit_count"] or 0,
            )
            if score < 1.0:
                decaying += 1
            age_days = (now - created).total_seconds() / 86400
            if age_days >= min_age_days and score < decay_threshold:
                candidates.append(
                    {
                        "id": row["id"],
                        "tier": tier,
                        "score": round(score, 6),
                        "age_days": round(age_days, 1),
                    }
                )
        candidates.sort(key=lambda item: item["score"])

        return {
            "user_id": user_id or "all",
            "total": sum(row["total"] for row in tier_rows),
            "distribution": [
                {
                    "tier": row["tier"],
                    "total": row["total"],
                    "deleted": row["deleted"] or 0,
                }
                for row in tier_rows
            ],
            "decaying": decaying,
            "candidates": len(candidates),
            "next": candidates[: max(0, limit)],
            "threshold": decay_threshold,
            "min_age_days": min_age_days,
        }

    async def get_all(
        self, user_id: str = "default", limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        if not self._initialized:
            await self.initialize()

        safe_limit = min(limit, 100)
        async with self._read_lock:
            db = self._db_read
            assert db is not None
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, text, created_at FROM memories WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (user_id, safe_limit, offset),
            )
            rows = await cursor.fetchall()

        results = [
            {"id": r["id"], "memory": r["text"], "created_at": r["created_at"]}
            for r in rows
        ]
        return results

    async def consolidate(
        self,
        threshold: float = 0.92,
        min_age_hours: float = 1.0,
        batch_size: int = 200,
    ) -> Dict[str, Any]:
        """Run a consolidation pass to merge near-duplicate memories."""
        if not self._initialized:
            await self.initialize()

        from memento.consolidation import ConsolidationEngine

        engine = ConsolidationEngine(
            db_path=self.db_path,
            threshold=threshold,
            min_age_hours=min_age_hours,
            batch_size=batch_size,
        )
        return await engine.consolidate()

    async def search_vnext_bundle(
        self,
        query: str,
        user_id: str = "default",
        limit: int = 50,
        filters: dict | None = None,
        trace: bool = False,
    ):
        from memento.retrieval.pipeline import retrieve_bundle

        if not self._initialized:
            await self.initialize()

        code_memory_ids: list[str] = []
        if self.code_grounder is not None and query:
            try:
                code_memory_ids = await asyncio.to_thread(
                    self.code_grounder.memory_ids_for_query, query, 40
                )
            except Exception as exc:
                logger.debug(f"Code grounding candidates skipped: {exc}")

        async with self._read_lock:
            db_read = self._db_read
            assert db_read is not None
            bundle = await retrieve_bundle(
                db_path=self.db_path,
                query=query,
                user_id=user_id,
                limit=limit,
                filters=filters,
                embed_fn=self._get_embedding,
                trace=trace,
                db=db_read,
                vsa_index=getattr(self.orchestrator, "_vsa_index", None),
                code_memory_ids=code_memory_ids,
            )
            if bundle.get("results"):
                from memento.memory.governor import MemoryGovernor

                bundle["results"] = MemoryGovernor().annotate_results(bundle["results"])
        if self.code_grounder is not None and bundle.get("results"):
            try:
                links = await asyncio.to_thread(
                    self.code_grounder.links_for_memories,
                    [r["id"] for r in bundle["results"]],
                )
                for result in bundle["results"]:
                    own = links.get(result["id"])
                    if own:
                        result["code_links"] = own
            except Exception as exc:
                logger.debug(f"Code grounding lookup skipped: {exc}")
        return bundle

    async def soft_delete_memory(
        self,
        memory_id: str,
        delete_reason: str,
        supersedes_id: str | None = None,
    ) -> Dict[str, Any]:
        if not self._initialized:
            await self.initialize()

        now = datetime.now().isoformat()

        async with self._write_lock:
            db = self._db
            assert db is not None
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT created_at FROM memories WHERE id = ? LIMIT 1",
                (memory_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                raise ValueError(f"Memory not found: {memory_id}")
            created_at = row["created_at"] or now

            await db.execute(
                """
                INSERT OR IGNORE INTO memory_meta (id, created_at, updated_at, is_deleted)
                VALUES (?, ?, ?, 0)
                """,
                (memory_id, created_at, now),
            )
            await db.execute(
                """
                UPDATE memory_meta
                SET is_deleted = 1,
                    deleted_at = ?,
                    delete_reason = ?,
                    supersedes_id = ?,
                    replaced_by_id = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, delete_reason, supersedes_id, supersedes_id, now, memory_id),
            )
            await db.commit()

        return {
            "id": memory_id,
            "is_deleted": True,
            "deleted_at": now,
            "delete_reason": delete_reason,
            "supersedes_id": supersedes_id,
        }

    async def list_deleted_memories(
        self,
        limit: int = 50,
        offset: int = 0,
        user_id: str = "default",
    ) -> List[Dict[str, Any]]:
        if not self._initialized:
            await self.initialize()

        safe_limit = min(int(limit), 200)
        safe_offset = max(int(offset), 0)

        async with self._read_lock:
            db = self._db_read
            assert db is not None
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT mm.id, m.user_id, m.created_at, mm.deleted_at, mm.delete_reason,
                       mm.supersedes_id, mm.replaced_by_id
                FROM memory_meta mm
                JOIN memories m ON m.id = mm.id
                WHERE mm.is_deleted = 1 AND m.user_id = ?
                ORDER BY mm.deleted_at DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, safe_limit, safe_offset),
            )
            rows = await cursor.fetchall()

        return [
            {
                "id": r["id"],
                "user_id": r["user_id"],
                "created_at": r["created_at"],
                "deleted_at": r["deleted_at"],
                "delete_reason": r["delete_reason"],
                "supersedes_id": r["supersedes_id"],
                "replaced_by_id": r["replaced_by_id"],
            }
            for r in rows
        ]

    async def set_goals(
        self,
        goals: List[str],
        *,
        context: str | None = None,
        mode: str = "replace",
        delete_reason: str = "replaced",
    ) -> Dict[str, Any]:
        if not self._initialized:
            await self.initialize()

        now = datetime.now().isoformat()
        batch_id = str(uuid.uuid4())

        clean_goals = [
            g.strip() for g in (goals or []) if isinstance(g, str) and g.strip()
        ]
        if not clean_goals:
            raise ValueError("goals must be a non-empty list of strings")

        if mode not in {"replace", "append"}:
            raise ValueError("mode must be 'replace' or 'append'")

        async with self._write_lock:
            db = self._db
            assert db is not None
            if mode == "replace":
                await db.execute(
                    """
                    UPDATE goals
                    SET is_active = 0,
                        is_deleted = 1,
                        deleted_at = ?,
                        delete_reason = ?,
                        replaced_by_id = ?,
                        updated_at = ?
                    WHERE is_active = 1 AND is_deleted = 0
                      AND (context IS ? OR context = ?)
                    """,
                    (now, delete_reason, batch_id, now, context, context),
                )

            inserted_ids: list[str] = []
            for g in clean_goals:
                gid = str(uuid.uuid4())
                inserted_ids.append(gid)
                goal_now = datetime.now().isoformat()
                await db.execute(
                    """
                    INSERT INTO goals (id, context, goal, created_at, updated_at, is_active, is_deleted)
                    VALUES (?, ?, ?, ?, ?, 1, 0)
                    """,
                    (gid, context, g, goal_now, goal_now),
                )

            await db.commit()

        return {
            "batch_id": batch_id,
            "inserted_ids": inserted_ids,
            "mode": mode,
            "context": context,
        }

    async def list_goals(
        self,
        *,
        context: str | None = None,
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        if not self._initialized:
            await self.initialize()

        safe_limit = min(int(limit), 200)
        safe_offset = max(int(offset), 0)

        where: list[str] = []
        params: list[Any] = []
        if context is not None:
            where.append("(context IS ? OR context = ?)")
            params.extend([context, context])
        if active_only:
            where.append("is_active = 1 AND is_deleted = 0")

        where_sql = " AND ".join(where)
        where_clause = f"WHERE {where_sql}" if where_sql else ""
        async with self._read_lock:
            db = self._db_read
            assert db is not None
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""
                SELECT id, context, goal, created_at, updated_at,
                       is_active, is_deleted, deleted_at, delete_reason, replaced_by_id
                FROM goals
                {where_clause}
                ORDER BY created_at DESC, rowid DESC
                LIMIT ? OFFSET ?
                 """,
                (*params, safe_limit, safe_offset),
            )
            rows = await cursor.fetchall()

        return [
            {
                "id": r["id"],
                "context": r["context"],
                "goal": r["goal"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "is_active": bool(r["is_active"]),
                "is_deleted": bool(r["is_deleted"]),
                "deleted_at": r["deleted_at"],
                "delete_reason": r["delete_reason"],
                "replaced_by_id": r["replaced_by_id"],
            }
            for r in rows
        ]

    async def extract_kg(self, max_memories: int = 50) -> Dict[str, Any]:
        """Extract entities and relationships from unprocessed memories into the KG."""
        if not self._initialized:
            await self.initialize()
        from memento.kg_extraction import KGExtractionEngine

        engine = KGExtractionEngine(
            db_path=self.db_path,
            kg=self.kg.kg,
            llm_client=self.llm_client,
            model=os.environ.get("MEM0_MODEL", "openai/gpt-4o-mini"),
        )
        return await engine.run_extraction_cycle(max_memories=max_memories)
