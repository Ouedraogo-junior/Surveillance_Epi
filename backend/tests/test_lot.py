"""Tests de la réception d'un fichier (lot)."""
from sqlalchemy import text

from surveillance.generation.declarations import COLONNES
from surveillance.pipeline.lot import EN_TETE_ATTENDU, enregistrer_lot

EN_TETE = ",".join(EN_TETE_ATTENDU)
LIGNE = "FS-D01-01,PALU,2026,9,10,5,0,2026-03-10"


def ecrire(chemin, lignes):
    chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return chemin


def lire_lot(connexion, lot_id):
    return connexion.execute(
        text("SELECT statut, nom_fichier, length(empreinte), detail FROM audit.lot_ingestion WHERE id = :id"),
        {"id": lot_id},
    ).one()


def test_l_en_tete_attendu_est_celui_du_generateur():
    assert EN_TETE_ATTENDU == COLONNES


def test_un_fichier_valide_cree_un_lot(connexion, tmp_path):
    fichier = ecrire(tmp_path / "declarations_2026-S10.csv", [EN_TETE, LIGNE])
    lot = enregistrer_lot(connexion, fichier)
    assert lot.statut == "nouveau"
    assert lot.id is not None
    statut, nom, longueur, detail = lire_lot(connexion, lot.id)
    assert (statut, nom, longueur, detail) == ("recu", "declarations_2026-S10.csv", 64, None)


def test_un_fichier_renvoye_a_l_identique_est_refuse(connexion, tmp_path):
    original = ecrire(tmp_path / "declarations_2026-S10.csv", [EN_TETE, LIGNE])
    renvoi = ecrire(tmp_path / "declarations_2026-S10_renvoi.csv", [EN_TETE, LIGNE])
    premier = enregistrer_lot(connexion, original)
    second = enregistrer_lot(connexion, renvoi)
    assert second.statut == "deja_recu"
    assert second.id is None
    assert str(premier.id) in second.detail
    nb_lots = connexion.execute(text("SELECT count(*) FROM audit.lot_ingestion")).scalar_one()
    assert nb_lots == 1


def test_un_en_tete_invalide_met_le_lot_en_echec(connexion, tmp_path):
    en_tete_incomplet = "formation_code,maladie_code,annee,semaine,cas_suspects,cas_confirmes,date_reception"
    fichier = ecrire(tmp_path / "format_invalide.csv", [en_tete_incomplet, LIGNE])
    lot = enregistrer_lot(connexion, fichier)
    assert lot.statut == "en_tete_invalide"
    statut, _, _, detail = lire_lot(connexion, lot.id)
    assert statut == "echec"
    assert detail.startswith("En-tête invalide")


def test_un_fichier_vide_est_refuse(connexion, tmp_path):
    fichier = tmp_path / "vide.csv"
    fichier.write_text("", encoding="utf-8")
    assert enregistrer_lot(connexion, fichier).statut == "en_tete_invalide"


def test_un_en_tete_precede_d_une_marque_excel_est_accepte(connexion, tmp_path):
    fichier = tmp_path / "excel.csv"
    fichier.write_bytes(b"\xef\xbb\xbf" + (EN_TETE + "\n" + LIGNE + "\n").encode("utf-8"))
    assert enregistrer_lot(connexion, fichier).statut == "nouveau"