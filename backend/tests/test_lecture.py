"""Tests de la relecture de la zone brute, des référentiels et de la reprise d'un lot en échec."""
from datetime import date

from sqlalchemy import text

from surveillance.pipeline.brut import charger_brut, lire_brut, lire_lignes
from surveillance.pipeline.lot import EN_TETE_ATTENDU, enregistrer_lot, marquer_echec
from surveillance.pipeline.referentiels import charger_referentiels

EN_TETE = ",".join(EN_TETE_ATTENDU)


def test_lire_brut_redonne_exactement_ce_qui_a_ete_range(connexion, tmp_path):
    fichier = tmp_path / "declarations_2026-S10.csv"
    fichier.write_text("\n".join([
        EN_TETE,
        "FS-D01-01,PALU,2026,10,5,2,0,2026-03-10",
        "",
        "ligne,trop,courte",
        "FS-D01-01,ROUG,2026,10,é,2,0,2026-03-10",
    ]) + "\n", encoding="utf-8")
    lot = enregistrer_lot(connexion, fichier)
    charger_brut(connexion, lot.id, fichier)
    assert lire_brut(connexion, lot.id) == lire_lignes(fichier)


def test_les_referentiels_sont_lus_en_base(connexion):
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
    ref, ids = charger_referentiels(connexion)
    assert ids == {"FS-D01-01": formation_id}
    assert ref.formations == frozenset({"FS-D01-01"})
    assert ref.maladies == frozenset({"MENI", "PALU", "ROUG"})
    assert ref.calendrier[202610] == date(2026, 3, 2)
    assert ref.calendrier[202601] == date(2025, 12, 29)


def test_un_lot_en_echec_est_repris_quand_le_fichier_est_renvoye(connexion, tmp_path):
    fichier = tmp_path / "declarations_2026-S10.csv"
    fichier.write_text(EN_TETE + "\nFS-D01-01,PALU,2026,10,5,2,0,2026-03-10\n", encoding="utf-8")
    premier = enregistrer_lot(connexion, fichier)
    marquer_echec(connexion, premier.id, "panne simulée")

    second = enregistrer_lot(connexion, fichier)
    assert second.statut == "nouveau"
    assert second.id == premier.id
    statut, detail = connexion.execute(text(
        "SELECT statut, detail FROM audit.lot_ingestion WHERE id = :id"), {"id": premier.id}).one()
    assert (statut, detail) == ("recu", None)
    assert connexion.execute(text("SELECT count(*) FROM audit.lot_ingestion")).scalar_one() == 1


def test_un_lot_en_cours_n_est_pas_repris(connexion, tmp_path):
    fichier = tmp_path / "declarations_2026-S10.csv"
    fichier.write_text(EN_TETE + "\nFS-D01-01,PALU,2026,10,5,2,0,2026-03-10\n", encoding="utf-8")
    premier = enregistrer_lot(connexion, fichier)
    charger_brut(connexion, premier.id, fichier)           # le lot passe « en_cours »
    assert enregistrer_lot(connexion, fichier).statut == "deja_recu"