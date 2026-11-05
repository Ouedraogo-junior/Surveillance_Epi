"""Écrit les déclarations simulées sous forme de fichiers CSV, un par semaine de réception.

Usage, depuis le dossier backend :  python -m surveillance.generation.fichiers
"""
import csv
import shutil

from surveillance.config import RACINE
from surveillance.generation.apercu import lire_districts
from surveillance.generation.declarations import COLONNES, Resultat, produire
from surveillance.generation.simulation import simuler
from surveillance.generation.structure import generer_formations, generer_populations, generer_risque

DOSSIER = RACINE / "data" / "generated" / "declarations"
RAPPORT = RACINE / "data" / "generated" / "erreurs_injectees.csv"


def ecrire(resultat: Resultat) -> list[tuple[str, int, str]]:
    """Écrit les fichiers. Retourne la liste des erreurs injectées : (fichier, numéro de ligne, type)."""
    shutil.rmtree(DOSSIER, ignore_errors=True)
    DOSSIER.mkdir(parents=True)
    injectees = []

    for nom in sorted(resultat.fichiers):
        with (DOSSIER / nom).open("w", encoding="utf-8", newline="") as f:
            ecrivain = csv.writer(f)
            ecrivain.writerow(COLONNES)
            for numero, ligne in enumerate(resultat.fichiers[nom], start=2):   # la ligne 1 est l'en-tête
                ecrivain.writerow(ligne[:-1])
                if ligne[-1]:
                    injectees.append((nom, numero, ligne[-1]))

    # Deux fichiers particuliers pour tester la robustesse du pipeline.
    shutil.copyfile(DOSSIER / "declarations_2023-S15.csv", DOSSIER / "declarations_2023-S15_renvoi.csv")
    injectees.append(("declarations_2023-S15_renvoi.csv", 0, "fichier_renvoye"))

    with (DOSSIER / "declarations_2024-S20_format_invalide.csv").open("w", encoding="utf-8", newline="") as f:
        f.write("formation_code,maladie_code,annee,semaine,cas_suspects,cas_confirmes,date_reception\n")
        f.write("FS-D01-01,PALU,2024,19,120,70,2024-05-14\n")
        f.write("FS-D01-02,PALU,2024,19,95,50,2024-05-15\n")
    injectees.append(("declarations_2024-S20_format_invalide.csv", 0, "en_tete_invalide"))

    with RAPPORT.open("w", encoding="utf-8", newline="") as f:
        ecrivain = csv.writer(f)
        ecrivain.writerow(["fichier", "ligne", "type_erreur"])
        ecrivain.writerows(injectees)
    return injectees


def main() -> None:
    districts = lire_districts()
    signal = simuler(districts, generer_formations(districts), generer_populations(districts), generer_risque(districts))
    resultat = produire(signal)
    injectees = ecrire(resultat)

    s = resultat.statistiques
    nb_lignes = sum(len(v) for v in resultat.fichiers.values())
    print(f"{len(resultat.fichiers)} fichiers hebdomadaires, {nb_lignes:,} lignes".replace(",", " "))
    print(f"Rapports reçus : {s['rapports_recus']:,} sur {s['rapports_attendus']:,} attendus "
          f"({100 * s['rapports_recus'] / s['rapports_attendus']:.1f} %), "
          f"dont à temps : {100 * s['rapports_a_temps'] / s['rapports_recus']:.1f} %".replace(",", " "))
    print(f"Lignes corrigées après un premier envoi faux : {s['corrections']:,}".replace(",", " "))
    print("Erreurs injectées :")
    for type_erreur, nombre in sorted(s["erreurs"].items()):
        print(f"  {type_erreur:<24}{nombre:>6}")
    print(f"Plus 2 fichiers particuliers. Rapport : {RAPPORT.relative_to(RACINE)}")


if __name__ == "__main__":
    main()