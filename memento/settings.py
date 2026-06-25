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
        # Temporal decay: lambda per tier (half-life: semantic~200d, episodic~50d, working~14d)
        self.decay_lambda: dict = {
            "semantic": float(os.environ.get("MEMENTO_DECAY_SEMANTIC", "0.005")),
            "episodic": float(os.environ.get("MEMENTO_DECAY_EPISODIC", "0.02")),
            "working":  float(os.environ.get("MEMENTO_DECAY_WORKING",  "0.05")),
        }
        # Proactive context injection on every tool call
        self.proactive_inject: bool = os.environ.get("MEMENTO_PROACTIVE_INJECT", "1").strip() not in ("0", "false", "no")
        self.proactive_top_k: int = int(os.environ.get("MEMENTO_PROACTIVE_TOP_K", "3"))
        # Federation: optional shared KG path (multi-workspace) and socket push
        self.shared_kg_path: str = os.environ.get("MEMENTO_SHARED_KG_PATH", "").strip()
        self.federation_socket: str = os.environ.get("MEMENTO_FEDERATION_SOCKET", "").strip()

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

    def reload(self) -> None:
        """Re-read all env vars — useful in tests after monkeypatch.setenv."""
        self.__init__()


settings = Settings()
