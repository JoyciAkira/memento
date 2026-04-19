import pytest
from memento.redaction import redact_secrets


class TestRedaction:
    def test_redacts_openai_key(self):
        text = "Use this key: sk-abcdefghijklmnopqrstuvwxy1234567890abcdefghijklmnop"
        result = redact_secrets(text)
        assert "sk-abcdefghijklmnop" not in result

    def test_redacts_password_equals(self):
        text = "password=supersecret123 in config"
        result = redact_secrets(text)
        assert "supersecret123" not in result

    def test_redacts_generic_api_key(self):
        text = "api_key=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
        result = redact_secrets(text)
        assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456" not in result

    def test_preserves_normal_text(self):
        text = "This is a normal message about building features."
        result = redact_secrets(text)
        assert result == text

    def test_handles_empty_string(self):
        assert redact_secrets("") == ""

    def test_redacts_jwt_token(self):
        text = "Token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijklmnop"
        result = redact_secrets(text)
        assert "eyJhbGciOiJIUzI1NiJ9" not in result
