import logging
from typing import List, Dict, Any, Optional
from mempalace.knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)

class MemPalaceGraphProvider:
    """
    A GraphStore provider for mem0ai that uses MemPalace's local SQLite KnowledgeGraph.
    This allows Mem0 to use a local, zero-cost, PageRank-optimized graph database.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        db_path = self.config.get("db_path")
        self.kg = KnowledgeGraph(db_path=db_path)
        logger.info(f"Initialized MemPalaceGraphProvider at {self.kg.db_path}")

    def add(self, edges: List[Dict[str, Any]], **kwargs) -> None:
        """Add edges to the graph. Expected Mem0 format: [{'source': 'A', 'target': 'B', 'relationship': 'R'}]"""
        for edge in edges:
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
        # Convert back to Mem0 format
        mem0_edges = []
        for t in triples:
            if t["current"]: # Only return currently valid facts
                mem0_edges.append({
                    "source": t["subject"],
                    "relationship": t["predicate"],
                    "target": t["object"]
                })
        return mem0_edges

    def search(self, query: str, limit: int = 100, **kwargs) -> List[Dict[str, Any]]:
        """Search for edges related to a node (query string)."""
        # MemPalace's query_entity gets all relationships for a node
        results = self.kg.query_entity(query, direction="both")
        
        mem0_edges = []
        for r in results:
            if not r["current"]:
                continue
                
            # Convert MemPalace direction format to Mem0 source/target
            if r["direction"] == "outgoing":
                mem0_edges.append({
                    "source": r["subject"],
                    "relationship": r["predicate"],
                    "target": r["object"]
                })
            else: # incoming
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

    @classmethod
    def get_mem0_config(cls, db_path: Optional[str] = None) -> Dict[str, Any]:
        """Helper method to generate a Mem0 compatible configuration dictionary."""
        return {
            "graph_store": {
                "provider": "custom",
                "custom_class": cls,
                "config": {"db_path": db_path} if db_path else {}
            }
        }
