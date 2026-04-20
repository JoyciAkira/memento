import aiosqlite
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

logger = logging.getLogger(__name__)

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
                subject=source,
                predicate=relationship,
                obj=target,
                source_file="mem0_integration"
            )
            
    def get_all(self, **kwargs) -> List[Dict[str, Any]]:
        """Get all edges in Mem0 format."""
        triples = self.kg.timeline()
        mem0_edges = []
        for t in triples:
            if t["current"]: 
                mem0_edges.append({
                    "source": t["subject"],
                    "relationship": t["predicate"],
                    "target": t["object"]
                })
        return mem0_edges

    def search(self, *args, **kwargs) -> List[Dict[str, Any]]:
        query = args[0] if len(args) > 0 else kwargs.get("query", "")
        limit = kwargs.get("limit", 100)
        
        results = self.kg.query_entity(str(query), direction="both")
        
        mem0_edges = []
        for r in results:
            if not r["current"]:
                continue
                
            mem0_edges.append({
                "source": r["subject"],
                "relationship": r["predicate"],
                "target": r["object"]
            })
                
        return mem0_edges[:limit]

    def delete(self, edges: List[Dict[str, Any]], **kwargs) -> None:
        """Delete specific edges (in Memento this means invalidating them)."""
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            relationship = edge.get("relationship")
            
            if source and target and relationship:
                self.kg.invalidate(subject=source, predicate=relationship, obj=target)

