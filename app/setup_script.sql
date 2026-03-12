-- ============================================================
-- SNOWSLED v2 - Native App Setup Script
-- Cloud: AWS (us-east-1)
-- ============================================================

-- ---------------------------------------------------------
-- 0. APPLICATION ROLE (must be created first)
-- ---------------------------------------------------------
CREATE APPLICATION ROLE IF NOT EXISTS APP_PUBLIC;

-- ---------------------------------------------------------
-- 1. SCHEMAS INTERNES DE L'APPLICATION
-- ---------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS APP_SCHEMA;
CREATE SCHEMA IF NOT EXISTS CONFIG_SCHEMA;
CREATE SCHEMA IF NOT EXISTS AUDIT_SCHEMA;

-- ---------------------------------------------------------
-- 1b. NETWORK RULE & EXTERNAL ACCESS INTEGRATION
-- Crees dynamiquement par APP_SCHEMA.INSTALL_EAI_PROCEDURES()
-- en fin de script. Sur les comptes trial (EAI non supporte),
-- l appel echoue silencieusement et les stubs restent actifs.
-- ---------------------------------------------------------

-- ---------------------------------------------------------
-- 2. TABLES DE CONFIGURATION
-- ---------------------------------------------------------

-- Configuration globale du compte
CREATE TABLE IF NOT EXISTS CONFIG_SCHEMA.ACCOUNT_CONFIG (
    CONFIG_KEY      VARCHAR(100)    NOT NULL,
    CONFIG_VALUE    VARIANT,
    DESCRIPTION     VARCHAR(500),
    UPDATED_AT      TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_BY      VARCHAR(200)    DEFAULT CURRENT_USER(),
    CONSTRAINT PK_ACCOUNT_CONFIG PRIMARY KEY (CONFIG_KEY)
);

-- Configuration de la convention de nommage
CREATE TABLE IF NOT EXISTS CONFIG_SCHEMA.NAMING_CONVENTION (
    LAYER_CODE      VARCHAR(50)     NOT NULL,   -- DSI, DSO, RAW, CURATED, ...
    PREFIX          VARCHAR(50),
    SUFFIX          VARCHAR(50),
    SEPARATOR       VARCHAR(5)      DEFAULT '_',
    DESCRIPTION     VARCHAR(500),
    ENABLED         BOOLEAN         DEFAULT TRUE,
    UPDATED_AT      TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_NAMING PRIMARY KEY (LAYER_CODE)
);

-- Connexions externes
CREATE TABLE IF NOT EXISTS CONFIG_SCHEMA.EXTERNAL_CONNECTIONS (
    CONNECTION_NAME VARCHAR(100)    NOT NULL,   -- GITHUB, DBT_CLOUD, FIVETRAN
    CONNECTION_TYPE VARCHAR(50)     NOT NULL,
    ENDPOINT_URL    VARCHAR(1000),
    ACCOUNT_ID      VARCHAR(200),
    SECRET_REF      VARCHAR(500),
    STATUS          VARCHAR(50)     DEFAULT 'PENDING',  -- PENDING, CONNECTED, ERROR
    LAST_TEST_AT    TIMESTAMP_NTZ,
    LAST_TEST_MSG   VARCHAR(1000),
    CREATED_AT      TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_AT      TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_EXT_CONN PRIMARY KEY (CONNECTION_NAME)
);

-- Projets Snowsled
CREATE TABLE IF NOT EXISTS CONFIG_SCHEMA.PROJECTS (
    PROJECT_ID      VARCHAR(100)    NOT NULL,
    PROJECT_NAME    VARCHAR(200)    NOT NULL,
    DESCRIPTION     VARCHAR(1000),
    DSI_DB          VARCHAR(200),   -- Base de donnees DSI associee
    DSO_DB          VARCHAR(200),   -- Base de donnees DSO associee
    WH_SIZE         VARCHAR(50)     DEFAULT 'SMALL',
    STATUS          VARCHAR(50)     DEFAULT 'ACTIVE',
    CREATED_AT      TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    CREATED_BY      VARCHAR(200)    DEFAULT CURRENT_USER(),
    CONSTRAINT PK_PROJECTS PRIMARY KEY (PROJECT_ID)
);

-- Roles fonctionnels geres
CREATE TABLE IF NOT EXISTS CONFIG_SCHEMA.MANAGED_ROLES (
    ROLE_NAME       VARCHAR(200)    NOT NULL,
    ROLE_TYPE       VARCHAR(50),    -- ADMIN, ANALYST, DEVELOPER, VIEWER
    PROJECT_ID      VARCHAR(100),
    PRIVILEGES      VARIANT,
    CREATED_AT      TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_ROLES PRIMARY KEY (ROLE_NAME)
);

-- Objets crees par Snowsled
CREATE TABLE IF NOT EXISTS CONFIG_SCHEMA.MANAGED_OBJECTS (
    OBJECT_ID       VARCHAR(200)    NOT NULL,
    OBJECT_TYPE     VARCHAR(100),   -- DATABASE, SCHEMA, TABLE, VIEW, TASK, PIPE, ...
    OBJECT_NAME     VARCHAR(500),
    LAYER           VARCHAR(50),    -- DSI, DSO
    PROJECT_ID      VARCHAR(100),
    SNOWSLED_MANAGED BOOLEAN        DEFAULT TRUE,
    METADATA        VARIANT,
    CREATED_AT      TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_AT      TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_OBJECTS PRIMARY KEY (OBJECT_ID)
);

-- Connecteurs Fivetran (cache / enregistrement local)
CREATE TABLE IF NOT EXISTS CONFIG_SCHEMA.FIVETRAN_CONNECTORS (
    CONNECTOR_KEY           VARCHAR(300)    NOT NULL,   -- cle locale : SNOWSLED_ID_NOM
    CONNECTOR_NAME          VARCHAR(300),
    SERVICE                 VARCHAR(100),               -- ex: salesforce, postgres, s3...
    DESTINATION_SCHEMA      VARCHAR(300),
    DSI_DB                  VARCHAR(300),
    GROUP_ID                VARCHAR(300),               -- Group/destination Fivetran
    SYNC_FREQUENCY          NUMBER,                     -- minutes
    PAUSED                  BOOLEAN         DEFAULT FALSE,
    SNOWSLED_PROJECT_ID     VARCHAR(100),
    FIVETRAN_CONNECTOR_ID   VARCHAR(300),               -- ID retourne par l'API Fivetran apres sync
    STATUS                  VARCHAR(50)     DEFAULT 'PENDING', -- PENDING, ACTIVE, ERROR
    CREATED_AT              TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_AT              TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_FIVETRAN_CONNECTORS PRIMARY KEY (CONNECTOR_KEY)
);

-- Projets dbt Cloud (enregistrement local / cache)
CREATE TABLE IF NOT EXISTS CONFIG_SCHEMA.DBT_PROJECTS (
    DBT_PROJECT_KEY     VARCHAR(300)    NOT NULL,   -- cle locale : SNOWSLED_ID_NOM
    PROJECT_NAME        VARCHAR(300),
    REPO_URL            VARCHAR(1000),
    PROJECT_SUBDIR      VARCHAR(500),
    SF_ACCOUNT          VARCHAR(300),
    SF_DATABASE         VARCHAR(300),
    SF_SCHEMA           VARCHAR(300),
    SF_WAREHOUSE        VARCHAR(300),
    SNOWSLED_PROJECT_ID VARCHAR(100),
    DBT_CLOUD_ID        NUMBER,                     -- ID retourne par l'API dbt Cloud apres sync
    STATUS              VARCHAR(50)   DEFAULT 'PENDING', -- PENDING, ACTIVE, ERROR
    CREATED_AT          TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_AT          TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_DBT_PROJECTS PRIMARY KEY (DBT_PROJECT_KEY)
);

-- Journal d'audit
CREATE TABLE IF NOT EXISTS AUDIT_SCHEMA.AUDIT_LOG (
    LOG_ID          NUMBER          AUTOINCREMENT,
    EVENT_TIME      TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    EVENT_TYPE      VARCHAR(100),
    ACTOR           VARCHAR(200)    DEFAULT CURRENT_USER(),
    OBJECT_TYPE     VARCHAR(100),
    OBJECT_NAME     VARCHAR(500),
    STATUS          VARCHAR(50),
    DETAILS         VARIANT,
    CONSTRAINT PK_AUDIT PRIMARY KEY (LOG_ID)
);

-- ---------------------------------------------------------
-- 3. VALEURS PAR DEFAUT DE LA CONVENTION DE NOMMAGE
-- ---------------------------------------------------------

MERGE INTO CONFIG_SCHEMA.NAMING_CONVENTION AS t
USING (
    SELECT 'DSI'    AS LAYER_CODE, 'DSI'  AS PREFIX, NULL AS SUFFIX, '_' AS SEPARATOR, 'Data Source Integration - Couche brute / Raw'         AS DESCRIPTION UNION ALL
    SELECT 'DSO',                  'DSO',             NULL,           '_',              'Data Source Output - Couche curated / Presentee'                     UNION ALL
    SELECT 'WH',                   'WH',              NULL,           '_',              'Warehouse Snowflake'                                                 UNION ALL
    SELECT 'ROLE',                 'ROLE',            NULL,           '_',              'Roles fonctionnels'                                                  UNION ALL
    SELECT 'SCHEMA',               NULL,              NULL,           '_',              'Schemas au sein des bases de donnees'
) AS s ON t.LAYER_CODE = s.LAYER_CODE
WHEN NOT MATCHED THEN INSERT (LAYER_CODE, PREFIX, SUFFIX, SEPARATOR, DESCRIPTION)
    VALUES (s.LAYER_CODE, s.PREFIX, s.SUFFIX, s.SEPARATOR, s.DESCRIPTION);

