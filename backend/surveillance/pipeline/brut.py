"""Zone brute : chaque ligne d'un fichier accepté est rangée telle quelle, sans aucun contrôle.

On garde les valeurs sous forme de texte, exactement comme elles sont arrivées. Si un contrôle de
qualité se trompe un jour, on pourra tout rejouer à partir de cette zone.
"""
import csv
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection

SQL_BRUT = text("""
    INSERT INTO raw.declaration_brute (lot_id, numero_ligne, contenu)
    VALUES (:lot_id, :numero_ligne, CAST(:contenu AS jsonb))
""")

SQL_LOT_EN_COURS = text("""
    UPDATE audit.lot_ingestion SET statut = 'en_cours', nb_lignes = :nb_lignes WHERE id = :id
""")


def lire_lignes(chemin: Path) -> list[tuple[int, dict]]:
    """Retourne (numéro de ligne dans le fichier, contenu) pour chaque ligne de données.

    La ligne 1 est l'en-tête, donc la première ligne de données porte le numéro 2.
    Une ligne vide est ignorée mais le numéro des suivantes reste celui du fichier.
    Une ligne qui n'a pas le bon nombre de colonnes est conservée sous la clé "_champs".
    """
    lignes = []
    with chemin.open(encoding="utf-8-sig", newline="") as f:
        lecteur = csv.reader(f)
        en_tete = next(lecteur)
        for champs in lecteur:
            if not champs:
                continue
            if len(champs) == len(en_tete):
                contenu = dict(zip(en_tete, champs))
            else:
                contenu = {"_champs": champs}
            lignes.append((lecteur.line_num, contenu))
    return lignes


def charger_brut(connexion: Connection, lot_id: int, chemin: Path) -> int:
    """Range les lignes du fichier dans raw.declaration_brute et passe le lot « en cours »."""
    lignes = lire_lignes(chemin)
    if lignes:
        connexion.execute(
            SQL_BRUT,
            [
                {"lot_id": lot_id, "numero_ligne": numero, "contenu": json.dumps(contenu, ensure_ascii=False)}
                for numero, contenu in lignes
            ],
        )
    connexion.execute(SQL_LOT_EN_COURS, {"id": lot_id, "nb_lignes": len(lignes)})
    return len(lignes)

SQL_LIRE_BRUT = text("""
    SELECT numero_ligne, contenu FROM raw.declaration_brute
    WHERE lot_id = :lot_id ORDER BY numero_ligne
""")


def lire_brut(connexion: Connection, lot_id: int) -> list[tuple[int, dict]]:
    """Relit les lignes d'un lot depuis la zone brute, dans le même format que lire_lignes()."""
    return [(r.numero_ligne, r.contenu) for r in connexion.execute(SQL_LIRE_BRUT, {"lot_id": lot_id})]