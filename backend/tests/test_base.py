"""Vérifie que la base de test est bien construite par les migrations."""
from sqlalchemy import text


def test_on_travaille_sur_la_base_de_test(moteur):
    with moteur.connect() as connexion:
        nom = connexion.execute(text("SELECT current_database()")).scalar_one()
    assert nom.endswith("_test")


def test_les_tables_attendues_existent(moteur):
    with moteur.connect() as connexion:
        nb_tables = connexion.execute(text("""
            SELECT count(*) FROM information_schema.tables
            WHERE table_schema IN ('ref', 'raw', 'staging', 'dwh', 'sec', 'audit')
              AND table_type = 'BASE TABLE' AND table_name <> 'alembic_version'
        """)).scalar_one()
    assert nb_tables == 15


def test_les_maladies_et_les_regles_sont_chargees_par_les_migrations(moteur):
    with moteur.connect() as connexion:
        maladies = connexion.execute(text("SELECT code FROM ref.maladie ORDER BY code")).scalars().all()
        regles = connexion.execute(text("SELECT count(*) FROM ref.regle_seuil")).scalar_one()
    assert maladies == ["MENI", "PALU", "ROUG"]
    assert regles == 3