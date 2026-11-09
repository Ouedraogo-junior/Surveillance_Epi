"""Lecture des référentiels en base, sous la forme attendue par les contrôles."""
from sqlalchemy import text
from sqlalchemy.engine import Connection

from surveillance.pipeline.controles import Referentiels

SQL_FORMATIONS = text("SELECT code, id FROM ref.formation_sanitaire")
SQL_MALADIES = text("SELECT code FROM ref.maladie")
SQL_SEMAINES = text("SELECT id, date_debut FROM ref.semaine")


def charger_referentiels(connexion: Connection) -> tuple[Referentiels, dict[str, int]]:
    """Retourne les référentiels pour les contrôles, et la table code -> identifiant des formations."""
    ids_formations = {r.code: r.id for r in connexion.execute(SQL_FORMATIONS)}
    maladies = frozenset(connexion.execute(SQL_MALADIES).scalars())
    calendrier = {r.id: r.date_debut for r in connexion.execute(SQL_SEMAINES)}
    return Referentiels(frozenset(ids_formations), maladies, calendrier), ids_formations