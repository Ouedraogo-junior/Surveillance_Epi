"""Réception d'un fichier : empreinte, détection des renvois, contrôle de l'en-tête.

Chaque fichier reçu devient un « lot » dans audit.lot_ingestion. Le contrôle de l'en-tête décide
si le fichier peut être traité : un fichier qui n'a pas les bonnes colonnes met son lot en échec.
"""
import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection

EN_TETE_ATTENDU = ["formation_code", "maladie_code", "annee", "semaine",
                   "cas_suspects", "cas_confirmes", "deces", "date_reception"]

SQL_NOUVEAU_LOT = text("""
    INSERT INTO audit.lot_ingestion (source, nom_fichier, empreinte)
    VALUES (:source, :nom_fichier, :empreinte)
    ON CONFLICT (empreinte) DO NOTHING
    RETURNING id
""")

SQL_LOT_EXISTANT = text("""
    SELECT id, nom_fichier, statut FROM audit.lot_ingestion WHERE empreinte = :empreinte
""")

SQL_REPRISE = text("""
    UPDATE audit.lot_ingestion
    SET statut = 'recu', detail = NULL, nb_lignes = 0, nb_rejets = 0
    WHERE id = :id AND statut = 'echec'
""")

SQL_ECHEC = text("""
    UPDATE audit.lot_ingestion SET statut = 'echec', detail = :detail WHERE id = :id
""")


@dataclass(frozen=True)
class Lot:
    id: int | None          # None quand le fichier est un renvoi : aucun nouveau lot n'est créé
    nom_fichier: str
    empreinte: str
    statut: str             # "nouveau", "deja_recu" ou "en_tete_invalide"
    detail: str = ""


def calculer_empreinte(chemin: Path) -> str:
    """Signature SHA-256 du contenu du fichier : deux fichiers identiques ont la même empreinte."""
    sha = hashlib.sha256()
    with chemin.open("rb") as f:
        for bloc in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(bloc)
    return sha.hexdigest()


def lire_en_tete(chemin: Path) -> list[str]:
    # utf-8-sig accepte aussi les fichiers enregistrés par Excel, qui commencent par une marque invisible (BOM).
    with chemin.open(encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f), [])


def marquer_echec(connexion: Connection, lot_id: int, detail: str) -> None:
    connexion.execute(SQL_ECHEC, {"id": lot_id, "detail": detail})


def enregistrer_lot(connexion: Connection, chemin: Path, source: str = "fichier_hebdomadaire") -> Lot:
    """Enregistre le fichier comme nouveau lot, sauf s'il a déjà été reçu. Ne valide pas la transaction."""
    empreinte = calculer_empreinte(chemin)
    ligne = connexion.execute(
        SQL_NOUVEAU_LOT, {"source": source, "nom_fichier": chemin.name, "empreinte": empreinte}
    ).first()

    if ligne is None:
        existant = connexion.execute(SQL_LOT_EXISTANT, {"empreinte": empreinte}).one()
        if existant.statut != "echec":
            detail = f"Fichier identique au lot {existant.id} ({existant.nom_fichier}), déjà reçu"
            return Lot(None, chemin.name, empreinte, "deja_recu", detail)
        connexion.execute(SQL_REPRISE, {"id": existant.id})     # on retente le même lot
        lot_id = existant.id
    else:
        lot_id = ligne[0]

    try:
        en_tete = lire_en_tete(chemin)
    except UnicodeDecodeError:
        en_tete = None
    if en_tete != EN_TETE_ATTENDU:
        if en_tete is None:
            detail = "Fichier illisible : l'encodage n'est pas UTF-8"
        else:
            detail = f"En-tête invalide : colonnes attendues {EN_TETE_ATTENDU}, reçues {en_tete}"
        marquer_echec(connexion, lot_id, detail)
        return Lot(lot_id, chemin.name, empreinte, "en_tete_invalide", detail)

    return Lot(lot_id, chemin.name, empreinte, "nouveau")