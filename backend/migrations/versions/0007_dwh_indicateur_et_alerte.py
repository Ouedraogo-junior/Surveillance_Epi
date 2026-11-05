"""dwh : indicateurs par district et alertes"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Agrégats par district, maladie et semaine. Table dérivée : elle peut être recalculée.
    op.execute("""
        CREATE TABLE dwh.fait_indicateur_district (
            district_id             integer  NOT NULL REFERENCES ref.district (id),
            maladie_code            text     NOT NULL REFERENCES ref.maladie (code),
            semaine_id              integer  NOT NULL REFERENCES ref.semaine (id),
            cas_suspects            integer  NOT NULL CHECK (cas_suspects >= 0),
            cas_confirmes           integer  NOT NULL CHECK (cas_confirmes >= 0),
            deces                   integer  NOT NULL CHECK (deces >= 0),
            population              integer  CHECK (population > 0),
            declarations_attendues  integer  NOT NULL CHECK (declarations_attendues >= 0),
            declarations_recues     integer  NOT NULL CHECK (declarations_recues >= 0),
            declarations_a_temps    integer  NOT NULL CHECK (declarations_a_temps >= 0),
            taux_100000  numeric(10,2) GENERATED ALWAYS AS (
                CASE WHEN population > 0
                     THEN round(100000.0 * cas_suspects / population, 2) END
            ) STORED,
            completude   numeric(5,1) GENERATED ALWAYS AS (
                CASE WHEN declarations_attendues > 0
                     THEN round(100.0 * declarations_recues / declarations_attendues, 1) END
            ) STORED,
            promptitude  numeric(5,1) GENERATED ALWAYS AS (
                CASE WHEN declarations_attendues > 0
                     THEN round(100.0 * declarations_a_temps / declarations_attendues, 1) END
            ) STORED,
            calcule_le   timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (district_id, maladie_code, semaine_id),
            CHECK (declarations_recues <= declarations_attendues),
            CHECK (declarations_a_temps <= declarations_recues)
        );
        COMMENT ON TABLE dwh.fait_indicateur_district IS 'Agregats par district, maladie et semaine. Table derivee, recalculable.';
        CREATE INDEX ix_indicateur_maladie_semaine ON dwh.fait_indicateur_district (maladie_code, semaine_id);
    """)

    # Alertes calculées : chacune garde la valeur observée, le seuil appliqué et la règle utilisée.
    op.execute("""
        CREATE TABLE dwh.fait_alerte (
            id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            district_id      integer NOT NULL REFERENCES ref.district (id),
            maladie_code     text    NOT NULL REFERENCES ref.maladie (code),
            semaine_id       integer NOT NULL REFERENCES ref.semaine (id),
            niveau           text    NOT NULL CHECK (niveau IN ('alerte', 'epidemie')),
            valeur_observee  numeric NOT NULL,
            unite            text    NOT NULL,
            seuil_applique   numeric NOT NULL,
            regle_id         integer NOT NULL REFERENCES ref.regle_seuil (id),
            calcule_le       timestamptz NOT NULL DEFAULT now(),
            UNIQUE (district_id, maladie_code, semaine_id)
        );
        COMMENT ON TABLE dwh.fait_alerte IS 'Alertes calculees. Chaque alerte garde la valeur observee, le seuil applique et la regle utilisee.';
        CREATE INDEX ix_alerte_semaine ON dwh.fait_alerte (semaine_id, maladie_code);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE dwh.fait_alerte;")
    op.execute("DROP TABLE dwh.fait_indicateur_district;")