-- ---------------------------------------------------------
-- 3b. TABLES FINOPS MONITOR (quotas, alertes, logs)
-- ---------------------------------------------------------

-- Configuration des quotas de credits par warehouse
CREATE TABLE IF NOT EXISTS CONFIG_SCHEMA.WAREHOUSE_CONFIG (
    WAREHOUSE_NAME      VARCHAR(200)    NOT NULL,
    FREQUENCY           VARCHAR(50)     DEFAULT 'DAILY',
    CREDIT_LIMIT        NUMBER(18,4)    DEFAULT 100,
    AUTO_SUSPEND_AT_100 BOOLEAN         DEFAULT FALSE,
    ALERT_THRESHOLD_70  BOOLEAN         DEFAULT TRUE,
    ALERT_THRESHOLD_85  BOOLEAN         DEFAULT TRUE,
    ALERT_THRESHOLD_95  BOOLEAN         DEFAULT TRUE,
    ALERT_EMAILS        ARRAY,
    IS_ACTIVE           BOOLEAN         DEFAULT TRUE,
    CREATED_AT          TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    UPDATED_AT          TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_WH_CONFIG PRIMARY KEY (WAREHOUSE_NAME)
);

-- Configuration des quotas de credits par service serverless
CREATE TABLE IF NOT EXISTS CONFIG_SCHEMA.SERVERLESS_CONFIG (
    SERVICE_TYPE        VARCHAR(200)    NOT NULL,
    FREQUENCY           VARCHAR(50)     DEFAULT 'DAILY',
    CREDIT_LIMIT        NUMBER(18,4)    DEFAULT 50,
    ALERT_EMAILS        ARRAY,
    IS_ACTIVE           BOOLEAN         DEFAULT TRUE,
    CREATED_AT          TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_SL_CONFIG PRIMARY KEY (SERVICE_TYPE)
);

-- Journal des alertes FinOps
CREATE TABLE IF NOT EXISTS CONFIG_SCHEMA.MONITORING_ALERT_LOG (
    ALERT_ID        NUMBER          AUTOINCREMENT,
    ALERT_TIME      TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    SCOPE           VARCHAR(100),
    RESOURCE_NAME   VARCHAR(200),
    THRESHOLD_PCT   NUMBER(5,1),
    CREDITS_USED    NUMBER(18,4),
    CREDIT_LIMIT    NUMBER(18,4),
    STATUS          VARCHAR(50),
    MESSAGE         VARCHAR(1000),
    CONSTRAINT PK_ALERT PRIMARY KEY (ALERT_ID)
);

-- Journal des executions du monitoring
CREATE TABLE IF NOT EXISTS CONFIG_SCHEMA.MONITORING_EXEC_LOG (
    EXEC_ID         NUMBER          AUTOINCREMENT,
    EXECUTION_TIME  TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP(),
    SCOPE           VARCHAR(100),
    STATUS          VARCHAR(50),
    DETAILS         VARIANT,
    CONSTRAINT PK_EXEC_LOG PRIMARY KEY (EXEC_ID)
);

-- Vues FinOps Monitor
CREATE OR REPLACE VIEW CONFIG_SCHEMA.V_EXECUTION_HISTORY AS
    SELECT EXEC_ID, EXECUTION_TIME, SCOPE, STATUS, DETAILS
    FROM CONFIG_SCHEMA.MONITORING_EXEC_LOG
    ORDER BY EXECUTION_TIME DESC;

CREATE OR REPLACE VIEW CONFIG_SCHEMA.V_ALERT_HISTORY AS
    SELECT ALERT_ID, ALERT_TIME AS EVENT_TIME, SCOPE, RESOURCE_NAME,
           THRESHOLD_PCT, CREDITS_USED, CREDIT_LIMIT, STATUS, MESSAGE
    FROM CONFIG_SCHEMA.MONITORING_ALERT_LOG
    ORDER BY ALERT_TIME DESC;

CREATE OR REPLACE VIEW CONFIG_SCHEMA.V_SERVERLESS_ALERT_HISTORY AS
    SELECT ALERT_ID, ALERT_TIME AS EVENT_TIME, RESOURCE_NAME AS SERVICE_TYPE,
           THRESHOLD_PCT, CREDITS_USED, CREDIT_LIMIT, STATUS, MESSAGE
    FROM CONFIG_SCHEMA.MONITORING_ALERT_LOG
    WHERE SCOPE = 'SERVERLESS'
    ORDER BY ALERT_TIME DESC;

-- View requires IMPORTED PRIVILEGES ON SNOWFLAKE DB (may not be granted yet at install time)
-- Call APP_SCHEMA.INITIALIZE_FINOPS_VIEWS() after granting the privilege.
BEGIN
    CREATE OR REPLACE VIEW CONFIG_SCHEMA.V_SERVERLESS_TOP_CONSUMERS AS
        SELECT
            service_type,
            ROUND(SUM(credits_used), 2) AS total_credits,
            COUNT(*)                    AS periods_active
        FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
        WHERE start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
          AND service_type != 'WAREHOUSE_METERING'
        GROUP BY service_type
        ORDER BY total_credits DESC;
EXCEPTION
    WHEN OTHER THEN
        NULL; -- SNOWFLAKE DB not yet accessible; view will be created by INITIALIZE_FINOPS_VIEWS()
END;

-- ---------------------------------------------------------
-- 4. STREAMLIT APPLICATIONS
-- ---------------------------------------------------------
CREATE OR REPLACE STREAMLIT APP_SCHEMA.SNOWSLED_PLATFORM
    FROM '/src/snowsled_platform'
    MAIN_FILE = 'snowsled_platform.py';

CREATE OR REPLACE STREAMLIT APP_SCHEMA.SNOWSLED_ADMIN
    FROM '/src/snowsled_admin'
    MAIN_FILE = 'snowsled_admin.py';

CREATE OR REPLACE STREAMLIT APP_SCHEMA.SNOWSLED
    FROM '/src/snowsled'
    MAIN_FILE = 'snowsled.py';

CREATE OR REPLACE STREAMLIT APP_SCHEMA.FINOPS_MONITOR
    FROM '/src/finops_monitor'
    MAIN_FILE = 'streamlit_app.py';

-- ---------------------------------------------------------
-- 5. PROCEDURES STOCKEES
-- ---------------------------------------------------------

-- Procedure de callback pour l'enregistrement des references externes
-- (GitHub PAT, dbt Cloud, Fivetran) declarees dans manifest.yml
CREATE OR REPLACE PROCEDURE APP_SCHEMA.REGISTER_REFERENCE(
    REF_NAME   VARCHAR,
    OPERATION  VARCHAR,
    REF_OR_ALIAS VARCHAR
)
RETURNS STRING
LANGUAGE SQL
AS $$
BEGIN
    CASE (OPERATION)
        WHEN 'ADD' THEN
            SELECT SYSTEM$SET_REFERENCE(:REF_NAME, :REF_OR_ALIAS);
        WHEN 'REMOVE' THEN
            SELECT SYSTEM$REMOVE_REFERENCE(:REF_NAME);
        WHEN 'CLEAR' THEN
            SELECT SYSTEM$REMOVE_REFERENCE(:REF_NAME);
    END CASE;
    RETURN 'SUCCESS';
END;
$$;

GRANT USAGE ON PROCEDURE APP_SCHEMA.REGISTER_REFERENCE(VARCHAR, VARCHAR, VARCHAR)
    TO APPLICATION ROLE APP_PUBLIC;

-- Procedure pour journaliser une action
CREATE OR REPLACE PROCEDURE APP_SCHEMA.LOG_ACTION(
    P_EVENT_TYPE    VARCHAR,
    P_OBJECT_TYPE   VARCHAR,
    P_OBJECT_NAME   VARCHAR,
    P_STATUS        VARCHAR,
    P_DETAILS       VARIANT
)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
BEGIN
    INSERT INTO AUDIT_SCHEMA.AUDIT_LOG
        (EVENT_TYPE, OBJECT_TYPE, OBJECT_NAME, STATUS, DETAILS)
    VALUES
        (:P_EVENT_TYPE, :P_OBJECT_TYPE, :P_OBJECT_NAME, :P_STATUS, :P_DETAILS);
    RETURN 'OK';
END;
$$;

-- TEST_CONNECTION : stub trial-safe (sans EAI)
CREATE OR REPLACE PROCEDURE APP_SCHEMA.TEST_CONNECTION(P_CONNECTION_NAME VARCHAR)
RETURNS VARIANT LANGUAGE PYTHON RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python') HANDLER = 'test_connection'
AS $$
def test_connection(session, p_connection_name):
    return {"status": "ERROR", "message": "Acces externe (EAI) non disponible sur ce compte"}
$$;

-- ---------------------------------------------------------
-- 6. PROCEDURE : DEPLOY_CORTEX_AGENT
-- Deploie le Cortex AI Monitor (SNOWFLAKE_INTELLIGENCE)
-- 3 vues semantiques + 3 agents Cortex AI
-- Source : github.com/augustorosa/cortex-snowflake-account-security-agent
-- ---------------------------------------------------------
CREATE OR REPLACE PROCEDURE APP_SCHEMA.DEPLOY_CORTEX_AGENT()
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'deploy_cortex_agent'
EXECUTE AS OWNER
AS
$$
import json

