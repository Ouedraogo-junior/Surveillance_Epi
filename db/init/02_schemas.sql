-- Les six zones logiques de la base (schémas PostgreSQL).
-- Les tables seront créées à l'étape 2 par Alembic, pas ici.

CREATE SCHEMA IF NOT EXISTS ref;      -- référentiels : régions, districts, formations sanitaires, maladies, semaines, seuils
CREATE SCHEMA IF NOT EXISTS raw;      -- données brutes, telles que reçues, jamais modifiées
CREATE SCHEMA IF NOT EXISTS staging;  -- données en cours de contrôle qualité, rejets
CREATE SCHEMA IF NOT EXISTS dwh;      -- entrepôt : faits validés, indicateurs, alertes
CREATE SCHEMA IF NOT EXISTS sec;      -- sécurité : périmètre des utilisateurs (national / région / district)
CREATE SCHEMA IF NOT EXISTS audit;    -- traçabilité : lots d'ingestion, journal des accès