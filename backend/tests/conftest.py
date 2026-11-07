"""Préparation commune des tests : une base de test jetable, créée et migrée à chaque session."""
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from surveillance.config import RACINE, url_base

# À partir d'ici, tout le code du projet se connecte à la base de test et jamais à la vraie :
# url_base() relit la variable d'environnement à chaque appel.
BASE_PRINCIPALE = os.environ["POSTGRES_DB"]
NOM_BASE_TEST = f"{BASE_PRINCIPALE}_test"
os.environ["POSTGRES_DB"] = NOM_BASE_TEST


def _recreer_base_test() -> None:
    # CREATE DATABASE ne peut pas s'exécuter dans une transaction : mode AUTOCOMMIT.
    admin = create_engine(url_base().set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connexion:
        connexion.execute(text(f'DROP DATABASE IF EXISTS "{NOM_BASE_TEST}" WITH (FORCE)'))
        connexion.execute(text(f'CREATE DATABASE "{NOM_BASE_TEST}"'))
    admin.dispose()

    # Les mêmes scripts d'initialisation que ceux de Docker (extensions et schémas).
    moteur = create_engine(url_base())
    with moteur.begin() as connexion:
        for script in sorted((RACINE / "db" / "init").glob("*.sql")):
            connexion.exec_driver_sql(script.read_text(encoding="utf-8"))
    moteur.dispose()

    # Puis toutes les migrations, de la première à la dernière.
    configuration = Config(str(RACINE / "backend" / "alembic.ini"))
    configuration.set_main_option("script_location", str(RACINE / "backend" / "migrations"))
    command.upgrade(configuration, "head")


@pytest.fixture(scope="session")
def moteur():
    _recreer_base_test()
    moteur = create_engine(url_base())
    yield moteur
    moteur.dispose()
    admin = create_engine(url_base().set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connexion:
        connexion.execute(text(f'DROP DATABASE IF EXISTS "{NOM_BASE_TEST}" WITH (FORCE)'))
    admin.dispose()

@pytest.fixture
def connexion(moteur):
    """Une connexion dont tout le travail est annulé à la fin du test."""
    with moteur.connect() as connexion:
        transaction = connexion.begin()
        yield connexion
        transaction.rollback()