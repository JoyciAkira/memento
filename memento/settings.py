import os


class Settings:
    def __init__(self):
        self.openai_api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.openai_base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        self.embedding_model = os.environ.get("MEM0_EMBEDDING_MODEL", "text-embedding-3-small").strip()
        self.llm_model = os.environ.get("MEM0_MODEL", "openai/gpt-4o-mini").strip()
        self.embedding_backend = self._detect_embedding_backend()
        self.memento_dir = os.environ.get("MEMENTO_DIR", os.getcwd()).strip()
        self.ui_port = int(os.environ.get("MEMENTO_UI_PORT", "8089"))
        self.ui_enabled = os.environ.get("MEMENTO_UI", "").strip().lower() in ("1", "true")
        self.ui_auth_token = os.environ.get("MEMENTO_UI_AUTH_TOKEN", "").strip()
        self.rule_confirmation = os.environ.get("MEMENTO_RULE_CONFIRMATION", "true").strip().lower() == "true"

    def _detect_embedding_backend(self) -> str:
        explicit = os.environ.get("MEMENTO_EMBEDDING_BACKEND", "").strip().lower()
        if explicit:
            return explicit
        if self.openai_api_key:
            return "openai"
        from memento.local_embeddings import is_fastembed_available
        if is_fastembed_available():
            return "local"
        return "none"

    @property
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key)


settings = Settings()
