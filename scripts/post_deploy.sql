-- ============================================================
-- Post-deploy : execute apres l'installation de l'application
-- Initialisations specifiques au compte cible
-- ============================================================

MERGE INTO CONFIG_SCHEMA.ACCOUNT_CONFIG AS t
USING (
    SELECT 'SNOWSLED_VERSION' AS CONFIG_KEY, PARSE_JSON('"2.0.0"')          AS CONFIG_VALUE, 'Version de Snowsled installee'     AS DESCRIPTION UNION ALL
    SELECT 'CLOUD_PROVIDER',                  PARSE_JSON('"AWS"'),                            'Cloud provider du compte Snowflake'              UNION ALL
    SELECT 'CLOUD_REGION',                    PARSE_JSON('"us-east-1"'),                      'Region AWS du compte'                            UNION ALL
    SELECT 'INSTALL_DATE',                    TO_VARIANT(CURRENT_TIMESTAMP()),                'Date d installation'
) AS s ON t.CONFIG_KEY = s.CONFIG_KEY
WHEN NOT MATCHED THEN INSERT (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION)
    VALUES (s.CONFIG_KEY, s.CONFIG_VALUE, s.DESCRIPTION);

-- Initialiser les vues FinOps qui dependent de SNOWFLAKE.ACCOUNT_USAGE
-- (silencieux si IMPORTED PRIVILEGES pas encore accorde)
CALL APP_SCHEMA.INITIALIZE_FINOPS_VIEWS();
