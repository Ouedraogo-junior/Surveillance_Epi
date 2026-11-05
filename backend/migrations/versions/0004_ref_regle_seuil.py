"""ref : règles de seuil d'alerte, versionnées"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SOURCE_OMS = "Guide technique SIMR, OMS-AFRO, 2e édition (2010). A confirmer avec la 3e édition nationale (2021)."


def upgrade() -> None:
    op.execute("""
        CREATE EXTENSION IF NOT EXISTS btree_gist;

        CREATE TABLE ref.regle_seuil (
            id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            maladie_code  text NOT NULL REFERENCES ref.maladie (code),
            version       smallint NOT NULL,
            parametres    jsonb NOT NULL,
            valide_du     date NOT NULL,
            valide_au     date,
            source        text NOT NULL,
            UNIQUE (maladie_code, version),
            CHECK (valide_au IS NULL OR valide_au >= valide_du),
            -- Une même maladie ne peut pas avoir deux règles valables en même temps.
            EXCLUDE USING gist (
                maladie_code WITH =,
                (daterange(valide_du, valide_au, '[]')) WITH &&
            )
        );
        COMMENT ON TABLE ref.regle_seuil IS 'Règles de seuil versionnées. Chaque alerte référence la règle appliquée.';
    """)

    # Règles de la version 1. Les valeurs sont celles du guide OMS-AFRO 2010 ; une correction
    # ultérieure sera une nouvelle version (nouvelle migration), jamais une modification de celle-ci.
    op.execute(f"""
        INSERT INTO ref.regle_seuil (maladie_code, version, parametres, valide_du, source) VALUES
        ('MENI', 1, '{{
            "unite": "cas pour 100 000 habitants par semaine",
            "alerte": 5,
            "epidemie": 15,
            "epidemie_risque_eleve": 10,
            "petite_population": {{
                "population_max": 30000,
                "alerte_cas_semaine": 2,
                "epidemie_cas_semaine": 5
            }},
            "saison_seche": {{"mois_debut": 11, "mois_fin": 5}}
        }}'::jsonb, DATE '2015-01-01', '{SOURCE_OMS}'),

        ('PALU', 1, '{{
            "methode": "quartile_historique",
            "annees_reference": 5,
            "quantile": 0.75,
            "granularite": "semaine"
        }}'::jsonb, DATE '2015-01-01', '{SOURCE_OMS}'),

        ('ROUG', 1, '{{
            "unite": "cas par mois et par district",
            "seuil": 5,
            "operateur": "superieur_a"
        }}'::jsonb, DATE '2015-01-01', '{SOURCE_OMS}');
    """)


def downgrade() -> None:
    op.execute("DROP TABLE ref.regle_seuil;")