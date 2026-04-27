import hashlib
from typing import Dict, Tuple, List

Dimensionality = 65536

class BitVector:
    def __init__(self, value: int, d: int):
        self.value = value & ((1 << d) - 1)
        self.d = d

    def __int__(self) -> int:
        return self.value

    def __len__(self) -> int:
        return self.d

    def __iter__(self):
        for bit in range(self.d):
            yield 1 if self.value & (1 << bit) else 0

    def __array__(self, dtype=None):
        try:
            import numpy as np
        except Exception as exc:
            raise TypeError("numpy is required for array conversion") from exc
        return np.fromiter(self, dtype=dtype or np.uint8, count=self.d)

    def __eq__(self, other):
        other_value = int(other) if isinstance(other, BitVector) else int(other)
        return [((self.value >> bit) & 1) == ((other_value >> bit) & 1) for bit in range(self.d)]


class HDCEncoder:
    def __init__(self, d: int = Dimensionality, seed: int = 0):
        self.d = d
        self._concept_vectors: Dict[str, BitVector] = {}
        self._seed = seed
        self._mask = (1 << d) - 1

    def concept(self, name: str) -> BitVector:
        key = self._normalize(name)
        if key not in self._concept_vectors:
            self._concept_vectors[key] = self._vector_from_name(key)
        return self._concept_vectors[key]

    def _normalize(self, name: str) -> str:
        return " ".join(str(name).lower().strip().split())

    def _vector_from_name(self, name: str) -> BitVector:
        out = bytearray()
        counter = 0
        needed = (self.d + 7) // 8
        seed = f"{self._seed}:{name}".encode("utf-8")
        while len(out) < needed:
            out.extend(hashlib.blake2b(seed + counter.to_bytes(4, "little"), digest_size=64).digest())
            counter += 1
        return BitVector(int.from_bytes(bytes(out[:needed]), "little"), self.d)

    def bind(self, a: int | BitVector, b: int | BitVector) -> BitVector:
        return BitVector((int(a) ^ int(b)) & self._mask, self.d)

    def bundle(self, vectors: List[int | BitVector]) -> BitVector:
        if not vectors:
            raise ValueError("Cannot bundle empty list")
        if len(vectors) == 1:
            return BitVector(int(vectors[0]), self.d)
        threshold = len(vectors) // 2
        result = 0
        for bit in range(self.d):
            count = 0
            bit_mask = 1 << bit
            for v in vectors:
                if int(v) & bit_mask:
                    count += 1
            if count > threshold or (count == threshold and ((bit + len(vectors)) & 1)):
                result |= bit_mask
        return BitVector(result & self._mask, self.d)

    def permute(self, v: int | BitVector, steps: int = 1) -> BitVector:
        steps = steps % self.d
        value = int(v)
        if steps == 0:
            return BitVector(value & self._mask, self.d)
        return BitVector(((value << steps) | (value >> (self.d - steps))) & self._mask, self.d)

    def similarity(self, a: int | BitVector, b: int | BitVector) -> float:
        differing = ((int(a) ^ int(b)) & self._mask).bit_count()
        return float((self.d - differing) / self.d)

    def to_bytes(self, v: int | BitVector) -> bytes:
        return int(int(v) & self._mask).to_bytes((self.d + 7) // 8, "little")

    def from_bytes(self, data: bytes) -> BitVector:
        return BitVector(int.from_bytes(data, "little") & self._mask, self.d)

    def encode_text(self, text: str, tokens: List[str] | None = None) -> BitVector:
        terms = tokens or [t for t in self._normalize(text).split() if len(t) >= 3]
        if not terms:
            terms = [self._normalize(text) or "__empty__"]
        vectors = []
        for i, term in enumerate(terms[:64]):
            role = self.permute(self.concept("__position__"), i)
            vectors.append(self.bind(role, self.concept(term)))
        return self.bundle(vectors)

    def encode_relation(self, subject: str, predicate: str, obj: str) -> BitVector:
        s = self.concept(subject)
        p = self.concept(predicate)
        o = self.concept(obj)
        return self.bundle([self.bind(s, p), self.bind(p, o)])

    def decode_relation(self, hv: int | BitVector, top_k: int = 3) -> List[Tuple[str, float]]:
        scores: Dict[str, float] = {}
        for name, vec in self._concept_vectors.items():
            scores[name] = self.similarity(hv, vec)
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
