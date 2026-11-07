"""Tests de la zone brute."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from surveillance.pipeline.brut import charger_brut
from surveillance.pipeline.lot import EN_TETE_ATTENDU, enregistrer_lot

EN_TETE = ",".join(EN_TETE_ATTENDU)


def preparer(connexion, tmp_path, lignes):
    fichier = tmp_path / "declarations_2026-S10.csv"
    fichier.write_text("\n".join([EN_TETE] + lignes) + "\n", encoding="utf-8")
    lot = enregistrer_lot(connexion, fichier)
    return lot, fichier


def lire_brut(connexion, lot_id):
    return connexion.execute(
        text("SELECT numero_ligne, contenu FROM raw.declaration_brute WHERE lot_id = :id ORDER BY numero_ligne"),
        {"id": lot_id},
    ).all()


def test_les_lignes_sont_rangees_telles_quelles_avec_leur_numero(connexion, tmp_path):
    lot, fichier = preparer(connexion, tmp_path, [
        "FS-D01-01,PALU,2026,9,10,5,0,2026-03-10",
        "FS-D01-02,PALU,2026,9,N/A,,0,2026-03-10",
        "FS-D01-03,PALU,2026,9,-3,1,0,2026-03-10",
    ])
    assert charger_brut(connexion, lot.id, fichier) == 3
    brut = lire_brut(connexion, lot.id)
    assert [numero for numero, _ in brut] == [2, 3, 4]
    assert brut[1][1]["cas_suspects"] == "N/A"          # rien n'est converti ni corrigé
    assert brut[1][1]["cas_confirmes"] == ""
    assert brut[2][1]["cas_suspects"] == "-3"           # même un nombre reste du texte
    assert all(isinstance(v, str) for _, c in brut for v in c.values())


def test_une_ligne_vide_est_ignoree_mais_la_numerotation_reste_celle_du_fichier(connexion, tmp_path):
    lot, fichier = preparer(connexion, tmp_path, [
        "FS-D01-01,PALU,2026,9,10,5,0,2026-03-10",
        "",
        "FS-D01-02,PALU,2026,9,12,6,0,2026-03-10",
    ])
    assert charger_brut(connexion, lot.id, fichier) == 2
    assert [numero for numero, _ in lire_brut(connexion, lot.id)] == [2, 4]


def test_une_ligne_au_mauvais_nombre_de_colonnes_est_conservee(connexion, tmp_path):
    lot, fichier = preparer(connexion, tmp_path, ["FS-D01-01,PALU,2026"])
    charger_brut(connexion, lot.id, fichier)
    assert lire_brut(connexion, lot.id)[0][1] == {"_champs": ["FS-D01-01", "PALU", "2026"]}


def test_le_lot_passe_en_cours_avec_son_nombre_de_lignes(connexion, tmp_path):
    lot, fichier = preparer(connexion, tmp_path, [
        "FS-D01-01,PALU,2026,9,10,5,0,2026-03-10",
        "FS-D01-02,PALU,2026,9,12,6,0,2026-03-10",
    ])
    charger_brut(connexion, lot.id, fichier)
    statut, nb = connexion.execute(
        text("SELECT statut, nb_lignes FROM audit.lot_ingestion WHERE id = :id"), {"id": lot.id}
    ).one()
    assert (statut, nb) == ("en_cours", 2)


def test_la_zone_brute_ne_peut_etre_ni_modifiee_ni_supprimee(connexion, tmp_path):
    lot, fichier = preparer(connexion, tmp_path, ["FS-D01-01,PALU,2026,9,10,5,0,2026-03-10"])
    charger_brut(connexion, lot.id, fichier)
    with pytest.raises(DBAPIError, match="ajout seul"):
        with connexion.begin_nested():
            connexion.execute(text("UPDATE raw.declaration_brute SET contenu = CAST('{}' AS jsonb)"))
    with pytest.raises(DBAPIError, match="ajout seul"):
        with connexion.begin_nested():
            connexion.execute(text("DELETE FROM raw.declaration_brute"))