"""Génère les données de structure fictives et les charge dans la base (idempotent).

Prérequis : les régions et districts sont déjà chargés (surveillance.chargement.referentiels).
Usage, depuis le dossier backend :  python -m surveillance.chargement.structure
"""
from sqlalchemy import create_engine, text

from surveillance.config import url_base
from surveillance.generation.structure import (
    generer_formations,
    generer_populations,
    generer_risque,
)

SQL_DISTRICTS = text("""
    SELECT d.code, r.code
    FROM ref.district d JOIN ref.region r ON r.id = d.region_id
    ORDER BY d.code
""")

SQL_FORMATION = text("""
    INSERT INTO ref.formation_sanitaire (code, nom, type, statut, district_id)
    SELECT CAST(:code AS text), CAST(:nom AS text), CAST(:type AS text), CAST(:statut AS text), d.id
    FROM ref.district d
    WHERE d.code = :district_code
    ON CONFLICT (code) DO UPDATE
        SET nom = EXCLUDED.nom, type = EXCLUDED.type,
            statut = EXCLUDED.statut, district_id = EXCLUDED.district_id
""")

SQL_POPULATION = text("""
    INSERT INTO ref.population_district (district_id, annee, population, source)
    SELECT d.id, CAST(:annee AS smallint), CAST(:population AS integer), CAST(:source AS text)
    FROM ref.district d
    WHERE d.code = :district_code
    ON CONFLICT (district_id, annee) DO UPDATE
        SET population = EXCLUDED.population, source = EXCLUDED.source
""")

SQL_RISQUE = text("""
    INSERT INTO ref.risque_meningite (district_id, saison, risque_eleve)
    SELECT d.id, CAST(:saison AS text), CAST(:risque_eleve AS boolean)
    FROM ref.district d
    WHERE d.code = :district_code
    ON CONFLICT (district_id, saison) DO UPDATE SET risque_eleve = EXCLUDED.risque_eleve
""")


def main() -> None:
    moteur = create_engine(url_base())
    with moteur.begin() as connexion:
        districts = [(code_d, code_r) for code_d, code_r in connexion.execute(SQL_DISTRICTS)]
        if not districts:
            raise SystemExit("Aucun district en base : lancez d'abord surveillance.chargement.referentiels")

        connexion.execute(SQL_FORMATION, generer_formations(districts))
        connexion.execute(SQL_POPULATION, generer_populations(districts))
        connexion.execute(SQL_RISQUE, generer_risque(districts))

        nb_formations = connexion.execute(text("SELECT count(*) FROM ref.formation_sanitaire")).scalar_one()
        nb_populations = connexion.execute(text("SELECT count(*) FROM ref.population_district")).scalar_one()
        nb_risques = connexion.execute(text("SELECT count(*) FROM ref.risque_meningite")).scalar_one()

    print(f"{nb_formations} formations, {nb_populations} populations, {nb_risques} classements de risque.")


if __name__ == "__main__":
    main()