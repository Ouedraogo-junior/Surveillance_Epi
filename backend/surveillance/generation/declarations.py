"""Transforme le signal simulé en déclarations reçues, comme le système les recevrait :
une déclaration par formation, maladie et semaine, avec des oublis, des retards,
des corrections et des erreurs volontairement injectées.

Tout est fictif. Le hasard est fixé par une graine : mêmes entrées, mêmes résultats.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from surveillance.generation.simulation import MALADIES, Signal
from surveillance.generation.structure import GRAINE

DATE_LIMITE = date(2026, 11, 5)     # "aujourd'hui" : aucune déclaration n'est reçue après cette date
COLONNES = ["formation_code", "maladie_code", "annee", "semaine",
            "cas_suspects", "cas_confirmes", "deces", "date_reception"]

PROBA_CORRECTION = 0.02             # part des lignes envoyées d'abord avec des chiffres faux, puis corrigées
PROBA_ERREUR = 0.010                # part des lignes qui contiennent une erreur volontaire
TYPES_ERREUR = ("valeur_negative", "valeur_non_numerique", "valeur_manquante", "formation_inconnue",
                "maladie_inconnue", "semaine_invalide", "semaine_future", "doublon_exact")


@dataclass
class Resultat:
    fichiers: dict       # nom de fichier -> liste de lignes (formation, maladie, annee, semaine, s, c, d, date, erreur)
    statistiques: dict


def _generateur(numero: int) -> np.random.Generator:
    return np.random.default_rng([GRAINE, numero])


def _nom_fichier(jour: date) -> str:
    annee, semaine, _ = jour.isocalendar()
    return f"declarations_{annee}-S{semaine:02d}.csv"


def produire(signal: Signal) -> Resultat:
    nf, nw = len(signal.formations), len(signal.semaines)
    rng = _generateur(30)

    # Chaque formation a sa fiabilité : le secteur public envoie moins régulièrement que le privé,
    # d'après les taux de complétude du bulletin de santé publique de juin 2025 (88 % et 94 %).
    prive = np.array([f["statut"] == "prive" for f in signal.formations])
    p_recu = np.clip(np.where(prive, rng.normal(0.94, 0.04, nf), rng.normal(0.88, 0.07, nf)), 0.5, 1.0)
    p_temps = np.clip(rng.normal(0.80, 0.10, nf), 0.4, 0.98)

    recu = rng.random((nf, nw)) < p_recu[:, None]                   # le rapport est-il un jour reçu ?
    a_temps = rng.random((nf, nw)) < p_temps[:, None]               # arrive-t-il la semaine suivante ?
    retard = np.minimum(1 + rng.geometric(0.5, size=(nf, nw)), 8)   # sinon, de 2 à 8 semaines après
    delai = np.where(a_temps, 1, retard)
    jour = rng.integers(0, 6, size=(nf, nw))                        # du lundi au samedi

    debuts = [s["date_debut"] for s in signal.semaines]
    annees = [s["annee"] for s in signal.semaines]
    numeros = [s["numero"] for s in signal.semaines]
    cas = {m: {k: v.tolist() for k, v in signal.cas[m].items()} for m in MALADIES}

    rng_corr, rng_err = _generateur(31), _generateur(32)
    fichiers = defaultdict(list)
    stats = {"rapports_attendus": nf * nw, "rapports_recus": 0, "rapports_a_temps": 0,
             "corrections": 0, "erreurs": defaultdict(int)}

    def ajouter(date_reception, ligne):
        fichiers[_nom_fichier(date_reception)].append(ligne)

    for f, w in zip(*np.nonzero(recu)):
        f, w = int(f), int(w)
        date_rec = debuts[w] + timedelta(days=7 * int(delai[f, w]) + int(jour[f, w]))
        if date_rec > DATE_LIMITE:
            continue                                                # pas encore reçu à la date du jour
        stats["rapports_recus"] += 1
        stats["rapports_a_temps"] += int(delai[f, w] == 1)
        code = signal.formations[f]["code"]

        for m in MALADIES:
            s, c, d = cas[m]["suspects"][f][w], cas[m]["confirmes"][f][w], cas[m]["deces"][f][w]
            base = [code, m, annees[w], numeros[w]]

            if rng_corr.random() < PROBA_CORRECTION:
                # Premier envoi avec des chiffres faux, puis correction plus tard avec les bons.
                s_faux = max(0, s + int(rng_corr.integers(-4, 6)))
                if s_faux == s:
                    s_faux += 1
                lignes = [(date_rec, base + [s_faux, c, d, date_rec], "")]
                date_corr = date_rec + timedelta(days=7 * int(rng_corr.integers(1, 5)))
                if date_corr <= DATE_LIMITE:
                    lignes.append((date_corr, base + [s, c, d, date_corr], ""))
                    stats["corrections"] += 1
            else:
                lignes = [(date_rec, base + [s, c, d, date_rec], "")]

            for date_ligne, valeurs, _ in lignes:
                erreur = ""
                if rng_err.random() < PROBA_ERREUR:
                    erreur = TYPES_ERREUR[int(rng_err.integers(len(TYPES_ERREUR)))]
                    duplicata = list(valeurs)
                    if erreur == "valeur_negative":
                        valeurs[4] = -int(rng_err.integers(1, 6))
                    elif erreur == "valeur_non_numerique":
                        valeurs[4] = "N/A"
                    elif erreur == "valeur_manquante":
                        valeurs[5] = ""
                    elif erreur == "formation_inconnue":
                        valeurs[0] = f"FS-D99-{int(rng_err.integers(1, 30)):02d}"
                    elif erreur == "maladie_inconnue":
                        valeurs[1] = ("PALUDISME", "MENINGITE", "XXXX")[int(rng_err.integers(3))]
                    elif erreur == "semaine_invalide":
                        valeurs[3] = 54
                    elif erreur == "semaine_future":
                        valeurs[2], valeurs[3] = 2027, 5
                    stats["erreurs"][erreur] += 1
                if erreur == "doublon_exact":
                    ajouter(date_ligne, tuple(duplicata) + ("",))                 # l'original, valide
                    ajouter(date_ligne, tuple(duplicata) + ("doublon_exact",))    # sa copie
                else:
                    ajouter(date_ligne, tuple(valeurs) + (erreur,))

    for lignes in fichiers.values():
        lignes.sort(key=lambda l: (l[0], l[1], l[2], l[3]))         # tri stable : une copie reste après son original
    return Resultat(dict(fichiers), stats)