def deploy_cortex_agent(session):
    steps  = []
    errors = []

    def run(sql, label):
        try:
            session.sql(sql).collect()
            steps.append(label)
            return True
        except Exception as e:
            errors.append(f"{label}: {str(e)[:300]}")
            return False

    # Prerequis : la DB SNOWFLAKE_INTELLIGENCE doit exister (via Script 1 ACCOUNTADMIN)
    prereq = session.sql("SHOW DATABASES LIKE 'SNOWFLAKE_INTELLIGENCE'").collect()
    if not prereq:
        return {
            "success": False,
            "steps": steps,
            "errors": [
                "Database SNOWFLAKE_INTELLIGENCE introuvable. "
                "Executez d abord le Script 1 (Foundations) en tant qu ACCOUNTADMIN."
            ]
        }

    # 1. Activer Cortex cross-region
    run("ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION'", "Cortex cross-region enabled")

    # ----------------------------------------------------------------
    # 2. Vue semantique COST_PERFORMANCE_SVW
    #    2 tables : QUERY_HISTORY + QUERY_ATTRIBUTION_HISTORY
    #    Specialiste performance & couts
    # ----------------------------------------------------------------
    run(
        """
CREATE OR REPLACE SEMANTIC VIEW SNOWFLAKE_INTELLIGENCE.TOOLS.COST_PERFORMANCE_SVW
TABLES (
    SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY,
    SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY
)
FACTS (
    QUERY_HISTORY.TOTAL_ELAPSED_TIME     AS TOTAL_ELAPSED_TIME     COMMENT='Total query execution time in ms',
    QUERY_HISTORY.EXECUTION_TIME         AS EXECUTION_TIME          COMMENT='Query execution time in ms',
    QUERY_HISTORY.COMPILATION_TIME       AS COMPILATION_TIME        COMMENT='Query compilation time in ms',
    QUERY_HISTORY.QUEUED_PROVISIONING_TIME AS QUEUED_PROVISIONING_TIME COMMENT='Time queued for provisioning',
    QUERY_HISTORY.QUEUED_OVERLOAD_TIME   AS QUEUED_OVERLOAD_TIME    COMMENT='Time queued due to overload',
    QUERY_HISTORY.BYTES_SCANNED          AS BYTES_SCANNED           COMMENT='Total bytes scanned',
    QUERY_HISTORY.BYTES_WRITTEN          AS BYTES_WRITTEN           COMMENT='Total bytes written',
    QUERY_HISTORY.BYTES_SPILLED_TO_LOCAL_STORAGE  AS BYTES_SPILLED_TO_LOCAL_STORAGE  COMMENT='Bytes spilled to local',
    QUERY_HISTORY.BYTES_SPILLED_TO_REMOTE_STORAGE AS BYTES_SPILLED_TO_REMOTE_STORAGE COMMENT='Bytes spilled to remote',
    QUERY_HISTORY.ROWS_PRODUCED          AS ROWS_PRODUCED           COMMENT='Total rows produced',
    QUERY_HISTORY.ROWS_INSERTED          AS ROWS_INSERTED           COMMENT='Total rows inserted',
    QUERY_HISTORY.ROWS_UPDATED           AS ROWS_UPDATED            COMMENT='Total rows updated',
    QUERY_HISTORY.ROWS_DELETED           AS ROWS_DELETED            COMMENT='Total rows deleted',
    QUERY_HISTORY.PARTITIONS_SCANNED     AS PARTITIONS_SCANNED      COMMENT='Partitions scanned',
    QUERY_HISTORY.PARTITIONS_TOTAL       AS PARTITIONS_TOTAL        COMMENT='Total partitions',
    QUERY_HISTORY.PERCENTAGE_SCANNED_FROM_CACHE AS PERCENTAGE_SCANNED_FROM_CACHE COMMENT='Cache hit %',
    QUERY_HISTORY.CREDITS_USED_CLOUD_SERVICES   AS CREDITS_USED_CLOUD_SERVICES   COMMENT='Cloud services credits',
    QUERY_ATTRIBUTION_HISTORY.CREDITS_ATTRIBUTED_COMPUTE     AS CREDITS_ATTRIBUTED_COMPUTE     COMMENT='Compute credits',
    QUERY_ATTRIBUTION_HISTORY.CREDITS_USED_QUERY_ACCELERATION AS CREDITS_USED_QUERY_ACCELERATION COMMENT='QA credits'
)
DIMENSIONS (
    QUERY_HISTORY.QUERY_ID         AS QUERY_ID         COMMENT='Unique query identifier',
    QUERY_HISTORY.QUERY_TEXT       AS QUERY_TEXT       COMMENT='SQL text of the query',
    QUERY_HISTORY.QUERY_TYPE       AS QUERY_TYPE       COMMENT='Type of query (SELECT, INSERT...)',
    QUERY_HISTORY.USER_NAME        AS USER_NAME        COMMENT='User who executed the query',
    QUERY_HISTORY.ROLE_NAME        AS ROLE_NAME        COMMENT='Role used for execution',
    QUERY_HISTORY.WAREHOUSE_NAME   AS WAREHOUSE_NAME   COMMENT='Warehouse name',
    QUERY_HISTORY.WAREHOUSE_SIZE   AS WAREHOUSE_SIZE   COMMENT='Warehouse size',
    QUERY_HISTORY.DATABASE_NAME    AS DATABASE_NAME    COMMENT='Database name',
    QUERY_HISTORY.SCHEMA_NAME      AS SCHEMA_NAME      COMMENT='Schema name',
    QUERY_HISTORY.EXECUTION_STATUS AS EXECUTION_STATUS COMMENT='SUCCESS or FAIL',
    QUERY_HISTORY.ERROR_CODE       AS ERROR_CODE       COMMENT='Error code if failed',
    QUERY_HISTORY.ERROR_MESSAGE    AS ERROR_MESSAGE    COMMENT='Error message if failed',
    QUERY_HISTORY.START_TIME       AS START_TIME       COMMENT='Query start time',
    QUERY_HISTORY.END_TIME         AS END_TIME         COMMENT='Query end time',
    QUERY_HISTORY.QUERY_TAG        AS QUERY_TAG        COMMENT='User-defined query tag'
)
COMMENT='Cost and performance semantic view: QUERY_HISTORY + QUERY_ATTRIBUTION_HISTORY.'
""".strip(),
        "Semantic view COST_PERFORMANCE_SVW created"
    )

    # ----------------------------------------------------------------
    # 3. Vue semantique SECURITY_MONITORING_SVW
    #    6 tables : LOGIN_HISTORY, SESSIONS, USERS,
    #               PASSWORD_POLICIES, SESSION_POLICIES, NETWORK_POLICIES
    #    Specialiste securite & conformite
    # ----------------------------------------------------------------
    run(
        """
CREATE OR REPLACE SEMANTIC VIEW SNOWFLAKE_INTELLIGENCE.TOOLS.SECURITY_MONITORING_SVW
TABLES (
    login         AS SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY,
    sessions      AS SNOWFLAKE.ACCOUNT_USAGE.SESSIONS,
    users         AS SNOWFLAKE.ACCOUNT_USAGE.USERS,
    pwd_policies  AS SNOWFLAKE.ACCOUNT_USAGE.PASSWORD_POLICIES,
    sess_policies AS SNOWFLAKE.ACCOUNT_USAGE.SESSION_POLICIES,
    net_policies  AS SNOWFLAKE.ACCOUNT_USAGE.NETWORK_POLICIES
)
DIMENSIONS (
    login.EVENT_TIMESTAMP             AS event_timestamp             COMMENT='When the login attempt occurred',
    login.USER_NAME                   AS user_name                   COMMENT='User attempting login',
    login.CLIENT_IP                   AS client_ip                   COMMENT='IP address',
    login.REPORTED_CLIENT_TYPE        AS reported_client_type        COMMENT='Client software type',
    login.REPORTED_CLIENT_VERSION     AS reported_client_version     COMMENT='Client software version',
    login.FIRST_AUTHENTICATION_FACTOR AS first_authentication_factor COMMENT='First auth method',
    login.SECOND_AUTHENTICATION_FACTOR AS second_authentication_factor COMMENT='Second factor (MFA)',
    login.IS_SUCCESS                  AS is_success                  COMMENT='YES or NO',
    login.ERROR_CODE                  AS error_code                  COMMENT='Error code if failed',
    login.ERROR_MESSAGE               AS error_message               COMMENT='Error message if failed',
    login.CONNECTION                  AS connection                  COMMENT='Connection name',
    sessions.SESSION_ID               AS session_id                  COMMENT='Unique session ID',
    sessions.CREATED_ON               AS created_on                  COMMENT='Session creation timestamp',
    sessions.AUTHENTICATION_METHOD    AS authentication_method       COMMENT='Auth method used',
    sessions.CLIENT_APPLICATION_ID    AS client_application_id       COMMENT='Client application ID',
    sessions.CLOSED_REASON            AS closed_reason               COMMENT='NULL = still active'
)
METRICS (
    login.total_login_attempts        AS COUNT(*) COMMENT='Total login attempts',
    login.failed_login_attempts       AS COUNT(CASE WHEN login.IS_SUCCESS = 'NO'  THEN 1 END) COMMENT='Failed logins',
    login.successful_login_attempts   AS COUNT(CASE WHEN login.IS_SUCCESS = 'YES' THEN 1 END) COMMENT='Successful logins',
    login.unique_login_users          AS COUNT(DISTINCT login.USER_NAME)  COMMENT='Distinct users trying to login',
    login.unique_login_ips            AS COUNT(DISTINCT login.CLIENT_IP)   COMMENT='Distinct IP addresses',
    login.mfa_login_usage             AS COUNT(CASE WHEN login.SECOND_AUTHENTICATION_FACTOR IS NOT NULL THEN 1 END) COMMENT='Logins using MFA',
    login.users_with_login_failures   AS COUNT(DISTINCT CASE WHEN login.IS_SUCCESS = 'NO'  THEN login.USER_NAME END) COMMENT='Users with failures',
    login.ips_with_login_failures     AS COUNT(DISTINCT CASE WHEN login.IS_SUCCESS = 'NO'  THEN login.CLIENT_IP  END) COMMENT='IPs with failures',
    login.login_success_rate_pct      AS (CAST(COUNT(CASE WHEN login.IS_SUCCESS = 'YES' THEN 1 END) AS FLOAT) * 100.0 / NULLIF(COUNT(*), 0)) COMMENT='Login success rate %',
    login.mfa_adoption_pct            AS (CAST(COUNT(CASE WHEN login.SECOND_AUTHENTICATION_FACTOR IS NOT NULL THEN 1 END) AS FLOAT) * 100.0 / NULLIF(COUNT(CASE WHEN login.IS_SUCCESS = 'YES' THEN 1 END), 0)) COMMENT='% successful logins using MFA',
    sessions.total_sessions           AS COUNT(*) COMMENT='Total sessions',
    sessions.active_sessions          AS COUNT(CASE WHEN sessions.CLOSED_REASON IS NULL     THEN 1 END) COMMENT='Active sessions',
    sessions.closed_sessions          AS COUNT(CASE WHEN sessions.CLOSED_REASON IS NOT NULL THEN 1 END) COMMENT='Closed sessions',
    sessions.unique_session_users     AS COUNT(DISTINCT sessions.USER_NAME) COMMENT='Distinct users with sessions',
    sessions.unique_session_apps      AS COUNT(DISTINCT sessions.CLIENT_APPLICATION_ID) COMMENT='Distinct client applications',
    users.total_users                 AS COUNT(*) COMMENT='Total users',
    users.active_users                AS COUNT_IF(users.DISABLED IS NULL OR users.DISABLED = FALSE) COMMENT='Active users',
    users.mfa_enabled_users           AS COUNT_IF(users.HAS_MFA = TRUE) COMMENT='Users with MFA',
    users.mfa_disabled_users          AS COUNT_IF(users.HAS_MFA = FALSE OR users.HAS_MFA IS NULL) COMMENT='Users without MFA',
    users.user_mfa_adoption_rate      AS (CAST(COUNT_IF(users.HAS_MFA = TRUE) AS FLOAT) * 100.0 / NULLIF(COUNT(*), 0)) COMMENT='% of users with MFA',
    pwd_policies.total_password_policies   AS COUNT(*) COMMENT='Total password policies',
    pwd_policies.active_password_policies  AS COUNT_IF(pwd_policies.DELETED IS NULL) COMMENT='Active password policies',
    pwd_policies.avg_min_password_length   AS AVG(pwd_policies.PASSWORD_MIN_LENGTH) COMMENT='Avg min password length',
    pwd_policies.strong_password_policies  AS COUNT_IF(pwd_policies.PASSWORD_MIN_LENGTH >= 12 AND pwd_policies.PASSWORD_MIN_UPPER_CASE_CHARS >= 1 AND pwd_policies.PASSWORD_MIN_LOWER_CASE_CHARS >= 1 AND pwd_policies.PASSWORD_MIN_NUMERIC_CHARS >= 1 AND pwd_policies.PASSWORD_MIN_SPECIAL_CHARS >= 1) COMMENT='Strong policies (12+ chars, mixed)',
    sess_policies.total_session_policies   AS COUNT(*) COMMENT='Total session policies',
    sess_policies.active_session_policies  AS COUNT_IF(sess_policies.DELETED IS NULL) COMMENT='Active session policies',
    sess_policies.avg_idle_timeout_mins    AS AVG(sess_policies.SESSION_IDLE_TIMEOUT_MINS) COMMENT='Avg idle timeout min',
    net_policies.total_network_policies    AS COUNT(*) COMMENT='Total network policies',
    net_policies.active_network_policies   AS COUNT_IF(net_policies.DELETED IS NULL) COMMENT='Active network policies',
    net_policies.policies_with_allowed_ips AS COUNT_IF(net_policies.ALLOWED_IP_LIST IS NOT NULL) COMMENT='Policies with IP whitelist',
    net_policies.policies_with_blocked_ips AS COUNT_IF(net_policies.BLOCKED_IP_LIST  IS NOT NULL) COMMENT='Policies with IP blacklist'
)
COMMENT='Security monitoring: logins, sessions, users, password/session/network policies (6 ACCOUNT_USAGE tables).'
""".strip(),
        "Semantic view SECURITY_MONITORING_SVW created"
    )

    # ----------------------------------------------------------------
    # 4. Vue semantique SNOWFLAKE_MAINTENANCE_SVW (Generalist)
    #    24 tables ACCOUNT_USAGE — perf, securite, couts, gouvernance,
    #    operations, clustering, MVs, replication, data transfer, metering
    # ----------------------------------------------------------------
    run(
        """
CREATE OR REPLACE SEMANTIC VIEW SNOWFLAKE_INTELLIGENCE.TOOLS.SNOWFLAKE_MAINTENANCE_SVW
TABLES (
    qh            AS SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY,
    qa            AS SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY,
    login         AS SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY,
    sessions      AS SNOWFLAKE.ACCOUNT_USAGE.SESSIONS,
    wh            AS SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY,
    storage       AS SNOWFLAKE.ACCOUNT_USAGE.STORAGE_USAGE,
    db_storage    AS SNOWFLAKE.ACCOUNT_USAGE.DATABASE_STORAGE_USAGE_HISTORY,
    stage_storage AS SNOWFLAKE.ACCOUNT_USAGE.STAGE_STORAGE_USAGE_HISTORY,
    users         AS SNOWFLAKE.ACCOUNT_USAGE.USERS,
    roles         AS SNOWFLAKE.ACCOUNT_USAGE.ROLES,
    grants_users  AS SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS,
    grants_roles  AS SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES,
    pwd_policies  AS SNOWFLAKE.ACCOUNT_USAGE.PASSWORD_POLICIES,
    sess_policies AS SNOWFLAKE.ACCOUNT_USAGE.SESSION_POLICIES,
    net_policies  AS SNOWFLAKE.ACCOUNT_USAGE.NETWORK_POLICIES,
    task_hist     AS SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY,
    serverless_task AS SNOWFLAKE.ACCOUNT_USAGE.SERVERLESS_TASK_HISTORY,
    pipe_usage    AS SNOWFLAKE.ACCOUNT_USAGE.PIPE_USAGE_HISTORY,
    clustering    AS SNOWFLAKE.ACCOUNT_USAGE.AUTOMATIC_CLUSTERING_HISTORY,
    mv_refresh    AS SNOWFLAKE.ACCOUNT_USAGE.MATERIALIZED_VIEW_REFRESH_HISTORY,
    replication   AS SNOWFLAKE.ACCOUNT_USAGE.REPLICATION_USAGE_HISTORY,
    data_transfer AS SNOWFLAKE.ACCOUNT_USAGE.DATA_TRANSFER_HISTORY,
    wh_load       AS SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_LOAD_HISTORY,
    metering_daily AS SNOWFLAKE.ACCOUNT_USAGE.METERING_DAILY_HISTORY
)
RELATIONSHIPS (
    qh    (USER_NAME) REFERENCES users (NAME),
    login (USER_NAME) REFERENCES users (NAME)
)
DIMENSIONS (
    qh.QUERY_ID                        AS query_id,
    qh.QUERY_TEXT                      AS query_text,
    qh.DATABASE_NAME                   AS database_name,
    qh.SCHEMA_NAME                     AS schema_name,
    qh.QUERY_TYPE                      AS query_type,
    qh.USER_NAME                       AS user_name,
    qh.ROLE_NAME                       AS role_name,
    qh.WAREHOUSE_NAME                  AS warehouse_name,
    qh.WAREHOUSE_SIZE                  AS warehouse_size,
    qh.WAREHOUSE_TYPE                  AS warehouse_type,
    qh.QUERY_TAG                       AS query_tag,
    qh.EXECUTION_STATUS                AS execution_status,
    qh.ERROR_CODE                      AS error_code,
    qh.ERROR_MESSAGE                   AS error_message,
    login.CLIENT_IP                    AS client_ip,
    login.REPORTED_CLIENT_TYPE         AS reported_client_type,
    login.IS_SUCCESS                   AS is_success,
    login.FIRST_AUTHENTICATION_FACTOR  AS first_authentication_factor,
    login.SECOND_AUTHENTICATION_FACTOR AS second_authentication_factor,
    sessions.SESSION_ID                AS session_id,
    sessions.AUTHENTICATION_METHOD     AS authentication_method,
    sessions.CLOSED_REASON             AS closed_reason,
    storage.USAGE_DATE                 AS usage_date
)
TIME_DIMENSIONS (
    qh.START_TIME,
    login.EVENT_TIMESTAMP,
    wh.START_TIME,
    storage.USAGE_DATE,
    task_hist.SCHEDULED_TIME
)
METRICS (
    -- Perf requetes
    qh.total_queries              AS COUNT(qh.QUERY_ID),
    qh.failed_queries             AS COUNT_IF(qh.EXECUTION_STATUS = 'FAIL'),
    qh.successful_queries         AS COUNT_IF(qh.EXECUTION_STATUS = 'SUCCESS'),
    qh.avg_query_ms               AS AVG(qh.EXECUTION_TIME),
    qh.avg_elapsed_ms             AS AVG(qh.TOTAL_ELAPSED_TIME),
    qh.bytes_scanned              AS SUM(qh.BYTES_SCANNED),
    qh.bytes_spilled_to_local     AS SUM(qh.BYTES_SPILLED_TO_LOCAL_STORAGE),
    qh.bytes_spilled_to_remote    AS SUM(qh.BYTES_SPILLED_TO_REMOTE_STORAGE),
    qh.cache_hit_rate             AS AVG(qh.PERCENTAGE_SCANNED_FROM_CACHE),
    qh.credits_cloud_services     AS SUM(qh.CREDITS_USED_CLOUD_SERVICES),
    qa.credits_compute            AS SUM(qa.CREDITS_ATTRIBUTED_COMPUTE),
    qa.credits_acceleration       AS SUM(qa.CREDITS_USED_QUERY_ACCELERATION),
    -- Securite logins
    login.total_logins            AS COUNT(login.EVENT_ID),
    login.failed_logins           AS COUNT_IF(login.IS_SUCCESS = 'NO'),
    login.unique_login_ips        AS COUNT(DISTINCT login.CLIENT_IP),
    login.mfa_login_usage         AS COUNT(CASE WHEN login.SECOND_AUTHENTICATION_FACTOR IS NOT NULL THEN 1 END),
    login.login_success_rate_pct  AS (CAST(COUNT(CASE WHEN login.IS_SUCCESS = 'YES' THEN 1 END) AS FLOAT) * 100.0 / NULLIF(COUNT(login.EVENT_ID), 0)),
    login.mfa_adoption_pct        AS (CAST(COUNT(CASE WHEN login.SECOND_AUTHENTICATION_FACTOR IS NOT NULL THEN 1 END) AS FLOAT) * 100.0 / NULLIF(COUNT(CASE WHEN login.IS_SUCCESS = 'YES' THEN 1 END), 0)),
    -- Sessions
    sessions.total_sessions       AS COUNT(sessions.SESSION_ID),
    sessions.active_sessions      AS COUNT(CASE WHEN sessions.CLOSED_REASON IS NULL     THEN 1 END),
    -- Couts warehouses
    wh.total_credits_used         AS SUM(wh.CREDITS_USED),
    wh.total_credits_compute      AS SUM(wh.CREDITS_USED_COMPUTE),
    wh.avg_credits_per_hour       AS AVG(wh.CREDITS_USED),
    -- Stockage
    storage.total_storage_bytes   AS SUM(storage.STORAGE_BYTES),
    storage.total_stage_bytes     AS SUM(storage.STAGE_BYTES),
    storage.total_failsafe_bytes  AS SUM(storage.FAILSAFE_BYTES),
    db_storage.avg_database_bytes AS AVG(db_storage.AVERAGE_DATABASE_BYTES),
    stage_storage.total_stage_storage AS SUM(stage_storage.AVERAGE_STAGE_BYTES),
    -- Gouvernance utilisateurs
    users.total_users             AS COUNT(users.NAME),
    users.active_users            AS COUNT_IF(users.DISABLED IS NULL OR users.DISABLED = FALSE),
    users.mfa_enabled_users       AS COUNT_IF(users.HAS_MFA = TRUE),
    users.users_without_mfa       AS COUNT_IF(users.HAS_MFA = FALSE),
    users.mfa_adoption_rate       AS (CAST(COUNT_IF(users.HAS_MFA = TRUE) AS FLOAT) * 100.0 / NULLIF(COUNT(users.NAME), 0)),
    roles.total_roles             AS COUNT(roles.NAME),
    grants_users.total_role_grants_to_users AS COUNT(grants_users.ROLE),
    grants_roles.total_privilege_grants     AS COUNT(grants_roles.PRIVILEGE),
    -- Securite politiques
    pwd_policies.strong_password_policies  AS COUNT_IF(pwd_policies.PASSWORD_MIN_LENGTH >= 12 AND pwd_policies.PASSWORD_MIN_UPPER_CASE_CHARS >= 1 AND pwd_policies.PASSWORD_MIN_LOWER_CASE_CHARS >= 1 AND pwd_policies.PASSWORD_MIN_NUMERIC_CHARS >= 1 AND pwd_policies.PASSWORD_MIN_SPECIAL_CHARS >= 1),
    net_policies.active_network_policies   AS COUNT_IF(net_policies.DELETED IS NULL),
    -- Taches
    task_hist.total_task_runs     AS COUNT(task_hist.RUN_ID),
    task_hist.successful_tasks    AS COUNT_IF(task_hist.STATE = 'SUCCEEDED'),
    task_hist.failed_tasks        AS COUNT_IF(task_hist.STATE = 'FAILED'),
    task_hist.task_success_rate   AS (CAST(COUNT_IF(task_hist.STATE = 'SUCCEEDED') AS FLOAT) * 100.0 / NULLIF(COUNT(task_hist.RUN_ID), 0)),
    serverless_task.total_serverless_credits AS SUM(serverless_task.CREDITS_USED),
    -- Operations avancees
    pipe_usage.total_pipe_credits       AS SUM(pipe_usage.CREDITS_USED),
    pipe_usage.total_files_inserted     AS SUM(pipe_usage.FILES_INSERTED),
    pipe_usage.total_bytes_inserted     AS SUM(pipe_usage.BYTES_INSERTED),
    clustering.total_clustering_credits AS SUM(clustering.CREDITS_USED),
    clustering.total_bytes_reclustered  AS SUM(clustering.NUM_BYTES_RECLUSTERED),
    mv_refresh.total_mv_credits         AS SUM(mv_refresh.CREDITS_USED),
    mv_refresh.total_mv_refreshes       AS COUNT(mv_refresh.CREDITS_USED),
    replication.total_replication_credits AS SUM(replication.CREDITS_USED),
    replication.total_bytes_replicated  AS SUM(replication.BYTES_TRANSFERRED),
    data_transfer.total_transfer_bytes  AS SUM(data_transfer.BYTES_TRANSFERRED),
    wh_load.avg_running_queries         AS AVG(wh_load.AVG_RUNNING),
    wh_load.avg_queued_load             AS AVG(wh_load.AVG_QUEUED_LOAD),
    metering_daily.total_daily_credits  AS SUM(metering_daily.CREDITS_USED),
    metering_daily.total_compute_credits_daily AS SUM(metering_daily.CREDITS_USED_COMPUTE)
)
COMMENT='Generalist: 24 ACCOUNT_USAGE tables — perf, securite, couts, gouvernance, taches, Snowpipe, clustering, MVs, replication, data transfer, metering.'
""".strip(),
        "Semantic view SNOWFLAKE_MAINTENANCE_SVW created (generalist 24 tables)"
    )

    # 5. Grants vues semantiques
    run(
        "GRANT SELECT ON ALL SEMANTIC VIEWS IN SCHEMA SNOWFLAKE_INTELLIGENCE.TOOLS TO ROLE PUBLIC",
        "Semantic views access granted to PUBLIC"
    )

    # ----------------------------------------------------------------
    # 6. Agent COST_PERFORMANCE_AGENT
    # ----------------------------------------------------------------
    run(
        """
CREATE OR REPLACE AGENT SNOWFLAKE_INTELLIGENCE.AGENTS.COST_PERFORMANCE_AGENT
  COMMENT = 'Specialiste couts et performances : analyse requetes, credits warehouses, spilling, cache, attribution.'
  SEMANTIC_MODELS (
    SEMANTIC_VIEW = SNOWFLAKE_INTELLIGENCE.TOOLS.COST_PERFORMANCE_SVW
  )
  SAMPLE_QUESTIONS (
    'What were the most expensive queries in the last hour?',
    'Which queries are spilling to disk?',
    'Show me failed queries with error details',
    'Which users are running the slowest queries?',
    'Which warehouses are consuming the most credits?',
    'Show queries with low cache hit rates'
  )
""".strip(),
        "Cortex agent COST_PERFORMANCE_AGENT created"
    )

    # ----------------------------------------------------------------
    # 7. Agent SECURITY_MONITORING_AGENT
    # ----------------------------------------------------------------
    run(
        """
CREATE OR REPLACE AGENT SNOWFLAKE_INTELLIGENCE.AGENTS.SECURITY_MONITORING_AGENT
  COMMENT = 'Specialiste securite : logins, MFA, sessions actives, politiques mot de passe/session/reseau, detection de menaces.'
  SEMANTIC_MODELS (
    SEMANTIC_VIEW = SNOWFLAKE_INTELLIGENCE.TOOLS.SECURITY_MONITORING_SVW
  )
  SAMPLE_QUESTIONS (
    'Show me failed login attempts in the last 7 days',
    'Are there suspicious login attempts or brute force attacks?',
    'How many active sessions do we have right now?',
    'What is our MFA adoption rate for users?',
    'Show me users without MFA enabled',
    'How strong are our password policies?',
    'Do we have network policies configured?',
    'Give me an overall security posture summary'
  )
""".strip(),
        "Cortex agent SECURITY_MONITORING_AGENT created"
    )

    # ----------------------------------------------------------------
    # 8. Agent SNOWFLAKE_MAINTENANCE_AGENT (Generalist)
    # ----------------------------------------------------------------
    run(
        """
CREATE OR REPLACE AGENT SNOWFLAKE_INTELLIGENCE.AGENTS.SNOWFLAKE_MAINTENANCE_AGENT
  COMMENT = 'Generalist multi-domaines : perf, securite, couts, gouvernance, taches, operations avancees. Ideal pour les analyses croisees.'
  SEMANTIC_MODELS (
    SEMANTIC_VIEW = SNOWFLAKE_INTELLIGENCE.TOOLS.SNOWFLAKE_MAINTENANCE_SVW
  )
  SAMPLE_QUESTIONS (
    'What is my overall Snowflake account health?',
    'Show me total costs across all services this month',
    'Which users have both failed logins and expensive queries?',
    'What is my MFA adoption rate?',
    'How much data has Snowpipe loaded this month?',
    'What are my automatic clustering costs?',
    'What is my daily billable credit consumption trend?',
    'Which warehouses are most expensive and have the most failed queries?'
  )
""".strip(),
        "Cortex agent SNOWFLAKE_MAINTENANCE_AGENT created"
    )

    # 9. Grants agents
    run(
        "GRANT USAGE ON ALL AGENTS IN SCHEMA SNOWFLAKE_INTELLIGENCE.AGENTS TO ROLE PUBLIC",
        "Agents access granted to PUBLIC"
    )

    return {
        "success": len(errors) == 0,
        "steps":   steps,
        "errors":  errors,
    }
