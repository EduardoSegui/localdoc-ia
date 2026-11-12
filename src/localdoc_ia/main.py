import logging

from localdoc_ia.config import settings
from localdoc_ia.database.init_db import create_tables
from localdoc_ia.telegram.bot import main as run_telegram_bot


def main() -> None:
    """Inicializa el esquema y ejecuta el bot de Telegram."""

    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger(__name__).info(
        "Iniciando %s (entorno: %s)",
        settings.app_name,
        settings.app_env,
    )
    create_tables()
    run_telegram_bot()

if __name__ == "__main__":
    main()
