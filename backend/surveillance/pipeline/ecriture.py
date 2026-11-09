"""Écriture des résultats du traitement : rejets, entrepôt (avec versions) et clôture du lot."""
from dataclasses import dataclass
from datetime import datetime, time, timezone

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection

from surveillance.pipeline.controles import Rejet

SQL_REJET = text("""
    INSERT INTO staging.rejet (lot_id, numero_ligne, regle, detail)
    VALUES (:lot_id, :numero_ligne, :regle, :detail)
""")

# Dernière version connue de chaque déclaration concernée par le fichier.
SQL_DERNIERES_VERSIONS = text("""
    SELECT DISTINCT ON (d.formation_id, d.maladie_code, d.semaine_id)
           d.formation_id, d.maladie_code, d.semaine_id, d.version,
           d.cas_suspects, d.cas_confirmes, d.deces
    FROM dwh.fait_declaration d
    JOIN unnest(CAST(:formations AS integer[]), CAST(:maladies AS text[]), CAST(:semaines AS integer[]))
         AS k(formation_id, maladie_code, semaine_id)
      ON d.formation_id = k.formation_id
     AND d.maladie_code = k.maladie_code
     AND d.semaine_id = k.semaine_id
    ORDER BY d.formation_id, d.maladie_code, d.semaine_id, d.version DESC
""")

SQL_FAIT = text("""
    INSERT INTO dwh.fait_declaration
        (formation_id, maladie_code, semaine_id, version, cas_suspects, cas_confirmes, deces, recu_le, lot_id)
    VALUES
        (:formation_id, :maladie_code, :semaine_id, :version, :cas_suspects, :cas_confirmes, :deces, :recu_le, :lot_id)
""")

SQL_TERMINER_LOT = text("""
    UPDATE audit.lot_ingestion SET statut = 'termine', nb_rejets = :nb_rejets WHERE id = :id
""")


@dataclass
class BilanEntrepot:
    nouvelles: int = 0       # première version d'une déclaration
    corrections: int = 0     # nouvelle version : les chiffres ont changé
    identiques: int = 0      # renvoi des mêmes chiffres : rien n'est écrit


def consigner_rejets(connexion: Connection, lot_id: int, rejets: list[Rejet]) -> None:
    if rejets:
        connexion.execute(SQL_REJET, [
            {"lot_id": lot_id, "numero_ligne": r.numero_ligne, "regle": r.regle, "detail": r.detail}
            for r in rejets
        ])


def charger_dwh(connexion: Connection, lot_id: int, valides: pd.DataFrame,
                ids_formations: dict[str, int]) -> BilanEntrepot:
    """Écrit les lignes valides dans l'entrepôt, en ajoutant une version quand les chiffres changent."""
    bilan = BilanEntrepot()
    if valides.empty:
        return bilan

    lignes = [
        {
            "formation_id": ids_formations[r.formation_code],
            "maladie_code": r.maladie_code,
            "semaine_id": int(r.semaine_id),
            "cas_suspects": int(r.cas_suspects),
            "cas_confirmes": int(r.cas_confirmes),
            "deces": int(r.deces),
            "recu_le": datetime.combine(r.date_reception, time.min, tzinfo=timezone.utc),
        }
        for r in valides.itertuples(index=False)
    ]

    derniere = {}
    for r in connexion.execute(SQL_DERNIERES_VERSIONS, {
        "formations": [l["formation_id"] for l in lignes],
        "maladies": [l["maladie_code"] for l in lignes],
        "semaines": [l["semaine_id"] for l in lignes],
    }):
        derniere[(r.formation_id, r.maladie_code, r.semaine_id)] = (
            r.version, (r.cas_suspects, r.cas_confirmes, r.deces))

    a_inserer = []
    for ligne in lignes:                                   # dans l'ordre du fichier
        cle = (ligne["formation_id"], ligne["maladie_code"], ligne["semaine_id"])
        valeurs = (ligne["cas_suspects"], ligne["cas_confirmes"], ligne["deces"])
        precedente = derniere.get(cle)
        if precedente is None:
            version = 1
            bilan.nouvelles += 1
        elif precedente[1] == valeurs:
            bilan.identiques += 1
            continue
        else:
            version = precedente[0] + 1
            bilan.corrections += 1
        derniere[cle] = (version, valeurs)
        a_inserer.append({**ligne, "version": version, "lot_id": lot_id})

    if a_inserer:
        connexion.execute(SQL_FAIT, a_inserer)
    return bilan


def terminer_lot(connexion: Connection, lot_id: int, nb_rejets: int) -> None:
    connexion.execute(SQL_TERMINER_LOT, {"id": lot_id, "nb_rejets": nb_rejets})