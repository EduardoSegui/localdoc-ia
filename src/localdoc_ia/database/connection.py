from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from localdoc_ia.config import settings


# Clase base para todos los modelos ORM
class Base(DeclarativeBase):
    pass


# Motor de conexión a PostgreSQL
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=False,
)


# Fábrica de sesiones para interactuar con la base
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)
