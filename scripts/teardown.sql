-- ============================================================
-- SNOWSLED v2 - Teardown complet
-- ATTENTION : supprime toutes les ressources Snowsled
-- ============================================================

USE ROLE ACCOUNTADMIN;

-- 1. Supprimer l'application
DROP APPLICATION IF EXISTS SNOWSLED_V2 CASCADE;

-- 2. Supprimer le package
DROP APPLICATION PACKAGE IF EXISTS SNOWSLED_V2_PKG;

-- 3. Supprimer le role de packaging
DROP ROLE IF EXISTS SNOWSLED_PKG_ROLE;

-- 4. Nettoyage des secrets crees par la Platform app (optionnel)
-- DROP SECRET IF EXISTS SNOWSLED_GITHUB_PAT;
-- DROP SECRET IF EXISTS SNOWSLED_DBT_TOKEN;
-- DROP SECRET IF EXISTS SNOWSLED_FIVETRAN_CREDS;
