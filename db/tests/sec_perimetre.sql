-- Test fonctionnel de la sécurité par périmètre. Tout est annulé à la fin.
BEGIN;

INSERT INTO ref.region (code, nom) VALUES ('R1', 'Region 1'), ('R2', 'Region 2');
INSERT INTO ref.district (code, nom, region_id)
    SELECT 'D1', 'District 1', id FROM ref.region WHERE code = 'R1';
INSERT INTO ref.district (code, nom, region_id)
    SELECT 'D2', 'District 2', id FROM ref.region WHERE code = 'R2';

INSERT INTO dwh.fait_indicateur_district
    (district_id, maladie_code, semaine_id, cas_suspects, cas_confirmes, deces,
     population, declarations_attendues, declarations_recues, declarations_a_temps)
SELECT id, 'PALU', 202601, 5, 1, 0, 30000, 10, 10, 10
FROM ref.district WHERE code IN ('D1', 'D2');

INSERT INTO sec.perimetre_utilisateur (utilisateur_id, niveau, region_id)
    SELECT 'user-region-1', 'region', id FROM ref.region WHERE code = 'R1';
INSERT INTO sec.perimetre_utilisateur (utilisateur_id, niveau, district_id)
    SELECT 'user-district-2', 'district', id FROM ref.district WHERE code = 'D2';
INSERT INTO sec.perimetre_utilisateur (utilisateur_id, niveau)
    VALUES ('user-national', 'national');

-- On se place maintenant dans la peau du rôle applicatif.
SET LOCAL ROLE app_api;

\echo '--- Sans utilisateur indique : attendu 0 ligne'
SELECT count(*) FROM dwh.fait_indicateur_district;

SET LOCAL app.utilisateur_id = 'user-region-1';
\echo '--- Agent de la region 1 : attendu D1 seulement'
SELECT d.code FROM dwh.fait_indicateur_district i JOIN ref.district d ON d.id = i.district_id ORDER BY 1;

SET LOCAL app.utilisateur_id = 'user-district-2';
\echo '--- Agent du district 2 : attendu D2 seulement'
SELECT d.code FROM dwh.fait_indicateur_district i JOIN ref.district d ON d.id = i.district_id ORDER BY 1;

SET LOCAL app.utilisateur_id = 'user-national';
\echo '--- Niveau national : attendu D1 et D2'
SELECT d.code FROM dwh.fait_indicateur_district i JOIN ref.district d ON d.id = i.district_id ORDER BY 1;

\echo '--- Ecriture interdite : attendu permission denied'
DELETE FROM dwh.fait_indicateur_district;

ROLLBACK;