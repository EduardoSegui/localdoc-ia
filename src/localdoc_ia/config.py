from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "gpt-oss:20b"
    ollama_temperature: float = 0.0

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