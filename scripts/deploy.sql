-- ============================================================
-- SNOWSLED v2 - Script de deploiement (Snowflake CLI)
-- Prerequis : Snowflake CLI (snow) installe et configure
-- Cloud cible : AWS us-east-1
-- ============================================================

-- -------------------------------------------------------
-- 1 - Roles de packaging (a executer en tant que ORGADMIN / ACCOUNTADMIN)
-- -------------------------------------------------------
USE ROLE ACCOUNTADMIN;

CREATE ROLE IF NOT EXISTS SNOWSLED_PKG_ROLE
    COMMENT = 'Role owner du package Snowsled v2 - Native App';

GRANT CREATE APPLICATION PACKAGE ON ACCOUNT TO ROLE SNOWSLED_PKG_ROLE;
GRANT CREATE APPLICATION         ON ACCOUNT TO ROLE SNOWSLED_PKG_ROLE;
GRANT CREATE DATABASE            ON ACCOUNT TO ROLE SNOWSLED_PKG_ROLE;
GRANT CREATE WAREHOUSE           ON ACCOUNT TO ROLE SNOWSLED_PKG_ROLE;

-- Attribuer le role a l'utilisateur courant
GRANT ROLE SNOWSLED_PKG_ROLE TO USER CURRENT_USER();

-- -------------------------------------------------------
-- 2 - Stage de contenu de l'application
-- -------------------------------------------------------
USE ROLE SNOWSLED_PKG_ROLE;

CREATE APPLICATION PACKAGE IF NOT EXISTS SNOWSLED_V2_PKG
    COMMENT = 'Package Snowsled v2';

CREATE SCHEMA IF NOT EXISTS SNOWSLED_V2_PKG.STAGE_CONTENT;

CREATE STAGE IF NOT EXISTS SNOWSLED_V2_PKG.STAGE_CONTENT.APP_CODE
    DIRECTORY = (ENABLE = TRUE)
    COMMENT   = 'Stage contenant les artefacts de Snowsled v2';

-- -------------------------------------------------------
-- 3 - Upload des fichiers via Snowflake CLI
-- (Ces commandes sont a executer en dehors de Snowflake, via "snow app run")
-- -------------------------------------------------------
-- $ snow app run --app-name SNOWSLED_V2

-- -------------------------------------------------------
-- 4 - Creer la version de l'application
-- -------------------------------------------------------
ALTER APPLICATION PACKAGE SNOWSLED_V2_PKG
    ADD VERSION v2
    USING '@SNOWSLED_V2_PKG.STAGE_CONTENT.APP_CODE';

ALTER APPLICATION PACKAGE SNOWSLED_V2_PKG
    SET DEFAULT RELEASE DIRECTIVE
    VERSION   = v2
    PATCH     = 0;

-- -------------------------------------------------------
-- 5 - Installer l'application localement (DEV / POC)
-- -------------------------------------------------------
CREATE APPLICATION SNOWSLED_V2
    FROM APPLICATION PACKAGE SNOWSLED_V2_PKG
    USING VERSION v2
    COMMENT = 'Snowsled v2 - POC client (AWS)';

-- Accorder les privileges necessaires a l'application
GRANT CREATE DATABASE  ON ACCOUNT  TO APPLICATION SNOWSLED_V2;
GRANT CREATE WAREHOUSE ON ACCOUNT  TO APPLICATION SNOWSLED_V2;
GRANT CREATE ROLE      ON ACCOUNT  TO APPLICATION SNOWSLED_V2;
GRANT EXECUTE TASK     ON ACCOUNT  TO APPLICATION SNOWSLED_V2;

-- -------------------------------------------------------
-- 6 - Ouvrir l'application Streamlit par defaut
-- -------------------------------------------------------
-- Dans l'UI Snowflake : Apps -> SNOWSLED_V2 -> Snowsled Platform
