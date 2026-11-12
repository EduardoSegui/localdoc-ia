from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "LocalDoc AI"
    app_env: str = "development"
    log_level: str = "INFO"

    database_url: str

    ollama_host: str = Field(
        default="http://127.0.0.1:11434",
        validation_alias=AliasChoices("OLLAMA_HOST", "OLLAMA_BASE_URL"),
    )
    # Modelos pequeños con salida JSON y visión estructurada compatibles con
    # Ollama. Se pueden reemplazar mediante las variables OLLAMA_*.
    ollama_model: str = "qwen2.5:7b"
    ollama_vision_model: str = "qwen2.5vl:7b"
    ollama_temperature: float = 0.0
    ollama_timeout: float = 120.0
    # El contexto por defecto de Ollama es 4096 tokens. El prompt del agente,
    # las definiciones de herramientas y los resultados MCP no entran en ese
    # límite, por lo que el modelo pierde contexto y entra en repeticiones.
    ollama_num_ctx: int = 16384
    # Evita que una respuesta se extienda indefinidamente si el modelo repite.
    ollama_num_predict: int = 1024
    # Máximo de caracteres de un resultado MCP antes de truncarlo.
    max_tool_result_chars: int = 30000

    documents_dir: Path = Path("data")
    inbox_dir: Path | None = None
    samples_dir: Path | None = None
    reports_dir: Path = Path("reports")

    ocr_lang: str = "spa"
    ocr_dpi: int = 300

    max_agent_steps: int = 5
    max_conversation_turns: int = 6

    telegram_bot_token: str | None = None
    telegram_allowed_user_ids: str = ""
    max_file_size_mb: int = 20

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        """Normaliza el nivel de logging para logging.basicConfig."""

        return value.strip().upper()

    @staticmethod
    def _resolve_path(path: Path) -> Path:
        """Convierte rutas relativas en absolutas desde la raíz del proyecto."""

        value = Path(path)

        if value.is_absolute():
            return value

        return (PROJECT_ROOT / value).resolve()

    @property
    def inbox_path(self) -> Path:
        return self._resolve_path(
            self.inbox_dir or self.documents_dir / "inbox"
        )

    @property
    def samples_path(self) -> Path:
        return self._resolve_path(
            self.samples_dir or self.documents_dir / "samples"
        )

    @property
    def reports_path(self) -> Path:
        return self._resolve_path(self.reports_dir)

    @property
    def allowed_telegram_user_ids(self) -> set[int]:
        """Convierte la lista configurada de IDs en un conjunto."""

        if not self.telegram_allowed_user_ids.strip():
            return set()

        try:
            return {
                int(user_id.strip())
                for user_id in self.telegram_allowed_user_ids.split(",")
                if user_id.strip()
            }
        except ValueError as error:
            raise ValueError(
                "TELEGRAM_ALLOWED_USER_IDS debe contener IDs numéricos "
                "separados por comas."
            ) from error
settings = Settings()