$$;

-- ---------------------------------------------------------
-- Stubs trial-safe pour les procedures EAI (proc 7 a 11)
-- Remplacees par les versions completes si EAI disponible
-- ---------------------------------------------------------
CREATE OR REPLACE PROCEDURE APP_SCHEMA.TRIGGER_DBT_JOB(P_JOB_ID VARCHAR, P_CAUSE VARCHAR)
RETURNS VARIANT LANGUAGE PYTHON RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python') HANDLER = 'handler'
AS $$
def handler(session, p_job_id, p_cause):
    return {"status": "ERROR", "message": "Acces externe (EAI) non disponible sur ce compte"}
$$;

CREATE OR REPLACE PROCEDURE APP_SCHEMA.LIST_FIVETRAN_CONNECTORS(P_GROUP_ID VARCHAR)
RETURNS VARIANT LANGUAGE PYTHON RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python') HANDLER = 'handler'
AS $$
def handler(session, p_group_id):
    return {"error": "Acces externe (EAI) non disponible sur ce compte"}
$$;

CREATE OR REPLACE PROCEDURE APP_SCHEMA.CREATE_FIVETRAN_CONNECTOR(P_PAYLOAD VARCHAR)
RETURNS VARIANT LANGUAGE PYTHON RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python') HANDLER = 'handler'
AS $$
def handler(session, p_payload):
    return {"error": "Acces externe (EAI) non disponible sur ce compte"}
