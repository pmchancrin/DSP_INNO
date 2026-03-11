# ============================================================
# SNOWSLED
# Création et mise à jour des objets de données
# ============================================================

import streamlit as st
import pandas as pd
import sys
import os

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
    page_title="Snowsled",
    page_icon="🛷",
    layout="wide",
)

# ── Session Snowflake (Snowflake natif ou connexion locale) ──
session = get_session()

# ── Helpers ──────────────────────────────────────────────────
def run_sql(query: str, success_msg: str = None, echo: bool = False) -> bool:
    try:
        if echo:
            with st.expander("SQL exécuté"):
                st.code(query, language="sql")
        session.sql(query).collect()
        if success_msg:
            st.success(success_msg)
        return True
    except Exception as e:
        st.error(f"Erreur SQL : {e}")
        return False


def load_projects():
    return session.sql("""
        SELECT PROJECT_ID, PROJECT_NAME, DSI_DB, DSO_DB, WH_SIZE, STATUS
        FROM CONFIG_SCHEMA.PROJECTS
        WHERE STATUS = 'ACTIVE'
        ORDER BY PROJECT_NAME
    """).to_pandas()


def load_objects(project_id: str = None, layer: str = None):
    where = []
    if project_id:
        where.append(f"PROJECT_ID = '{project_id}'")
    if layer:
        where.append(f"LAYER = '{layer}'")
    w = "WHERE " + " AND ".join(where) if where else ""
    return session.sql(f"""
        SELECT OBJECT_ID, OBJECT_TYPE, OBJECT_NAME, LAYER,
               PROJECT_ID, CREATED_AT, UPDATED_AT
        FROM CONFIG_SCHEMA.MANAGED_OBJECTS
        {w}
        ORDER BY LAYER, OBJECT_TYPE, OBJECT_NAME
    """).to_pandas()


def get_naming(layer: str) -> dict:
    rows = session.sql(f"""
        SELECT PREFIX, SUFFIX, SEPARATOR
        FROM CONFIG_SCHEMA.NAMING_CONVENTION
        WHERE LAYER_CODE = '{layer}' AND ENABLED = TRUE
    """).collect()
    if rows:
        r = rows[0]
        return {"prefix": r["PREFIX"] or layer, "suffix": r["SUFFIX"] or "", "sep": r["SEPARATOR"] or "_"}
    return {"prefix": layer, "suffix": "", "sep": "_"}


def build_name(layer: str, project: str, name: str) -> str:
    n = get_naming(layer)
    parts = [p for p in [n["prefix"], project.upper(), name.upper(), n["suffix"]] if p]
    return n["sep"].join(parts)


def register_object(obj_id, obj_type, obj_name, layer, project_id, metadata=None):
    import json
    meta = json.dumps(metadata or {})
    meta_esc = meta.replace("'", "''")
    session.sql(f"""
        MERGE INTO CONFIG_SCHEMA.MANAGED_OBJECTS t
        USING (SELECT '{obj_id}' AS OID) s ON t.OBJECT_ID = s.OID
        WHEN MATCHED THEN UPDATE
            SET t.OBJECT_TYPE = '{obj_type}',
                t.OBJECT_NAME = '{obj_name}',
                t.LAYER       = '{layer}',
                t.PROJECT_ID  = '{project_id}',
                t.METADATA    = PARSE_JSON('{meta_esc}'),
                t.UPDATED_AT  = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT
            (OBJECT_ID, OBJECT_TYPE, OBJECT_NAME, LAYER, PROJECT_ID, METADATA)
            VALUES ('{obj_id}', '{obj_type}', '{obj_name}', '{layer}', '{project_id}',
                    PARSE_JSON('{meta_esc}'))
    """).collect()


# ── Navigation ────────────────────────────────────────────────
st.sidebar.image(
    "https://upload.wikimedia.org/wikipedia/commons/f/ff/Snowflake_Logo.svg",
    width=160
)
st.sidebar.title("Snowsled")
st.sidebar.caption("Gestion des objets de données")
st.sidebar.markdown("---")

projects_df = load_projects()

if projects_df.empty:
    st.sidebar.warning("Aucun projet actif.")
    proj_sel = None
else:
    proj_names = dict(zip(
        projects_df["PROJECT_ID"],
        projects_df["PROJECT_NAME"] + " (" + projects_df["PROJECT_ID"] + ")"
    ))
    sel_pid = st.sidebar.selectbox(
        "Projet actif", options=list(proj_names.keys()),
        format_func=lambda x: proj_names[x]
    )
    proj_sel = projects_df[projects_df["PROJECT_ID"] == sel_pid].iloc[0]

st.sidebar.markdown("---")
pages = {
    "🏠  Vue d'ensemble":    "overview",
    "📥  Ingestion (DSI)":   "dsi",
    "📤  Présentation (DSO)":"dso",
    "🔄  Pipelines":         "pipelines",
    "�  Fivetran":          "fivetran",
    "�🔗  dbt Models":        "dbt",
    "📊  Monitoring":        "monitoring",
}
choice  = st.sidebar.radio("", list(pages.keys()))
page    = pages[choice]

