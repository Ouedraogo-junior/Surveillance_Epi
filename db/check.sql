\echo '--- 1. Version de PostgreSQL'
SELECT version();

\echo '--- 2. Extensions installées (attendu : pgcrypto, postgis)'
SELECT extname, extversion FROM pg_extension WHERE extname IN ('postgis', 'pgcrypto') ORDER BY extname;

\echo '--- 3. Schémas du projet (attendu : 6 lignes)'
SELECT nspname AS schema FROM pg_namespace
WHERE nspname IN ('ref', 'raw', 'staging', 'dwh', 'sec', 'audit')
ORDER BY nspname;

\echo '--- 4. Test PostGIS : distance Ouagadougou - Bobo-Dioulasso en km (attendu : environ 320)'
SELECT round((ST_Distance(
    ST_SetSRID(ST_MakePoint(-1.5197, 12.3714), 4326)::geography,
    ST_SetSRID(ST_MakePoint(-4.2979, 11.1771), 4326)::geography
) / 1000)::numeric) AS distance_km;