$$;

CREATE OR REPLACE PROCEDURE APP_SCHEMA.TRIGGER_FIVETRAN_SYNC(P_CONNECTOR_ID VARCHAR, P_FORCE_FULL_SYNC VARCHAR)
RETURNS VARIANT LANGUAGE PYTHON RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python') HANDLER = 'handler'
AS $$
def handler(session, p_connector_id, p_force_full_sync):
    return {"code": "ERROR", "message": "Acces externe (EAI) non disponible sur ce compte"}
$$;

CREATE OR REPLACE PROCEDURE APP_SCHEMA.CREATE_DBT_PROJECT(P_PAYLOAD VARCHAR)
RETURNS VARIANT LANGUAGE PYTHON RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python') HANDLER = 'handler'
AS $$
def handler(session, p_payload):
    return {"error": "Acces externe (EAI) non disponible sur ce compte"}
$$;

-- ---------------------------------------------------------
-- PROCEDURE : INSTALL_EAI_PROCEDURES
-- Installe dynamiquement le Network Rule, l'EAI SNOWSLED_EAI
-- et les 6 procedures qui en dependent, via session.sql().
-- Sa DEFINITION n'a pas d'EXTERNAL_ACCESS_INTEGRATIONS
-- => passe la validation statique du validateur Native App.
-- DD = '$' + '$' evite tout $$ litteral dans le corps Python
-- => le scanner $$ ne trouve que les delimiteurs debut/fin.
-- ---------------------------------------------------------
CREATE OR REPLACE PROCEDURE APP_SCHEMA.INSTALL_EAI_PROCEDURES()
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'install_eai_procedures'
AS
$$
def install_eai_procedures(session):
    DD = '$' + '$'
    r  = {'installed': [], 'errors': []}

    def run(sql, lbl):
        try:
            session.sql(sql).collect()
            r['installed'].append(lbl)
            return True
        except Exception as e:
            r['errors'].append(lbl + ': ' + str(e)[:200])
            return False

    run(
        'CREATE OR REPLACE NETWORK RULE APP_SCHEMA.EXTERNAL_APIS_RULE'
        ' TYPE=HOST_PORT MODE=EGRESS'
        " VALUE_LIST=('cloud.getdbt.com','api.fivetran.com','api.github.com','gitlab.com','dev.azure.com')",
        'NETWORK_RULE'
    )
    if not run(
        'CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION SNOWSLED_EAI'
        ' ALLOWED_NETWORK_RULES=(APP_SCHEMA.EXTERNAL_APIS_RULE)'
        " ALLOWED_AUTHENTICATION_SECRETS=(reference('GITHUB_SECRET'),"
        "reference('DBT_CLOUD_SECRET'),reference('FIVETRAN_SECRET'),"
        "reference('GITLAB_SECRET'),reference('AZURE_DEVOPS_SECRET'))"
        ' ENABLED=TRUE',
        'EAI'
    ):
        r['note'] = 'EAI not supported on this account (trial) - stub procedures kept'
        return r

    # ---- TEST_CONNECTION ----
    b_tc = '''
import _snowflake, json
import requests as req
def test_connection(session, connection_name):
    try:
        row = session.sql(
            f"SELECT CONNECTION_TYPE, ENDPOINT_URL FROM CONFIG_SCHEMA.EXTERNAL_CONNECTIONS"
            f" WHERE CONNECTION_NAME = '{connection_name}'"
        ).collect()
        if not row:
            return {'status': 'ERROR', 'message': 'Connexion non trouvee'}
        ct, ep = row[0]['CONNECTION_TYPE'], row[0]['ENDPOINT_URL']
        if ct == 'GITHUB':
            token = _snowflake.get_generic_secret_string('github_token')
            resp  = req.get('https://api.github.com/user',
                            headers={'Authorization': f'Bearer {token}'}, timeout=10)
            if resp.status_code == 200:
                d = resp.json()
                msg = f"Connecte en tant que {d.get('login','?')} ({d.get('name','?')})"
                st  = 'CONNECTED'
            else:
                msg, st = f'Erreur HTTP {resp.status_code}', 'ERROR'
        elif ct == 'GITLAB':
            token = _snowflake.get_generic_secret_string('gitlab_token')
            resp  = req.get('https://gitlab.com/api/v4/user',
                            headers={'PRIVATE-TOKEN': token}, timeout=10)
            if resp.status_code == 200:
                d = resp.json()
                msg = f"Connecte en tant que {d.get('username','?')} ({d.get('name','?')})"
                st  = 'CONNECTED'
            else:
                msg, st = f'Erreur HTTP {resp.status_code}', 'ERROR'
        elif ct == 'AZURE_DEVOPS':
            import base64
            token   = _snowflake.get_generic_secret_string('azure_devops_token')
            org_row = session.sql(
                "SELECT ACCOUNT_ID FROM CONFIG_SCHEMA.EXTERNAL_CONNECTIONS"
                " WHERE CONNECTION_NAME = 'AZURE_DEVOPS'"
            ).collect()
            org   = org_row[0]['ACCOUNT_ID'] if org_row else ''
            creds = base64.b64encode(f':{token}'.encode()).decode()
            resp  = req.get(f'https://dev.azure.com/{org}/_apis/projects?api-version=7.0',
                            headers={'Authorization': f'Basic {creds}'}, timeout=10)
            if resp.status_code == 200:
                cnt = len(resp.json().get('value', []))
                msg, st = f'{cnt} projet(s) Azure DevOps trouve(s)', 'CONNECTED'
            else:
                msg, st = f'Erreur HTTP {resp.status_code}', 'ERROR'
        elif ct == 'DBT_CLOUD':
            token = _snowflake.get_generic_secret_string('dbt_token')
            resp  = req.get(f'{ep}/api/v2/accounts/',
                            headers={'Authorization': f'Token {token}'}, timeout=10)
            if resp.status_code == 200:
                msg = f"{len(resp.json().get('data',[]))} compte(s) dbt Cloud trouve(s)"
                st  = 'CONNECTED'
            else:
                msg, st = f'Erreur HTTP {resp.status_code}', 'ERROR'
        elif ct == 'FIVETRAN':
            creds = json.loads(_snowflake.get_generic_secret_string('fivetran_creds'))
            resp  = req.get(f'{ep}/v1/connectors',
                            auth=(creds.get('api_key'), creds.get('api_secret')), timeout=10)
            if resp.status_code == 200:
                items = resp.json().get('data', {}).get('items', [])
                msg   = f'{len(items)} connecteur(s) Fivetran trouve(s)'
                st    = 'CONNECTED'
            else:
                msg, st = f'Erreur HTTP {resp.status_code}', 'ERROR'
        else:
            msg, st = 'Type de connexion non supporte', 'ERROR'
        esc = msg.replace("'", "''")
        session.sql(
            f"UPDATE CONFIG_SCHEMA.EXTERNAL_CONNECTIONS"
            f" SET STATUS='{st}', LAST_TEST_AT=CURRENT_TIMESTAMP(), LAST_TEST_MSG='{esc}'"
            f" WHERE CONNECTION_NAME='{connection_name}'"
        ).collect()
        return {'status': st, 'message': msg}
    except Exception as e:
        return {'status': 'ERROR', 'message': str(e)}
'''
    run(
        "CREATE OR REPLACE PROCEDURE APP_SCHEMA.TEST_CONNECTION(P_CONNECTION_NAME VARCHAR)"
        " RETURNS VARIANT LANGUAGE PYTHON RUNTIME_VERSION='3.11'"
        " PACKAGES=('snowflake-snowpark-python','requests')"
        " EXTERNAL_ACCESS_INTEGRATIONS=(SNOWSLED_EAI)"
        " SECRETS=('github_token'=reference('GITHUB_SECRET'),"
        "'dbt_token'=reference('DBT_CLOUD_SECRET'),"
        "'fivetran_creds'=reference('FIVETRAN_SECRET'),"
        "'gitlab_token'=reference('GITLAB_SECRET'),"
        "'azure_devops_token'=reference('AZURE_DEVOPS_SECRET'))"
        " HANDLER='test_connection' AS " + DD + b_tc + DD,
        'TEST_CONNECTION'
    )

    # ---- TRIGGER_DBT_JOB ----
    b_dbt = '''
import _snowflake
import requests as req
def trigger_dbt_job(session, job_id, cause):
    try:
        row = session.sql(
            "SELECT ENDPOINT_URL, ACCOUNT_ID FROM CONFIG_SCHEMA.EXTERNAL_CONNECTIONS"
            " WHERE CONNECTION_NAME='DBT_CLOUD'"
        ).collect()
        if not row:
            return {'status': 'ERROR', 'message': 'dbt Cloud non configure'}
        ep, acc_id = row[0]['ENDPOINT_URL'].rstrip('/'), row[0]['ACCOUNT_ID']
        token = _snowflake.get_generic_secret_string('dbt_token')
        resp  = req.post(
            f'{ep}/api/v2/accounts/{acc_id}/jobs/{job_id}/run/',
            headers={'Authorization': f'Token {token}', 'Content-Type': 'application/json'},
            json={'cause': cause}, timeout=15
        )
        if resp.status_code in (200, 201):
            d = resp.json().get('data', {})
            return {'status': 'RUNNING', 'run_id': d.get('id'), 'href': d.get('href', ''),
                    'message': f'Job {job_id} declenche avec succes'}
        return {'status': 'ERROR', 'message': f'HTTP {resp.status_code}: {resp.text[:300]}'}
    except Exception as e:
        return {'status': 'ERROR', 'message': str(e)}
'''
    run(
        "CREATE OR REPLACE PROCEDURE APP_SCHEMA.TRIGGER_DBT_JOB(P_JOB_ID VARCHAR,P_CAUSE VARCHAR)"
        " RETURNS VARIANT LANGUAGE PYTHON RUNTIME_VERSION='3.11'"
        " PACKAGES=('snowflake-snowpark-python','requests')"
        " EXTERNAL_ACCESS_INTEGRATIONS=(SNOWSLED_EAI)"
        " SECRETS=('dbt_token'=reference('DBT_CLOUD_SECRET'))"
        " HANDLER='trigger_dbt_job' AS " + DD + b_dbt + DD,
        'TRIGGER_DBT_JOB'
    )

    # ---- LIST_FIVETRAN_CONNECTORS ----
    b_lfv = '''
import _snowflake, json
import requests as req
def list_fivetran_connectors(session, group_id):
    try:
        row  = session.sql(
            "SELECT ENDPOINT_URL FROM CONFIG_SCHEMA.EXTERNAL_CONNECTIONS"
            " WHERE CONNECTION_NAME='FIVETRAN'"
        ).collect()
        ep    = row[0]['ENDPOINT_URL'].rstrip('/') if row else 'https://api.fivetran.com'
        creds = json.loads(_snowflake.get_generic_secret_string('fivetran_creds'))
        url   = f'{ep}/v1/connectors?limit=100'
        if group_id and group_id not in ('N/A', ''):
            url += f'&destination_id={group_id}'
        resp = req.get(url, auth=(creds['api_key'], creds['api_secret']), timeout=15)
        if resp.status_code == 200:
            return resp.json().get('data', {}).get('items', [])
        return {'error': f'HTTP {resp.status_code}: {resp.text[:300]}'}
    except Exception as e:
        return {'error': str(e)}
'''
    run(
        "CREATE OR REPLACE PROCEDURE APP_SCHEMA.LIST_FIVETRAN_CONNECTORS(P_GROUP_ID VARCHAR)"
        " RETURNS VARIANT LANGUAGE PYTHON RUNTIME_VERSION='3.11'"
        " PACKAGES=('snowflake-snowpark-python','requests')"
        " EXTERNAL_ACCESS_INTEGRATIONS=(SNOWSLED_EAI)"
        " SECRETS=('fivetran_creds'=reference('FIVETRAN_SECRET'))"
        " HANDLER='list_fivetran_connectors' AS " + DD + b_lfv + DD,
        'LIST_FIVETRAN_CONNECTORS'
    )

    # ---- CREATE_FIVETRAN_CONNECTOR ----
    b_cfv = '''
import _snowflake, json
import requests as req
def create_fivetran_connector(session, payload_str):
    try:
        p     = json.loads(payload_str)
        row   = session.sql(
            "SELECT ENDPOINT_URL FROM CONFIG_SCHEMA.EXTERNAL_CONNECTIONS"
            " WHERE CONNECTION_NAME='FIVETRAN'"
        ).collect()
        ep    = row[0]['ENDPOINT_URL'].rstrip('/') if row else 'https://api.fivetran.com'
        creds = json.loads(_snowflake.get_generic_secret_string('fivetran_creds'))
        body  = {
            'group_id': p['group_id'], 'service': p['service'],
            'sync_frequency': p['sync_frequency'], 'paused': p['paused'],
            'pause_after_trial': False,
            'config': {'schema': p['destination_schema'], **p.get('config', {})}
        }
        resp = req.post(f'{ep}/v1/connectors',
                        auth=(creds['api_key'], creds['api_secret']),
                        json=body, timeout=20)
        if resp.status_code in (200, 201):
            data = resp.json().get('data', {})
            cid  = data.get('id', '')
            if cid:
                def q(s): return str(s).replace("'", "''")
                ck   = f"{q(p['snowsled_project_id'])}_{q(p['connector_name']).upper().replace(' ', '_')}"
                freq = int(p['sync_frequency'])
                pv   = 'TRUE' if p['paused'] else 'FALSE'
                session.sql(
                    f"MERGE INTO CONFIG_SCHEMA.FIVETRAN_CONNECTORS t"
                    f" USING (SELECT '{ck}' AS CK) s ON t.CONNECTOR_KEY=s.CK"
                    f" WHEN MATCHED THEN UPDATE SET FIVETRAN_CONNECTOR_ID='{cid}',"
                    f"STATUS='ACTIVE',UPDATED_AT=CURRENT_TIMESTAMP()"
                    f" WHEN NOT MATCHED THEN INSERT (CONNECTOR_KEY,CONNECTOR_NAME,SERVICE,"
                    f"DESTINATION_SCHEMA,DSI_DB,GROUP_ID,SYNC_FREQUENCY,PAUSED,"
                    f"SNOWSLED_PROJECT_ID,FIVETRAN_CONNECTOR_ID,STATUS,CREATED_AT)"
                    f" VALUES ('{ck}','{q(p['connector_name'])}','{q(p['service'])}',"
                    f"'{q(p['destination_schema'])}','{q(p['dsi_db'])}',"
                    f"'{q(p['group_id'])}',{freq},{pv},"
                    f"'{q(p['snowsled_project_id'])}','{cid}','ACTIVE',CURRENT_TIMESTAMP())"
                ).collect()
            return data
        return {'error': f'HTTP {resp.status_code}: {resp.text[:300]}'}
    except Exception as e:
        return {'error': str(e)}
'''
    run(
        "CREATE OR REPLACE PROCEDURE APP_SCHEMA.CREATE_FIVETRAN_CONNECTOR(P_PAYLOAD VARCHAR)"
        " RETURNS VARIANT LANGUAGE PYTHON RUNTIME_VERSION='3.11'"
        " PACKAGES=('snowflake-snowpark-python','requests')"
        " EXTERNAL_ACCESS_INTEGRATIONS=(SNOWSLED_EAI)"
        " SECRETS=('fivetran_creds'=reference('FIVETRAN_SECRET'))"
        " HANDLER='create_fivetran_connector' AS " + DD + b_cfv + DD,
        'CREATE_FIVETRAN_CONNECTOR'
    )

    # ---- TRIGGER_FIVETRAN_SYNC ----
    b_sfv = '''
import _snowflake, json
import requests as req
def trigger_fivetran_sync(session, connector_id, force_full_sync):
    try:
        row   = session.sql(
            "SELECT ENDPOINT_URL FROM CONFIG_SCHEMA.EXTERNAL_CONNECTIONS"
            " WHERE CONNECTION_NAME='FIVETRAN'"
        ).collect()
        ep    = row[0]['ENDPOINT_URL'].rstrip('/') if row else 'https://api.fivetran.com'
        creds = json.loads(_snowflake.get_generic_secret_string('fivetran_creds'))
        force = force_full_sync.lower() == 'true'
        resp  = req.post(f'{ep}/v1/connectors/{connector_id}/sync',
                         auth=(creds['api_key'], creds['api_secret']),
                         json={'force': force}, timeout=15)
        if resp.status_code in (200, 204):
            return {'code': 'Success', 'message': f'Sync triggered for connector {connector_id}'}
        return {'code': str(resp.status_code), 'message': resp.text[:300]}
    except Exception as e:
        return {'code': 'ERROR', 'message': str(e)}
'''
    run(
        "CREATE OR REPLACE PROCEDURE APP_SCHEMA.TRIGGER_FIVETRAN_SYNC(P_CONNECTOR_ID VARCHAR,P_FORCE_FULL_SYNC VARCHAR)"
        " RETURNS VARIANT LANGUAGE PYTHON RUNTIME_VERSION='3.11'"
        " PACKAGES=('snowflake-snowpark-python','requests')"
        " EXTERNAL_ACCESS_INTEGRATIONS=(SNOWSLED_EAI)"
        " SECRETS=('fivetran_creds'=reference('FIVETRAN_SECRET'))"
        " HANDLER='trigger_fivetran_sync' AS " + DD + b_sfv + DD,
        'TRIGGER_FIVETRAN_SYNC'
    )

    # ---- CREATE_DBT_PROJECT ----
    b_dp = '''
import _snowflake, json
import requests as req
def create_dbt_project(session, payload_str):
    try:
        p   = json.loads(payload_str)
        row = session.sql(
            "SELECT ENDPOINT_URL, ACCOUNT_ID FROM CONFIG_SCHEMA.EXTERNAL_CONNECTIONS"
            " WHERE CONNECTION_NAME='DBT_CLOUD'"
        ).collect()
        if not row:
            return {'error': 'dbt Cloud non configure'}
        ep  = row[0]['ENDPOINT_URL'].rstrip('/')
        acc = p.get('account_id') or row[0]['ACCOUNT_ID']
        tok = _snowflake.get_generic_secret_string('dbt_token')
        hdrs = {'Authorization': f'Token {tok}', 'Content-Type': 'application/json'}
        body_r = {'name': p['project_name']}
        if p.get('project_subdir'):
            body_r['dbt_project_subdirectory'] = p['project_subdir']
        resp = req.post(f'{ep}/api/v2/accounts/{acc}/projects/',
                        headers=hdrs, json=body_r, timeout=20)
        if resp.status_code not in (200, 201):
            return {'error': f'HTTP {resp.status_code}: {resp.text[:300]}'}
        pd  = resp.json().get('data', {})
        pid = pd.get('id')
        if pid:
            if p.get('repo_url'):
                req.post(f'{ep}/api/v2/accounts/{acc}/projects/{pid}/repositories/',
                         headers=hdrs,
                         json={'account_id': acc, 'project_id': pid,
                               'remote_url': p['repo_url']},
                         timeout=20)
            req.post(f'{ep}/api/v2/accounts/{acc}/projects/{pid}/connections/',
                     headers=hdrs,
                     json={'type': 'snowflake',
                           'name': f"{p['project_name']}_snowflake",
                           'account':   p.get('snowflake_account', ''),
                           'database':  p.get('snowflake_database', ''),
                           'warehouse': p.get('snowflake_warehouse', ''),
                           'schema':    p.get('snowflake_schema', '')},
                     timeout=20)
            def q(s): return str(s).replace("'", "''")
            pk = (f"{q(p['snowsled_project_id'])}_"
                  f"{q(p['project_name']).upper().replace(' ', '_')}")
            session.sql(
                f"MERGE INTO CONFIG_SCHEMA.DBT_PROJECTS t"
                f" USING (SELECT '{pk}' AS PK) s ON t.DBT_PROJECT_KEY=s.PK"
                f" WHEN MATCHED THEN UPDATE SET DBT_CLOUD_ID={pid},"
                f"STATUS='ACTIVE',UPDATED_AT=CURRENT_TIMESTAMP()"
                f" WHEN NOT MATCHED THEN INSERT (DBT_PROJECT_KEY,PROJECT_NAME,REPO_URL,"
                f"PROJECT_SUBDIR,SF_ACCOUNT,SF_DATABASE,SF_SCHEMA,SF_WAREHOUSE,"
                f"SNOWSLED_PROJECT_ID,DBT_CLOUD_ID,STATUS,CREATED_AT)"
                f" VALUES ('{pk}','{q(p['project_name'])}',"
                f"'{q(p.get('repo_url',''))}','{q(p.get('project_subdir',''))}',"
                f"'{q(p.get('snowflake_account',''))}','{q(p.get('snowflake_database',''))}',"
                f"'{q(p.get('snowflake_schema',''))}','{q(p.get('snowflake_warehouse',''))}',"
                f"'{q(p['snowsled_project_id'])}',{pid},'ACTIVE',CURRENT_TIMESTAMP())"
            ).collect()
        return pd
    except Exception as e:
        return {'error': str(e)}
'''
    run(
        "CREATE OR REPLACE PROCEDURE APP_SCHEMA.CREATE_DBT_PROJECT(P_PAYLOAD VARCHAR)"
        " RETURNS VARIANT LANGUAGE PYTHON RUNTIME_VERSION='3.11'"
        " PACKAGES=('snowflake-snowpark-python','requests')"
        " EXTERNAL_ACCESS_INTEGRATIONS=(SNOWSLED_EAI)"
        " SECRETS=('dbt_token'=reference('DBT_CLOUD_SECRET'))"
        " HANDLER='create_dbt_project' AS " + DD + b_dp + DD,
        'CREATE_DBT_PROJECT'
    )

    return r