class NeuroGraphProvider:
    """
    A native, concurrent, lightweight hybrid memory provider replacing Mem0.
    Uses SQLite FTS5 + WAL. Due connessioni aiosqlite (write / read) riducono contesa:
    scritture serializzate su `_write_lock`, letture su `_read_lock` (compatibile WAL con
    INSERT concorrenti). I/O trace e query KG non tengono lock SQLite.
    """
    def __init__(self, db_path: str = None):
        if not db_path:
            memento_dir = os.path.join(os.environ.get("MEMENTO_DIR", os.getcwd()), ".memento")
            os.makedirs(memento_dir, exist_ok=True)
            db_path = os.path.join(memento_dir, "neurograph_memory.db")
            
        self.db_path = db_path
        self.kg_db_path = resolve_kg_db_path(db_path)
        self.kg = MementoGraphProvider({"db_path": self.kg_db_path})
        self._goal_store = GoalStore(db_path)

        requested_backend = os.environ.get("MEMENTO_EMBEDDING_BACKEND", "").strip().lower()
        has_openai_key = bool(os.environ.get("OPENAI_API_KEY", "").strip())
        if requested_backend:
            self.embedding_backend = requested_backend
        else:
            self.embedding_backend = "openai" if has_openai_key else "none"

        self.llm_client = None
        if self.embedding_backend == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "").strip()
            if not api_key:
                logger.warning("OPENAI_API_KEY not set; embedding backend disabled.")
                self.embedding_backend = "none"
                self.embed_model = os.environ.get("MEM0_EMBEDDING_MODEL", "none")
            else:
                base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
                self.embed_model = os.environ.get("MEM0_EMBEDDING_MODEL", "text-embedding-3-small")
                self.llm_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        else:
            self.embed_model = os.environ.get("MEM0_EMBEDDING_MODEL", "none")
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
        self._write_lock = asyncio.Lock()
        self._read_lock = asyncio.Lock()

    async def initialize(self):
        if self._initialized:
            return
        async with self._write_lock:
            if self._initialized:
                return
            from memento.migrations.runner import MigrationRunner
            from memento.migrations.versions import get_all_migrations

            runner = MigrationRunner(self.db_path)
            for version, name, fn in get_all_migrations():
                runner.register(version, name, fn)

            await asyncio.to_thread(runner.run)
            await asyncio.to_thread(migrate_kg_tables_if_needed, self.db_path, self.kg_db_path)

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

    def _write_search_trace_file(self, trace: dict) -> None:
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
                input=text,
                model=self.embed_model
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

    async def add(self, text: str, user_id: str = "default", metadata: dict = None) -> Dict[str, Any]:
        if not self._initialized:
            await self.initialize()
            
        # Redact secrets before embedding
        redacted_text = redact_secrets(text)
        memory_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()

        meta = dict(metadata) if isinstance(metadata, dict) else {}
        workspace_root = os.environ.get("MEMENTO_DIR", os.getcwd())
        if isinstance(workspace_root, str) and workspace_root.strip():
            abs_root = os.path.abspath(workspace_root)
            meta.setdefault("workspace_root", abs_root)
            meta.setdefault("workspace_name", os.path.basename(abs_root))

        meta_str = json.dumps(meta) if meta else "{}"
        
        embedding = await self._get_embedding(redacted_text)
        emb_str = json.dumps(embedding) if embedding else "[]"

        async with self._write_lock:
            db = self._db
            assert db is not None
            await db.execute(
                "INSERT INTO memories (id, user_id, text, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
                (memory_id, user_id, redacted_text, created_at, meta_str),
            )
            await db.execute(
                "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?)",
                (memory_id, emb_str),
            )
            await db.commit()

        if self.kg:
            try:
                await asyncio.to_thread(self.kg.add, redacted_text)
            except Exception as e:
                logger.warning(f"Failed to add to KG: {e}")
            
        return {"id": memory_id, "memory": redacted_text, "event": "ADD"}

    async def search(self, query: str, user_id: str = "default", limit: int = 100, filters: dict = None) -> List[Dict[str, Any]]:
        if not self._initialized:
            await self.initialize()

        query_emb = await self._get_embedding(query)
        has_query_embedding = bool(query_emb)

        async with self._read_lock:
            db = self._db_read
            assert db is not None
            db.row_factory = aiosqlite.Row
            terms = re.findall(r"[A-Za-z0-9_]{3,}", query or "")
            fts_query = " OR ".join([f"{t}*" for t in terms]) if terms else (query or "").strip()
            if not fts_query:
                fts_query = "*"

            allowed_filter_keys = {"workspace_root", "workspace_name", "room", "module", "type"}
            filter_clauses: list[str] = []
            filter_params: list[Any] = []
            if isinstance(filters, dict):
                for k, v in filters.items():
                    if k not in allowed_filter_keys:
                        continue
                    filter_clauses.append("json_extract(metadata, ?) = ?")
                    filter_params.extend([f"$.{k}", v])

            filter_sql = f" AND {' AND '.join(filter_clauses)}" if filter_clauses else ""

            try:
                cursor = await db.execute(
                    f"SELECT id, text, created_at, bm25(memories) as fts_score FROM memories WHERE user_id = ? AND memories MATCH ? {filter_sql} LIMIT 200",
                    (user_id, fts_query, *filter_params),
                )
                fts_rows = await cursor.fetchall()
            except Exception as e:
                logger.warning(f"FTS MATCH failed: {e}. Fallback to LIKE.")
                cursor = await db.execute(
                    f"SELECT id, text, created_at, 1000000 as fts_score FROM memories WHERE user_id = ? AND text LIKE ? {filter_sql} LIMIT 200",
                    (user_id, f"%{query}%", *filter_params),
                )
                fts_rows = await cursor.fetchall()

            cursor = await db.execute(
                f"SELECT id, text, created_at FROM memories WHERE user_id = ? {filter_sql} ORDER BY created_at DESC LIMIT 200",
                (user_id, *filter_params),
            )
            recent_rows = await cursor.fetchall()

            candidate_ids: list[str] = []
            seen: set[str] = set()
            for row in list(fts_rows) + list(recent_rows):
                row_id = row["id"]
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
                        f"SELECT m.id, m.text, m.created_at, e.embedding FROM memories m "
                        f"LEFT JOIN memory_embeddings e ON m.id = e.id "
                        f"WHERE m.user_id = ? {filter_sql} AND m.id IN ({placeholders})",
                        (user_id, *filter_params, *candidate_ids),
                    )
                else:
                    cursor = await db.execute(
                        f"SELECT m.id, m.text, m.created_at FROM memories m "
                        f"WHERE m.user_id = ? {filter_sql} AND m.id IN ({placeholders})",
                        (user_id, *filter_params, *candidate_ids),
                    )
                candidate_rows = await cursor.fetchall()

            semantic_scores: dict[str, float] = {}
            row_map: dict[str, aiosqlite.Row] = {}
            for row in candidate_rows:
                row_id = row["id"]
                row_map[row_id] = row
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
                rrf_scores[row["id"]] = rrf_scores.get(row["id"], 0) + 1.0 / (k_rrf + rank)

            semantic_sorted = sorted(semantic_scores.items(), key=lambda x: x[1], reverse=True)
            for rank, (row_id, score) in enumerate(semantic_sorted, 1):
                rrf_scores[row_id] = rrf_scores.get(row_id, 0) + 1.0 / (k_rrf + rank)

            recent_sorted = sorted(recent_rows, key=lambda x: x["created_at"], reverse=True)
            for rank, row in enumerate(recent_sorted, 1):
                rrf_scores[row["id"]] = rrf_scores.get(row["id"], 0) + 0.5 / (k_rrf + rank)

            final_sorted = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:limit]

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
                },
                "final": [{"id": row_id, "score": float(score)} for row_id, score in final_sorted[:50]],
            }
            rows_snapshot: dict[str, dict[str, Any]] = {
                rid: {"id": r["id"], "text": r["text"], "created_at": r["created_at"]}
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
                batch_relations = await asyncio.to_thread(self.kg.query_entities_batch, all_names)
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
                    entity_id = self.kg._entity_id(snap["text"])
                    if entity_id in batch_relations:
                        res["relations"] = batch_relations[entity_id]
                    results.append(res)
            except Exception:
                logger.debug("KG batch query failed, returning results without relations")
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

        return results

    async def get_all(self, user_id: str = "default", limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
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

        results = [{"id": r["id"], "memory": r["text"], "created_at": r["created_at"]} for r in rows]
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

        async with self._read_lock:
            db_read = self._db_read
            assert db_read is not None
            return await retrieve_bundle(
                db_path=self.db_path,
                query=query,
                user_id=user_id,
                limit=limit,
                filters=filters,
                embed_fn=self._get_embedding,
                trace=trace,
                db=db_read,
            )

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

        clean_goals = [g.strip() for g in (goals or []) if isinstance(g, str) and g.strip()]
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

        return {"batch_id": batch_id, "inserted_ids": inserted_ids, "mode": mode, "context": context}

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

        where = ["(context IS ? OR context = ?)"]
        params: list[Any] = [context, context]
        if active_only:
            where.append("is_active = 1 AND is_deleted = 0")

        where_sql = " AND ".join(where)
        async with self._read_lock:
            db = self._db_read
            assert db is not None
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""
                SELECT id, context, goal, created_at, updated_at,
                       is_active, is_deleted, deleted_at, delete_reason, replaced_by_id
                FROM goals
                WHERE {where_sql}
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
