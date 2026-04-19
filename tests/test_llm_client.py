import pytest
from memento.llm_client import _is_retryable


class TestRetryLogic:
    def test_rate_limit_retryable(self):
        assert _is_retryable(Exception("Rate limit exceeded (429)"))

    def test_timeout_retryable(self):
        assert _is_retryable(Exception("Request timeout"))

    def test_503_retryable(self):
        assert _is_retryable(Exception("Server error: 503"))

    def test_auth_error_not_retryable(self):
        assert not _is_retryable(Exception("Invalid API key"))

    def test_generic_error_not_retryable(self):
        assert not _is_retryable(Exception("Something went wrong"))
