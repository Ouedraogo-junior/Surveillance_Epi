"""Tests des contrôles de qualité (sans base de données)."""
from datetime import date

import pytest

from surveillance.pipeline.controles import Referentiels, controler

REF = Referentiels(
    formations=frozenset({"FS-D01-01", "FS-D01-02"}),
    maladies=frozenset({"MENI", "PALU", "ROUG"}),
    calendrier={202609: date(2026, 2, 23), 202705: date(2027, 2, 1)},
)


def ligne(**modifications):
    base = {"formation_code": "FS-D01-01", "maladie_code": "PALU", "annee": "2026", "semaine": "9",
            "cas_suspects": "10", "cas_confirmes": "5", "deces": "0", "date_reception": "2026-03-10"}
    base.update(modifications)
    return base


def test_une_ligne_valide_passe_avec_ses_types():
    resultat = controler([(2, ligne())], REF)
    assert resultat.rejets == []
    valide = resultat.valides.iloc[0]
    assert valide["numero_ligne"] == 2
    assert valide["semaine_id"] == 202609
    assert (valide["cas_suspects"], valide["cas_confirmes"], valide["deces"]) == (10, 5, 0)
    assert valide["date_reception"] == date(2026, 3, 10)


@pytest.mark.parametrize("modifications, regle", [
    ({"cas_suspects": "-3"}, "valeur_negative"),
    ({"cas_suspects": "N/A"}, "valeur_non_numerique"),
    ({"cas_suspects": "3.5"}, "valeur_non_numerique"),
    ({"cas_confirmes": ""}, "valeur_manquante"),
    ({"deces": "  "}, "valeur_manquante"),
    ({"formation_code": "FS-D99-01"}, "formation_inconnue"),
    ({"maladie_code": "PALUDISME"}, "maladie_inconnue"),
    ({"semaine": "54"}, "semaine_invalide"),
    ({"semaine": "abc"}, "semaine_invalide"),
    ({"annee": "2027", "semaine": "5"}, "semaine_future"),
    ({"date_reception": "2026-13-45"}, "date_reception_invalide"),
    ({"date_reception": ""}, "date_reception_invalide"),
])
def test_chaque_erreur_declenche_une_seule_regle(modifications, regle):
    resultat = controler([(2, ligne(**modifications))], REF)
    assert [r.regle for r in resultat.rejets] == [regle]
    assert resultat.valides.empty


def test_le_detail_indique_la_valeur_en_cause():
    resultat = controler([(7, ligne(cas_suspects="N/A"))], REF)
    assert resultat.rejets[0].numero_ligne == 7
    assert resultat.rejets[0].detail == "cas_suspects = 'N/A'"


def test_une_ligne_peut_violer_plusieurs_regles():
    resultat = controler([(2, ligne(cas_suspects="-3", formation_code="FS-D99-01"))], REF)
    assert [r.regle for r in resultat.rejets] == ["formation_inconnue", "valeur_negative"]


def test_le_doublon_exact_est_refuse_mais_pas_l_original():
    resultat = controler([(2, ligne()), (3, ligne()), (4, ligne(formation_code="FS-D01-02"))], REF)
    assert [(r.numero_ligne, r.regle) for r in resultat.rejets] == [(3, "doublon_exact")]
    assert list(resultat.valides["numero_ligne"]) == [2, 4]


def test_une_ligne_au_mauvais_nombre_de_colonnes_est_refusee():
    resultat = controler([(2, {"_champs": ["FS-D01-01", "PALU", "2026"]}), (3, ligne())], REF)
    assert [(r.numero_ligne, r.regle) for r in resultat.rejets] == [(2, "structure_invalide")]
    assert list(resultat.valides["numero_ligne"]) == [3]


def test_un_fichier_sans_ligne_valide_donne_un_resultat_vide():
    resultat = controler([(2, {"_champs": ["x"]})], REF)
    assert resultat.valides.empty
    assert len(resultat.rejets) == 1