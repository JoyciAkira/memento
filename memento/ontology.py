import math
import os
from typing import List, Optional, Any

def extract_logical_namespace(filepath: str, workspace_root: str = None) -> str:
    """
    Extracts a logical namespace (e.g. module name) from a file path.
    If it's a file like src/backend/api.py, returns "backend".
    If it's just main.py, returns "".
    """
    if not filepath:
        return ""
        
    if workspace_root and filepath.startswith(workspace_root):
        filepath = os.path.relpath(filepath, workspace_root)
        
    parts = [p for p in filepath.replace('\\', '/').split('/') if p]
    
    if len(parts) <= 1:
        return ""
        
    common_roots = {"src", "app", "lib", "packages", "apps"}
    if parts[0] in common_roots:
        if len(parts) > 2:
            return parts[1]
        else:
            return ""
            
    return parts[0]

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    dot_product = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot_product / (mag1 * mag2)

class OntologyManager:
    def __init__(self, kg: Any, embedder: Any, threshold: float = 0.85):
        self.kg = kg
        self.embedder = embedder
        self.threshold = threshold

    def assign_room(self, text: str) -> Optional[str]:
        vector = self.embedder.embed(text)
        rooms = self.kg.get_all_rooms()
        
        best_match = None
        best_score = -1.0
        
        for room in rooms:
            score = cosine_similarity(vector, room["centroid"])
            if score > best_score:
                best_score = score
                best_match = room["name"]
                
        if best_score >= self.threshold:
            return best_match
            
        return None
