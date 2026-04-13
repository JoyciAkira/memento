import sqlite3
import uuid
from datetime import datetime
from memento.redaction import redact_secrets
import logging
import os
from typing import List, Dict, Any, Optional
from memento.knowledge_graph import KnowledgeGraph
from mem0 import Memory
from memento.ontology import OntologyManager

logger = logging.getLogger(__name__)

class MementoGraphProvider:
    """
    A GraphStore provider for mem0ai that uses MemPalace's local SQLite KnowledgeGraph.
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
        """Delete specific edges (in MemPalace this means invalidating them)."""
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            relationship = edge.get("relationship")
            
            if source and target and relationship:
                self.kg.invalidate(subject=source, predicate=relationship, obj=target)

class MementoProvider:
    def __init__(self, db_path: Optional[str] = None):
        # We manually inject the MemPalace graph store into mem0.Memory
        # because "custom" provider is not natively supported in mem0's pydantic config.
        # Note: OPENAI_API_KEY must be set in environment for mem0 to work.
        
        # Check if API key is set to avoid crashing on init if not provided
        # The user of this MCP should have OPENAI_API_KEY in their env.
        if not os.environ.get("OPENAI_API_KEY"):
            # Set a dummy key to pass validation if not present, though add() will fail
            os.environ["OPENAI_API_KEY"] = "sk-dummy"
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
        self._init_db()
        
        self.kg = MementoGraphProvider({"db_path": db_path})

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute('''
                CREATE VIRTUAL TABLE IF NOT EXISTS memories 
                USING fts5(id UNINDEXED, user_id UNINDEXED, text, created_at UNINDEXED, metadata UNINDEXED);
            ''')
            conn.commit()

    def add(self, text: str, user_id: str = "default", metadata: dict = None) -> Dict[str, Any]:
        text = redact_secrets(text)
        memory_id = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        import json

        meta = dict(metadata) if isinstance(metadata, dict) else {}
        workspace_root = os.environ.get("MEMENTO_DIR")
        if isinstance(workspace_root, str) and workspace_root.strip():
            abs_root = os.path.abspath(workspace_root)
            meta.setdefault("workspace_root", abs_root)
            meta.setdefault("workspace_name", os.path.basename(abs_root))

        meta_str = json.dumps(meta) if meta else "{}"
        
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO memories (id, user_id, text, created_at, metadata) VALUES (?, ?, ?, ?, ?)",
                (memory_id, user_id, text, created_at, meta_str)
            )
            conn.commit()
            
        if self.kg:
            try:
                self.kg.add(text)
            except Exception as e:
                logger.warning(f"Failed to add to KG: {e}")
            
        return {"id": memory_id, "memory": text, "event": "ADD"}

    def search(self, query: str, user_id: str = "default", limit: int = 100, filters: dict = None) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            fts_query = " OR ".join([f"{word}*" for word in query.split() if len(word) > 2])
            if not fts_query:
                fts_query = f"{query}*"
                
            filter_sql = ""
            filter_params = []
            if filters:
                for k, v in filters.items():
                    filter_sql += f" AND json_extract(metadata, '$.{k}') = ?"
                    filter_params.append(v)
                
            try:
                cursor = conn.execute(
                    f"SELECT id, text, created_at FROM memories WHERE user_id = ? AND text MATCH ? {filter_sql} ORDER BY rank LIMIT ?",
                    (user_id, fts_query, *filter_params, limit)
                )
                rows = cursor.fetchall()
            except sqlite3.OperationalError:
                cursor = conn.execute(
                    f"SELECT id, text, created_at FROM memories WHERE user_id = ? AND text LIKE ? {filter_sql} LIMIT ?",
                    (user_id, f"%{query}%", *filter_params, limit)
                )
                rows = cursor.fetchall()

        results = []
        for r in rows:
            res = {"id": r["id"], "memory": r["text"], "created_at": r["created_at"]}
            if self.kg:
                try:
                    relations = self.kg.query_entity(r["text"], direction="both")
                    res["relations"] = relations
                except Exception:
                    pass
            results.append(res)
        return results

    def get_all(self, user_id: str = "default", limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        safe_limit = min(limit, 100)
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT id, text, created_at FROM memories WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (user_id, safe_limit, offset)
            )
            rows = cursor.fetchall()
            
        results = [{"id": r["id"], "memory": r["text"], "created_at": r["created_at"]} for r in rows]
        return results
