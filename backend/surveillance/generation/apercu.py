"""Aperçu du signal simulé : quelques chiffres pour vérifier que la simulation est réaliste.

Usage, depuis le dossier backend :  python -m surveillance.generation.apercu
"""
import csv

import numpy as np

from surveillance.config import RACINE
from surveillance.generation.simulation import MALADIES, Signal, simuler
from surveillance.generation.structure import generer_formations, generer_populations, generer_risque


def _espace(n: float) -> str:
    return f"{int(round(n)):,}".replace(",", " ")


def lire_districts() -> list[tuple[str, str]]:
    chemin = RACINE / "data" / "reference" / "districts_sanitaires.csv"
    with chemin.open(encoding="utf-8", newline="") as f:
        return sorted({(l["district_code"], l["region_code"]) for l in csv.DictReader(f)})


def _par_district(signal: Signal, valeurs: np.ndarray) -> np.ndarray:
    """Additionne les formations de chaque district : (formations, semaines) -> (districts, semaines)."""
    resultat = np.zeros((len(signal.districts), valeurs.shape[1]))
    np.add.at(resultat, signal.formation_district, valeurs)
    return resultat


def afficher(signal: Signal) -> None:
    annee = np.array([s["annee"] for s in signal.semaines])
    numero = np.array([s["numero"] for s in signal.semaines])
    debut_saison = np.where(numero >= 44, annee, annee - 1)
    premiere, derniere = signal.semaines[0], signal.semaines[-1]
    nf, nw = len(signal.formations), len(signal.semaines)

    print(f"Période : {premiere['annee']}-S{premiere['numero']:02d} à {derniere['annee']}-S{derniere['numero']:02d}"
          f" ({nw} semaines), {len(signal.districts)} districts, {nf} formations")
    print(f"Lignes de déclaration attendues : {_espace(nf * nw * len(MALADIES))}\n")

    print("Cas suspects par année (national)")
    print("  année " + "".join(f"{m:>14}" for m in MALADIES))
    for a in sorted(set(annee)):
        ligne = "".join(f"{_espace(signal.cas[m]['suspects'][:, annee == a].sum()):>14}" for m in MALADIES)
        print(f"  {a}  {ligne}")

    print("\nMéningite : taux hebdomadaire par district, pour 100 000 habitants")
    print("  saison      maximum   semaines-district >= 5   >= 15")
    taux = _par_district(signal, signal.cas["MENI"]["suspects"]) / signal.population * 100_000
    for s in sorted(set(debut_saison)):
        c = debut_saison == s
        print(f"  {s}-{s + 1}   {taux[:, c].max():7.1f}   {int((taux[:, c] >= 5).sum()):>22}   {int((taux[:, c] >= 15).sum()):>5}")

    print("\nPaludisme : national, 8 dernières semaines contre les mêmes semaines de 2025")
    dernieres = np.arange(nw - 8, nw)
    for c in dernieres:
        meme = np.where((annee == 2025) & (numero == numero[c]))[0][0]
        courant = signal.cas["PALU"]["suspects"][:, c].sum()
        passe = signal.cas["PALU"]["suspects"][:, meme].sum()
        print(f"  S{numero[c]:02d}   {_espace(courant):>11}   {_espace(passe):>11}   x{courant / passe:.2f}")

    print("\nRougeole : semaines-district avec 5 cas suspects ou plus")
    rougeole = _par_district(signal, signal.cas["ROUG"]["suspects"])
    for a in sorted(set(annee)):
        print(f"  {a}   {int((rougeole[:, annee == a] >= 5).sum()):>4}   (maximum sur une semaine : {int(rougeole[:, annee == a].max())})")

    print("\nDécès (national, total sur la période)")
    for m in MALADIES:
        print(f"  {m}   {_espace(signal.cas[m]['deces'].sum())}")


def main() -> None:
    districts = lire_districts()
    signal = simuler(districts, generer_formations(districts), generer_populations(districts), generer_risque(districts))
    afficher(signal)


if __name__ == "__main__":
    main()