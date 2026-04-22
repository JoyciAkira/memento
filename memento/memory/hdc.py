import numpy as np
from typing import Dict, Tuple, List, Any

Dimensionality = 10000

class HDCEncoder:
    def __init__(self, d: int = Dimensionality):
        self.d = d
        self._concept_vectors: Dict[str, np.ndarray] = {}
        self._rng = np.random.default_rng()

    def concept(self, name: str) -> np.ndarray:
        if name not in self._concept_vectors:
            self._concept_vectors[name] = self._rng.integers(0, 2, size=self.d, dtype=np.uint8)
        return self._concept_vectors[name]

    def bind(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return np.bitwise_xor(a, b)

    def bundle(self, vectors: List[np.ndarray]) -> np.ndarray:
        if not vectors:
            raise ValueError("Cannot bundle empty list")
        arr = np.stack(vectors, axis=0)
        return (np.sum(arr, axis=0) >= (len(vectors) // 2 + 1)).astype(np.uint8)

    def permute(self, v: np.ndarray, steps: int = 1) -> np.ndarray:
        return np.roll(v, steps)

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.mean(a == b))

    def encode_relation(self, subject: str, predicate: str, obj: str) -> np.ndarray:
        s = self.concept(subject)
        p = self.concept(predicate)
        o = self.concept(obj)
        return self.bundle([self.bind(s, p), self.bind(p, o)])

    def decode_relation(self, hv: np.ndarray, top_k: int = 3) -> List[Tuple[str, float]]:
        scores: Dict[str, float] = {}
        for name, vec in self._concept_vectors.items():
            scores[name] = self.similarity(hv, vec)
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
