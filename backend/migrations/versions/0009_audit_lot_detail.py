"""audit : motif d'échec ou remarque sur un lot"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE audit.lot_ingestion ADD COLUMN detail text;
        COMMENT ON COLUMN audit.lot_ingestion.detail IS 'Motif de l echec ou remarque sur le traitement du lot';
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE audit.lot_ingestion DROP COLUMN detail;")