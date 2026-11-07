"""Contrôles de qualité : chaque ligne brute est validée par un schéma Pandera.

Une règle est une fonction nommée. Une ligne qui viole une règle est refusée et consignée avec le
nom de la règle et le détail de la valeur en cause. Une ligne peut violer plusieurs règles.

Les règles sont écrites pour ne pas se recouper : une valeur vide relève de « valeur_manquante »,
un texte qui n'est pas un entier de « valeur_non_numerique », un entier négatif de « valeur_negative ».
"""
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

from surveillance.pipeline.lot import EN_TETE_ATTENDU

COLONNES_EFFECTIFS = ("cas_suspects", "cas_confirmes", "deces")

REGLES = (
    "structure_invalide", "formation_inconnue", "maladie_inconnue", "semaine_invalide", "semaine_future",
    "date_reception_invalide", "valeur_manquante", "valeur_non_numerique", "valeur_negative", "doublon_exact",
)


@dataclass(frozen=True)
class Referentiels:
    formations: frozenset[str]       # codes des formations sanitaires connues
    maladies: frozenset[str]         # codes des maladies suivies
    calendrier: dict[int, date]      # identifiant de semaine (ex. 202609) -> date de début


@dataclass(frozen=True)
class Rejet:
    numero_ligne: int
    regle: str
    detail: str


@dataclass
class Controle:
    valides: pd.DataFrame
    rejets: list[Rejet] = field(default_factory=list)


def _aligner(resultat: pd.Series, s: pd.Series) -> pd.Series:
    return resultat.reindex(s.index).astype(bool)


def _controles_effectifs() -> list:
    """Les trois règles d'une colonne de comptage : manquant, pas un entier, négatif."""
    return [
        pa.Check(lambda s: s.str.strip() != "", name="valeur_manquante"),
        pa.Check(lambda s: (s.str.strip() == "") | s.str.fullmatch(r"-?\d+"), name="valeur_non_numerique"),
        pa.Check(lambda s: ~s.str.fullmatch(r"-\d+"), name="valeur_negative"),
    ]


def _detail(regle: str, colonne: str, ligne: pd.Series) -> str:
    if regle in ("valeur_manquante", "valeur_non_numerique", "valeur_negative",
                 "formation_inconnue", "maladie_inconnue", "date_reception_invalide"):
        return f"{colonne} = {ligne[colonne]!r}"
    if regle == "semaine_invalide":
        return f"semaine {ligne['annee']!r}-S{ligne['semaine']!r} absente du calendrier"
    if regle == "semaine_future":
        return (f"semaine {ligne['annee']}-S{ligne['semaine']} commence après "
                f"la date de réception {ligne['date_reception']}")
    return "ligne identique à une ligne précédente du fichier"


def controler(lignes: list[tuple[int, dict]], ref: Referentiels) -> Controle:
    """Valide les lignes brutes (numéro de ligne, contenu). Retourne les lignes valides et les rejets."""
    rejets: list[Rejet] = []
    completes = []
    for numero, contenu in lignes:
        if "_champs" in contenu:
            rejets.append(Rejet(numero, "structure_invalide",
                                f"{len(contenu['_champs'])} colonnes reçues au lieu de {len(EN_TETE_ATTENDU)}"))
        else:
            completes.append((numero, contenu))

    if not completes:
        return Controle(pd.DataFrame(columns=["numero_ligne", *EN_TETE_ATTENDU[:2], "semaine_id",
                                              *COLONNES_EFFECTIFS, "date_reception"]), rejets)

    df = pd.DataFrame([c for _, c in completes], index=[n for n, _ in completes], dtype=object)
    df.index.name = "numero_ligne"

    # Valeurs calculées une fois, utilisées par plusieurs règles.
    semaine_id = pd.to_numeric(df["annee"], errors="coerce") * 100 + pd.to_numeric(df["semaine"], errors="coerce")
    date_reception = pd.to_datetime(df["date_reception"], format="%Y-%m-%d", errors="coerce")
    semaine_connue = semaine_id.isin([float(k) for k in ref.calendrier])
    debut_semaine = pd.to_datetime(semaine_id.map({float(k): v for k, v in ref.calendrier.items()}))
    semaine_future = semaine_connue & date_reception.notna() & (debut_semaine > date_reception)

    schema = pa.DataFrameSchema({
        "formation_code": pa.Column(checks=[
            pa.Check(lambda s: _aligner(s.isin(ref.formations), s), name="formation_inconnue"),
            pa.Check(lambda s: _aligner(~df.duplicated(keep="first"), s), name="doublon_exact"),
        ]),
        "maladie_code": pa.Column(checks=[
            pa.Check(lambda s: _aligner(s.isin(ref.maladies), s), name="maladie_inconnue"),
        ]),
        "annee": pa.Column(checks=[
            pa.Check(lambda s: _aligner(~semaine_future, s), name="semaine_future"),
        ]),
        "semaine": pa.Column(checks=[
            pa.Check(lambda s: _aligner(semaine_connue, s), name="semaine_invalide"),
        ]),
        "date_reception": pa.Column(checks=[
            pa.Check(lambda s: _aligner(date_reception.notna(), s), name="date_reception_invalide"),
        ]),
        **{colonne: pa.Column(checks=_controles_effectifs()) for colonne in COLONNES_EFFECTIFS},
    })

    try:
        schema.validate(df, lazy=True)
    except SchemaErrors as erreurs:
        for cas in erreurs.failure_cases.itertuples():
            numero = int(cas.index)
            rejets.append(Rejet(numero, cas.check, _detail(cas.check, cas.column, df.loc[numero])))
        rejetees = {r.numero_ligne for r in rejets}
        df = df.drop(index=[n for n in df.index if n in rejetees])

    rejets.sort(key=lambda r: (r.numero_ligne, REGLES.index(r.regle)))

    valides = pd.DataFrame({
        "formation_code": df["formation_code"],
        "maladie_code": df["maladie_code"],
        "semaine_id": (pd.to_numeric(df["annee"]) * 100 + pd.to_numeric(df["semaine"])).astype("int64"),
        **{c: pd.to_numeric(df[c]).astype("int64") for c in COLONNES_EFFECTIFS},
        "date_reception": pd.to_datetime(df["date_reception"], format="%Y-%m-%d").dt.date,
    }, index=df.index).reset_index()
    return Controle(valides, rejets)