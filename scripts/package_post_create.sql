-- ============================================================
-- Script execute automatiquement par Snowflake CLI apres la
-- creation du package (package.post_deploy).
-- NOTE: La release directive est reservee au workflow Marketplace.
--       A executer manuellement APRES : snow app version create
-- ============================================================

-- La commande ci-dessous est commentee intentionnellement :
-- elle necessite qu une version ait ete creee au prealable.
-- Decommenter uniquement pour publier sur le Marketplace :
--
-- ALTER APPLICATION PACKAGE SNOWSLED_V2_PKG
--     SET DEFAULT RELEASE DIRECTIVE
--     VERSION = v2
--     PATCH   = 0;

SELECT 'Package SNOWSLED_V2_PKG pret.' AS STATUS;
