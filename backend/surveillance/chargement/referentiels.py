"""Charge les régions et les districts sanitaires dans la base.

Le script peut être relancé autant de fois que l'on veut : il met à jour sans créer de doublons.
Usage, depuis le dossier backend :  python -m surveillance.chargement.referentiels
"""
import csv
from pathlib import Path

from sqlalchemy import create_engine, text

from surveillance.config import RACINE, url_base

FICHIER = RACINE / "data" / "reference" / "districts_sanitaires.csv"

SQL_REGION = text("""
    INSERT INTO ref.region (code, nom)
    VALUES (:code, :nom)
    ON CONFLICT (code) DO UPDATE SET nom = EXCLUDED.nom
""")

SQL_DISTRICT = text("""
    INSERT INTO ref.district (code, nom, region_id)
    SELECT CAST(:code AS text), CAST(:nom AS text), r.id
    FROM ref.region r
    WHERE r.code = :region_code
    ON CONFLICT (code) DO UPDATE SET nom = EXCLUDED.nom, region_id = EXCLUDED.region_id
""")


def lire_fichier(chemin: Path) -> list[dict[str, str]]:
    with chemin.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def charger(lignes: list[dict[str, str]]) -> tuple[int, int]:
    """Insère ou met à jour les régions puis les districts. Retourne les effectifs présents en base."""
    regions = {ligne["region_code"]: ligne["region_nom"] for ligne in lignes}
    moteur = create_engine(url_base())
    # engine.begin() ouvre une transaction : tout est enregistré, ou rien.
    with moteur.begin() as connexion:
        connexion.execute(
            SQL_REGION,
            [{"code": code, "nom": nom} for code, nom in regions.items()],
        )
        connexion.execute(
            SQL_DISTRICT,
            [
                {"code": l["district_code"], "nom": l["district_nom"], "region_code": l["region_code"]}
                for l in lignes
            ],
        )
        nb_regions = connexion.execute(text("SELECT count(*) FROM ref.region")).scalar_one()
        nb_districts = connexion.execute(text("SELECT count(*) FROM ref.district")).scalar_one()
    return nb_regions, nb_districts


def main() -> None:
    lignes = lire_fichier(FICHIER)
    nb_regions, nb_districts = charger(lignes)
    print(f"Base à jour : {nb_regions} régions et {nb_districts} districts.")


if __name__ == "__main__":
    main()