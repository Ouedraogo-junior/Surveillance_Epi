"""Tests du traitement complet d'un fichier, sur la vraie base de test."""
import pytest
from sqlalchemy import text

from surveillance.pipeline import traitement
from surveillance.pipeline.lot import EN_TETE_ATTENDU
from surveillance.pipeline.traitement import traiter_fichier

EN_TETE = ",".join(EN_TETE_ATTENDU)
BONNE = "FS-D01-01,PALU,2026,10,10,5,0,2026-03-10"
NEGATIVE = "FS-D01-02,PALU,2026,10,-3,1,0,2026-03-10"
INCONNUE = "FS-INCONNUE,PALU,2026,10,4,1,0,2026-03-10"


@pytest.fixture
def formations(connexion):
    """Une région, un district et deux formations dans la base de test (annulés en fin de test)."""
    connexion.execute(text("""
        WITH r AS (
            INSERT INTO ref.region (code, nom) VALUES ('R01', 'Région test') RETURNING id
        ), d AS (
            INSERT INTO ref.district (code, nom, region_id)
            SELECT 'D01', 'District test', id FROM r RETURNING id
        )
        INSERT INTO ref.formation_sanitaire (code, nom, type, statut, district_id)
        SELECT code, 'Formation test', 'CSPS', 'public', d.id
        FROM d, (VALUES ('FS-D01-01'), ('FS-D01-02')) AS f(code)
    """))


def ecrire(chemin, *lignes):
    chemin.write_text("\n".join([EN_TETE, *lignes]) + "\n", encoding="utf-8")
    return chemin


def compter(connexion, table):
    return connexion.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


def test_un_fichier_melange_est_traite_et_les_rejets_sont_tracables(connexion, formations, tmp_path):
    fichier = ecrire(tmp_path / "declarations_2026-S10.csv", BONNE, NEGATIVE, INCONNUE)
    bilan = traiter_fichier(connexion, fichier)

    assert (bilan.statut, bilan.nb_lignes, bilan.nb_rejets) == ("termine", 3, 2)
    assert (bilan.entrepot.nouvelles, bilan.entrepot.corrections, bilan.entrepot.identiques) == (1, 0, 0)
    assert compter(connexion, "dwh.fait_declaration") == 1
    statut, nb_lignes, nb_rejets = connexion.execute(text(
        "SELECT statut, nb_lignes, nb_rejets FROM audit.lot_ingestion WHERE id = :id"), {"id": bilan.lot_id}).one()
    assert (statut, nb_lignes, nb_rejets) == ("termine", 3, 2)

    rejets = connexion.execute(text("""
        SELECT r.numero_ligne, r.regle, b.contenu ->> 'formation_code'
        FROM staging.rejet r JOIN raw.declaration_brute b USING (lot_id, numero_ligne)
        WHERE r.lot_id = :lot ORDER BY r.numero_ligne
    """), {"lot": bilan.lot_id}).all()
    assert [tuple(r) for r in rejets] == [
        (3, "valeur_negative", "FS-D01-02"),
        (4, "formation_inconnue", "FS-INCONNUE"),
    ]


def test_un_fichier_ulterieur_aux_chiffres_differents_cree_la_version_2(connexion, formations, tmp_path):
    traiter_fichier(connexion, ecrire(tmp_path / "declarations_2026-S10.csv", BONNE))
    correction = "FS-D01-01,PALU,2026,10,12,5,0,2026-03-17"
    bilan = traiter_fichier(connexion, ecrire(tmp_path / "declarations_2026-S11.csv", correction))

    assert (bilan.entrepot.nouvelles, bilan.entrepot.corrections) == (0, 1)
    assert compter(connexion, "dwh.fait_declaration") == 2
    courante = connexion.execute(text("SELECT version, cas_suspects FROM dwh.v_declaration_courante")).all()
    assert [tuple(c) for c in courante] == [(2, 12)]


def test_un_fichier_ulterieur_aux_memes_chiffres_n_ajoute_pas_de_version(connexion, formations, tmp_path):
    traiter_fichier(connexion, ecrire(tmp_path / "declarations_2026-S10.csv", BONNE))
    meme_chiffres = "FS-D01-01,PALU,2026,10,10,5,0,2026-03-17"
    bilan = traiter_fichier(connexion, ecrire(tmp_path / "declarations_2026-S11.csv", meme_chiffres))

    assert bilan.statut == "termine"
    assert (bilan.entrepot.nouvelles, bilan.entrepot.corrections, bilan.entrepot.identiques) == (0, 0, 1)
    assert compter(connexion, "dwh.fait_declaration") == 1


def test_un_fichier_renvoye_a_l_identique_est_ignore(connexion, formations, tmp_path):
    fichier = ecrire(tmp_path / "declarations_2026-S10.csv", BONNE)
    traiter_fichier(connexion, fichier)
    bilan = traiter_fichier(connexion, fichier)
    assert bilan.statut == "deja_recu"
    assert compter(connexion, "audit.lot_ingestion") == 1
    assert compter(connexion, "dwh.fait_declaration") == 1


def test_un_en_tete_invalide_n_ecrit_rien_dans_la_zone_brute(connexion, formations, tmp_path):
    fichier = tmp_path / "format_invalide.csv"
    fichier.write_text("code,semaine\nFS-D01-01,10\n", encoding="utf-8")
    bilan = traiter_fichier(connexion, fichier)

    assert bilan.statut == "en_tete_invalide"
    statut = connexion.execute(text("SELECT statut FROM audit.lot_ingestion WHERE id = :id"),
                               {"id": bilan.lot_id}).scalar_one()
    assert statut == "echec"
    assert compter(connexion, "raw.declaration_brute") == 0


def test_une_panne_annule_le_fichier_et_le_renvoi_le_traite(connexion, formations, tmp_path, monkeypatch):
    fichier = ecrire(tmp_path / "declarations_2026-S10.csv", BONNE, NEGATIVE)

    def panne(*args, **kwargs):
        raise RuntimeError("panne simulée")

    monkeypatch.setattr(traitement, "charger_dwh", panne)
    bilan = traiter_fichier(connexion, fichier)
    assert bilan.statut == "echec"
    assert "panne simulée" in bilan.detail
    # Tout ce que le fichier avait écrit est annulé ; seul le lot reste, en échec.
    assert compter(connexion, "raw.declaration_brute") == 0
    assert compter(connexion, "staging.rejet") == 0
    assert compter(connexion, "dwh.fait_declaration") == 0
    statut, detail = connexion.execute(text(
        "SELECT statut, detail FROM audit.lot_ingestion WHERE id = :id"), {"id": bilan.lot_id}).one()
    assert statut == "echec" and "panne simulée" in detail

    # La panne est réparée : on renvoie le même fichier, le même lot est repris et mené au bout.
    monkeypatch.undo()
    reprise = traiter_fichier(connexion, fichier)
    assert reprise.statut == "termine"
    assert reprise.lot_id == bilan.lot_id
    assert (reprise.nb_lignes, reprise.nb_rejets) == (2, 1)
    assert compter(connexion, "dwh.fait_declaration") == 1