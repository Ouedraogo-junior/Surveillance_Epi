"""Configuration d'Alembic : la connexion à la base est lue dans les variables d'environnement."""
import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import URL

# Lit le fichier .env à la racine du projet (surveillance-epi/.env).
# Si une variable existe déjà dans l'environnement (cas de la production), elle reste prioritaire.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Les migrations sont écrites à la main : pas de modèles à comparer.
target_metadata = None

# La table qui mémorise la version de la base est rangée dans le schéma "audit".
VERSION_TABLE_SCHEMA = "audit"


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Variable d'environnement manquante : {name} (voir le fichier .env)")
    return value


def get_url() -> URL:
    return URL.create(
        drivername="postgresql+psycopg",
        username=_require("POSTGRES_USER"),
        password=_require("POSTGRES_PASSWORD"),
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database=_require("POSTGRES_DB"),
    )


def run_migrations_offline() -> None:
    """Mode 'hors ligne' : produit le SQL sans se connecter à la base."""
    context.configure(
        url=get_url().render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=VERSION_TABLE_SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Mode normal : se connecte à la base et applique les migrations."""
    engine = create_engine(get_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=VERSION_TABLE_SCHEMA,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()