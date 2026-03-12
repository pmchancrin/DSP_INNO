# ============================================================
# SNOWSLED PLATFORM
# Application de setup et de connexion aux outils tiers
# ============================================================

import streamlit as st
import json
import sys
import os
import pandas as pd
import altair as alt
from datetime import datetime

# utils/ is copied into this directory by snowflake.yml artifacts mapping
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
# local dev fallback: utils is one level up under src/
_src = os.path.join(_here, "..")
if _src not in sys.path:
    sys.path.insert(0, _src)
from utils.session import get_session

st.set_page_config(
    page_title="Snowsled Platform",
    page_icon="❄️",
    layout="wide",
)

# ── Session Snowflake (Snowflake natif ou connexion locale) ──
session = get_session()

# ── Helpers ──────────────────────────────────────────────────
def run_sql(query: str, success_msg: str = None):
    """Exécute du SQL et retourne True/message en cas de succès."""
    try:
        session.sql(query).collect()
        if success_msg:
            st.success(success_msg)
        return True
    except Exception as e:
        st.error(f"Erreur SQL : {e}")
        return False


def run_query(sql: str) -> pd.DataFrame:
    """Exécute une requête SQL et retourne un DataFrame pandas."""
    try:
        return session.sql(sql).to_pandas()
    except Exception as e:
        st.error(f"Erreur requête : {e}")
        return pd.DataFrame()


def upsert_config(key: str, value, description: str = ""):
    """Enregistre ou met à jour une clé de configuration."""
    v = json.dumps(value)
    v_esc   = v.replace("'", "''")
    desc_esc = description.replace("'", "''")
    key_esc  = key.replace("'", "''")
    session.sql(f"""
        MERGE INTO CONFIG_SCHEMA.ACCOUNT_CONFIG t
        USING (SELECT '{key_esc}'          AS K,
                      PARSE_JSON('{v_esc}') AS V,
                      '{desc_esc}'          AS D) s
            ON t.CONFIG_KEY = s.K
        WHEN MATCHED THEN UPDATE
            SET t.CONFIG_VALUE = s.V,
                t.DESCRIPTION  = s.D,
                t.UPDATED_AT   = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION)
            VALUES (s.K, s.V, s.D)
    """).collect()


def get_config(key: str):
    rows = session.sql(f"""
        SELECT CONFIG_VALUE::STRING AS V
        FROM CONFIG_SCHEMA.ACCOUNT_CONFIG
        WHERE CONFIG_KEY = '{key}'
    """).collect()
    return rows[0]["V"] if rows else None


def upsert_connection(name, conn_type, endpoint, account_id, secret_ref):
    n  = name.replace("'", "''")
    ct = conn_type.replace("'", "''")
    ep = endpoint.replace("'", "''")
    ai = account_id.replace("'", "''")
    sr = secret_ref.replace("'", "''")
    session.sql(f"""
        MERGE INTO CONFIG_SCHEMA.EXTERNAL_CONNECTIONS t
        USING (SELECT '{n}' AS N) s ON t.CONNECTION_NAME = s.N
        WHEN MATCHED THEN UPDATE
            SET t.CONNECTION_TYPE = '{ct}',
                t.ENDPOINT_URL    = '{ep}',
                t.ACCOUNT_ID      = '{ai}',
                t.SECRET_REF      = '{sr}',
                t.STATUS          = 'PENDING',
                t.UPDATED_AT      = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT
            (CONNECTION_NAME, CONNECTION_TYPE, ENDPOINT_URL, ACCOUNT_ID, SECRET_REF)
            VALUES ('{n}', '{ct}', '{ep}', '{ai}', '{sr}')
    """).collect()


def get_connection(name: str):
    rows = session.sql(f"""
        SELECT * FROM CONFIG_SCHEMA.EXTERNAL_CONNECTIONS
        WHERE CONNECTION_NAME = '{name}'
    """).collect()
    return rows[0].as_dict() if rows else {}


def test_connection(name: str):
    result = session.call("APP_SCHEMA.TEST_CONNECTION", name)
    return result


# ── Navigation ────────────────────────────────────────────────
st.sidebar.image(
    "https://upload.wikimedia.org/wikipedia/commons/f/ff/Snowflake_Logo.svg",
    width=160
)
st.sidebar.title("Snowsled Platform")
st.sidebar.markdown("---")

pages = {
    "🏠  Accueil":          "home",
    "⚙️  Compte Snowflake": "snowflake_setup",
    "�  Source Control":   "git",
    "🔵  dbt Cloud":        "dbt",
    "🔴  Fivetran":         "fivetran",
    "❄️  Compliance":       "compliance",
}
choice = st.sidebar.radio("Navigation", list(pages.keys()))
page = pages[choice]

# ── PAGE : Accueil ────────────────────────────────────────────
if page == "home":
    st.title("❄️ Snowsled Platform — Setup & Connexions")
    st.markdown("""
    Bienvenue dans **Snowsled Platform**, le point de départ de votre POC.
    
    Cette application vous permet de :
    - Configurer les bases de votre compte Snowflake (warehouse, bases, rôles)
    - Connecter un gestionnaire de code source (**GitHub**, **GitLab** ou **Azure DevOps**)
    - Connecter un compte trial **dbt Cloud**
    - Connecter un compte trial **Fivetran**
    """)

    st.markdown("---")
    st.subheader("Statut des connexions")

    conn_rows = session.sql("""
        SELECT CONNECTION_NAME, CONNECTION_TYPE, STATUS, LAST_TEST_AT, LAST_TEST_MSG
        FROM CONFIG_SCHEMA.EXTERNAL_CONNECTIONS
        ORDER BY CONNECTION_NAME
    """).to_pandas()

    if conn_rows.empty:
        st.info("Aucune connexion configurée pour l'instant.")
    else:
        for _, row in conn_rows.iterrows():
            icon = {"CONNECTED": "✅", "ERROR": "❌", "PENDING": "🔄"}.get(row["STATUS"], "❓")
            st.metric(
                label=f"{icon} {row['CONNECTION_NAME']} ({row['CONNECTION_TYPE']})",
                value=row["STATUS"],
                help=row["LAST_TEST_MSG"] or "Aucun test effectué",
            )

    st.markdown("---")
    cfg_rows = session.sql("""
        SELECT CONFIG_KEY, CONFIG_VALUE::STRING AS CONFIG_VALUE, UPDATED_AT
        FROM CONFIG_SCHEMA.ACCOUNT_CONFIG
        ORDER BY CONFIG_KEY
    """).to_pandas()

    if not cfg_rows.empty:
        st.subheader("Configuration Snowflake enregistrée")
        st.dataframe(cfg_rows, use_container_width=True)