# ═════════════════════════════════════════════════════════════
# PAGE : Vue d'ensemble
# ═════════════════════════════════════════════════════════════
if page == "overview":
    st.title("🛷 Snowsled — Gestion des objets")
    if proj_sel is None:
        st.warning("Créez d'abord un projet dans **Snowsled Admin**.")
        st.stop()

    st.markdown(f"**Projet actif :** `{proj_sel['PROJECT_NAME']}` | "
                f"DSI : `{proj_sel['DSI_DB']}` | DSO : `{proj_sel['DSO_DB']}`")
    st.markdown("---")

    objs_df = load_objects(proj_sel["PROJECT_ID"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total objets", len(objs_df))
    c2.metric("Objets DSI", len(objs_df[objs_df["LAYER"] == "DSI"]) if not objs_df.empty else 0)
    c3.metric("Objets DSO", len(objs_df[objs_df["LAYER"] == "DSO"]) if not objs_df.empty else 0)

    c4.metric("Warehouse", f"WH_{proj_sel['PROJECT_ID']}")

    st.subheader("Objets gérés")
    if objs_df.empty:
        st.info("Aucun objet créé via Snowsled pour ce projet.")
    else:
        layer_filter = st.multiselect("Filtrer par couche", ["DSI", "DSO"], default=["DSI", "DSO"])
        type_filter  = st.multiselect(
            "Filtrer par type",
            options=objs_df["OBJECT_TYPE"].unique().tolist(),
            default=objs_df["OBJECT_TYPE"].unique().tolist()
        )
        filtered = objs_df[
            objs_df["LAYER"].isin(layer_filter) &
            objs_df["OBJECT_TYPE"].isin(type_filter)
        ]
        st.dataframe(filtered, use_container_width=True)

# ═════════════════════════════════════════════════════════════
# PAGE : Ingestion DSI
# ═════════════════════════════════════════════════════════════
elif page == "dsi":
    st.title("📥 Couche d'intégration — DSI")
    if proj_sel is None:
        st.stop()

    dsi_db = proj_sel["DSI_DB"]
    st.markdown(f"Base cible : `{dsi_db}`")
    st.markdown("---")

    tab_schema, tab_table, tab_pipe, tab_stage = st.tabs([
        "📁 Schémas", "📄 Tables brutes", "🚿 Snowpipe", "🗃️ Stages"
    ])

    # ── Schémas DSI ──────────────────────────────────────────
    with tab_schema:
        st.subheader("Gérer les schémas DSI")
        existing_schemas = session.sql(f"SHOW SCHEMAS IN DATABASE {dsi_db}").to_pandas()
        if not existing_schemas.empty:
            st.dataframe(
                existing_schemas[["name","owner","comment"]],
                use_container_width=True
            )

        with st.form("dsi_schema_form"):
            schema_name = st.text_input("Nom du schéma (ex: SALESFORCE, POSTGRES_CRM)").upper().strip()
            schema_desc = st.text_area("Description / source de données", height=60)
            retention   = st.slider("Data Retention (jours)", 0, 90, 7)
            submitted   = st.form_submit_button("Créer le schéma")

        if submitted and schema_name:
            full_schema = f"{dsi_db}.{schema_name}"
            ok = run_sql(f"""
                CREATE SCHEMA IF NOT EXISTS {full_schema}
                DATA_RETENTION_TIME_IN_DAYS = {retention}
                COMMENT = $${schema_desc}$$
            """, f"Schéma `{full_schema}` créé.", echo=True)
            if ok:
                register_object(
                    f"{dsi_db}.{schema_name}", "SCHEMA", full_schema, "DSI",
                    proj_sel["PROJECT_ID"], {"description": schema_desc}
                )

    # ── Tables brutes ────────────────────────────────────────
    with tab_table:
        st.subheader("Créer une table de landing (brute)")

        schemas_dsi = session.sql(f"SHOW SCHEMAS IN DATABASE {dsi_db}").to_pandas()
        schema_opts = schemas_dsi["name"].tolist() if not schemas_dsi.empty else []

        with st.form("dsi_table_form"):
            tbl_schema = st.selectbox("Schéma", options=schema_opts, key="dsi_tbl_schema")
            tbl_name   = st.text_input("Nom de la table").upper().strip()

            st.markdown("**Colonnes techniques (ajoutées automatiquement)**")
            st.code("""
_LOADED_AT    TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
_SOURCE_FILE  VARCHAR(500)
_ROW_HASH     VARCHAR(64)
_IS_CURRENT   BOOLEAN DEFAULT TRUE
            """)

            st.markdown("**Colonnes métier**")
            num_cols = st.number_input("Nombre de colonnes métier", min_value=1, max_value=20, value=3)

            cols = []
            col_grid = st.columns(3)
            for i in range(int(num_cols)):
                with col_grid[i % 3]:
                    cname = st.text_input(f"Col {i+1} - Nom", key=f"cn_{i}").upper()
                    ctype = st.selectbox(
                        f"Col {i+1} - Type",
                        ["VARCHAR(500)", "NUMBER(18,0)", "NUMBER(18,4)",
                         "DATE", "TIMESTAMP_NTZ", "BOOLEAN", "VARIANT"],
                        key=f"ct_{i}"
                    )
                    cols.append((cname, ctype))

            use_clustering = st.checkbox("Activer le clustering", value=False)
            clustering_col = st.text_input("Colonne de clustering (si activé)") if use_clustering else ""
            submitted = st.form_submit_button("Créer la table")

        if submitted and tbl_name and tbl_schema:
            col_defs = ",\n    ".join([f"{n}  {t}" for n, t in cols if n])
            clustering_clause = f"\nCLUSTER BY ({clustering_col.upper()})" if use_clustering and clustering_col else ""
            full_table = f"{dsi_db}.{tbl_schema}.{tbl_name}"
            sql = f"""
CREATE TABLE IF NOT EXISTS {full_table} (
    {col_defs},
    _LOADED_AT   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    _SOURCE_FILE VARCHAR(500),
    _ROW_HASH    VARCHAR(64),
    _IS_CURRENT  BOOLEAN DEFAULT TRUE
){clustering_clause}
COMMENT = 'Table DSI brute - projet {proj_sel["PROJECT_ID"]} - Snowsled'
"""
            ok = run_sql(sql, f"Table `{full_table}` créée.", echo=True)
            if ok:
                register_object(
                    full_table, "TABLE", full_table, "DSI",
                    proj_sel["PROJECT_ID"], {"schema": tbl_schema, "columns": len(cols)}
                )

    # ── Snowpipe ─────────────────────────────────────────────
    with tab_pipe:
        st.subheader("Créer un Snowpipe (chargement continu)")
        st.info("Un Snowpipe surveille un stage et charge automatiquement les nouveaux fichiers.")

        schemas_dsi = session.sql(f"SHOW SCHEMAS IN DATABASE {dsi_db}").to_pandas()
        schema_opts = schemas_dsi["name"].tolist() if not schemas_dsi.empty else []

        with st.form("pipe_form"):
            pipe_schema = st.selectbox("Schéma", options=schema_opts, key="pipe_schema")
            pipe_name   = st.text_input("Nom du pipe").upper().strip()
            pipe_table  = st.text_input("Table cible (ex: MA_TABLE)").upper().strip()
            pipe_stage  = st.text_input("Stage source (ex: MY_STAGE)").upper().strip()
            file_format = st.selectbox(
                "Format de fichier",
                ["CSV", "JSON", "PARQUET", "AVRO", "ORC"],
                index=0
            )
            auto_ingest = st.checkbox("Auto-ingest (via SQS/SNS)", value=True)
            submitted   = st.form_submit_button("Créer le Snowpipe")

        if submitted and pipe_name and pipe_table:
            full_pipe  = f"{dsi_db}.{pipe_schema}.{pipe_name}"
            full_table = f"{dsi_db}.{pipe_schema}.{pipe_table}"
            full_stage = f"{dsi_db}.{pipe_schema}.{pipe_stage}"
            sql = f"""
CREATE PIPE IF NOT EXISTS {full_pipe}
  {'AUTO_INGEST = TRUE' if auto_ingest else ''}
  COMMENT = 'Snowpipe - {proj_sel["PROJECT_ID"]} - Snowsled'
AS
COPY INTO {full_table}
FROM @{full_stage}
FILE_FORMAT = (TYPE = '{file_format}')
"""
            ok = run_sql(sql, f"Pipe `{full_pipe}` créé.", echo=True)
            if ok:
                register_object(
                    full_pipe, "PIPE", full_pipe, "DSI",
                    proj_sel["PROJECT_ID"], {"table": full_table, "auto_ingest": auto_ingest}
                )

                if auto_ingest:
                    pipe_info = session.sql(f"SHOW PIPES LIKE '{pipe_name}' IN SCHEMA {dsi_db}.{pipe_schema}").collect()
                    if pipe_info:
                        sqs_arn = pipe_info[0].get("notification_channel", "N/A")
                        st.info(f"ARN SQS à configurer dans S3 : `{sqs_arn}`")

    # ── Stages ───────────────────────────────────────────────
    with tab_stage:
        st.subheader("Créer un Stage de chargement")

        schemas_dsi = session.sql(f"SHOW SCHEMAS IN DATABASE {dsi_db}").to_pandas()
        schema_opts = schemas_dsi["name"].tolist() if not schemas_dsi.empty else []

        with st.form("stage_form"):
            stage_schema  = st.selectbox("Schéma", options=schema_opts, key="stage_schema")
            stage_name    = st.text_input("Nom du stage").upper().strip()
            stage_type    = st.radio("Type", ["Interne", "S3 externe", "Azure Blob", "GCS"])
            stage_url     = ""
            stage_int     = ""
            if stage_type != "Interne":
                stage_url = st.text_input("URL (ex: s3://mon-bucket/prefix/)")
                stage_int = st.text_input("Storage Integration (ex: MY_S3_INT)")
            file_format_stage = st.selectbox(
                "Format par défaut", ["CSV", "JSON", "PARQUET", "AVRO"], index=0,
                key="stage_ff"
            )
            submitted = st.form_submit_button("Créer le stage")

        if submitted and stage_name and stage_schema:
            full_stage = f"{dsi_db}.{stage_schema}.{stage_name}"
            if stage_type == "Interne":
                sql = f"""
CREATE STAGE IF NOT EXISTS {full_stage}
  FILE_FORMAT = (TYPE = '{file_format_stage}')
  COMMENT = 'Stage interne DSI - Snowsled'
"""
            else:
                sql = f"""
CREATE STAGE IF NOT EXISTS {full_stage}
  URL = '{stage_url}'
  STORAGE_INTEGRATION = {stage_int}
  FILE_FORMAT = (TYPE = '{file_format_stage}')
  COMMENT = 'Stage externe DSI - Snowsled'
"""
            ok = run_sql(sql, f"Stage `{full_stage}` créé.", echo=True)
            if ok:
                register_object(
                    full_stage, "STAGE", full_stage, "DSI",
                    proj_sel["PROJECT_ID"], {"type": stage_type, "url": stage_url}
                )

# ═════════════════════════════════════════════════════════════
# PAGE : Présentation DSO
# ═════════════════════════════════════════════════════════════
elif page == "dso":
    st.title("📤 Couche de présentation — DSO")
    if proj_sel is None:
        st.stop()

    dso_db = proj_sel["DSO_DB"]
    st.markdown(f"Base cible : `{dso_db}`")
    st.markdown("---")

    tab_schema, tab_view, tab_dshare = st.tabs(["📁 Schémas", "👁️ Vues / Vues sécurisées", "🔗 Secure Data Sharing"])

    with tab_schema:
        st.subheader("Gérer les schémas DSO")
        existing = session.sql(f"SHOW SCHEMAS IN DATABASE {dso_db}").to_pandas()
        if not existing.empty:
            st.dataframe(existing[["name", "owner", "comment"]], use_container_width=True)

        with st.form("dso_schema_form"):
            schema_name = st.text_input("Nom du schéma (ex: SALES_REPORTING, MARKETING)").upper().strip()
            schema_desc = st.text_area("Description", height=60)
            submitted = st.form_submit_button("Créer le schéma")

        if submitted and schema_name:
            full = f"{dso_db}.{schema_name}"
            ok = run_sql(f"""
                CREATE SCHEMA IF NOT EXISTS {full}
                COMMENT = $${schema_desc}$$
            """, f"Schéma `{full}` créé.", echo=True)
            if ok:
                register_object(f"{dso_db}.{schema_name}", "SCHEMA", full, "DSO", proj_sel["PROJECT_ID"])

    with tab_view:
        st.subheader("Créer une vue de présentation")

        schemas_dso = session.sql(f"SHOW SCHEMAS IN DATABASE {dso_db}").to_pandas()
        schema_opts = schemas_dso["name"].tolist() if not schemas_dso.empty else []

        with st.form("dso_view_form"):
            view_schema = st.selectbox("Schéma DSO", options=schema_opts, key="dso_view_schema")
            view_name   = st.text_input("Nom de la vue").upper().strip()
            is_secure   = st.checkbox("Vue sécurisée (SECURE VIEW)", value=True,
                                      help="Empêche l'optimiseur de divulguer les données sources")
            view_sql    = st.text_area(
                "Requête SQL de la vue",
                height=200,
                value=f"SELECT *\nFROM {proj_sel['DSI_DB']}.MY_SCHEMA.MY_TABLE\nWHERE _IS_CURRENT = TRUE",
            )
            submitted = st.form_submit_button("Créer la vue")

        if submitted and view_name and view_sql.strip():
            full_view  = f"{dso_db}.{view_schema}.{view_name}"
            secure_kw  = "SECURE " if is_secure else ""
            sql = f"""
CREATE OR REPLACE {secure_kw}VIEW {full_view}
COMMENT = 'Vue DSO - projet {proj_sel["PROJECT_ID"]} - Snowsled'
AS
{view_sql}
"""
            ok = run_sql(sql, f"Vue `{full_view}` créée.", echo=True)
            if ok:
                register_object(
                    full_view, "SECURE_VIEW" if is_secure else "VIEW",
                    full_view, "DSO", proj_sel["PROJECT_ID"],
                    {"secure": is_secure, "definition": view_sql[:500]}
                )

    with tab_dshare:
        st.subheader("Secure Data Sharing")
        st.info("Partagez vos vues DSO avec d'autres comptes Snowflake sans copie de données.")

        with st.form("share_form"):
            share_name   = st.text_input("Nom du partage").upper().strip()
            target_acct  = st.text_input("Compte cible Snowflake (ex: ABC12345.us-east-1.aws)")
            schema_share = st.selectbox(
                "Schéma à partager",
                options=[""] + (session.sql(f"SHOW SCHEMAS IN DATABASE {dso_db}")
                                .to_pandas()["name"].tolist()),
                key="share_schema"
            )
            submitted = st.form_submit_button("Créer le partage")

        if submitted and share_name and target_acct and schema_share:
            run_sql(f"CREATE SHARE IF NOT EXISTS {share_name}", echo=True)
            run_sql(f"GRANT USAGE ON DATABASE {dso_db} TO SHARE {share_name}")
            run_sql(f"GRANT USAGE ON SCHEMA {dso_db}.{schema_share} TO SHARE {share_name}")
            run_sql(f"GRANT SELECT ON ALL VIEWS IN SCHEMA {dso_db}.{schema_share} TO SHARE {share_name}")
            run_sql(f"ALTER SHARE {share_name} ADD ACCOUNTS = {target_acct}",
                    f"Partage `{share_name}` créé et partagé avec `{target_acct}`.", echo=True)

# ═════════════════════════════════════════════════════════════
# PAGE : Pipelines (Tasks)
# ═════════════════════════════════════════════════════════════
elif page == "pipelines":
    st.title("🔄 Pipelines de transformation")
    if proj_sel is None:
        st.stop()

    dsi_db = proj_sel["DSI_DB"]
    dso_db = proj_sel["DSO_DB"]

    tab_task, tab_list = st.tabs(["➕ Créer un pipeline", "📋 Pipelines existants"])

    with tab_task:
        st.subheader("Créer un pipeline via Snowflake Tasks")

        with st.form("task_form"):
            task_db     = st.selectbox("Base de données", [dsi_db, dso_db])
            task_schema = st.text_input("Schéma").upper()
            task_name   = st.text_input("Nom de la tâche").upper()
            task_wh     = st.text_input(
                "Warehouse", value=f"WH_{proj_sel['PROJECT_ID']}"
            ).upper()
            schedule    = st.selectbox(
                "Schedule",
                ["1 MINUTE", "5 MINUTES", "15 MINUTES", "30 MINUTES",
                 "1 HOUR", "6 HOURS", "1 DAY", "USING CRON 0 6 * * MON-FRI UTC"]
            )
            task_sql    = st.text_area(
                "SQL du pipeline",
                height=150,
                value=f"INSERT INTO {dso_db}.MY_SCHEMA.MY_TARGET\nSELECT * FROM {dsi_db}.MY_SCHEMA.MY_SOURCE\nWHERE _IS_CURRENT = TRUE"
            )
            start_task  = st.checkbox("Démarrer la tâche immédiatement", value=False)
            submitted   = st.form_submit_button("Créer le pipeline")

        if submitted and task_name and task_schema:
            full_task = f"{task_db}.{task_schema}.{task_name}"
            sql = f"""
CREATE TASK IF NOT EXISTS {full_task}
  WAREHOUSE = {task_wh}
  SCHEDULE  = '{schedule}'
AS
{task_sql}
"""
            ok = run_sql(sql, f"Tâche `{full_task}` créée.", echo=True)
            if ok and start_task:
                run_sql(f"ALTER TASK {full_task} RESUME", f"Tâche `{full_task}` démarrée.")
                register_object(
                    full_task, "TASK", full_task,
                    "DSI" if task_db == dsi_db else "DSO",
                    proj_sel["PROJECT_ID"],
                    {"schedule": schedule, "active": start_task}
                )

    with tab_list:
        st.subheader("Tâches existantes")
        for db in [dsi_db, dso_db]:
            try:
                tasks = session.sql(f"SHOW TASKS IN DATABASE {db}").to_pandas()
                if not tasks.empty:
                    st.markdown(f"**{db}**")
                    cols = [c for c in ["name","state","schedule","warehouse","definition"] if c in tasks.columns]
                    st.dataframe(tasks[cols], use_container_width=True)
            except Exception:
                pass

# ═════════════════════════════════════════════════════════════
# PAGE : Fivetran
# ═════════════════════════════════════════════════════════════
elif page == "fivetran":
    st.title("🔴 Fivetran — Connecteurs d'ingestion")
    if proj_sel is None:
        st.stop()

    ft_conn = session.sql("""
        SELECT STATUS, ACCOUNT_ID, ENDPOINT_URL
        FROM CONFIG_SCHEMA.EXTERNAL_CONNECTIONS
        WHERE CONNECTION_NAME = 'FIVETRAN'
    """).collect()

    if not ft_conn or ft_conn[0]["STATUS"] != "CONNECTED":
        st.warning("Fivetran n'est pas connecté. Configurez la connexion dans **Snowsled Platform**.")
        st.stop()

    ft_account_id = ft_conn[0]["ACCOUNT_ID"]
    ft_endpoint   = ft_conn[0]["ENDPOINT_URL"] or "https://api.fivetran.com"

    st.success(f"Connecté à Fivetran — Account ID : `{ft_account_id}`")
    st.markdown("---")

    tab_list, tab_create, tab_sync = st.tabs([
        "📋 Connecteurs", "➕ Créer un connecteur", "▶️ Déclencher une sync"
    ])

    # ── Onglet : Liste des connecteurs ────────────────────────
    with tab_list:
        st.subheader("Connecteurs Fivetran")
        if st.button("Actualiser la liste", key="btn_ft_refresh"):
            try:
                result = session.call("APP_SCHEMA.LIST_FIVETRAN_CONNECTORS", ft_account_id)
                if isinstance(result, list) and result:
                    import pandas as _pd
                    st.dataframe(_pd.DataFrame(result), use_container_width=True)
                else:
                    st.info("Aucun connecteur trouvé ou réponse vide.")
            except Exception as ex:
                st.error(f"Erreur : {ex}")

        # Affichage connecteurs enregistrés localement
        try:
            local_connectors = session.sql(f"""
                SELECT CONNECTOR_KEY, CONNECTOR_NAME, SERVICE, DESTINATION_SCHEMA,
                       DSI_DB, FIVETRAN_CONNECTOR_ID, STATUS, CREATED_AT
                FROM CONFIG_SCHEMA.FIVETRAN_CONNECTORS
                WHERE SNOWSLED_PROJECT_ID = '{proj_sel["PROJECT_ID"]}'
                ORDER BY CREATED_AT DESC
            """).to_pandas()
            if not local_connectors.empty:
                st.markdown("**Connecteurs enregistrés localement**")
                st.dataframe(local_connectors, use_container_width=True)
        except Exception:
            pass

    # ── Onglet : Créer un connecteur ──────────────────────────
    with tab_create:
        st.subheader("Créer un nouveau connecteur Fivetran")
        st.markdown(
            "Remplit le formulaire ci-dessous pour créer un connecteur Fivetran "
            "via l'[API Fivetran](https://fivetran.com/docs/rest-api/connectors#createaconnector)."
        )

        FIVETRAN_SERVICES = [
            "snowflake", "salesforce", "hubspot", "google_analytics",
            "google_sheets", "postgres", "mysql", "mssql", "oracle",
            "s3", "gcs", "azure_blob_storage", "github", "jira",
            "zendesk", "stripe", "shopify", "marketo", "netsuite",
            "bigquery", "redshift", "mongodb", "facebook_ads",
            "google_ads", "linkedin_ads", "twitter_ads", "other"
        ]

        with st.form("form_create_fivetran_connector"):
            col1, col2 = st.columns(2)
            with col1:
                ft_service = st.selectbox(
                    "Source / Service *",
                    options=FIVETRAN_SERVICES,
                    help="Type de source de données Fivetran"
                )
                ft_connector_name = st.text_input(
                    "Nom du connecteur *",
                    placeholder="ex: SALESFORCE_PROD",
                    help="Identifiant lisible pour ce connecteur"
                )
                ft_dest_schema = st.text_input(
                    "Schéma de destination (DSI) *",
                    value=f"{proj_sel['PROJECT_ID']}_{ft_service.upper()}" if True else "",
                    help="Schéma dans la base DSI où Fivetran écrira les données"
                ).upper().strip()
            with col2:
                ft_group_id = st.text_input(
                    "Group ID Fivetran *",
                    value=ft_account_id,
                    help="ID du groupe/destination Fivetran (visible dans l'URL)"
                )
                ft_sync_frequency = st.selectbox(
                    "Fréquence de sync (minutes)",
                    options=[5, 15, 30, 60, 120, 360, 720, 1440],
                    index=2,
                    help="Intervalle entre deux synchronisations automatiques"
                )
                ft_paused = st.checkbox(
                    "Démarrer en pause",
                    value=False,
                    help="Créer le connecteur sans déclencher de sync immédiate"
                )

            st.markdown("**Configuration spécifique à la source** (optionnel)")
            ft_config_json = st.text_area(
                "Config JSON supplémentaire",
                value="{}",
                height=80,
                help="Paramètres de connexion propres à la source (host, port, database…)"
            )

            submitted_ft = st.form_submit_button("🚀 Créer le connecteur", type="primary")

        if submitted_ft:
            import json as _json
            errors = []
            if not ft_connector_name.strip():
                errors.append("Le nom du connecteur est obligatoire.")
            if not ft_dest_schema.strip():
                errors.append("Le schéma de destination est obligatoire.")
            if not ft_group_id.strip():
                errors.append("Le Group ID Fivetran est obligatoire.")
            try:
                _json.loads(ft_config_json)
            except ValueError:
                errors.append("La config JSON est invalide.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                payload = _json.dumps({
                    "action":             "create_fivetran_connector",
                    "group_id":            ft_group_id.strip(),
                    "service":             ft_service,
                    "connector_name":      ft_connector_name.strip(),
                    "destination_schema":  ft_dest_schema,
                    "sync_frequency":      ft_sync_frequency,
                    "paused":              ft_paused,
                    "config":              _json.loads(ft_config_json),
                    "snowsled_project_id": str(proj_sel["PROJECT_ID"]),
                    "dsi_db":              str(proj_sel["DSI_DB"]),
                })
                try:
                    result = session.call("APP_SCHEMA.CREATE_FIVETRAN_CONNECTOR", payload)
                    if isinstance(result, dict) and result.get("id"):
                        st.success(
                            f"✅ Connecteur **{ft_connector_name}** créé ! "
                            f"ID Fivetran : `{result['id']}`"
                        )
                        st.json(result)
                    else:
                        # Enregistrement local en attente de sync API
                        conn_key = f"{proj_sel['PROJECT_ID']}_{ft_connector_name.strip().upper().replace(' ', '_')}"
                        session.sql(f"""
                            MERGE INTO CONFIG_SCHEMA.FIVETRAN_CONNECTORS t
                            USING (SELECT '{conn_key}' AS CK) s ON t.CONNECTOR_KEY = s.CK
                            WHEN NOT MATCHED THEN INSERT
                                (CONNECTOR_KEY, CONNECTOR_NAME, SERVICE, DESTINATION_SCHEMA,
                                 DSI_DB, GROUP_ID, SYNC_FREQUENCY, PAUSED,
                                 SNOWSLED_PROJECT_ID, STATUS, CREATED_AT)
                            VALUES (
                                s.CK,
                                '{ft_connector_name.strip().replace("'", "''")}',
                                '{ft_service}',
                                '{ft_dest_schema}',
                                '{str(proj_sel["DSI_DB"])}',
                                '{ft_group_id.strip().replace("'", "''")}',
                                {ft_sync_frequency},
                                {'TRUE' if ft_paused else 'FALSE'},
                                '{proj_sel["PROJECT_ID"]}',
                                'PENDING',
                                CURRENT_TIMESTAMP()
                            )
                        """).collect()
                        st.warning(
                            "La procédure APP_SCHEMA.CREATE_FIVETRAN_CONNECTOR n'a pas retourné d'ID. "
                            "Le connecteur a été enregistré localement avec le statut **PENDING**."
                        )
                except Exception as ex:
                    st.error(f"Erreur lors de la création du connecteur : {ex}")

    # ── Onglet : Déclencher une sync ──────────────────────────
    with tab_sync:
        st.subheader("Déclencher une synchronisation Fivetran")

        # Récupération des connecteurs locaux pour pré-remplir
        connector_options = {}
        try:
            local_conn_df = session.sql(f"""
                SELECT CONNECTOR_KEY, CONNECTOR_NAME, FIVETRAN_CONNECTOR_ID
                FROM CONFIG_SCHEMA.FIVETRAN_CONNECTORS
                WHERE SNOWSLED_PROJECT_ID = '{proj_sel["PROJECT_ID"]}'
                  AND STATUS = 'ACTIVE'
            """).to_pandas()
            if not local_conn_df.empty:
                for _, row in local_conn_df.iterrows():
                    if row["FIVETRAN_CONNECTOR_ID"]:
                        connector_options[row["CONNECTOR_NAME"]] = str(row["FIVETRAN_CONNECTOR_ID"])
        except Exception:
            pass

        if connector_options:
            selected_conn_name = st.selectbox(
                "Connecteur",
                options=list(connector_options.keys()),
                key="ft_sync_select"
            )
            connector_id = connector_options[selected_conn_name]
            st.info(f"Connector ID : `{connector_id}`")
        else:
            connector_id = st.text_input(
                "Connector ID Fivetran",
                help="Visible dans l'URL du connecteur dans l'interface Fivetran"
            )

        force_full_sync = st.checkbox(
            "Forcer une resync complète",
            value=False,
            help="Recharge toutes les données depuis la source (plus lent)"
        )

        if st.button("▶️ Déclencher la sync", key="btn_ft_sync", type="primary"):
            if connector_id:
                try:
                    result = session.call(
                        "APP_SCHEMA.TRIGGER_FIVETRAN_SYNC",
                        connector_id,
                        str(force_full_sync).lower()
                    )
                    if result and result.get("code") in ("Success", "200"):
                        st.success(f"✅ Sync déclenchée pour le connecteur `{connector_id}` !")
                    else:
                        st.error(f"Erreur : {result}")
                except Exception as ex:
                    st.error(f"Erreur : {ex}")
            else:
                st.warning("Veuillez renseigner un Connector ID.")

# ═════════════════════════════════════════════════════════════
# PAGE : dbt Models
# ═════════════════════════════════════════════════════════════
elif page == "dbt":
    st.title("🔗 dbt Cloud — Modèles")
    if proj_sel is None:
        st.stop()

    dbt_conn = session.sql("""
        SELECT STATUS, ACCOUNT_ID, ENDPOINT_URL
        FROM CONFIG_SCHEMA.EXTERNAL_CONNECTIONS
        WHERE CONNECTION_NAME = 'DBT_CLOUD'
    """).collect()

    if not dbt_conn or dbt_conn[0]["STATUS"] != "CONNECTED":
        st.warning("dbt Cloud n'est pas connecté. Configurez la connexion dans **Snowsled Platform**.")
        st.stop()

    dbt_account_id = dbt_conn[0]["ACCOUNT_ID"]
    dbt_endpoint   = dbt_conn[0]["ENDPOINT_URL"] or "https://cloud.getdbt.com"

    st.success(f"Connecté à dbt Cloud — Account ID : `{dbt_account_id}`")
    st.markdown("---")

    tab_proj, tab_create, tab_run = st.tabs(["📁 Projets dbt", "➕ Créer un projet", "▶️ Déclencher un run"])

    with tab_proj:
        st.subheader("Projets dbt Cloud")
        if st.button("Actualiser la liste des projets", key="btn_dbt_refresh"):
            result = session.sql("""
                SELECT SYSTEM$SEND_SNOWFLAKE_NOTIFICATION(
                    SNOWFLAKE.NOTIFICATION.APPLICATION_JSON(
                        '{"action": "list_dbt_projects"}'
                    )
                )
            """).collect()
        st.info("Les projets dbt Cloud sont listés via l'intégration API configurée.")

    with tab_create:
        st.subheader("Créer un nouveau projet dbt Cloud")
        st.markdown(
            "Remplit le formulaire ci-dessous pour créer un projet dbt Cloud "
            "via l'[API Administrative dbt Cloud](https://docs.getdbt.com/dbt-cloud/api-v2)."
        )

        with st.form("form_create_dbt_project"):
            col1, col2 = st.columns(2)
            with col1:
                dbt_proj_name = st.text_input(
                    "Nom du projet *",
                    value=f"{proj_sel['PROJECT_NAME']}_dbt" if proj_sel is not None else "",
                    help="Nom affiché dans dbt Cloud"
                )
                dbt_repo_url = st.text_input(
                    "URL du dépôt Git *",
                    placeholder="https://github.com/organisation/repo.git",
                    help="Dépôt contenant vos modèles dbt"
                )
                dbt_project_subdir = st.text_input(
                    "Sous-répertoire du projet",
                    value="",
                    placeholder="dbt/  (laisser vide si racine)",
                    help="Chemin relatif dans le dépôt où se trouve le dbt_project.yml"
                )
            with col2:
                dbt_sf_account  = st.text_input(
                    "Compte Snowflake (locator) *",
                    help="ex. xy12345.eu-west-1"
                )
                dbt_sf_database = st.text_input(
                    "Base cible Snowflake",
                    value=str(proj_sel["DSO_DB"]) if proj_sel is not None else "",
                    help="Base de données Snowflake où dbt écrira les modèles"
                )
                dbt_sf_schema   = st.text_input(
                    "Schéma cible",
                    value="DBT_PROD",
                    help="Schéma Snowflake par défaut pour les modèles dbt"
                )
                dbt_sf_warehouse = st.text_input(
                    "Warehouse Snowflake",
                    value=f"WH_{proj_sel['PROJECT_ID']}" if proj_sel is not None else "",
                )

            submitted = st.form_submit_button("🚀 Créer le projet dbt Cloud", type="primary")

        if submitted:
            errors = []
            if not dbt_proj_name.strip():
                errors.append("Le nom du projet est obligatoire.")
            if not dbt_repo_url.strip():
                errors.append("L'URL du dépôt Git est obligatoire.")
            if not dbt_sf_account.strip():
                errors.append("Le compte Snowflake est obligatoire.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                import json as _json
                payload = _json.dumps({
                    "action":           "create_dbt_project",
                    "account_id":       dbt_account_id,
                    "project_name":     dbt_proj_name.strip(),
                    "repo_url":         dbt_repo_url.strip(),
                    "project_subdir":   dbt_project_subdir.strip(),
                    "snowflake_account": dbt_sf_account.strip(),
                    "snowflake_database": dbt_sf_database.strip(),
                    "snowflake_schema":  dbt_sf_schema.strip(),
                    "snowflake_warehouse": dbt_sf_warehouse.strip(),
                    "snowsled_project_id": str(proj_sel["PROJECT_ID"]),
                })
                payload_esc = payload.replace("'", "''")
                try:
                    result = session.call("APP_SCHEMA.CREATE_DBT_PROJECT", payload)
                    if isinstance(result, dict) and result.get("id"):
                        st.success(
                            f"✅ Projet **{dbt_proj_name}** créé avec succès ! "
                            f"ID dbt Cloud : `{result['id']}`"
                        )
                        st.json(result)
                    else:
                        # Fallback : enregistrement local en attente de sync API
                        proj_id = proj_sel["PROJECT_ID"]
                        session.sql(f"""
                            MERGE INTO CONFIG_SCHEMA.DBT_PROJECTS t
                            USING (SELECT '{proj_id}_{dbt_proj_name.strip().replace(" ", "_").upper()}'
                                   AS PID) s ON t.DBT_PROJECT_KEY = s.PID
                            WHEN NOT MATCHED THEN INSERT
                                (DBT_PROJECT_KEY, PROJECT_NAME, REPO_URL, PROJECT_SUBDIR,
                                 SF_ACCOUNT, SF_DATABASE, SF_SCHEMA, SF_WAREHOUSE,
                                 SNOWSLED_PROJECT_ID, STATUS, CREATED_AT)
                            VALUES (
                                s.PID,
                                '{dbt_proj_name.strip().replace("'", "''")}',
                                '{dbt_repo_url.strip().replace("'", "''")}',
                                '{dbt_project_subdir.strip().replace("'", "''")}',
                                '{dbt_sf_account.strip().replace("'", "''")}',
                                '{dbt_sf_database.strip().replace("'", "''")}',
                                '{dbt_sf_schema.strip().replace("'", "''")}',
                                '{dbt_sf_warehouse.strip().replace("'", "''")}',
                                '{proj_id}',
                                'PENDING',
                                CURRENT_TIMESTAMP()
                            )
                        """).collect()
                        st.warning(
                            "La procédure APP_SCHEMA.CREATE_DBT_PROJECT n'a pas retourné d'ID. "
                            "Le projet a été enregistré localement avec le statut **PENDING** "
                            "et sera synchronisé avec dbt Cloud lors du prochain déploiement."
                        )
                except Exception as ex:
                    st.error(f"Erreur lors de la création du projet dbt : {ex}")

    with tab_run:
        st.subheader("Déclencher un run dbt Cloud")
        job_id = st.text_input("Job ID dbt Cloud", help="Visible dans l'URL du job dbt Cloud")
        cause  = st.text_input("Cause / description du run", value=f"Déclenché par Snowsled - {proj_sel['PROJECT_ID']}")
        if st.button("Déclencher le job", key="btn_dbt_run"):
            if job_id:
                result = session.call("APP_SCHEMA.TRIGGER_DBT_JOB", job_id, cause)
                if result and result.get("status") == "RUNNING":
                    st.success(f"Job `{job_id}` déclenché ! Run ID : {result.get('run_id')}")
                else:
                    st.error(f"Erreur : {result}")

# ═════════════════════════════════════════════════════════════
# PAGE : Monitoring
# ═════════════════════════════════════════════════════════════
elif page == "monitoring":
    st.title("📊 Monitoring")
    if proj_sel is None:
        st.stop()

    wh_name = f"WH_{proj_sel['PROJECT_ID']}"
    st.markdown(f"Warehouse surveillé : `{wh_name}`")
    st.markdown("---")

    tab_credits, tab_queries, tab_pipes, tab_tasks = st.tabs([
        "💰 Consommation", "🔍 Requêtes", "🚿 Snowpipes", "⏱️ Tasks"
    ])

    with tab_credits:
        st.subheader("Consommation de crédits (7 derniers jours)")
        credits_df = session.sql(f"""
            SELECT
                DATE_TRUNC('DAY', START_TIME)::DATE AS DAY,
                ROUND(SUM(CREDITS_USED_COMPUTE), 4) AS CREDITS_COMPUTE,
                ROUND(SUM(CREDITS_USED_CLOUD_SERVICES), 4) AS CREDITS_CLOUD
            FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
            WHERE WAREHOUSE_NAME = '{wh_name}'
              AND START_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
            GROUP BY 1
            ORDER BY 1
        """).to_pandas()
        if credits_df.empty:
            st.info("Aucune consommation enregistrée pour ce warehouse.")
        else:
            st.bar_chart(credits_df.set_index("DAY")["CREDITS_COMPUTE"])
            st.dataframe(credits_df, use_container_width=True)

    with tab_queries:
        st.subheader("Requêtes récentes")
        n_rows = st.slider("Nombre de requêtes", 10, 200, 50)
        qh_df = session.sql(f"""
            SELECT
                QUERY_ID, QUERY_TEXT, QUERY_TYPE,
                EXECUTION_STATUS, START_TIME,
                ROUND(TOTAL_ELAPSED_TIME/1000, 2) AS ELAPSED_SEC,
                ROUND(BYTES_SCANNED/1e6, 2)       AS MB_SCANNED
            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
            WHERE WAREHOUSE_NAME = '{wh_name}'
              AND START_TIME >= DATEADD(DAY, -1, CURRENT_TIMESTAMP())
            ORDER BY START_TIME DESC
            LIMIT {n_rows}
        """).to_pandas()
        if qh_df.empty:
            st.info("Aucune requête récente.")
        else:
            st.dataframe(qh_df, use_container_width=True)

    with tab_pipes:
        st.subheader("Statut des Snowpipes")
        try:
            pipes_df = session.sql(f"SHOW PIPES IN DATABASE {proj_sel['DSI_DB']}").to_pandas()
            if not pipes_df.empty:
                st.dataframe(pipes_df, use_container_width=True)
            else:
                st.info("Aucun Snowpipe dans ce projet.")
        except Exception as e:
            st.warning(f"Impossible de lister les pipes : {e}")

    with tab_tasks:
        st.subheader("Statut des Tasks")
        task_hist = session.sql(f"""
            SELECT
                NAME, DATABASE_NAME, SCHEMA_NAME,
                STATE, SCHEDULED_TIME, COMPLETED_TIME,
                RETURN_VALUE, ERROR_CODE, ERROR_MESSAGE
            FROM SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY
            WHERE DATABASE_NAME IN ('{proj_sel["DSI_DB"]}', '{proj_sel["DSO_DB"]}')
              AND SCHEDULED_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
            ORDER BY SCHEDULED_TIME DESC
            LIMIT 100
        """).to_pandas()
        if task_hist.empty:
            st.info("Aucune exécution de task récente.")
        else:
            st.dataframe(task_hist, use_container_width=True)
