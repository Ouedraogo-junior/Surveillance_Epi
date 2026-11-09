"""Tests de l'écriture : rejets, entrepôt avec versions, clôture du lot."""
from datetime import date

import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from surveillance.pipeline.brut import charger_brut
from surveillance.pipeline.controles import Rejet
from surveillance.pipeline.ecriture import charger_dwh, consigner_rejets, terminer_lot
from surveillance.pipeline.lot import EN_TETE_ATTENDU, enregistrer_lot

COLONNES_VALIDES = ["formation_code", "maladie_code", "semaine_id",
                    "cas_suspects", "cas_confirmes", "deces", "date_reception"]
RECU = date(2026, 3, 10)


def preparer_formation(connexion) -> dict[str, int]:
    """Crée une région, un district et une formation dans la base de test (annulé en fin de test)."""
    formation_id = connexion.execute(text("""
        WITH r AS (
            INSERT INTO ref.region (code, nom) VALUES ('R01', 'Région test') RETURNING id
        ), d AS (
            INSERT INTO ref.district (code, nom, region_id)
            SELECT 'D01', 'District test', id FROM r RETURNING id
        )
        INSERT INTO ref.formation_sanitaire (code, nom, type, statut, district_id)
        SELECT 'FS-D01-01', 'Formation test', 'CSPS', 'public', id FROM d
        RETURNING id
    """)).scalar_one()
    return {"FS-D01-01": formation_id}


def creer_lot(connexion, numero: int) -> int:
    """Lot minimal pour les tests : l'empreinte doit faire 64 caractères hexadécimaux."""
    return connexion.execute(text("""
        INSERT INTO audit.lot_ingestion (source, nom_fichier, empreinte)
        VALUES ('test', 'test.csv', lpad(CAST(:n AS text), 64, '0'))
        RETURNING id
    """), {"n": str(numero)}).scalar_one()


def valides(*lignes) -> pd.DataFrame:
    return pd.DataFrame(list(lignes), columns=COLONNES_VALIDES)


def versions(connexion) -> list[tuple]:
    lignes = connexion.execute(text(
        "SELECT version, cas_suspects FROM dwh.fait_declaration ORDER BY version"
    )).all()
    return [tuple(ligne) for ligne in lignes]


def test_une_premiere_declaration_recoit_la_version_1(connexion):
    ids = preparer_formation(connexion)
    lot_id = creer_lot(connexion, 1)
    bilan = charger_dwh(connexion, lot_id, valides(("FS-D01-01", "PALU", 202610, 10, 5, 0, RECU)), ids)
    assert (bilan.nouvelles, bilan.corrections, bilan.identiques) == (1, 0, 0)
    assert versions(connexion) == [(1, 10)]


def test_un_renvoi_des_memes_chiffres_n_ecrit_rien(connexion):
    ids = preparer_formation(connexion)
    ligne = ("FS-D01-01", "PALU", 202610, 10, 5, 0, RECU)
    charger_dwh(connexion, creer_lot(connexion, 1), valides(ligne), ids)
    bilan = charger_dwh(connexion, creer_lot(connexion, 2), valides(ligne), ids)
    assert (bilan.nouvelles, bilan.corrections, bilan.identiques) == (0, 0, 1)
    assert versions(connexion) == [(1, 10)]


def test_des_chiffres_differents_ajoutent_une_version_et_la_vue_donne_la_derniere(connexion):
    ids = preparer_formation(connexion)
    charger_dwh(connexion, creer_lot(connexion, 1), valides(("FS-D01-01", "PALU", 202610, 10, 5, 0, RECU)), ids)
    bilan = charger_dwh(connexion, creer_lot(connexion, 2), valides(("FS-D01-01", "PALU", 202610, 12, 5, 0, RECU)), ids)
    assert (bilan.nouvelles, bilan.corrections, bilan.identiques) == (0, 1, 0)
    assert versions(connexion) == [(1, 10), (2, 12)]          # l'ancienne version est conservée
    courante = connexion.execute(text(
        "SELECT version, cas_suspects FROM dwh.v_declaration_courante")).all()
    assert [tuple(c) for c in courante] == [(2, 12)]