# ── PAGE : Compte Snowflake ───────────────────────────────────
elif page == "snowflake_setup":
    st.title("⚙️ Setup du compte Snowflake")
    st.markdown("Configurez les ressources de base de votre compte Snowflake.")

    tab1, tab2, tab3 = st.tabs(["Warehouse", "Bases de données", "Rôles"])

    # -- Warehouses
    with tab1:
        st.subheader("Création d'un Virtual Warehouse")
        wh_name = st.text_input("Nom du warehouse", value="DSP_WH", key="wh_name")
        wh_size = st.selectbox(
            "Taille", ["X-SMALL", "SMALL", "MEDIUM", "LARGE", "X-LARGE"],
            index=1, key="wh_size"
        )
        wh_auto_suspend = st.number_input(
            "Auto-suspend (secondes)", min_value=30, max_value=3600,
            value=120, step=30, key="wh_auto_suspend"
        )
        wh_auto_resume = st.checkbox("Auto-resume", value=True, key="wh_auto_resume")

        if st.button("Créer / Mettre à jour le Warehouse", key="btn_wh"):
            sql = f"""
                CREATE WAREHOUSE IF NOT EXISTS {wh_name}
                  WITH WAREHOUSE_SIZE = '{wh_size}'
                  AUTO_SUSPEND = {wh_auto_suspend}
                  AUTO_RESUME  = {'TRUE' if wh_auto_resume else 'FALSE'}
                  INITIALLY_SUSPENDED = TRUE
                  COMMENT = 'Créé via Snowsled Platform'
            """
            if run_sql(sql, f"Warehouse **{wh_name}** prêt."):
                upsert_config("DEFAULT_WAREHOUSE", wh_name, "Warehouse par défaut Snowsled")
                upsert_config("DEFAULT_WH_SIZE", wh_size, "Taille du warehouse par défaut")

        st.markdown("---")
        st.subheader("Warehouses existants")
        wh_df = session.sql("""
            SHOW WAREHOUSES
        """).to_pandas()
        if not wh_df.empty:
            st.dataframe(
                wh_df[["name", "size", "state", "auto_suspend"]],
                use_container_width=True
            )

    # -- Bases de données
    with tab2:
        st.subheader("Création des bases de données")
        st.info("Les bases DSI et DSO seront créées selon la convention de nommage configurée dans **Snowsled Admin**.")

        project_name = st.text_input(
            "Nom du projet / domaine (ex: RETAIL, FINANCE, MARKETING)",
            value="DEMO", key="db_project"
        ).upper().strip()

        col1, col2 = st.columns(2)
        with col1:
            dsi_db = st.text_input("Nom base DSI", value=f"DSI_{project_name}", key="dsi_db").upper()
        with col2:
            dso_db = st.text_input("Nom base DSO", value=f"DSO_{project_name}", key="dso_db").upper()

        data_retention = st.slider("Data Retention Time (jours)", 0, 90, value=7, key="data_ret")

        if st.button("Créer les bases DSI + DSO", key="btn_db"):
            ok_dsi = run_sql(f"""
                CREATE DATABASE IF NOT EXISTS {dsi_db}
                DATA_RETENTION_TIME_IN_DAYS = {data_retention}
                COMMENT = 'Couche intégration brute - Snowsled'
            """, f"Base **{dsi_db}** créée.")

            ok_dso = run_sql(f"""
                CREATE DATABASE IF NOT EXISTS {dso_db}
                DATA_RETENTION_TIME_IN_DAYS = {data_retention}
                COMMENT = 'Couche output curated - Snowsled'
            """, f"Base **{dso_db}** créée.")

            if ok_dsi and ok_dso:
                upsert_config(f"DB_DSI_{project_name}", dsi_db, f"Base DSI projet {project_name}")
                upsert_config(f"DB_DSO_{project_name}", dso_db, f"Base DSO projet {project_name}")

    # -- Rôles
    with tab3:
        st.subheader("Création des rôles fonctionnels")

        role_types = {
            "ADMIN":     "Accès complet sur les bases du projet",
            "DEVELOPER": "Lecture/écriture sur DSI, lecture sur DSO",
            "ANALYST":   "Lecture seule sur DSO",
            "VIEWER":    "Lecture sur les vues partagées uniquement",
        }

        project_r = st.text_input(
            "Nom du projet pour les rôles", value="DEMO", key="role_project"
        ).upper().strip()

        roles_to_create = st.multiselect(
            "Rôles à créer",
            options=list(role_types.keys()),
            default=["ADMIN", "DEVELOPER", "ANALYST"],
            key="roles_sel",
        )

        if st.button("Créer les rôles", key="btn_roles"):
            for r in roles_to_create:
                role_name = f"ROLE_{project_r}_{r}"
                run_sql(f"""
                    CREATE ROLE IF NOT EXISTS {role_name}
                    COMMENT = '{role_types[r]} - Créé via Snowsled'
                """, f"Rôle **{role_name}** créé.")

# ── PAGE : Source Control (GitHub / GitLab / Azure DevOps) ───
elif page == "git":
    st.title("🔗 Connexion Source Control")
    st.markdown("""
    Connectez votre gestionnaire de code source pour permettre à Snowsled de :
    - Versionner les objets SQL / dbt models
    - Synchroniser les configurations
    - Déclencher des workflows CI/CD
    """)

    PROVIDERS = {
        "GitHub": {
            "key":           "GITHUB",
            "url":           "https://api.github.com",
            "token_label":   "Personal Access Token (PAT)",
            "token_help":    "Scopes requis : repo, workflow, read:org",
            "org_label":     "Organisation / Utilisateur GitHub",
            "secret_name":   "SNOWSLED_GITHUB_PAT",
        },
        "GitLab": {
            "key":           "GITLAB",
            "url":           "https://gitlab.com",
            "token_label":   "Personal Access Token (PAT)",
            "token_help":    "Scopes requis : api, read_repository",
            "org_label":     "Namespace / Groupe GitLab",
            "secret_name":   "SNOWSLED_GITLAB_PAT",
        },
        "Azure DevOps": {
            "key":           "AZURE_DEVOPS",
            "url":           "https://dev.azure.com",
            "token_label":   "Personal Access Token (PAT)",
            "token_help":    "Scopes requis : Code (Read), Project and Team (Read)",
            "org_label":     "Organisation Azure DevOps",
            "secret_name":   "SNOWSLED_AZDEVOPS_PAT",
        },
    }

    provider_name = st.selectbox(
        "Fournisseur de code source",
        options=list(PROVIDERS.keys()),
        key="git_provider",
    )
    prov     = PROVIDERS[provider_name]
    conn_key = prov["key"]
    existing = get_connection(conn_key)

    with st.form("git_form"):
        st.subheader(f"Paramètres {provider_name}")
        git_token = st.text_input(
            prov["token_label"],
            value=existing.get("SECRET_REF", ""),
            type="password",
            help=prov["token_help"],
        )
        git_org = st.text_input(
            prov["org_label"],
            value=existing.get("ACCOUNT_ID", ""),
        )
        git_repo = st.text_input(
            "Dépôt principal (ex: mon-org/snowsled-poc)",
            value=get_config(f"{conn_key}_REPO") or "",
        )
        submitted = st.form_submit_button("Enregistrer la connexion")

    if submitted:
        if not git_token or not git_org:
            st.warning(f"Le token et l'{prov['org_label'].lower()} sont requis.")
        else:
            secret_name = prov["secret_name"]
            run_sql(f"""
                CREATE OR REPLACE SECRET {secret_name}
                  TYPE = GENERIC_STRING
                  SECRET_STRING = $${git_token}$$
                  COMMENT = '{provider_name} PAT - Snowsled'
            """)
            upsert_connection(
                conn_key, conn_key,
                prov["url"], git_org, secret_name,
            )
            if git_repo:
                upsert_config(f"{conn_key}_REPO", git_repo, f"Dépôt {provider_name} principal Snowsled")
            st.success(f"Configuration {provider_name} enregistrée !")

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button(f"Tester la connexion {provider_name}", key="btn_test_git"):
            with st.spinner("Test en cours..."):
                result = test_connection(conn_key)
                if result and result.get("status") == "CONNECTED":
                    st.success(f"✅ {result['message']}")
                else:
                    st.error(f"❌ {result.get('message', 'Erreur inconnue') if result else 'Erreur'}")

    if existing.get("STATUS") == "CONNECTED":
        st.info(f"Dernière vérification : {existing.get('LAST_TEST_AT', 'N/A')}")

# ── PAGE : dbt Cloud ──────────────────────────────────────────
elif page == "dbt":
    st.title("🔵 Connexion dbt Cloud")
    st.markdown("""
    Connectez votre compte trial **dbt Cloud** pour :
    - Créer et synchroniser des projets dbt
    - Déclencher des runs depuis Snowsled
    - Accéder aux métadonnées de lignage
    """)

    existing = get_connection("DBT_CLOUD")

    with st.form("dbt_form"):
        st.subheader("Paramètres dbt Cloud")
        dbt_endpoint = st.selectbox(
            "Endpoint dbt Cloud",
            options=[
                "https://cloud.getdbt.com",
                "https://emea.dbt.com",
                "https://au.dbt.com",
            ],
            index=0,
        )
        dbt_api_key  = st.text_input(
            "Service Account Token (API Key)",
            value=existing.get("SECRET_REF", ""),
            type="password",
            help="Paramètres dbt Cloud → Account Settings → Service Accounts"
        )
        dbt_account_id = st.text_input(
            "Account ID dbt Cloud",
            value=existing.get("ACCOUNT_ID", ""),
            help="Visible dans l'URL : cloud.getdbt.com/accounts/<ID>"
        )
        submitted = st.form_submit_button("Enregistrer la connexion")

    if submitted:
        if not dbt_api_key or not dbt_account_id:
            st.warning("L'API Key et l'Account ID sont requis.")
        else:
            secret_name = "SNOWSLED_DBT_TOKEN"
            run_sql(f"""
                CREATE OR REPLACE SECRET {secret_name}
                  TYPE = GENERIC_STRING
                  SECRET_STRING = $${dbt_api_key}$$
                  COMMENT = 'dbt Cloud API Token - Snowsled'
            """)
            upsert_connection(
                "DBT_CLOUD", "DBT_CLOUD",
                dbt_endpoint, dbt_account_id, secret_name
            )
            upsert_config("DBT_CLOUD_ACCOUNT_ID", dbt_account_id, "Account ID dbt Cloud")
            upsert_config("DBT_CLOUD_ENDPOINT", dbt_endpoint, "Endpoint dbt Cloud")
            st.success("Configuration dbt Cloud enregistrée !")

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Tester la connexion dbt Cloud", key="btn_test_dbt"):
            with st.spinner("Test en cours..."):
                result = test_connection("DBT_CLOUD")
                if result and result.get("status") == "CONNECTED":
                    st.success(f"✅ {result['message']}")
                else:
                    st.error(f"❌ {result.get('message', 'Erreur inconnue') if result else 'Erreur'}")

