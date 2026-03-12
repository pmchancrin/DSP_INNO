-- ============================================================
-- SNOWSLED v2 - Creation du listing Snowflake Marketplace
-- Prerequis (dans l'ordre) :
--   1. Package SNOWSLED_V2_PKG ABSENT ou en distribution INTERNAL
--      Si besoin (package EXTERNAL existant) :
--        DROP APPLICATION IF EXISTS SNOWSLED_V2 CASCADE;
--        DROP APPLICATION PACKAGE IF EXISTS SNOWSLED_V2_PKG;
--   2. snow app run --connection beta
--      (recrée le package avec distribution: internal)
--   3. snow app version create v2 --connection beta
--      (crée la version nécessaire à la release directive)
--   4. Exécuter CE script
-- Role requis : ACCOUNTADMIN sur le compte Provider
-- ============================================================

USE ROLE ACCOUNTADMIN;

-- -------------------------------------------------------
-- Etape 1 : Créer le listing INTERNE
-- (visible uniquement dans votre organisation Snowflake)
-- -------------------------------------------------------
CREATE LISTING IF NOT EXISTS SNOWSLED_V2_PRIVATE_LISTING
    FOR APPLICATION PACKAGE SNOWSLED_V2_PKG
    AS $$
title: "Snowsled v2 - Pre-Sales POC Edition"
subtitle: "Snowflake-native DataOps platform for pre-sales POCs"
description: "Snowsled v2 - Native App Snowflake pour POC avant-vente."
listing_terms:
  type: STANDARD
$$
DISTRIBUTION = INTERNAL;

-- -------------------------------------------------------
-- Etape 2 : Activer la version v2 sur le package
-- (la version doit exister : snow app version create v2)
-- -------------------------------------------------------
ALTER APPLICATION PACKAGE SNOWSLED_V2_PKG
    SET DEFAULT RELEASE DIRECTIVE
    VERSION = v2
    PATCH   = 0;

-- -------------------------------------------------------
-- Option B : Listing PUBLIC (Snowflake Marketplace)
-- Necessite la validation par Snowflake (2-5 jours ouvres)
-- -------------------------------------------------------
-- CREATE LISTING IF NOT EXISTS SNOWSLED_V2_PUBLIC_LISTING
--     FOR APPLICATION PACKAGE SNOWSLED_V2_PKG
--     AS $$
--         title: "Snowsled v2"
--         subtitle: "Native DataOps Platform - POC Edition"
--         description: |
--             Snowsled v2 est une Snowflake Native App permettant aux ingenieurs
--             avant-vente de demarrer un POC Snowflake en moins de 15 minutes :
--             setup du compte, connexion GitHub / dbt Cloud / Fivetran,
--             gestion des objets DSI/DSO et monitoring FinOps.
--         listing_terms:
--             type: "STANDARD"
--         auto_fulfillment:
--             refresh_schedule: "1 DAYS"
--             refresh_type: "FULL_DATABASE"
--         categories:
--             - "DATA_ENGINEERING"
--         business_needs:
--             - "DATA_INTEGRATION"
--     $$;

-- -------------------------------------------------------
-- Verification du statut des listings
-- -------------------------------------------------------
SHOW LISTINGS;

-- Consulter les details d'un listing :
-- DESCRIBE LISTING SNOWSLED_V2_PRIVATE_LISTING;
