import re
from typing import Optional

def redact_secrets(text: Optional[str]) -> str:
    """
    Sostituisce dati sensibili (password, chiavi API, token) con [REDACTED].
    Utilizza regex robuste per evitare leak di sicurezza in ambienti open source.
    """
    if not text:
        return ""

    # Pattern per intercettare keyword generiche associate a secret in file JSON/YML/INI
    # Es: "password": "mypass", "api_key": "sk-1234"
    generic_secret_pattern = re.compile(
        r'(?i)(password|passwd|pwd|secret|token|api_key|apikey|access_token|auth_token)\s*[:=]\s*([\'"]?)[^\'"\s,]+([\'"]?)'
    )

    # Regex per token comuni specifici (OpenAI, Anthropic, AWS, JWT, GitHub)
    specific_patterns = [
        re.compile(r'sk-(ant-)?[a-zA-Z0-9]{32,80}'),         # OpenAI / Anthropic
        re.compile(r'(A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}'), # AWS Access Keys
        re.compile(r'gh[pousr]_[a-zA-Z0-9]{36}'),            # GitHub Tokens
        re.compile(r'eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+') # JWT Tokens
    ]

    redacted = text
    # Oscura i secret generici
    redacted = generic_secret_pattern.sub(r'\1: \2[REDACTED]\3', redacted)
    
    # Oscura i token specifici trovati nel testo
    for pattern in specific_patterns:
        redacted = pattern.sub('[REDACTED]', redacted)

    return redacted
