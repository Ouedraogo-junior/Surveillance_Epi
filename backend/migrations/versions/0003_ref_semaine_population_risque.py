"""ref : calendrier épidémiologique, populations, risque méningite"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Calendrier épidémiologique (convention ISO 8601 : semaine du lundi au dimanche) ---
    op.execute("""
        CREATE TABLE ref.semaine (
            id          integer PRIMARY KEY,                 -- année * 100 + numéro (ex. 202645)
            annee       smallint NOT NULL,
            numero      smallint NOT NULL CHECK (numero BETWEEN 1 AND 53),
            date_debut  date NOT NULL,
            date_fin    date NOT NULL,
            UNIQUE (annee, numero),
            CHECK (id = annee * 100 + numero),
            CHECK (date_fin = date_debut + 6),
            CHECK (EXTRACT(isodow FROM date_debut) = 1)      -- une semaine commence un lundi
        );
        COMMENT ON TABLE ref.semaine IS 'Calendrier épidémiologique (ISO 8601). Modifiable sans toucher au code.';

        INSERT INTO ref.semaine (id, annee, numero, date_debut, date_fin)
        SELECT EXTRACT(isoyear FROM d)::int * 100 + EXTRACT(week FROM d)::int,
               EXTRACT(isoyear FROM d)::smallint,
               EXTRACT(week FROM d)::smallint,
               d,
               d + 6
        FROM (
            SELECT g::date AS d
            FROM generate_series(date '2014-12-29', date '2035-12-31', interval '7 days') AS g
        ) AS lundis;
    """)

    # --- Population par district et par année ---
    op.execute("""
        CREATE TABLE ref.population_district (
            district_id  integer NOT NULL REFERENCES ref.district (id),
            annee        smallint NOT NULL,
            population   integer NOT NULL CHECK (population > 0),
            source       text,
            PRIMARY KEY (district_id, annee)
        );
        COMMENT ON TABLE ref.population_district IS 'Population par district et par année (dénominateur des taux pour 100 000)';
    """)

    # --- Risque élevé de méningite par district et par saison ---
    op.execute("""
        CREATE TABLE ref.risque_meningite (
            district_id   integer NOT NULL REFERENCES ref.district (id),
            saison        text NOT NULL CHECK (saison ~ '^[0-9]{4}-[0-9]{4}$'),   -- ex. 2025-2026
            risque_eleve  boolean NOT NULL,
            PRIMARY KEY (district_id, saison)
        );
        COMMENT ON TABLE ref.risque_meningite IS 'District à risque élevé de méningite pour la saison sèche (seuil épidémique abaissé)';
    """)


def downgrade() -> None:
    op.execute("DROP TABLE ref.risque_meningite;")
    op.execute("DROP TABLE ref.population_district;")
    op.execute("DROP TABLE ref.semaine;")