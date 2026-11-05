"""dwh : déclarations validées (une ligne par version) et vue de la version courante"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE dwh.fait_declaration (
            formation_id   integer  NOT NULL REFERENCES ref.formation_sanitaire (id),
            maladie_code   text     NOT NULL REFERENCES ref.maladie (code),
            semaine_id     integer  NOT NULL REFERENCES ref.semaine (id),
            version        smallint NOT NULL CHECK (version >= 1),
            cas_suspects   integer  NOT NULL CHECK (cas_suspects >= 0),
            cas_confirmes  integer  NOT NULL CHECK (cas_confirmes >= 0),
            deces          integer  NOT NULL CHECK (deces >= 0),
            recu_le        timestamptz NOT NULL DEFAULT now(),
            lot_id         bigint   NOT NULL REFERENCES audit.lot_ingestion (id),
            PRIMARY KEY (formation_id, maladie_code, semaine_id, version)
        );
        COMMENT ON TABLE dwh.fait_declaration IS 'Declarations validees, une ligne par version. Table en ajout seul.';
        CREATE INDEX ix_fait_declaration_semaine ON dwh.fait_declaration (semaine_id, maladie_code);
        CREATE INDEX ix_fait_declaration_lot     ON dwh.fait_declaration (lot_id);
    """)

    # Une correction ne modifie jamais une ligne : elle ajoute une nouvelle version.
    op.execute("""
        CREATE FUNCTION dwh.interdire_modification() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Table en ajout seul : toute correction passe par une nouvelle version';
        END;
        $$;

        CREATE TRIGGER trg_fait_declaration_ajout_seul
        BEFORE UPDATE OR DELETE ON dwh.fait_declaration
        FOR EACH ROW EXECUTE FUNCTION dwh.interdire_modification();
    """)

    # La vue donne, pour chaque déclaration, uniquement sa dernière version.
    op.execute("""
        CREATE VIEW dwh.v_declaration_courante
        WITH (security_invoker = true) AS
        SELECT DISTINCT ON (formation_id, maladie_code, semaine_id)
               formation_id, maladie_code, semaine_id, version,
               cas_suspects, cas_confirmes, deces, recu_le, lot_id
        FROM dwh.fait_declaration
        ORDER BY formation_id, maladie_code, semaine_id, version DESC;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW dwh.v_declaration_courante;")
    op.execute("DROP TABLE dwh.fait_declaration;")
    op.execute("DROP FUNCTION dwh.interdire_modification();")