def test_la_meme_declaration_trois_fois_dans_un_fichier_est_versionnee_dans_l_ordre(connexion):
    ids = preparer_formation(connexion)
    bilan = charger_dwh(connexion, creer_lot(connexion, 1), valides(
        ("FS-D01-01", "PALU", 202610, 10, 5, 0, RECU),
        ("FS-D01-01", "PALU", 202610, 12, 5, 0, RECU),
        ("FS-D01-01", "PALU", 202610, 12, 5, 0, RECU),
    ), ids)
    assert (bilan.nouvelles, bilan.corrections, bilan.identiques) == (1, 1, 1)
    assert versions(connexion) == [(1, 10), (2, 12)]


def test_un_fichier_sans_ligne_valide_n_ecrit_rien(connexion):
    ids = preparer_formation(connexion)
    bilan = charger_dwh(connexion, creer_lot(connexion, 1), valides(), ids)
    assert (bilan.nouvelles, bilan.corrections, bilan.identiques) == (0, 0, 0)
    assert versions(connexion) == []


def test_la_date_de_reception_est_conservee(connexion):
    ids = preparer_formation(connexion)
    charger_dwh(connexion, creer_lot(connexion, 1), valides(("FS-D01-01", "PALU", 202610, 10, 5, 0, RECU)), ids)
    jour = connexion.execute(text(
        "SELECT (recu_le AT TIME ZONE 'UTC')::date FROM dwh.fait_declaration")).scalar_one()
    assert jour == RECU


def lot_avec_deux_lignes_brutes(connexion, tmp_path) -> int:
    fichier = tmp_path / "declarations_2026-S10.csv"
    fichier.write_text("\n".join([
        ",".join(EN_TETE_ATTENDU),
        "FS-D01-01,PALU,2026,10,-3,5,0,2026-03-10",
        "FS-INCONNUE,PALU,2026,10,4,1,0,2026-03-10",
    ]) + "\n", encoding="utf-8")
    lot = enregistrer_lot(connexion, fichier)
    charger_brut(connexion, lot.id, fichier)
    return lot.id


def test_les_rejets_sont_rattaches_aux_lignes_brutes(connexion, tmp_path):
    lot_id = lot_avec_deux_lignes_brutes(connexion, tmp_path)
    consigner_rejets(connexion, lot_id, [
        Rejet(numero_ligne=2, regle="valeur_negative", detail="cas_suspects = -3"),
        Rejet(numero_ligne=3, regle="formation_inconnue", detail="FS-INCONNUE"),
    ])
    lignes = connexion.execute(text("""
        SELECT r.numero_ligne, r.regle, b.contenu ->> 'formation_code'
        FROM staging.rejet r
        JOIN raw.declaration_brute b USING (lot_id, numero_ligne)
        WHERE r.lot_id = :lot ORDER BY r.numero_ligne
    """), {"lot": lot_id}).all()
    assert [tuple(l) for l in lignes] == [
        (2, "valeur_negative", "FS-D01-01"),
        (3, "formation_inconnue", "FS-INCONNUE"),
    ]


def test_un_rejet_sur_une_ligne_qui_n_existe_pas_est_refuse_par_la_base(connexion, tmp_path):
    lot_id = lot_avec_deux_lignes_brutes(connexion, tmp_path)
    with pytest.raises(IntegrityError):
        with connexion.begin_nested():
            consigner_rejets(connexion, lot_id, [Rejet(numero_ligne=99, regle="x", detail="y")])


def test_terminer_le_lot_enregistre_le_statut_et_les_rejets(connexion):
    lot_id = creer_lot(connexion, 1)
    terminer_lot(connexion, lot_id, nb_rejets=7)
    statut, nb_rejets = connexion.execute(text(
        "SELECT statut, nb_rejets FROM audit.lot_ingestion WHERE id = :id"), {"id": lot_id}).one()
    assert (statut, nb_rejets) == ("termine", 7)