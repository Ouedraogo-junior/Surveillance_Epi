"""Vérification : les rejets en base correspondent-ils exactement aux erreurs injectées ?

Le générateur a noté, pour chaque erreur glissée dans les fichiers, le fichier, la ligne et le type.
On compare cette liste (la « vérité ») à ce que le pipeline a réellement rejeté.
"""
import sys

import pandas as pd
from sqlalchemy import create_engine, text

from surveillance.config import RACINE, url_base

RAPPORT = RACINE / "data" / "generated" / "erreurs_injectees.csv"

SQL_REJETS = text("""
    SELECT l.nom_fichier, r.numero_ligne, r.regle
    FROM staging.rejet r JOIN audit.lot_ingestion l ON l.id = r.lot_id
""")
SQL_LOTS = text("SELECT nom_fichier, statut FROM audit.lot_ingestion")

FICHIER_RENVOYE = "declarations_2023-S15_renvoi.csv"
FICHIER_ORIGINAL = "declarations_2023-S15.csv"
FICHIER_FORMAT_INVALIDE = "declarations_2024-S20_format_invalide.csv"


def afficher(titre: str, lignes: pd.DataFrame) -> None:
    if len(lignes):
        print(f"\n{titre} (5 premiers exemples) :")
        print(lignes.head(5).to_string(index=False))


def verifier() -> bool:
    attendu = pd.read_csv(RAPPORT)
    erreurs_de_lignes = attendu[attendu["ligne"] > 0]

    moteur = create_engine(url_base())
    with moteur.connect() as connexion:
        observe = pd.DataFrame([tuple(r) for r in connexion.execute(SQL_REJETS).all()],
                               columns=["fichier", "ligne", "regle"])
        lots = {nom: statut for nom, statut in connexion.execute(SQL_LOTS).all()}
    moteur.dispose()

    # Une ligne peut violer plusieurs règles : on les regroupe pour comparer ligne à ligne.
    regles = (observe.groupby(["fichier", "ligne"])["regle"]
              .agg(lambda s: "+".join(sorted(s))).rename("observe").reset_index())
    comparaison = erreurs_de_lignes.merge(regles, on=["fichier", "ligne"], how="outer", indicator=True)

    manquees = comparaison[comparaison["_merge"] == "left_only"]
    a_tort = comparaison[comparaison["_merge"] == "right_only"]
    les_deux = comparaison[comparaison["_merge"] == "both"]
    autre_regle = les_deux[les_deux["type_erreur"] != les_deux["observe"]]
    correctes = len(les_deux) - len(autre_regle)

    print(f"Erreurs injectées (lignes)         : {len(erreurs_de_lignes)}")
    print(f"Lignes rejetées en base            : {len(regles)}")
    print(f"Rejetées pour la bonne règle       : {correctes}")
    print(f"Injectées mais NON détectées       : {len(manquees)}")
    print(f"Rejetées à tort (pas injectées)    : {len(a_tort)}")
    print(f"Détectées mais par une autre règle : {len(autre_regle)}")

    presents = comparaison[comparaison["type_erreur"].notna()].copy()
    presents["detectee"] = presents["type_erreur"] == presents["observe"]
    print("\nPar type d'erreur :")
    print(presents.groupby("type_erreur")["detectee"].agg(injectees="size", detectees="sum").to_string())

    afficher("Non détectées", manquees)
    afficher("Rejetées à tort", a_tort[["fichier", "ligne", "observe"]])
    afficher("Mauvaise règle", autre_regle[["fichier", "ligne", "type_erreur", "observe"]])

    # Les deux fichiers particuliers.
    renvoi_ok = FICHIER_RENVOYE not in lots and lots.get(FICHIER_ORIGINAL) == "termine"
    format_ok = lots.get(FICHIER_FORMAT_INVALIDE) == "echec"
    print(f"\nFichier renvoyé à l'identique : {'OK, aucun second lot' if renvoi_ok else 'PROBLÈME'}")
    print(f"Fichier au mauvais en-tête    : {'OK, lot en échec' if format_ok else 'PROBLÈME'}")

    parfait = not (len(manquees) or len(a_tort) or len(autre_regle)) and renvoi_ok and format_ok
    print("\nRÉSULTAT : " + ("tout correspond." if parfait else "des écarts sont à examiner."))
    return parfait


if __name__ == "__main__":
    sys.exit(0 if verifier() else 1)