# ── PAGE : Fivetran ───────────────────────────────────────────
elif page == "fivetran":
    st.title("🔴 Connexion Fivetran")
    st.markdown("""
    Connectez votre compte trial **Fivetran** pour :
    - Lister et monitorer vos connecteurs de données
    - Déclencher des syncs depuis Snowsled
    - Visualiser le statut d'ingestion dans DSI
    """)

    existing = get_connection("FIVETRAN")

    with st.form("fivetran_form"):
        st.subheader("Paramètres Fivetran")
        ft_endpoint  = st.text_input(
            "Endpoint API Fivetran",
            value="https://api.fivetran.com",
            help="Généralement https://api.fivetran.com"
        )
        ft_api_key    = st.text_input(
            "API Key",
            value="",
            type="password",
            help="Fivetran → Settings → API Config"
        )
        ft_api_secret = st.text_input(
            "API Secret",
            value="",
            type="password",
        )
        ft_account_id = st.text_input(
            "Account ID Fivetran (optionnel)",
            value=existing.get("ACCOUNT_ID", ""),
        )
        submitted = st.form_submit_button("Enregistrer la connexion")

    if submitted:
        if not ft_api_key or not ft_api_secret:
            st.warning("L'API Key et l'API Secret sont requis.")
        else:
            credentials = json.dumps({"api_key": ft_api_key, "api_secret": ft_api_secret})
            secret_name = "SNOWSLED_FIVETRAN_CREDS"
            run_sql(f"""
                CREATE OR REPLACE SECRET {secret_name}
                  TYPE = GENERIC_STRING
                  SECRET_STRING = $${credentials}$$
                  COMMENT = 'Fivetran API Credentials - Snowsled'
            """)
            upsert_connection(
                "FIVETRAN", "FIVETRAN",
                ft_endpoint, ft_account_id or "N/A", secret_name
            )
            st.success("Configuration Fivetran enregistrée !")

    st.markdown("---")
    col1, _ = st.columns(2)
    with col1:
        if st.button("Tester la connexion Fivetran", key="btn_test_ft"):
            with st.spinner("Test en cours..."):
                result = test_connection("FIVETRAN")
                if result and result.get("status") == "CONNECTED":
                    st.success(f"✅ {result['message']}")
                else:
                    st.error(f"❌ {result.get('message', 'Erreur inconnue') if result else 'Erreur'}")

