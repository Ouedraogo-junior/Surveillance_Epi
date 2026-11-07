"""raw : la zone brute est en ajout seul"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # On réutilise le déclencheur de la migration 0006 : modifier ou supprimer une ligne est interdit.
    op.execute("""
        CREATE TRIGGER trg_declaration_brute_ajout_seul
        BEFORE UPDATE OR DELETE ON raw.declaration_brute
        FOR EACH ROW EXECUTE FUNCTION dwh.interdire_modification();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_declaration_brute_ajout_seul ON raw.declaration_brute;")