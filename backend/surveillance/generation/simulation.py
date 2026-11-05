"""Simulation du signal épidémiologique : ce qui se passe réellement dans la population,
avant toute déclaration (retards, oublis et erreurs sont ajoutés à l'étape suivante).

Tout est fictif. Le hasard est fixé par une graine : mêmes entrées, mêmes résultats.
"""
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from surveillance.generation.structure import GRAINE

PREMIERE_SEMAINE = (2021, 1)
DERNIERE_SEMAINE = (2026, 44)
MALADIES = ("MENI", "PALU", "ROUG")

# Poids d'une formation dans la population de son district (un CMA dessert plus de monde).
POIDS_TYPE = {"CMA": 3.0, "CM": 2.0, "CSPS": 1.0, "Clinique privée": 0.5}

# dispersion : plus elle est petite, plus les chiffres d'une semaine à l'autre sont irréguliers.
PARAMETRES = {
    "MENI": {"dispersion": 6, "part_confirmes": 0.20, "letalite": 0.10},
    "PALU": {"dispersion": 25, "part_confirmes": 0.60, "letalite": 0.002},
    "ROUG": {"dispersion": 4, "part_confirmes": 0.30, "letalite": 0.012},
}

SAISON_SECHE_MAX = 30   # la saison sèche dure environ 31 semaines à partir de la semaine 44


@dataclass
class Signal:
    districts: list            # [(code_district, code_region), ...]
    formations: list           # dictionnaires issus de generer_formations
    semaines: list             # [{"id", "annee", "numero", "date_debut"}, ...]
    formation_district: np.ndarray   # pour chaque formation, l'indice de son district
    population: np.ndarray           # population[district, semaine]
    cas: dict                        # cas[maladie]["suspects" | "confirmes" | "deces"][formation, semaine]


def calendrier() -> list[dict]:
    """Semaines ISO 8601 de PREMIERE_SEMAINE à DERNIERE_SEMAINE."""
    jour = date.fromisocalendar(*PREMIERE_SEMAINE, 1)
    fin = date.fromisocalendar(*DERNIERE_SEMAINE, 1)
    semaines = []
    while jour <= fin:
        annee, numero, _ = jour.isocalendar()
        semaines.append({"id": annee * 100 + numero, "annee": annee, "numero": numero, "date_debut": jour})
        jour += timedelta(days=7)
    return semaines


def _generateur(numero: int) -> np.random.Generator:
    return np.random.default_rng([GRAINE, numero])


def _cloche(t: np.ndarray, centre: float, largeur: float) -> np.ndarray:
    return np.exp(-(((t - centre) / largeur) ** 2))


def _poussee(taux: np.ndarray, district: int, colonnes: np.ndarray, pic: float) -> None:
    """Ajoute une flambée en arche (montée puis descente) sur les colonnes données."""
    if len(colonnes) == 0:
        return
    forme = np.sin(np.pi * (np.arange(len(colonnes)) + 1) / (len(colonnes) + 1))
    taux[district, colonnes] += pic * forme


def _chronologie(semaines: list[dict]):
    annee = np.array([s["annee"] for s in semaines])
    numero = np.array([s["numero"] for s in semaines])
    debut_saison = np.where(numero >= 44, annee, annee - 1)    # une saison sèche commence en semaine 44
    t = np.array([
        (s["date_debut"] - date.fromisocalendar(int(ds), 44, 1)).days // 7
        for s, ds in zip(semaines, debut_saison)
    ])
    return annee, numero, debut_saison, t


def _risque_par_semaine(districts, risque, debut_saison) -> np.ndarray:
    table = {(r["district_code"], r["saison"]): r["risque_eleve"] for r in risque}
    derniere = max(r["saison"] for r in risque)
    return np.array([
        [table.get((code, f"{ds}-{ds + 1}"), table.get((code, derniere), False)) for ds in debut_saison]
        for code, _ in districts
    ], dtype=bool)


def _taux_meningite(nd, debut_saison, t, risque_eleve) -> np.ndarray:
    """Cas suspects pour 100 000 habitants par semaine, par district."""
    rng = _generateur(10)
    facteur_district = rng.lognormal(0, 0.35, size=nd)
    en_saison = t <= SAISON_SECHE_MAX
    base = 0.03 + 0.7 * _cloche(t, 20, 7) * en_saison
    taux = base[None, :] * facteur_district[:, None] * np.where(risque_eleve, 1.6, 1.0)

    # Épidémies aléatoires : plus probables dans les districts à risque élevé.
    for saison in sorted(set(int(s) for s in debut_saison)):
        colonnes = np.where(debut_saison == saison)[0]
        for d in range(nd):
            probabilite = 0.15 if risque_eleve[d, colonnes[0]] else 0.03
            if rng.random() < probabilite:
                pic = rng.uniform(6, 35)
                centre = int(rng.integers(14, 27))
                largeur = rng.uniform(3, 5.5)
                taux[d, colonnes] += pic * _cloche(t[colonnes], centre, largeur) * en_saison[colonnes]

    # Scénario de démonstration : deux épidémies garanties dans la saison 2025-2026.
    colonnes = np.where(debut_saison == 2025)[0]
    for d, pic, centre in zip(rng.choice(nd, size=2, replace=False), (30, 12), (18, 22)):
        taux[d, colonnes] += pic * _cloche(t[colonnes], centre, 4) * en_saison[colonnes]
    return taux


