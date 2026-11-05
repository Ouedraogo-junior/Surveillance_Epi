"""Génération de données de structure synthétiques : formations sanitaires, populations, risque méningite.

Toutes les valeurs sont FICTIVES. La génération est déterministe : la même graine donne toujours
les mêmes données, ce qui rend le projet reproductible.
"""
import numpy as np

GRAINE = 2026
ANNEES_POPULATION = range(2021, 2027)                    # 2021 à 2026
SAISONS = [f"{a}-{a + 1}" for a in range(2020, 2026)]    # 2020-2021 à 2025-2026
CROISSANCE_ANNUELLE = 0.028
REGION_URBAINE = "R03"                                   # région Centre (Ouagadougou)
SOURCE = "synthetique"

# Un district est décrit par un couple (code du district, code de sa région).
Districts = list[tuple[str, str]]


def _generateur(numero: int) -> np.random.Generator:
    """Un générateur aléatoire par type de donnée : modifier l'un ne change pas les autres."""
    return np.random.default_rng([GRAINE, numero])


def generer_populations(districts: Districts) -> list[dict]:
    rng = _generateur(1)
    lignes = []
    for code_district, code_region in districts:
        base = rng.lognormal(mean=np.log(280_000), sigma=0.45)
        if code_region == REGION_URBAINE:
            base *= 1.5
        base = float(np.clip(base, 90_000, 650_000))
        for annee in ANNEES_POPULATION:
            croissance = (1 + CROISSANCE_ANNUELLE) ** (annee - ANNEES_POPULATION[0])
            lignes.append({
                "district_code": code_district,
                "annee": annee,
                "population": round(base * croissance),
                "source": SOURCE,
            })
    return lignes


def generer_formations(districts: Districts) -> list[dict]:
    rng = _generateur(2)
    lignes = []
    for code_district, code_region in districts:
        urbain = code_region == REGION_URBAINE
        nombre = int(rng.integers(8, 13)) if urbain else int(rng.integers(4, 11))
        part_privee = 0.25 if urbain else 0.05
        for numero in range(1, nombre + 1):
            if numero == 1:
                type_formation, statut = "CMA", "public"          # le centre de référence du district
            elif rng.random() < part_privee:
                type_formation, statut = "Clinique privée", "prive"
            else:
                type_formation = "CM" if rng.random() < 0.10 else "CSPS"
                statut = "public"
            lignes.append({
                "code": f"FS-{code_district}-{numero:02d}",
                "nom": f"{type_formation} fictif {code_district}-{numero:02d}",
                "type": type_formation,
                "statut": statut,
                "district_code": code_district,
            })
    return lignes


def generer_risque(districts: Districts) -> list[dict]:
    rng = _generateur(3)
    lignes = []
    for code_district, _ in districts:
        risque_eleve = bool(rng.random() < 0.25)
        for saison in SAISONS:
            if rng.random() < 0.08:                              # le classement peut changer d'une saison à l'autre
                risque_eleve = not risque_eleve
            lignes.append({
                "district_code": code_district,
                "saison": saison,
                "risque_eleve": risque_eleve,
            })
    return lignes