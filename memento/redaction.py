import re
from typing import Optional

def redact_secrets(text: Optional[str]) -> str:
    """
    Sostituisce dati sensibili (password, chiavi API, token) con [REDACTED].
    """
    if not text:
        return ""

    # Generic keyword-based secrets (JSON/YAML/INI style)
    generic_secret_pattern = re.compile(
        r'(?i)\b(password|passwd|pwd|secret|token|api_key|apikey|access_token|auth_token|'
        r'client_secret|client_id|bearer|db_password|database_url|private_key)\b'
        r'\s*(?:del\s+server\s+è\s+|is\s+|:\s*|=\s*)?([\'"]?)[^\'"\s,]+([\'"]?)'
    )

    specific_patterns = [
        # OpenAI sk-... and Anthropic sk-ant-api03-...-... (with hyphens)
        re.compile(r'sk-(?:ant-[a-zA-Z0-9]{2,10}-)?[a-zA-Z0-9\-_]{32,120}'),
        # AWS Access Keys
        re.compile(r'(A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}'),
        # GitHub Tokens
        re.compile(r'gh[pousr]_[a-zA-Z0-9]{36}'),
        # JWT Tokens
        re.compile(r'eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+'),
        # Database DSNs: postgres/mysql/mongodb://user:pass@host
        re.compile(r'(?i)(postgres|postgresql|mysql|mongodb|redis|amqp)://[^:]+:[^@\s]+@[^\s]+'),
        # Generic Bearer tokens in Authorization headers
        re.compile(r'(?i)Authorization\s*:\s*Bearer\s+[a-zA-Z0-9\-_\.]+'),
    ]

    redacted = text
    redacted = generic_secret_pattern.sub(r'\1 \2[REDACTED]\3', redacted)
    for pattern in specific_patterns:
        redacted = pattern.sub('[REDACTED]', redacted)

    return redacted
