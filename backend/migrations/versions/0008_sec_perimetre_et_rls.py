"""sec : périmètre des utilisateurs, rôle applicatif et sécurité par ligne"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Périmètre de chaque utilisateur : national, une région, ou un district.
    op.execute("""
        CREATE TABLE sec.perimetre_utilisateur (
            utilisateur_id  text PRIMARY KEY,
            niveau          text NOT NULL CHECK (niveau IN ('national', 'region', 'district')),
            region_id       smallint REFERENCES ref.region (id),
            district_id     integer  REFERENCES ref.district (id),
            CHECK (
                (niveau = 'national' AND region_id IS NULL     AND district_id IS NULL) OR
                (niveau = 'region'   AND region_id IS NOT NULL AND district_id IS NULL) OR
                (niveau = 'district' AND district_id IS NOT NULL AND region_id IS NULL)
            )
        );
        COMMENT ON TABLE sec.perimetre_utilisateur IS 'Perimetre de chaque utilisateur : national, region ou district';
    """)

    # Rôle de l'application (lecture seule). Il n'est pas superutilisateur : la sécurité par ligne
    # s'applique donc à lui. Le compte de connexion sera créé à l'étape de l'API.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_api') THEN
                CREATE ROLE app_api NOLOGIN;
            END IF;
        END
        $$;
    """)

    # Liste des districts que l'utilisateur courant a le droit de voir.
    # L'API indique l'utilisateur par : SET LOCAL app.utilisateur_id = '...'
    # Sans utilisateur indiqué, la fonction ne renvoie rien : tout est refusé par défaut.
    op.execute("""
        CREATE FUNCTION sec.districts_autorises() RETURNS SETOF integer
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT d.id
            FROM sec.perimetre_utilisateur p
            JOIN ref.district d
              ON p.niveau = 'national'
              OR (p.niveau = 'region'   AND d.region_id = p.region_id)
              OR (p.niveau = 'district' AND d.id = p.district_id)
            WHERE p.utilisateur_id = current_setting('app.utilisateur_id', true)
        $$;
    """)

    # Droits de lecture du rôle applicatif : référentiels et entrepôt seulement.
    # Il n'a aucun accès à audit, raw, staging, ni à la table des périmètres.
    op.execute("""
        GRANT USAGE ON SCHEMA ref, dwh, sec TO app_api;
        GRANT SELECT ON ALL TABLES IN SCHEMA ref TO app_api;
        GRANT SELECT ON dwh.fait_declaration, dwh.v_declaration_courante,
                        dwh.fait_indicateur_district, dwh.fait_alerte TO app_api;
        GRANT EXECUTE ON FUNCTION sec.districts_autorises() TO app_api;
    """)

    # Sécurité par ligne sur les trois tables de l'entrepôt qui dépendent d'un district.
    op.execute("""
        ALTER TABLE dwh.fait_indicateur_district ENABLE ROW LEVEL SECURITY;
        CREATE POLICY perimetre_lecture ON dwh.fait_indicateur_district
            FOR SELECT TO app_api
            USING (district_id IN (SELECT sec.districts_autorises()));

        ALTER TABLE dwh.fait_alerte ENABLE ROW LEVEL SECURITY;
        CREATE POLICY perimetre_lecture ON dwh.fait_alerte
            FOR SELECT TO app_api
            USING (district_id IN (SELECT sec.districts_autorises()));

        ALTER TABLE dwh.fait_declaration ENABLE ROW LEVEL SECURITY;
        CREATE POLICY perimetre_lecture ON dwh.fait_declaration
            FOR SELECT TO app_api
            USING (formation_id IN (
                SELECT f.id FROM ref.formation_sanitaire f
                WHERE f.district_id IN (SELECT sec.districts_autorises())
            ));
    """)


def downgrade() -> None:
    op.execute("""
        DROP POLICY perimetre_lecture ON dwh.fait_declaration;
        DROP POLICY perimetre_lecture ON dwh.fait_alerte;
        DROP POLICY perimetre_lecture ON dwh.fait_indicateur_district;
        ALTER TABLE dwh.fait_declaration DISABLE ROW LEVEL SECURITY;
        ALTER TABLE dwh.fait_alerte DISABLE ROW LEVEL SECURITY;
        ALTER TABLE dwh.fait_indicateur_district DISABLE ROW LEVEL SECURITY;
        DROP FUNCTION sec.districts_autorises();
        DROP TABLE sec.perimetre_utilisateur;
        DROP OWNED BY app_api;
        DROP ROLE app_api;
    """)