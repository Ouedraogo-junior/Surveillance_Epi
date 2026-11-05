"""ref : formations sanitaires et maladies suivies"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE ref.formation_sanitaire (
            id           integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            code         text NOT NULL UNIQUE,
            nom          text NOT NULL,
            type         text NOT NULL,
            statut       text NOT NULL CHECK (statut IN ('public', 'prive')),
            district_id  integer NOT NULL REFERENCES ref.district (id),
            actif        boolean NOT NULL DEFAULT true,
            geom         geometry(Point, 4326)
        );
        COMMENT ON TABLE ref.formation_sanitaire IS 'Sites de notification (CSPS, CMA, CHR, CHU, structures privées...)';
        CREATE INDEX ix_formation_district ON ref.formation_sanitaire (district_id);
        CREATE INDEX ix_formation_geom     ON ref.formation_sanitaire USING gist (geom);
    """)

    op.execute("""
        CREATE TABLE ref.maladie (
            code        text PRIMARY KEY,
            nom         text NOT NULL,
            type_regle  text NOT NULL CHECK (type_regle IN ('taux', 'historique', 'mensuel')),
            frequence   text NOT NULL CHECK (frequence IN ('hebdomadaire', 'mensuelle'))
        );
        COMMENT ON TABLE ref.maladie IS 'Maladies suivies et famille de règle de seuil applicable';

        INSERT INTO ref.maladie (code, nom, type_regle, frequence) VALUES
            ('MENI', 'Méningite',  'taux',       'hebdomadaire'),
            ('PALU', 'Paludisme',  'historique', 'hebdomadaire'),
            ('ROUG', 'Rougeole',   'mensuel',    'hebdomadaire');
    """)


def downgrade() -> None:
    op.execute("DROP TABLE ref.maladie;")
    op.execute("DROP TABLE ref.formation_sanitaire;")