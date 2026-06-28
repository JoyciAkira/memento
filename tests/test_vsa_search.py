"""Tests for VSA exact search correctness and scaling behavior.

An approximate bit-sampling LSH prefilter was evaluated for scaling the VSA
Hamming search but rejected: these bundle() hypervectors are near-orthogonal
(even true neighbours differ on ~45-50% of bits), so LSH recall collapsed below
0.2. Search therefore stays EXACT. These tests guard that exact path — the kind
of recall/correctness guard that was previously missing and that the silent
except in _batch_hv_similarity would have hidden.
"""
import numpy as np

from memento.memory.hdc import HDCEncoder
from memento.memory.vsa_index import VSAIndex


def _seed_index(idx: VSAIndex, n: int, seed: int = 0) -> None:
    rng = np.random.default_rng(seed)
    vocab = [f"tok{i}" for i in range(200)]
    for i in range(n):
        words = rng.choice(vocab, size=8, replace=False)
        text = f"mem{i} " + " ".join(words)
        ents = idx.extract_entities(text)
        idx._entity_cache[f"m{i}"] = ents
        for e in ents:
            idx.hdc.concept(e)
        idx._vector_cache[f"m{i}"] = int(idx.hdc.encode_text(text, ents))


def test_vectorized_matches_scalar_hamming():
    """The numpy packed-popcount path must produce the SAME Hamming similarity
    as the scalar HDCEncoder.similarity for every vector."""
    hdc = HDCEncoder()
    idx = VSAIndex(":memory:", hdc=hdc)
    _seed_index(idx, 500, seed=2)

    qv = int(hdc.encode_text("tok1 tok2 tok3"))
    vec = idx._batch_hv_similarity(qv)
    assert vec is not None
    vec = dict(vec)
    scalar = {mid: hdc.similarity(qv, hv) for mid, hv in idx._vector_cache.items()}
    assert set(vec) == set(scalar)
    for mid in scalar:
        assert abs(vec[mid] - scalar[mid]) < 1e-9


def test_exact_topk_finds_self():
    """Querying with a stored memory's own vector ranks that memory first."""
    hdc = HDCEncoder()
    idx = VSAIndex(":memory:", hdc=hdc)
    _seed_index(idx, 300, seed=3)

    target = "m42"
    qv = idx._vector_cache[target]
    ranked = idx._batch_hv_similarity(qv)
    top = max(ranked, key=lambda x: x[1])
    assert top[0] == target, f"self-query should rank itself first, got {top[0]}"


def test_query_deterministic():
    """Same query over the same index yields identical ordering across calls."""
    hdc = HDCEncoder()
    idx = VSAIndex(":memory:", hdc=hdc)
    _seed_index(idx, 400, seed=5)

    r1 = idx.query("tok10 tok20 tok30", top_k=10)
    r2 = idx.query("tok10 tok20 tok30", top_k=10)
    assert r1 == r2


def test_empty_index_query():
    """Querying an empty index returns an empty list, no crash."""
    hdc = HDCEncoder()
    idx = VSAIndex(":memory:", hdc=hdc)
    assert idx.query("anything", top_k=10) == []