# ── PAGE : Snowflake Compliance ───────────────────────────────
elif page == "compliance":

    # ── Styles ──────────────────────────────────────────────────
    st.markdown("""
    <style>
    .dashboard-header {
        background: linear-gradient(135deg, #29B5E8 0%, #1a7bb5 50%, #0d4f7a 100%);
        border-radius: 12px;
        padding: 22px 32px 18px 32px;
        margin-bottom: 18px;
        display: flex;
        align-items: center;
        gap: 18px;
        box-shadow: 0 4px 18px rgba(41,181,232,0.18);
    }
    .dashboard-header .icon { font-size: 2.6rem; }
    .dashboard-header h1 {
        color: white !important;
        font-size: 1.75rem !important;
        font-weight: 700 !important;
        margin: 0 !important;
        letter-spacing: 0.5px;
    }
    .dashboard-header .subtitle {
        color: rgba(255,255,255,0.80);
        font-size: 0.82rem;
        margin-top: 4px;
    }
    div[data-testid="stMetric"] {
        background: #f7fbff;
        border: 1px solid #d6eaf8;
        border-radius: 10px;
        padding: 14px 18px !important;
        box-shadow: 0 1px 4px rgba(41,181,232,0.07);
    }
    div[data-testid="stMetricLabel"] { font-size: 0.78rem !important; color: #5d7a8a !important; }
    div[data-testid="stMetricValue"] { font-size: 1.4rem !important; font-weight: 700 !important; color: #1a3a4a !important; }
    div[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
    div[data-testid="stAlert"] { border-radius: 8px !important; }
    hr { border-color: #d6eaf8 !important; margin: 8px 0 !important; }
    </style>
    """, unsafe_allow_html=True)

    # ── Bannière ─────────────────────────────────────────────────
    st.markdown(f"""
    <div class="dashboard-header">
      <span class="icon">❄️</span>
      <div>
        <h1>Snowflake Governance Dashboard</h1>
        <div class="subtitle">
          Monitoring · Sécurité · Warehouses · FinOps · Gouvernance
          &nbsp;·&nbsp; Mis à jour : {datetime.now().strftime('%Y-%m-%d %H:%M')}
          &nbsp;·&nbsp; Données ACCOUNT_USAGE (latence ~2h)
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    def fmt_credits(v) -> str:
        return f"{v:,.2f}" if v is not None else "N/A"

    def get_warehouse_config() -> pd.DataFrame:
        try:
            rows = session.sql("SHOW WAREHOUSES").collect()
            if not rows:
                return pd.DataFrame()
            df = pd.DataFrame([r.as_dict() for r in rows])
            df.columns = [c.upper() for c in df.columns]
            if 'AUTO_SUSPEND' in df.columns:
                df['AUTO_SUSPEND'] = pd.to_numeric(df['AUTO_SUSPEND'], errors='coerce')
            for col in ['MIN_CLUSTER_COUNT', 'MAX_CLUSTER_COUNT']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(1)
            return df
        except Exception as e:
            st.error(f"Erreur SHOW WAREHOUSES : {e}")
            return pd.DataFrame()

    # ── Onglets ───────────────────────────────────────────────────
    tab_overview, tab_monitor, tab_sec, tab_wh, tab_finops, tab_gov = st.tabs([
        "🏠 Vue d'ensemble",
        "📊 Monitoring",
        "🛡️ Sécurité",
        "🏭 Warehouses",
        "💰 FinOps",
        "✅ Gouvernance & Conformité",
    ])

    # ═══════════════════════════════════════════════════════════════
    # TAB 1 – VUE D'ENSEMBLE
    # ═══════════════════════════════════════════════════════════════
    with tab_overview:
        st.header("Vue d'ensemble du compte Snowflake")
        col1, col2, col3, col4 = st.columns(4)

        credits_month = run_query("""
            SELECT ROUND(SUM(credits_used), 2) AS total
            FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
            WHERE start_time >= DATE_TRUNC('month', CURRENT_DATE())
        """)
        credits_prev = run_query("""
            SELECT ROUND(SUM(credits_used), 2) AS total
            FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
            WHERE start_time >= DATE_TRUNC('month', DATEADD(month, -1, CURRENT_DATE()))
              AND start_time  <  DATE_TRUNC('month', CURRENT_DATE())
        """)
        active_users = run_query("""
            SELECT COUNT(DISTINCT user_name) AS cnt
            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
            WHERE start_time >= DATE_TRUNC('month', CURRENT_DATE())
        """)
        queries_24h = run_query("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN error_code IS NOT NULL THEN 1 ELSE 0 END) AS errors
            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
            WHERE start_time >= DATEADD(day, -1, CURRENT_TIMESTAMP())
        """)
        storage_df = run_query("""
            SELECT ROUND(AVG(storage_bytes)  / POWER(1024,4), 3) AS table_tb,
                   ROUND(AVG(stage_bytes)    / POWER(1024,4), 3) AS stage_tb,
                   ROUND(AVG(failsafe_bytes) / POWER(1024,4), 3) AS failsafe_tb
            FROM SNOWFLAKE.ACCOUNT_USAGE.STORAGE_USAGE
            WHERE usage_date >= DATEADD(day, -7, CURRENT_DATE())
        """)

        cur  = credits_month['TOTAL'].iloc[0] if not credits_month.empty else 0
        prev = credits_prev['TOTAL'].iloc[0]  if not credits_prev.empty  else 0
        delta_pct = ((cur - prev) / prev * 100) if prev and prev > 0 else None

        with col1:
            st.metric("Crédits ce mois", fmt_credits(cur),
                      delta=f"{delta_pct:+.1f}% vs mois préc." if delta_pct is not None else None,
                      delta_color="inverse")
        with col2:
            st.metric("Utilisateurs actifs (mois)",
                      int(active_users['CNT'].iloc[0]) if not active_users.empty else "N/A")
        with col3:
            total_q = int(queries_24h['TOTAL'].iloc[0])  if not queries_24h.empty else 0
            err_q   = int(queries_24h['ERRORS'].iloc[0]) if not queries_24h.empty else 0
            st.metric("Requêtes (24h)", total_q,
                      delta=f"{err_q} erreurs" if err_q else None, delta_color="inverse")
        with col4:
            if not storage_df.empty:
                total_tb = sum(filter(None, [storage_df['TABLE_TB'].iloc[0],
                                             storage_df['STAGE_TB'].iloc[0],
                                             storage_df['FAILSAFE_TB'].iloc[0]]))
            else:
                total_tb = 0
            st.metric("Stockage total (TB)", f"{total_tb:.3f}")

        st.divider()
        col_a, col_b = st.columns(2)

        with col_a:
            st.subheader("Crédits par type de service (30 jours)")
            svc = run_query("""
                SELECT service_type, ROUND(SUM(credits_used), 2) AS credits
                FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
                WHERE start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
                GROUP BY service_type ORDER BY credits DESC
            """)
            if not svc.empty:
                st.altair_chart(
                    alt.Chart(svc).mark_arc(innerRadius=60).encode(
                        theta=alt.Theta('CREDITS:Q'),
                        color=alt.Color('SERVICE_TYPE:N', legend=alt.Legend(title='Service')),
                        tooltip=['SERVICE_TYPE:N', 'CREDITS:Q']
                    ).properties(height=260),
                    use_container_width=True
                )
                st.dataframe(svc, use_container_width=True)

        with col_b:
            st.subheader("Tendance des crédits (30 jours)")
            trend = run_query("""
                SELECT DATE_TRUNC('day', start_time)::DATE AS jour,
                       ROUND(SUM(credits_used), 3) AS credits
                FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
                WHERE start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
                GROUP BY 1 ORDER BY 1
            """)
            if not trend.empty:
                st.altair_chart(
                    alt.Chart(trend).mark_line(point=True).encode(
                        x=alt.X('JOUR:T', title='Date'),
                        y=alt.Y('CREDITS:Q', title='Crédits'),
                        tooltip=['JOUR:T', 'CREDITS:Q']
                    ).properties(height=260),
                    use_container_width=True
                )

        st.subheader("Crédits empilés par service/jour (30 jours)")
        daily_svc = run_query("""
            SELECT DATE_TRUNC('day', start_time)::DATE AS jour,
                   service_type,
                   ROUND(SUM(credits_used), 3) AS credits
            FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
            WHERE start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
            GROUP BY 1, 2 ORDER BY 1
        """)
        if not daily_svc.empty:
            st.altair_chart(
                alt.Chart(daily_svc).mark_area().encode(
                    x=alt.X('JOUR:T', title='Date'),
                    y=alt.Y('CREDITS:Q', title='Crédits', stack='zero'),
                    color=alt.Color('SERVICE_TYPE:N', title='Service'),
                    tooltip=['JOUR:T', 'SERVICE_TYPE:N', 'CREDITS:Q']
                ).properties(height=300, title='Crédits empilés (Warehouse / Cloud Services / Snowpipe / Tasks …)'),
                use_container_width=True
            )

    # ═══════════════════════════════════════════════════════════════
    # TAB 2 – MONITORING
    # ═══════════════════════════════════════════════════════════════
    with tab_monitor:
        st.header("Monitoring & Supervision des requêtes")
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Requêtes longues en cours / récentes (1h)")
            running = run_query("""
                SELECT user_name, warehouse_name,
                       ROUND(DATEDIFF('second', start_time, CURRENT_TIMESTAMP()), 0) AS running_sec,
                       execution_status,
                       LEFT(query_text, 120) AS query_preview
                FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
                WHERE start_time >= DATEADD(hour, -1, CURRENT_TIMESTAMP())
                  AND execution_status IN ('RUNNING','QUEUED')
                ORDER BY running_sec DESC LIMIT 20
            """)
            if not running.empty:
                st.dataframe(running, use_container_width=True)
            else:
                st.info("Aucune requête en cours détectée (latence ACCOUNT_USAGE ~2h)")

        with col2:
            st.subheader("Erreurs de requêtes (24h)")
            query_errors = run_query("""
                SELECT user_name, warehouse_name, error_code, error_message, COUNT(*) AS cnt
                FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
                WHERE start_time >= DATEADD(day, -1, CURRENT_TIMESTAMP())
                  AND error_code IS NOT NULL
                GROUP BY 1,2,3,4 ORDER BY cnt DESC LIMIT 20
            """)
            if not query_errors.empty:
                st.dataframe(query_errors, use_container_width=True)
            else:
                st.success("✅ Aucune erreur de requête détectée sur les dernières 24h")

        st.subheader("Percentiles de durée des requêtes — P50 / P95 / P99 (7 jours)")
        query_perf = run_query("""
            SELECT DATE_TRUNC('day', start_time)::DATE AS jour,
                   ROUND(AVG(total_elapsed_time)/1000, 1)                                            AS avg_sec,
                   ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY total_elapsed_time)/1000, 1)   AS p50_sec,
                   ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_elapsed_time)/1000, 1)   AS p95_sec,
                   ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY total_elapsed_time)/1000, 1)   AS p99_sec,
                   COUNT(*) AS nb_queries
            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
            WHERE start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
              AND execution_status = 'SUCCESS'
            GROUP BY 1 ORDER BY 1
        """)
        if not query_perf.empty:
            melt = query_perf.melt(id_vars=['JOUR', 'NB_QUERIES'],
                                   value_vars=['AVG_SEC', 'P50_SEC', 'P95_SEC', 'P99_SEC'],
                                   var_name='Métrique', value_name='Secondes')
            st.altair_chart(
                alt.Chart(melt).mark_line(point=True).encode(
                    x=alt.X('JOUR:T', title='Date'),
                    y=alt.Y('Secondes:Q', title='Durée (s)'),
                    color=alt.Color('Métrique:N'),
                    tooltip=['JOUR:T', 'Métrique:N', 'Secondes:Q']
                ).properties(height=300, title='Durée des requêtes réussies (P50 / P95 / P99)'),
                use_container_width=True
            )

        col3, col4 = st.columns(2)
        with col3:
            st.subheader("Top 10 requêtes les plus longues (7j)")
            slow = run_query("""
                SELECT user_name, warehouse_name,
                       ROUND(total_elapsed_time/1000, 1) AS duration_sec,
                       ROUND(bytes_spilled_to_local_storage /1024/1024, 1) AS spill_local_mb,
                       ROUND(bytes_spilled_to_remote_storage/1024/1024, 1) AS spill_remote_mb,
                       ROUND(credits_used_cloud_services, 5)               AS cloud_credits,
                       LEFT(query_text, 100)                               AS query_preview
                FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
                WHERE start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
                  AND warehouse_name IS NOT NULL
                ORDER BY total_elapsed_time DESC LIMIT 10
            """)
            if not slow.empty:
                st.dataframe(slow, use_container_width=True)

        with col4:
            st.subheader("Top utilisateurs par volume de requêtes (7j)")
            usr_act = run_query("""
                SELECT user_name, COUNT(*) AS nb_queries,
                       ROUND(AVG(total_elapsed_time)/1000, 1) AS avg_sec,
                       ROUND(SUM(bytes_scanned)/POWER(1024,3), 2) AS total_gb_scanned,
                       SUM(CASE WHEN error_code IS NOT NULL THEN 1 ELSE 0 END) AS errors
                FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
                WHERE start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
                GROUP BY user_name ORDER BY nb_queries DESC LIMIT 15
            """)
            if not usr_act.empty:
                st.dataframe(usr_act, use_container_width=True)

        st.subheader("Heatmap d'activité — Requêtes par heure / jour (7 derniers jours)")
        hm_data = run_query("""
            SELECT DAYOFWEEK(start_time) AS dow, HOUR(start_time) AS heure, COUNT(*) AS nb
            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
            WHERE start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
            GROUP BY 1, 2
        """)
        if not hm_data.empty:
            day_map = {1: 'Lun', 2: 'Mar', 3: 'Mer', 4: 'Jeu', 5: 'Ven', 6: 'Sam', 0: 'Dim'}
            hm_data['JOUR'] = hm_data['DOW'].map(day_map)
            st.altair_chart(
                alt.Chart(hm_data).mark_rect().encode(
                    x=alt.X('HEURE:O', title='Heure'),
                    y=alt.Y('JOUR:O', title='Jour', sort=['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']),
                    color=alt.Color('NB:Q', scale=alt.Scale(scheme='blues'), title='Requêtes'),
                    tooltip=['JOUR:O', 'HEURE:O', 'NB:Q']
                ).properties(height=200, title='Activité par heure (7j)'),
                use_container_width=True
            )

    # ═══════════════════════════════════════════════════════════════
    # TAB 3 – SÉCURITÉ
    # ═══════════════════════════════════════════════════════════════
    with tab_sec:
        st.header("Audit de Sécurité")
        col1, col2, col3 = st.columns(3)

        users_df = run_query("""
            SELECT COUNT(*)                                                                     AS total_users,
                   SUM(CASE WHEN has_password      = 'true' THEN 1 ELSE 0 END)                AS with_password,
                   SUM(CASE WHEN has_rsa_public_key= 'true' THEN 1 ELSE 0 END)                AS with_keypair,
                   SUM(CASE WHEN ext_authn_duo      = 'true' THEN 1 ELSE 0 END)               AS with_mfa,
                   SUM(CASE WHEN disabled           = 'true' THEN 1 ELSE 0 END)               AS disabled_users,
                   SUM(CASE WHEN last_success_login < DATEADD(day,-30,CURRENT_TIMESTAMP())
                              OR last_success_login IS NULL THEN 1 ELSE 0 END)                 AS inactive_30d
            FROM SNOWFLAKE.ACCOUNT_USAGE.USERS
            WHERE deleted_on IS NULL
        """)
        if not users_df.empty:
            with col1:
                st.metric("Utilisateurs totaux", int(users_df['TOTAL_USERS'].iloc[0]))
                st.metric("Avec MFA", int(users_df['WITH_MFA'].iloc[0]))
            with col2:
                st.metric("Avec mot de passe", int(users_df['WITH_PASSWORD'].iloc[0]))
                st.metric("Inactifs (30j)", int(users_df['INACTIVE_30D'].iloc[0]))
            with col3:
                st.metric("Avec keypair RSA", int(users_df['WITH_KEYPAIR'].iloc[0]))
                st.metric("Désactivés", int(users_df['DISABLED_USERS'].iloc[0]))

        st.subheader("🚨 Utilisateurs privilégiés sans MFA")
        priv_no_mfa = run_query("""
            SELECT DISTINCT u.name AS user_name, u.email, u.default_role,
                   u.last_success_login, u.has_password, gtu.role AS privileged_role
            FROM SNOWFLAKE.ACCOUNT_USAGE.USERS u
            JOIN SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS gtu ON gtu.grantee_name = u.name
            WHERE u.deleted_on IS NULL AND u.disabled = 'false' AND u.ext_authn_duo = 'false'
              AND gtu.role IN ('ACCOUNTADMIN','SYSADMIN','SECURITYADMIN') AND gtu.deleted_on IS NULL
            ORDER BY privileged_role, user_name
        """)
        if not priv_no_mfa.empty:
            st.error(f"🚨 {len(priv_no_mfa)} utilisateur(s) avec rôle privilégié mais SANS MFA !")
            st.dataframe(priv_no_mfa, use_container_width=True)
        else:
            st.success("✅ Tous les utilisateurs privilégiés ont le MFA activé")

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Connexions échouées (7 derniers jours)")
            failed_logins = run_query("""
                SELECT DATE_TRUNC('day', event_timestamp)::DATE AS date,
                       user_name, reported_client_type, client_ip, error_message, COUNT(*) AS attempts
                FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
                WHERE is_success = 'NO' AND event_timestamp >= DATEADD(day, -7, CURRENT_TIMESTAMP())
                GROUP BY 1,2,3,4,5 ORDER BY attempts DESC LIMIT 30
            """)
            if not failed_logins.empty:
                st.dataframe(failed_logins, use_container_width=True)
            else:
                st.success("✅ Aucune connexion échouée sur les 7 derniers jours")

        with col_b:
            st.subheader("Connexions réussies par client (7j)")
            login_clients = run_query("""
                SELECT reported_client_type, COUNT(*) AS connexions, COUNT(DISTINCT user_name) AS utilisateurs
                FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
                WHERE is_success = 'YES' AND event_timestamp >= DATEADD(day, -7, CURRENT_TIMESTAMP())
                GROUP BY 1 ORDER BY connexions DESC
            """)
            if not login_clients.empty:
                st.dataframe(login_clients, use_container_width=True)

        st.subheader("Network Policies")
        network_policies = run_query("""
            SELECT name, owner, comment, allowed_ip_list, blocked_ip_list
            FROM SNOWFLAKE.ACCOUNT_USAGE.NETWORK_POLICIES
        """)
        if not network_policies.empty:
            st.dataframe(network_policies, use_container_width=True)
        else:
            st.warning("⚠️ Aucune network policy configurée — Fortement recommandé pour restreindre les accès par IP")

        st.subheader("Partages de données sortants (Outbound Shares)")
        outbound_shares = run_query("""
            SELECT name AS share_name, owner, comment FROM SNOWFLAKE.ACCOUNT_USAGE.SHARES
        """)
        if not outbound_shares.empty:
            st.warning(f"⚠️ {len(outbound_shares)} partage(s) de données configuré(s) — Vérifiez qu'ils sont intentionnels")
            st.dataframe(outbound_shares, use_container_width=True)
        else:
            st.info("ℹ️ Aucun partage de données configuré")

        col_c, col_d = st.columns(2)
        with col_c:
            st.subheader("Masking Policies (Protection PII)")
            masking = run_query("""
                SELECT policy_name, created, policy_owner
                FROM SNOWFLAKE.ACCOUNT_USAGE.MASKING_POLICIES WHERE deleted IS NULL ORDER BY created DESC
            """)
            if not masking.empty:
                st.success(f"✅ {len(masking)} masking polic(ies) configurée(s)")
                st.dataframe(masking, use_container_width=True)
            else:
                st.warning("ℹ️ Aucune masking policy — Recommandé pour la protection des données PII/sensibles")

        with col_d:
            st.subheader("Row Access Policies")
            row_policies = run_query("""
                SELECT policy_name, created, policy_owner
                FROM SNOWFLAKE.ACCOUNT_USAGE.ROW_ACCESS_POLICIES WHERE deleted IS NULL
            """)
            if not row_policies.empty:
                st.success(f"✅ {len(row_policies)} row access polic(ies) configurée(s)")
                st.dataframe(row_policies, use_container_width=True)
            else:
                st.info("ℹ️ Aucune row access policy configurée")

    # ═══════════════════════════════════════════════════════════════
    # TAB 4 – WAREHOUSES
    # ═══════════════════════════════════════════════════════════════
    with tab_wh:
        st.header("Warehouses — Dimensionnement & Performance")

        st.subheader("Configuration des Warehouses")
        wh_config = get_warehouse_config()
        if not wh_config.empty:
            wh_config['AUTO_SUSPEND_EVAL'] = wh_config['AUTO_SUSPEND'].apply(
                lambda x: '✅ ≤5 min' if pd.notna(x) and x <= 300
                          else '⚠️ ≤10 min' if pd.notna(x) and x <= 600
                          else '🔴 Trop long' if pd.notna(x)
                          else '❌ Désactivé'
            )
            wh_config['MULTI_CLUSTER'] = wh_config.apply(
                lambda r: f"✅ {int(r['MIN_CLUSTER_COUNT'])}-{int(r['MAX_CLUSTER_COUNT'])}"
                          if r['MAX_CLUSTER_COUNT'] > 1 else "—", axis=1
            )
            st.dataframe(
                wh_config[['NAME', 'SIZE', 'TYPE', 'STATE', 'AUTO_SUSPEND', 'AUTO_SUSPEND_EVAL',
                            'AUTO_RESUME', 'MULTI_CLUSTER', 'SCALING_POLICY', 'OWNER']],
                use_container_width=True
            )

        st.subheader("Consommation de crédits par Warehouse (30 jours)")
        wh_usage = run_query("""
            SELECT warehouse_name,
                   ROUND(SUM(credits_used), 2)  AS total_credits,
                   ROUND(AVG(credits_used), 4)  AS avg_credits_per_hour,
                   COUNT(DISTINCT DATE_TRUNC('day', start_time)) AS days_active
            FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
            WHERE start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
            GROUP BY warehouse_name ORDER BY total_credits DESC
        """)
        if not wh_usage.empty:
            st.altair_chart(
                alt.Chart(wh_usage).mark_bar().encode(
                    x=alt.X('TOTAL_CREDITS:Q', title='Crédits consommés'),
                    y=alt.Y('WAREHOUSE_NAME:N', sort='-x', title='Warehouse'),
                    color=alt.Color('WAREHOUSE_NAME:N', legend=None),
                    tooltip=['WAREHOUSE_NAME:N', 'TOTAL_CREDITS:Q', 'AVG_CREDITS_PER_HOUR:Q', 'DAYS_ACTIVE:Q']
                ).properties(height=max(200, len(wh_usage) * 35), title='Consommation par Warehouse (30j)'),
                use_container_width=True
            )

        st.subheader("Analyse de charge & Recommandations de dimensionnement (30j)")
        wh_load_agg = run_query("""
            SELECT warehouse_name,
                   ROUND(AVG(avg_running), 3)                                    AS avg_running,
                   ROUND(AVG(avg_queued_load), 3)                                AS avg_queued,
                   ROUND(MAX(avg_queued_load), 3)                                AS max_queued,
                   ROUND(AVG(avg_blocked), 3)                                    AS avg_blocked,
                   SUM(CASE WHEN avg_queued_load > 0 THEN 1 ELSE 0 END)         AS periodes_avec_queue,
                   COUNT(*)                                                       AS total_periodes
            FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_LOAD_HISTORY
            WHERE start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
            GROUP BY warehouse_name ORDER BY avg_queued DESC
        """)
        if not wh_load_agg.empty:
            def sizing_rec(row):
                q_pct = (row['PERIODES_AVEC_QUEUE'] / row['TOTAL_PERIODES'] * 100) if row['TOTAL_PERIODES'] > 0 else 0
                if row['MAX_QUEUED'] > 1:
                    return f"🔴 Scale up / Multi-cluster (queue max={row['MAX_QUEUED']:.1f})"
                elif row['AVG_QUEUED'] > 0.2:
                    return f"🟠 Taille à revoir ({q_pct:.0f}% du temps en queue)"
                elif row['AVG_RUNNING'] < 0.1 and row['AVG_QUEUED'] == 0:
                    return "🔵 Potentiellement surdimensionné (charge très faible)"
                return "🟢 Dimensionnement adapté"

            wh_load_agg['RECOMMANDATION'] = wh_load_agg.apply(sizing_rec, axis=1)
            st.dataframe(
                wh_load_agg[['WAREHOUSE_NAME', 'AVG_RUNNING', 'AVG_QUEUED', 'MAX_QUEUED',
                              'PERIODES_AVEC_QUEUE', 'RECOMMANDATION']],
                use_container_width=True
            )

        st.subheader("Spilling — Indicateur de sous-dimensionnement mémoire (30j)")
        spilling = run_query("""
            SELECT warehouse_name,
                   COUNT(*) AS nb_queries_avec_spill,
                   ROUND(SUM(bytes_spilled_to_local_storage) /POWER(1024,3), 2) AS spill_local_gb,
                   ROUND(SUM(bytes_spilled_to_remote_storage)/POWER(1024,3), 2) AS spill_remote_gb,
                   ROUND(AVG(total_elapsed_time)/1000, 1) AS avg_duration_sec
            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
            WHERE start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
              AND (bytes_spilled_to_local_storage > 0 OR bytes_spilled_to_remote_storage > 0)
              AND warehouse_name IS NOT NULL
            GROUP BY warehouse_name ORDER BY spill_remote_gb DESC, spill_local_gb DESC
        """)
        if not spilling.empty:
            st.warning("⚠️ Du spilling détecté — Ces warehouses ont des requêtes qui dépassent la mémoire disponible")
            st.dataframe(spilling, use_container_width=True)
            st.caption("Spilling local = disque local (modéré). Spilling remote = très coûteux en performance → scale up recommandé.")
        else:
            st.success("✅ Aucun spilling remote détecté sur les 30 derniers jours — Dimensionnement mémoire correct")

        st.subheader("Auto-suspend — Évaluation par Warehouse")
        if not wh_config.empty:
            idle_eval = wh_config[['NAME', 'SIZE', 'AUTO_SUSPEND']].copy()
            idle_eval.rename(columns={'NAME': 'WAREHOUSE_NAME', 'AUTO_SUSPEND': 'AUTO_SUSPEND_SEC'}, inplace=True)

            def _as_eval(v):
                if pd.isna(v) or v is None:
                    return '❌ Désactivé — gaspillage de crédits'
                v = int(v)
                if v <= 60:  return '✅ Agressif (≤1 min)'
                if v <= 300: return '✅ Recommandé (≤5 min)'
                if v <= 600: return '⚠️ Modéré (≤10 min)'
                return f'🔴 Trop long ({v} s) — optimisation recommandée'

            idle_eval['EVALUATION'] = idle_eval['AUTO_SUSPEND_SEC'].apply(_as_eval)
            idle_eval.sort_values('AUTO_SUSPEND_SEC', ascending=False, na_position='first', inplace=True)
            st.dataframe(idle_eval, use_container_width=True)

        st.subheader("Charge détaillée d'un Warehouse (7 jours)")
        if not wh_load_agg.empty:
            selected_wh = st.selectbox("Sélectionner un warehouse", wh_load_agg['WAREHOUSE_NAME'].unique(), key="compliance_wh_sel")
            wh_ts = run_query(f"""
                SELECT DATE_TRUNC('hour', start_time) AS heure,
                       AVG(avg_running) AS running, AVG(avg_queued_load) AS queued, AVG(avg_blocked) AS blocked
                FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_LOAD_HISTORY
                WHERE warehouse_name = '{selected_wh}'
                  AND start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
                GROUP BY 1 ORDER BY heure
            """)
            if not wh_ts.empty:
                melt_ts = wh_ts.melt(id_vars=['HEURE'], value_vars=['RUNNING', 'QUEUED', 'BLOCKED'],
                                     var_name='Métrique', value_name='Valeur')
                st.altair_chart(
                    alt.Chart(melt_ts).mark_line().encode(
                        x=alt.X('HEURE:T', title='Heure'),
                        y=alt.Y('Valeur:Q', title='Charge'),
                        color=alt.Color('Métrique:N'),
                        tooltip=['HEURE:T', 'Métrique:N', 'Valeur:Q']
                    ).properties(height=300, title=f'Charge du warehouse {selected_wh} (7j)'),
                    use_container_width=True
                )
                avg_q = wh_ts['QUEUED'].mean()
                if avg_q > 0.5:
                    st.warning(f"⚠️ Queue élevée en moyenne ({avg_q:.2f}) — Envisagez un scale-up ou l'activation du mode multi-cluster")

    # ═══════════════════════════════════════════════════════════════
    # TAB 5 – FINOPS
    # ═══════════════════════════════════════════════════════════════
    with tab_finops:
        st.header("FinOps — Analyse et Optimisation des Coûts")
        col1, col2, col3, col4 = st.columns(4)

        fin_summary = run_query("""
            SELECT ROUND(SUM(CASE WHEN start_time >= DATE_TRUNC('month', CURRENT_DATE())
                                   THEN credits_used END), 2) AS credits_this_month,
                   ROUND(SUM(CASE WHEN start_time >= DATE_TRUNC('month', DATEADD(month,-1,CURRENT_DATE()))
                                  AND start_time  <  DATE_TRUNC('month', CURRENT_DATE())
                                   THEN credits_used END), 2) AS credits_last_month,
                   ROUND(SUM(CASE WHEN start_time >= DATEADD(day,-7, CURRENT_TIMESTAMP())
                                   THEN credits_used END), 2) AS credits_7d
            FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
            WHERE start_time >= DATE_TRUNC('month', DATEADD(month,-1,CURRENT_DATE()))
        """)
        storage_costs = run_query("""
            SELECT ROUND(AVG(storage_bytes)  / POWER(1024,4), 3) AS table_tb,
                   ROUND(AVG(stage_bytes)    / POWER(1024,4), 3) AS stage_tb,
                   ROUND(AVG(failsafe_bytes) / POWER(1024,4), 3) AS failsafe_tb
            FROM SNOWFLAKE.ACCOUNT_USAGE.STORAGE_USAGE
            WHERE usage_date >= DATEADD(day,-7, CURRENT_DATE())
        """)
        if not fin_summary.empty:
            cur_m  = fin_summary['CREDITS_THIS_MONTH'].iloc[0] or 0
            prev_m = fin_summary['CREDITS_LAST_MONTH'].iloc[0] or 0
            w7     = fin_summary['CREDITS_7D'].iloc[0] or 0
            delta  = ((cur_m - prev_m) / prev_m * 100) if prev_m and prev_m > 0 else None
            with col1:
                st.metric("Crédits ce mois", fmt_credits(cur_m),
                          delta=f"{delta:+.1f}% vs mois préc." if delta else None, delta_color="inverse")
            with col2:
                st.metric("Crédits mois préc.", fmt_credits(prev_m))
            with col3:
                st.metric("Crédits (7 derniers jours)", fmt_credits(w7))
            with col4:
                if not storage_costs.empty:
                    total_tb = sum(filter(None, [storage_costs['TABLE_TB'].iloc[0],
                                                 storage_costs['STAGE_TB'].iloc[0],
                                                 storage_costs['FAILSAFE_TB'].iloc[0]]))
                    st.metric("Stockage total (TB)", f"{total_tb:.3f}")

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Crédits par type de service (30 jours)")
            svc_credits = run_query("""
                SELECT service_type,
                       ROUND(SUM(credits_used), 2) AS credits,
                       ROUND(SUM(credits_used)*100.0 / SUM(SUM(credits_used)) OVER (), 1) AS pct
                FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
                WHERE start_time >= DATEADD(day,-30, CURRENT_TIMESTAMP())
                GROUP BY service_type ORDER BY credits DESC
            """)
            if not svc_credits.empty:
                st.altair_chart(
                    alt.Chart(svc_credits).mark_arc(innerRadius=50).encode(
                        theta=alt.Theta('CREDITS:Q'),
                        color=alt.Color('SERVICE_TYPE:N', legend=alt.Legend(title='Service')),
                        tooltip=['SERVICE_TYPE:N', 'CREDITS:Q', 'PCT:Q']
                    ).properties(height=260),
                    use_container_width=True
                )
                st.dataframe(svc_credits, use_container_width=True)

        with col_b:
            st.subheader("Répartition du stockage (7j moyen)")
            if not storage_costs.empty:
                stor_df = pd.DataFrame({
                    'Type': ['Tables', 'Stages', 'Fail-safe'],
                    'TB':   [storage_costs['TABLE_TB'].iloc[0] or 0,
                             storage_costs['STAGE_TB'].iloc[0] or 0,
                             storage_costs['FAILSAFE_TB'].iloc[0] or 0]
                })
                st.altair_chart(
                    alt.Chart(stor_df).mark_arc(innerRadius=50).encode(
                        theta=alt.Theta('TB:Q'),
                        color=alt.Color('Type:N'),
                        tooltip=['Type:N', 'TB:Q']
                    ).properties(height=200),
                    use_container_width=True
                )
                st.dataframe(stor_df, use_container_width=True)

        st.subheader("Resource Monitors — Budget vs Consommation")
        rm_df = run_query("""
            SELECT name, credit_quota, used_credits, remaining_credits,
                   ROUND(used_credits / NULLIF(credit_quota,0) * 100, 1) AS pct_used, owner
            FROM SNOWFLAKE.ACCOUNT_USAGE.RESOURCE_MONITORS ORDER BY pct_used DESC NULLS LAST
        """)
        if not rm_df.empty:
            rm_df['ALERTE'] = rm_df['PCT_USED'].apply(
                lambda x: '🔴 Critique'    if x and x >= 90
                          else '🟠 À surveiller' if x and x >= 70
                          else '🟢 OK'
            )
            st.dataframe(rm_df[['NAME', 'CREDIT_QUOTA', 'USED_CREDITS', 'REMAINING_CREDITS',
                                 'PCT_USED', 'ALERTE', 'OWNER']], use_container_width=True)
        else:
            st.warning("⚠️ Aucun Resource Monitor configuré — Indispensable pour contrôler les dépenses et éviter les surprises en fin de mois")

        col_c, col_d = st.columns(2)
        with col_c:
            st.subheader("Top utilisateurs par cloud services crédits (30j)")
            user_credits = run_query("""
                SELECT user_name, COUNT(*) AS nb_queries,
                       ROUND(SUM(credits_used_cloud_services), 4) AS cloud_credits,
                       ROUND(AVG(total_elapsed_time)/1000, 1) AS avg_duration_sec,
                       ROUND(SUM(bytes_scanned)/POWER(1024,3), 2) AS total_gb_scanned
                FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
                WHERE start_time >= DATEADD(day,-30, CURRENT_TIMESTAMP()) AND user_name IS NOT NULL
                GROUP BY user_name ORDER BY cloud_credits DESC LIMIT 15
            """)
            if not user_credits.empty:
                st.dataframe(user_credits, use_container_width=True)

        with col_d:
            st.subheader("Top Warehouses par coûts (30j)")
            wh_costs = run_query("""
                SELECT warehouse_name,
                       ROUND(SUM(credits_used), 2) AS total_credits,
                       COUNT(DISTINCT DATE_TRUNC('day', start_time)) AS jours_actifs,
                       ROUND(SUM(credits_used)/NULLIF(COUNT(DISTINCT DATE_TRUNC('day',start_time)),0), 2) AS credits_par_jour
                FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
                WHERE start_time >= DATEADD(day,-30, CURRENT_TIMESTAMP())
                GROUP BY warehouse_name ORDER BY total_credits DESC
            """)
            if not wh_costs.empty:
                st.altair_chart(
                    alt.Chart(wh_costs).mark_bar().encode(
                        x=alt.X('WAREHOUSE_NAME:N', sort='-y', title='Warehouse'),
                        y=alt.Y('TOTAL_CREDITS:Q', title='Crédits'),
                        color=alt.Color('WAREHOUSE_NAME:N', legend=None),
                        tooltip=['WAREHOUSE_NAME:N', 'TOTAL_CREDITS:Q', 'CREDITS_PAR_JOUR:Q']
                    ).properties(height=260),
                    use_container_width=True
                )

        st.subheader("Top 10 requêtes les plus coûteuses en cloud services (7j)")
        top_queries = run_query("""
            SELECT query_id, user_name, warehouse_name,
                   ROUND(total_elapsed_time/1000, 1) AS duration_sec,
                   ROUND(credits_used_cloud_services, 5) AS cloud_credits,
                   ROUND(bytes_scanned/POWER(1024,3), 2) AS gb_scanned,
                   LEFT(query_text, 120) AS query_preview
            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
            WHERE start_time >= DATEADD(day,-7, CURRENT_TIMESTAMP()) AND warehouse_name IS NOT NULL
            ORDER BY credits_used_cloud_services DESC LIMIT 10
        """)
        if not top_queries.empty:
            st.dataframe(top_queries, use_container_width=True)

    # ═══════════════════════════════════════════════════════════════
    # TAB 6 – GOUVERNANCE & CONFORMITÉ
    # ═══════════════════════════════════════════════════════════════
    with tab_gov:
        st.header("Gouvernance & Conformité — RBAC & Best Practices")
        sub_rbac, sub_compliance = st.tabs(["👥 RBAC", "✅ Audit de Conformité"])

        # ── Sous-onglet RBAC ──────────────────────────────────────
        with sub_rbac:
            col1, col2 = st.columns(2)
            with col1:
                roles_df = run_query("""
                    SELECT name AS role_name, created_on, comment
                    FROM SNOWFLAKE.ACCOUNT_USAGE.ROLES WHERE deleted_on IS NULL ORDER BY created_on DESC
                """)
                if not roles_df.empty:
                    st.metric("Nombre de rôles", len(roles_df))
                    st.subheader("Liste des rôles")
                    st.dataframe(roles_df, use_container_width=True)

            with col2:
                st.subheader("Utilisateurs avec ACCOUNTADMIN")
                accountadmins = run_query("""
                    SELECT grantee_name AS user_name, created_on AS granted_on, granted_by
                    FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS
                    WHERE role = 'ACCOUNTADMIN' AND deleted_on IS NULL
                """)
                if not accountadmins.empty:
                    if len(accountadmins) > 3:
                        st.warning(f"⚠️ {len(accountadmins)} utilisateurs avec ACCOUNTADMIN — Snowflake recommande max 3")
                    else:
                        st.success(f"✅ {len(accountadmins)} utilisateurs avec ACCOUNTADMIN")
                    st.dataframe(accountadmins, use_container_width=True)

                st.subheader("SYSADMIN & SECURITYADMIN")
                priv_roles = run_query("""
                    SELECT grantee_name AS user_name, role, created_on AS granted_on, granted_by
                    FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS
                    WHERE role IN ('SYSADMIN','SECURITYADMIN') AND deleted_on IS NULL
                    ORDER BY role, user_name
                """)
                if not priv_roles.empty:
                    st.dataframe(priv_roles, use_container_width=True)

            st.subheader("Grants récents (7 jours)")
            recent_grants = run_query("""
                SELECT created_on, privilege, granted_on AS object_type,
                       name AS object_name, grantee_name AS granted_to, granted_by
                FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
                WHERE created_on >= DATEADD(day,-7, CURRENT_TIMESTAMP()) AND deleted_on IS NULL
                ORDER BY created_on DESC LIMIT 50
            """)
            if not recent_grants.empty:
                st.dataframe(recent_grants, use_container_width=True)
            else:
                st.info("Aucun nouveau grant ces 7 derniers jours")

            st.subheader("Utilisateurs actifs sans connexion depuis 90 jours")
            stale_users = run_query("""
                SELECT name, email, default_role, last_success_login,
                       DATEDIFF('day', last_success_login, CURRENT_DATE()) AS days_since_login,
                       has_password, ext_authn_duo AS has_mfa
                FROM SNOWFLAKE.ACCOUNT_USAGE.USERS
                WHERE deleted_on IS NULL AND disabled = 'false'
                  AND (last_success_login < DATEADD(day,-90, CURRENT_TIMESTAMP()) OR last_success_login IS NULL)
                ORDER BY last_success_login ASC NULLS FIRST LIMIT 30
            """)
            if not stale_users.empty:
                st.warning(f"⚠️ {len(stale_users)} utilisateur(s) inactifs depuis > 90 jours — À désactiver")
                st.dataframe(stale_users, use_container_width=True)
            else:
                st.success("✅ Aucun utilisateur inactif depuis plus de 90 jours")

        # ── Sous-onglet Conformité ────────────────────────────────
        with sub_compliance:
            st.subheader("Score de Conformité — Snowflake Best Practices")
            checks = []

            mfa_chk = run_query("""
                SELECT COUNT(*) AS total, SUM(CASE WHEN ext_authn_duo = 'true' THEN 1 ELSE 0 END) AS with_mfa
                FROM SNOWFLAKE.ACCOUNT_USAGE.USERS WHERE deleted_on IS NULL AND disabled = 'false'
            """)
            if not mfa_chk.empty and mfa_chk['TOTAL'].iloc[0] > 0:
                pct = mfa_chk['WITH_MFA'].iloc[0] / mfa_chk['TOTAL'].iloc[0] * 100
                checks.append({'Catégorie': 'Sécurité', 'Contrôle': 'MFA activé pour les utilisateurs',
                               'Statut': '✅ OK' if pct > 80 else '⚠️ À améliorer' if pct > 50 else '❌ Critique',
                               'Détails': f"{pct:.1f}% des utilisateurs actifs avec MFA"})

            np_chk = run_query("SELECT COUNT(*) AS cnt FROM SNOWFLAKE.ACCOUNT_USAGE.NETWORK_POLICIES")
            if not np_chk.empty:
                checks.append({'Catégorie': 'Sécurité', 'Contrôle': 'Network Policy configurée',
                               'Statut': '✅ OK' if np_chk['CNT'].iloc[0] > 0 else '❌ Manquante',
                               'Détails': f"{np_chk['CNT'].iloc[0]} network policy(ies)"})

            pnm_chk = run_query("""
                SELECT COUNT(DISTINCT u.name) AS cnt
                FROM SNOWFLAKE.ACCOUNT_USAGE.USERS u
                JOIN SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS gtu ON gtu.grantee_name = u.name
                WHERE u.deleted_on IS NULL AND u.disabled='false' AND u.ext_authn_duo='false'
                  AND gtu.role IN ('ACCOUNTADMIN','SYSADMIN','SECURITYADMIN') AND gtu.deleted_on IS NULL
            """)
            if not pnm_chk.empty:
                cnt = pnm_chk['CNT'].iloc[0]
                checks.append({'Catégorie': 'Sécurité', 'Contrôle': 'Admins privilégiés sans MFA',
                               'Statut': '✅ OK' if cnt == 0 else '❌ Critique',
                               'Détails': f"{cnt} admin(s) privilégié(s) sans MFA"})

            aa_cnt = len(accountadmins) if not accountadmins.empty else 0
            checks.append({'Catégorie': 'RBAC', 'Contrôle': "Nombre limité d'ACCOUNTADMIN",
                           'Statut': '✅ OK' if aa_cnt <= 3 else '⚠️ À revoir',
                           'Détails': f"{aa_cnt} utilisateur(s) avec ACCOUNTADMIN (max recommandé: 3)"})

            rm_chk = run_query("SELECT COUNT(*) AS cnt FROM SNOWFLAKE.ACCOUNT_USAGE.RESOURCE_MONITORS")
            if not rm_chk.empty:
                checks.append({'Catégorie': 'FinOps', 'Contrôle': 'Resource Monitors configurés',
                               'Statut': '✅ OK' if rm_chk['CNT'].iloc[0] > 0 else '⚠️ Recommandé',
                               'Détails': f"{rm_chk['CNT'].iloc[0]} resource monitor(s)"})

            _wh_cfg_chk = get_warehouse_config()
            if not _wh_cfg_chk.empty:
                cnt = int(_wh_cfg_chk[
                    _wh_cfg_chk['AUTO_SUSPEND'].isna() | (_wh_cfg_chk['AUTO_SUSPEND'] > 600)
                ].shape[0])
                checks.append({'Catégorie': 'Warehouse', 'Contrôle': 'Auto-suspend ≤ 10 min sur tous les WH',
                               'Statut': '✅ OK' if cnt == 0 else f'⚠️ {cnt} WH(s) à configurer',
                               'Détails': f"{cnt} warehouse(s) sans auto-suspend ou auto-suspend > 600s"})

            sc_chk = run_query("""
                SELECT COUNT(*) AS cnt FROM SNOWFLAKE.ACCOUNT_USAGE.USERS
                WHERE deleted_on IS NULL AND disabled='false'
                  AND (last_success_login < DATEADD(day,-90,CURRENT_TIMESTAMP()) OR last_success_login IS NULL)
            """)
            if not sc_chk.empty:
                cnt = sc_chk['CNT'].iloc[0]
                checks.append({'Catégorie': 'RBAC', 'Contrôle': 'Utilisateurs inactifs (90j+)',
                               'Statut': '✅ OK' if cnt == 0 else '⚠️ À nettoyer',
                               'Détails': f"{cnt} utilisateur(s) inactif(s) à désactiver"})

            mp_chk = run_query("SELECT COUNT(*) AS cnt FROM SNOWFLAKE.ACCOUNT_USAGE.MASKING_POLICIES WHERE deleted IS NULL")
            if not mp_chk.empty:
                checks.append({'Catégorie': 'Protection données', 'Contrôle': 'Masking Policies (PII)',
                               'Statut': '✅ OK' if mp_chk['CNT'].iloc[0] > 0 else 'ℹ️ À évaluer',
                               'Détails': f"{mp_chk['CNT'].iloc[0]} masking policy(ies)"})

            rap_chk = run_query("SELECT COUNT(*) AS cnt FROM SNOWFLAKE.ACCOUNT_USAGE.ROW_ACCESS_POLICIES WHERE deleted IS NULL")
            if not rap_chk.empty:
                checks.append({'Catégorie': 'Protection données', 'Contrôle': 'Row Access Policies',
                               'Statut': '✅ OK' if rap_chk['CNT'].iloc[0] > 0 else 'ℹ️ À évaluer',
                               'Détails': f"{rap_chk['CNT'].iloc[0]} row access policy(ies)"})

            sp_chk = run_query("""
                SELECT COUNT(DISTINCT warehouse_name) AS cnt
                FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
                WHERE start_time >= DATEADD(day,-30,CURRENT_TIMESTAMP())
                  AND bytes_spilled_to_remote_storage > 0
            """)
            if not sp_chk.empty:
                cnt = sp_chk['CNT'].iloc[0]
                checks.append({'Catégorie': 'Warehouse', 'Contrôle': 'Spilling remote (sous-dimensionnement mémoire)',
                               'Statut': '✅ OK' if cnt == 0 else f'🔴 {cnt} WH(s) concerné(s)',
                               'Détails': f"{cnt} warehouse(s) avec spilling remote storage (30j)"})

            if checks:
                df_checks = pd.DataFrame(checks)
                ok_cnt   = sum(1 for c in checks if '✅' in c['Statut'])
                warn_cnt = sum(1 for c in checks if '⚠️' in c['Statut'] or 'ℹ️' in c['Statut'])
                crit_cnt = sum(1 for c in checks if '❌' in c['Statut'] or '🔴' in c['Statut'])
                total    = len(checks)

                mc1, mc2, mc3, mc4 = st.columns(4)
                with mc1: st.metric("Score global", f"{ok_cnt}/{total}")
                with mc2: st.metric("✅ Conformes", ok_cnt)
                with mc3: st.metric("⚠️ À améliorer", warn_cnt)
                with mc4: st.metric("❌ Critiques", crit_cnt)

                st.progress(ok_cnt / total)
                st.divider()

                for cat in df_checks['Catégorie'].unique():
                    st.markdown(f"**{cat}**")
                    cat_df = df_checks[df_checks['Catégorie'] == cat][['Contrôle', 'Statut', 'Détails']]
                    st.dataframe(cat_df, use_container_width=True)

    st.markdown("""
    <div style="text-align:center; color:#8aa8b8; font-size:0.78rem; padding:12px 0 4px 0;">
      ❄️ <strong>Snowflake Governance Dashboard</strong>
      &nbsp;·&nbsp; Données <code>ACCOUNT_USAGE</code> (latence ~2h)
      &nbsp;·&nbsp; Toutes les vues sont en lecture seule
    </div>
    """, unsafe_allow_html=True)
