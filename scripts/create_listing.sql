-- ============================================================
-- SNOWSLED v2 - Creation du listing Snowflake Marketplace
-- Prerequis :
--   1. Compte Provider actif (Provider Studio active)
--   2. Package SNOWSLED_V2_PKG cree avec distribution: external
--   3. Version v2 creee + release directive activee
-- Role requis : ACCOUNTADMIN sur le compte Provider
-- ============================================================

USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWSLED_V2_PKG;

-- -------------------------------------------------------
-- Option A : Listing PRIVE (partage cible, ex. client POC)
-- Modifier les valeurs entre < > avant d'executer.
-- -------------------------------------------------------
CREATE LISTING IF NOT EXISTS SNOWSLED_V2_PRIVATE_LISTING
    FOR APPLICATION PACKAGE SNOWSLED_V2_PKG
    AS $$
        title: "Snowsled v2 - Pre-Sales POC Edition"
        subtitle: "Snowflake-native DataOps platform for pre-sales POCs"
        distribution: EXTERNAL
        description: |
            Snowsled v2 est une application native Snowflake permettant de :
            - Configurer un compte Snowflake (warehouses, bases, roles)
            - Connecter GitHub, dbt Cloud et Fivetran en quelques clics
            - Gerer la convention de nommage (DSI, DSO, ...)
            - Creer et mettre a jour des objets de donnees par projet
            - Monitorer les couts et la conformite via FinOps Monitor + Cortex AI
        listing_terms:
            type: "OFFLINE"
        targets:
            accounts:
                - "<ACCOUNT_LOCATOR_CLIENT_1>"   # remplacer par l'identifiant du compte consumer
    $$;

-- Publier la version v2 vers ce listing
ALTER LISTING SNOWSLED_V2_PRIVATE_LISTING
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
