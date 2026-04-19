import os
from typing import List, Optional, Any

from memento.math_utils import cosine_similarity


def extract_logical_namespace(filepath: str, workspace_root: str | None = None) -> str:
    if not filepath:
        return ""
    if workspace_root and filepath.startswith(workspace_root):
        filepath = os.path.relpath(filepath, workspace_root)
    parts = [p for p in filepath.replace("\\", "/").split("/") if p]
    if len(parts) <= 1:
        return ""
    common_roots = {"src", "app", "lib", "packages", "apps"}
    if parts[0] in common_roots:
        if len(parts) > 2:
            return parts[1]
        else:
            return ""
    return parts[0]


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
