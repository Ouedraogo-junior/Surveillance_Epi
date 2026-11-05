-- Test fonctionnel : les versions et la vue courante. Tout est annulé à la fin (ROLLBACK).
BEGIN;

INSERT INTO ref.region (code, nom) VALUES ('TEST', 'Region test');
INSERT INTO ref.district (code, nom, region_id)
    SELECT 'TD', 'District test', id FROM ref.region WHERE code = 'TEST';
INSERT INTO ref.formation_sanitaire (code, nom, type, statut, district_id)
    SELECT 'TF', 'CSPS test', 'CSPS', 'public', id FROM ref.district WHERE code = 'TD';
INSERT INTO audit.lot_ingestion (source, nom_fichier, empreinte)
    VALUES ('test', 't.csv', repeat('a', 64));

INSERT INTO dwh.fait_declaration
    (formation_id, maladie_code, semaine_id, version, cas_suspects, cas_confirmes, deces, lot_id)
SELECT f.id, 'PALU', 202601, v.version, v.cs, v.cc, 0, l.id
FROM ref.formation_sanitaire f, audit.lot_ingestion l,
     (VALUES (1, 10, 4), (2, 12, 5)) AS v(version, cs, cc)
WHERE f.code = 'TF' AND l.source = 'test';

\echo '--- Attendu : une seule ligne, version 2, 12 cas suspects'
SELECT version, cas_suspects FROM dwh.v_declaration_courante;

\echo '--- Attendu : erreur "Table en ajout seul"'
UPDATE dwh.fait_declaration SET cas_suspects = 99;

ROLLBACK;