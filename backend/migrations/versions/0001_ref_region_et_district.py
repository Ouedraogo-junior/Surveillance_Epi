"""ref : régions et districts sanitaires"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE ref.region (
            id    smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            code  text NOT NULL UNIQUE,
            nom   text NOT NULL
        );
        COMMENT ON TABLE ref.region IS 'Régions sanitaires';
    """)

    op.execute("""
        CREATE TABLE ref.district (
            id         integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            code       text NOT NULL UNIQUE,
            nom        text NOT NULL,
            region_id  smallint NOT NULL REFERENCES ref.region (id),
            geom       geometry(MultiPolygon, 4326)
        );
        COMMENT ON TABLE ref.district IS 'Districts sanitaires';
        CREATE INDEX ix_district_region ON ref.district (region_id);
        CREATE INDEX ix_district_geom   ON ref.district USING gist (geom);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE ref.district;")
    op.execute("DROP TABLE ref.region;")