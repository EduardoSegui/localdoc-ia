from sqlalchemy import text

from localdoc_ia.database.connection import Base, engine
from localdoc_ia.database import models  # Importa los modelos para registrar sus tablas


MIGRATIONS = (
    (
        "0001_documents_extraction_method_vision",
        (
            "ALTER TABLE documents "
            "DROP CONSTRAINT IF EXISTS ck_documents_extraction_method",
            "ALTER TABLE documents "
            "ADD CONSTRAINT ck_documents_extraction_method "
            "CHECK (extraction_method IN ('text', 'ocr', 'mixed', 'vision'))",
        ),
    ),
    (
        "0002_documents_observations",
        (
            "ALTER TABLE documents "
            "ADD COLUMN IF NOT EXISTS observations JSONB DEFAULT '[]'::jsonb",
            "UPDATE documents "
            "SET observations = COALESCE(extracted_data->'observations', '[]'::jsonb) "
            "WHERE extracted_data IS NOT NULL",
        ),
    ),
)


def apply_migrations() -> None:
    """Aplica migraciones pequeñas e idempotentes para bases ya creadas."""

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(100) PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )

        for version, migration_statements in MIGRATIONS:
            already_applied = connection.scalar(
                text(
                    "SELECT 1 FROM schema_migrations "
                    "WHERE version = :version"
                ),
                {"version": version},
            )

            if already_applied:
                continue

            for migration_statement in migration_statements:
                connection.execute(text(migration_statement))
            connection.execute(
                text(
                    "INSERT INTO schema_migrations (version) "
                    "VALUES (:version)"
                ),
                {"version": version},
            )


def create_tables() -> None:
    """Crea las tablas faltantes y actualiza el esquema existente."""

    Base.metadata.create_all(bind=engine)
    apply_migrations()

    print("Tablas creadas y migraciones verificadas correctamente.")


if __name__ == "__main__":
    create_tables()
