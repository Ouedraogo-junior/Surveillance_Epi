"""audit, raw, staging : traçabilité des lots, lignes brutes, rejets"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Un enregistrement par fichier reçu.
    op.execute("""
        CREATE TABLE audit.lot_ingestion (
            id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source      text NOT NULL,
            nom_fichier text NOT NULL,
            empreinte   text NOT NULL UNIQUE CHECK (empreinte ~ '^[0-9a-f]{64}$'),
            recu_le     timestamptz NOT NULL DEFAULT now(),
            statut      text NOT NULL DEFAULT 'recu'
                        CHECK (statut IN ('recu', 'en_cours', 'termine', 'echec')),
            nb_lignes   integer NOT NULL DEFAULT 0,
            nb_rejets   integer NOT NULL DEFAULT 0
        );
        COMMENT ON TABLE audit.lot_ingestion IS 'Un enregistrement par fichier reçu. L empreinte SHA-256 empêche de traiter deux fois le même fichier.';
    """)

    # Les lignes telles qu elles sont arrivées, sans aucune modification.
    op.execute("""
        CREATE TABLE raw.declaration_brute (
            lot_id        bigint NOT NULL REFERENCES audit.lot_ingestion (id),
            numero_ligne  integer NOT NULL,
            contenu       jsonb NOT NULL,
            PRIMARY KEY (lot_id, numero_ligne)
        );
        COMMENT ON TABLE raw.declaration_brute IS 'Lignes reçues telles quelles, conservées sans modification';
    """)

    # Les lignes refusées par les contrôles de qualité, avec la raison.
    op.execute("""
        CREATE TABLE staging.rejet (
            id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            lot_id        bigint NOT NULL,
            numero_ligne  integer NOT NULL,
            regle         text NOT NULL,
            detail        text,
            rejete_le     timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (lot_id, numero_ligne)
                REFERENCES raw.declaration_brute (lot_id, numero_ligne)
        );
        COMMENT ON TABLE staging.rejet IS 'Lignes refusées par les contrôles de qualité, avec la règle violée';
        CREATE INDEX ix_rejet_lot ON staging.rejet (lot_id);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE staging.rejet;")
    op.execute("DROP TABLE raw.declaration_brute;")
    op.execute("DROP TABLE audit.lot_ingestion;")