$$;

GRANT USAGE ON PROCEDURE APP_SCHEMA.INSTALL_EAI_PROCEDURES() TO APPLICATION ROLE APP_PUBLIC;

-- Tentative d installation au runtime (silencieuse sur les comptes trial)
BEGIN
    CALL APP_SCHEMA.INSTALL_EAI_PROCEDURES();
EXCEPTION
    WHEN OTHER THEN NULL;
END;

GRANT USAGE ON SCHEMA APP_SCHEMA    TO APPLICATION ROLE APP_PUBLIC;
GRANT USAGE ON SCHEMA CONFIG_SCHEMA TO APPLICATION ROLE APP_PUBLIC;
GRANT USAGE ON SCHEMA AUDIT_SCHEMA  TO APPLICATION ROLE APP_PUBLIC;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA CONFIG_SCHEMA TO APPLICATION ROLE APP_PUBLIC;
GRANT SELECT, INSERT                 ON ALL TABLES IN SCHEMA AUDIT_SCHEMA  TO APPLICATION ROLE APP_PUBLIC;
GRANT SELECT ON ALL VIEWS  IN SCHEMA CONFIG_SCHEMA TO APPLICATION ROLE APP_PUBLIC;

GRANT USAGE  ON ALL STREAMLITS IN SCHEMA APP_SCHEMA TO APPLICATION ROLE APP_PUBLIC;
GRANT USAGE  ON ALL PROCEDURES IN SCHEMA APP_SCHEMA TO APPLICATION ROLE APP_PUBLIC;

