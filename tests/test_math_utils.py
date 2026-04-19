import math
import pytest
from memento.math_utils import cosine_similarity


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_empty_vectors(self):
        assert cosine_similarity([], [1, 2]) == 0.0
        assert cosine_similarity([1, 2], []) == 0.0

    def test_zero_norm(self):
        assert cosine_similarity([0, 0], [1, 1]) == 0.0

    def test_length_mismatch(self):
        assert cosine_similarity([1, 2], [1, 2, 3]) == 0.0

    def test_known_value(self):
        a = [1, 2, 3]
        b = [4, 5, 6]
        dot = 4 + 10 + 18
        norm_a = math.sqrt(1 + 4 + 9)
        norm_b = math.sqrt(16 + 25 + 36)
        expected = dot / (norm_a * norm_b)
        assert cosine_similarity(a, b) == pytest.approx(expected)

    def test_high_dimensional(self):
        import random
        random.seed(42)
        v = [random.gauss(0, 1) for _ in range(1536)]
        assert cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-6)
