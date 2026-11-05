-- Test fonctionnel : indicateurs calculés et alerte traçable. Tout est annulé à la fin.
BEGIN;

INSERT INTO ref.region (code, nom) VALUES ('TEST', 'Region test');
INSERT INTO ref.district (code, nom, region_id)
    SELECT 'TD', 'District test', id FROM ref.region WHERE code = 'TEST';

INSERT INTO dwh.fait_indicateur_district
    (district_id, maladie_code, semaine_id, cas_suspects, cas_confirmes, deces,
     population, declarations_attendues, declarations_recues, declarations_a_temps)
SELECT id, 'MENI', 202601, 12, 3, 1, 40000, 10, 9, 8
FROM ref.district WHERE code = 'TD';

\echo '--- Attendu : taux 30.00, completude 90.0, promptitude 80.0'
SELECT cas_suspects, taux_100000, completude, promptitude FROM dwh.fait_indicateur_district;

INSERT INTO dwh.fait_alerte
    (district_id, maladie_code, semaine_id, niveau, valeur_observee, unite, seuil_applique, regle_id)
SELECT d.id, 'MENI', 202601, 'epidemie', 30.00, 'cas pour 100 000 par semaine', 15, r.id
FROM ref.district d, ref.regle_seuil r
WHERE d.code = 'TD' AND r.maladie_code = 'MENI' AND r.version = 1;

\echo '--- Attendu : epidemie, 30.00, 15, regle version 1'
SELECT a.niveau, a.valeur_observee, a.seuil_applique, r.version AS version_regle
FROM dwh.fait_alerte a JOIN ref.regle_seuil r ON r.id = a.regle_id;

\echo '--- Attendu : erreur de contrainte (plus de declarations recues que attendues)'
UPDATE dwh.fait_indicateur_district SET declarations_recues = 11;

ROLLBACK;