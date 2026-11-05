"""Configuration du projet : lecture du fichier .env et construction de l'adresse de la base."""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL

# Racine du projet (le dossier qui contient docker-compose.yml).
RACINE = Path(__file__).resolve().parents[2]

# Les variables déjà présentes dans l'environnement (production) restent prioritaires sur le .env.
load_dotenv(RACINE / ".env")


def _exiger(nom: str) -> str:
    valeur = os.environ.get(nom)
    if not valeur:
        raise RuntimeError(f"Variable d'environnement manquante : {nom} (voir le fichier .env)")
    return valeur


def url_base() -> URL:
    """Adresse de connexion à PostgreSQL, construite à partir des variables POSTGRES_*."""
    return URL.create(
        drivername="postgresql+psycopg",
        username=_exiger("POSTGRES_USER"),
        password=_exiger("POSTGRES_PASSWORD"),
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database=_exiger("POSTGRES_DB"),
    )