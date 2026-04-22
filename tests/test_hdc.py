import pytest
import numpy as np
from memento.memory.hdc import HDCEncoder

def test_hdc_concept_sparsity():
    hdc = HDCEncoder(d=10000)
    vec = hdc.concept("python")
    assert len(vec) == 10000
    ones = np.sum(vec)
    assert 100 < ones < 9900, "Vector should be sparse but not trivial"

def test_hdc_binding_and_unbinding():
    hdc = HDCEncoder(d=1000)
    a = hdc.concept("x")
    b = hdc.concept("y")
    bound = hdc.bind(a, b)
    recovered = hdc.bind(bound, b)
    assert np.mean(recovered == a) > 0.99

def test_hdc_bundle():
    hdc = HDCEncoder(d=1000)
    v1 = hdc.concept("a")
    v2 = hdc.concept("b")
    bundle = hdc.bundle([v1, v2])
    assert len(bundle) == 1000

def test_hdc_encode_decode_relation():
    hdc = HDCEncoder(d=10000)
    rel = hdc.encode_relation("user", "uses", "fastapi")
    decoded = hdc.decode_relation(rel, top_k=3)
    assert len(decoded) <= 3
    names = [n for n, _ in decoded]
    assert "user" in names or "fastapi" in names or "uses" in names

def test_hdc_permute():
    hdc = HDCEncoder(d=100)
    vec = hdc.concept("x")
    perm = hdc.permute(vec, steps=5)
    assert np.mean(vec == perm) < 1.0

def test_hdc_deterministic():
    hdc = HDCEncoder(d=5000)
    v1 = hdc.concept("cat")
    v2 = hdc.concept("cat")
    assert np.mean(v1 == v2) > 0.99
