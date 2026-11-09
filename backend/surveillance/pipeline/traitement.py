"""Traitement complet d'un fichier : lot -> zone brute -> contrôles -> rejets -> entrepôt.

traiter_fichier() ne valide jamais la transaction : c'est l'appelant qui décide (ici, un fichier = une
transaction). Le travail se fait dans un « point de sauvegarde » : si une panne survient en cours de
route, tout ce que le fichier a écrit est annulé, seul le lot reste, marqué en échec, et le fichier
pourra être renvoyé.
"""
import argparse
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from surveillance.config import RACINE, url_base
from surveillance.pipeline.brut import charger_brut, lire_brut
from surveillance.pipeline.controles import controler
from surveillance.pipeline.ecriture import BilanEntrepot, charger_dwh, consigner_rejets, terminer_lot
from surveillance.pipeline.lot import enregistrer_lot, marquer_echec
from surveillance.pipeline.referentiels import charger_referentiels

DOSSIER_PAR_DEFAUT = RACINE / "data" / "generated" / "declarations"


@dataclass
class Bilan:
    fichier: str
    statut: str                  # "termine", "deja_recu", "en_tete_invalide" ou "echec"
    lot_id: int | None = None
    nb_lignes: int = 0
    nb_rejets: int = 0           # nombre de lignes rejetées (une ligne peut violer plusieurs règles)
    entrepot: BilanEntrepot = field(default_factory=BilanEntrepot)
    detail: str = ""


def traiter_fichier(connexion: Connection, chemin: Path) -> Bilan:
    lot = enregistrer_lot(connexion, chemin)
    if lot.statut != "nouveau":
        return Bilan(chemin.name, lot.statut, lot.id, detail=lot.detail)

    try:
        with connexion.begin_nested():
            ref, ids_formations = charger_referentiels(connexion)
            nb_lignes = charger_brut(connexion, lot.id, chemin)
            resultat = controler(lire_brut(connexion, lot.id), ref)    # on contrôle ce qui est en zone brute
            consigner_rejets(connexion, lot.id, resultat.rejets)
            entrepot = charger_dwh(connexion, lot.id, resultat.valides, ids_formations)
            nb_rejets = len({r.numero_ligne for r in resultat.rejets})
            terminer_lot(connexion, lot.id, nb_rejets)
    except Exception as erreur:
        detail = f"{type(erreur).__name__}: {erreur}"[:2000]
        marquer_echec(connexion, lot.id, detail)
        return Bilan(chemin.name, "echec", lot.id, detail=detail)

    return Bilan(chemin.name, "termine", lot.id, nb_lignes, nb_rejets, entrepot)


def main(argv: list[str] | None = None) -> None:
    parseur = argparse.ArgumentParser(description="Traite les fichiers de déclarations, dans l'ordre chronologique.")
    parseur.add_argument("--dossier", type=Path, default=DOSSIER_PAR_DEFAUT)
    parseur.add_argument("--limite", type=int, default=None, help="ne traiter que les N premiers fichiers")
    args = parseur.parse_args(argv)

    # L'ordre alphabétique est l'ordre chronologique (declarations_2021-S01, 2021-S02, ...).
    # Il compte : la version d'une déclaration suit l'ordre de traitement.
    fichiers = sorted(args.dossier.glob("declarations_*.csv"))
    if args.limite is not None:
        fichiers = fichiers[: args.limite]
    if not fichiers:
        raise SystemExit(f"Aucun fichier declarations_*.csv dans {args.dossier}")

    moteur = create_engine(url_base())
    statuts: Counter = Counter()
    total = BilanEntrepot()
    lignes = rejets = 0
    debut = time.time()

    for numero, chemin in enumerate(fichiers, start=1):
        with moteur.begin() as connexion:                     # un fichier = une transaction
            bilan = traiter_fichier(connexion, chemin)
        statuts[bilan.statut] += 1
        lignes += bilan.nb_lignes
        rejets += bilan.nb_rejets
        total.nouvelles += bilan.entrepot.nouvelles
        total.corrections += bilan.entrepot.corrections
        total.identiques += bilan.entrepot.identiques
        if bilan.statut != "termine":
            print(f"  {bilan.fichier} : {bilan.statut}. {bilan.detail}")
        if numero % 25 == 0:
            print(f"  ... {numero}/{len(fichiers)} fichiers ({time.time() - debut:.0f} s)")

    print(f"\n{len(fichiers)} fichiers en {time.time() - debut:.0f} s : " + ", ".join(
        f"{n} {s}" for s, n in sorted(statuts.items())))
    print(f"Lignes lues : {lignes}. Lignes rejetées : {rejets}.")
    print(f"Entrepôt : {total.nouvelles} nouvelles déclarations, {total.corrections} corrections, "
          f"{total.identiques} renvois identiques ignorés.")


if __name__ == "__main__":
    main()