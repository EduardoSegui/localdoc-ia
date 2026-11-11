from localdoc_ia.database.connection import Base, engine
from localdoc_ia.database import models  # Importa los modelos para registrar sus tablas


def create_tables() -> None:
    """Crea las tablas que todavía no existen."""

    Base.metadata.create_all(bind=engine)

    print("Tablas creadas o verificadas correctamente.")


if __name__ == "__main__":
    create_tables()