-- ---------------------------------------------------------
-- 12. PROCEDURE : INITIALIZE_FINOPS_VIEWS
-- A appeler apres GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE
-- (post-deploy ou manuellement si le grant arrive apres installation)
-- ---------------------------------------------------------
CREATE OR REPLACE PROCEDURE APP_SCHEMA.INITIALIZE_FINOPS_VIEWS()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
BEGIN
    CREATE OR REPLACE VIEW CONFIG_SCHEMA.V_SERVERLESS_TOP_CONSUMERS AS
        SELECT
            service_type,
            ROUND(SUM(credits_used), 2) AS total_credits,
            COUNT(*)                    AS periods_active
        FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
        WHERE start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
          AND service_type != 'WAREHOUSE_METERING'
        GROUP BY service_type
        ORDER BY total_credits DESC;

    GRANT SELECT ON VIEW CONFIG_SCHEMA.V_SERVERLESS_TOP_CONSUMERS TO APPLICATION ROLE APP_PUBLIC;
    RETURN 'FinOps views initialized successfully';
EXCEPTION
    WHEN OTHER THEN
        RETURN 'ERROR: SNOWFLAKE.ACCOUNT_USAGE not accessible. Grant IMPORTED PRIVILEGES first, then call APP_SCHEMA.INITIALIZE_FINOPS_VIEWS().';
END;
$$;

GRANT USAGE ON PROCEDURE APP_SCHEMA.INITIALIZE_FINOPS_VIEWS() TO APPLICATION ROLE APP_PUBLIC;
