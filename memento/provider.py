import aiosqlite
import uuid
import json
import math
import asyncio
import re
from datetime import datetime
from memento.redaction import redact_secrets
import logging
import os
from typing import List, Dict, Any, Optional
from memento.knowledge_graph import KnowledgeGraph
from mem0 import Memory
from memento.ontology import OntologyManager
from openai import AsyncOpenAI

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

class MementoProvider:
    def __init__(self, db_path: Optional[str] = None):
        # Mem0 provider requires OPENAI_API_KEY
        if not os.environ.get("OPENAI_API_KEY"):
            logger.warning("OPENAI_API_KEY not found in environment. Mem0 requires it for LLM operations.")
        
        self.memory = Memory()
        self.graph_provider = MementoGraphProvider({"db_path": db_path})
        self.memory.graph = self.graph_provider
        self.memory.enable_graph = True
        
        class Mem0EmbedderAdapter:
            def __init__(self, memory_instance):
                self.mem = memory_instance
            def embed(self, text):
                return self.mem.embedding_model.embed(text)
                
        self.ontology = OntologyManager(
            kg=self.graph_provider.kg, 
            embedder=Mem0EmbedderAdapter(self.memory)
        )

    def add(self, text: str, user_id: str = "default", metadata: Optional[Dict[str, Any]] = None) -> Any:
        room = self.ontology.assign_room(text)
        
        if not room:
            # Fallback for now: create a general room
            room = "general-knowledge"
            vector = self.memory.embedding_model.embed(room)
            # Some versions of mem0 return a list of vectors, handle gracefully
            if isinstance(vector, list) and len(vector) > 0 and isinstance(vector[0], list):
                vector = vector[0]
            self.graph_provider.kg.add_room(room, vector)
            
        meta = metadata or {}
        meta["room"] = room
        
        return self.memory.add(text, user_id=user_id, metadata=meta)

    def search(self, query: str, user_id: str = "default") -> List[Dict[str, Any]]:
        return self.memory.search(query, user_id=user_id)

class NeuroGraphProvider:
    """
    A native, concurrent, lightweight hybrid memory provider replacing Mem0.
    Uses SQLite FTS5 for fast semantic/keyword retrieval and WAL mode to prevent locking.
    """
    def __init__(self, db_path: str = None):
        if not db_path:
            memento_dir = os.path.join(os.environ.get("MEMENTO_DIR", os.getcwd()), ".memento")
            os.makedirs(memento_dir, exist_ok=True)
            db_path = os.path.join(memento_dir, "neurograph_memory.db")
            
        self.db_path = db_path
        self.kg = MementoGraphProvider({"db_path": db_path})
        
        api_key = os.environ.get("OPENAI_API_KEY", "sk-dummy")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.embed_model = os.environ.get("MEM0_EMBEDDING_MODEL", "text-embedding-3-small")
        self.llm_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._initialized = False

    async def initialize(self):
        # Check if already initialized
        if self._initialized:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            await db.execute('''
                CREATE VIRTUAL TABLE IF NOT EXISTS memories 
                USING fts5(id UNINDEXED, user_id UNINDEXED, text, created_at UNINDEXED, metadata UNINDEXED);
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS memory_embeddings (
                    id TEXT PRIMARY KEY,
                    embedding TEXT
                );
            ''')
            await db.commit()
        self._initialized = True

    async def _get_embedding(self, text: str) -> List[float]:
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
        
        # Insert FTS5 and embedding data using redacted text
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO memories (id, user_id, text, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
                (memory_id, user_id, redacted_text, created_at, meta_str)
            )
            await db.execute(
                "INSERT INTO memory_embeddings (id, embedding) VALUES (?, ?)",
                (memory_id, emb_str)
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
        
        async with aiosqlite.connect(self.db_path) as db:
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
                
            # FTS5 search
            try:
                cursor = await db.execute(
                    f"SELECT id, text, created_at, bm25(memories) as fts_score FROM memories WHERE user_id = ? AND memories MATCH ? {filter_sql} LIMIT 200",
                    (user_id, fts_query, *filter_params)
                )
                fts_rows = await cursor.fetchall()
            except Exception as e:
                logger.warning(f"FTS MATCH failed: {e}. Fallback to LIKE.")
                # If FTS MATCH fails, fallback to LIKE
                cursor = await db.execute(
                    f"SELECT id, text, created_at, 1000000 as fts_score FROM memories WHERE user_id = ? AND text LIKE ? {filter_sql} LIMIT 200",
                    (user_id, f"%{query}%", *filter_params)
                )
                fts_rows = await cursor.fetchall()

            cursor = await db.execute(
                f"SELECT id, text, created_at FROM memories WHERE user_id = ? {filter_sql} ORDER BY created_at DESC LIMIT 200",
                (user_id, *filter_params)
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
                cursor = await db.execute(
                    f"SELECT m.id, m.text, m.created_at, e.embedding FROM memories m LEFT JOIN memory_embeddings e ON m.id = e.id WHERE m.user_id = ? {filter_sql} AND m.id IN ({placeholders})",
                    (user_id, *filter_params, *candidate_ids)
                )
                candidate_rows = await cursor.fetchall()

        # Calculate semantic scores
        semantic_scores = {}
        row_map = {}
        for row in candidate_rows:
            row_id = row["id"]
            row_map[row_id] = row
            emb_str = row["embedding"]
            if emb_str and query_emb:
                try:
                    vec = json.loads(emb_str)
                    score = self._cosine_similarity(query_emb, vec)
                    semantic_scores[row_id] = score
                except Exception:
                    semantic_scores[row_id] = 0.0
            else:
                semantic_scores[row_id] = 0.0

        # RRF (Reciprocal Rank Fusion)
        k_rrf = 60
        rrf_scores = {}
        
        # Rank FTS
        fts_sorted = sorted(fts_rows, key=lambda x: x["fts_score"])
        for rank, row in enumerate(fts_sorted, 1):
            rrf_scores[row["id"]] = rrf_scores.get(row["id"], 0) + 1.0 / (k_rrf + rank)
            
        # Rank Semantic
        semantic_sorted = sorted(semantic_scores.items(), key=lambda x: x[1], reverse=True)
        for rank, (row_id, score) in enumerate(semantic_sorted, 1):
            rrf_scores[row_id] = rrf_scores.get(row_id, 0) + 1.0 / (k_rrf + rank)

        recent_sorted = sorted(recent_rows, key=lambda x: x["created_at"], reverse=True)
        for rank, row in enumerate(recent_sorted, 1):
            rrf_scores[row["id"]] = rrf_scores.get(row["id"], 0) + 0.5 / (k_rrf + rank)

        # Sort by RRF score
        final_sorted = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:limit]

        results = []
        for row_id, score in final_sorted:
            r = row_map[row_id]
            res = {"id": r["id"], "memory": r["text"], "created_at": r["created_at"], "score": score}
            if self.kg:
                try:
                    relations = await asyncio.to_thread(self.kg.query_entity, r["text"], direction="both")
                    res["relations"] = relations
                except Exception:
                    pass
            results.append(res)
            
        return results

    async def get_all(self, user_id: str = "default", limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        if not self._initialized:
            await self.initialize()
            
        safe_limit = min(limit, 100)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, text, created_at FROM memories WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (user_id, safe_limit, offset)
            )
            rows = await cursor.fetchall()
            
        results = [{"id": r["id"], "memory": r["text"], "created_at": r["created_at"]} for r in rows]
        return results