def _taux_paludisme(nd, annee, numero) -> np.ndarray:
    """Cas suspects pour 100 000 habitants par semaine : pic en fin de saison des pluies (semaine 38)."""
    rng = _generateur(11)
    facteur_district = rng.lognormal(0, 0.30, size=nd)
    saisonnalite = 1 + 0.65 * np.cos(2 * np.pi * (numero - 38) / 52)
    taux = 700 * facteur_district[:, None] * saisonnalite[None, :]

    for a in sorted(set(int(x) for x in annee)):
        colonnes = np.where(annee == a)[0]
        taux[:, colonnes] *= rng.lognormal(0, 0.12) * rng.lognormal(0, 0.08, size=(nd, 1))
        for d in range(nd):                                  # poussées aléatoires
            if rng.random() < 0.04:
                debut = int(rng.integers(28, 41))
                duree = int(rng.integers(4, 7))
                cibles = colonnes[(numero[colonnes] >= debut) & (numero[colonnes] < debut + duree)]
                taux[d, cibles] *= rng.uniform(1.5, 2.3)

    # Scénario de démonstration : trois districts en forte hausse dans les dernières semaines.
    cibles = np.where((annee == 2026) & (numero >= 37) & (numero <= 43))[0]
    for d in rng.choice(nd, size=3, replace=False):
        taux[d, cibles] *= rng.uniform(1.8, 2.2)
    return taux


def _taux_rougeole(nd, annee, numero, t) -> np.ndarray:
    """Cas suspects pour 100 000 habitants par semaine : rares, avec des flambées locales."""
    rng = _generateur(12)
    facteur_district = rng.lognormal(0, 0.4, size=nd)
    saison_seche = 1 + 1.2 * _cloche(t, 18, 7) * (t <= SAISON_SECHE_MAX)
    taux = 0.12 * facteur_district[:, None] * saison_seche[None, :]

    for a in sorted(set(int(x) for x in annee)):
        colonnes = np.where(annee == a)[0]
        for _ in range(int(rng.poisson(4))):
            d = int(rng.integers(nd))
            debut = int(rng.integers(0, len(colonnes)))
            duree = int(rng.integers(4, 9))
            _poussee(taux, d, colonnes[debut:debut + duree], rng.uniform(8, 25))

    # Scénario de démonstration : une flambée garantie entre les semaines 30 et 37 de 2026.
    cibles = np.where((annee == 2026) & (numero >= 30) & (numero <= 37))[0]
    _poussee(taux, int(rng.integers(nd)), cibles, 20)
    return taux


def simuler(districts: list, formations: list, populations: list, risque: list) -> Signal:
    semaines = calendrier()
    annee, numero, debut_saison, t = _chronologie(semaines)
    nd = len(districts)

    table_pop = {(p["district_code"], p["annee"]): p["population"] for p in populations}
    population = np.array(
        [[table_pop[(code, int(a))] for a in annee] for code, _ in districts], dtype=float
    )

    indice = {code: i for i, (code, _) in enumerate(districts)}
    fd = np.array([indice[f["district_code"]] for f in formations])
    poids = np.array([POIDS_TYPE[f["type"]] for f in formations])
    part = poids / np.bincount(fd, weights=poids, minlength=nd)[fd]   # part de chaque formation dans son district

    risque_eleve = _risque_par_semaine(districts, risque, debut_saison)
    taux = {
        "MENI": _taux_meningite(nd, debut_saison, t, risque_eleve),
        "PALU": _taux_paludisme(nd, annee, numero),
        "ROUG": _taux_rougeole(nd, annee, numero, t),
    }

    cas = {}
    for numero_maladie, maladie in enumerate(MALADIES):
        rng = _generateur(20 + numero_maladie)
        p = PARAMETRES[maladie]
        attendu = taux[maladie][fd, :] / 100_000 * population[fd, :] * part[:, None]
        k = p["dispersion"]
        suspects = rng.poisson(attendu * rng.gamma(k, 1 / k, size=attendu.shape))
        cas[maladie] = {
            "suspects": suspects,
            "confirmes": rng.binomial(suspects, p["part_confirmes"]),
            "deces": rng.binomial(suspects, p["letalite"]),
        }
    return Signal(districts, formations, semaines, fd, population, cas)