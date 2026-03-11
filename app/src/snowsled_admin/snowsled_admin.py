# ============================================================
# SNOWSLED ADMIN
# Configuration du nommage et des bases Snowsled
# ============================================================

import streamlit as st
import pandas as pd
import json
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
    page_title="Snowsled Admin",
    page_icon="🛠️",
    layout="wide",
)

# ── Session Snowflake (Snowflake natif ou connexion locale) ──
session = get_session()

# ── Helpers ──────────────────────────────────────────────────
def run_sql(query: str, success_msg: str = None, echo: bool = False):
    try:
        if echo:
            with st.expander("SQL exécuté"):
                st.code(query, language="sql")
        session.sql(query).collect()
        if success_msg:
            st.success(success_msg)
        return True
    except Exception as e:
        st.error(f"Erreur : {e}")
        return False


def load_naming():
    return session.sql("""
        SELECT LAYER_CODE, PREFIX, SUFFIX, SEPARATOR, DESCRIPTION, ENABLED
        FROM CONFIG_SCHEMA.NAMING_CONVENTION
        ORDER BY LAYER_CODE
    """).to_pandas()


def load_projects():
    return session.sql("""
        SELECT PROJECT_ID, PROJECT_NAME, DESCRIPTION,
               DSI_DB, DSO_DB, WH_SIZE, STATUS, CREATED_AT
        FROM CONFIG_SCHEMA.PROJECTS
        ORDER BY CREATED_AT DESC
    """).to_pandas()


def load_managed_roles():
    return session.sql("""
        SELECT ROLE_NAME, ROLE_TYPE, PROJECT_ID, CREATED_AT
        FROM CONFIG_SCHEMA.MANAGED_ROLES
        ORDER BY PROJECT_ID, ROLE_TYPE
    """).to_pandas()


def build_db_name(layer: str, project: str) -> str:
    """Construit le nom de base selon la convention de nommage."""
    rows = session.sql(f"""
        SELECT PREFIX, SUFFIX, SEPARATOR
        FROM CONFIG_SCHEMA.NAMING_CONVENTION
        WHERE LAYER_CODE = '{layer}' AND ENABLED = TRUE
    """).collect()
    if not rows:
        return f"{layer}_{project.upper()}"
    r = rows[0]
    prefix = r["PREFIX"] or layer
    suffix = r["SUFFIX"] or ""
    sep    = r["SEPARATOR"] or "_"
    parts  = [p for p in [prefix, project.upper(), suffix] if p]
    return sep.join(parts)


def log_action(event_type, object_type, object_name, status, details=None):
    d_esc = json.dumps(details or {}).replace("'", "''")
    et_esc  = event_type.replace("'", "''")
    ot_esc  = object_type.replace("'", "''")
    on_esc  = object_name.replace("'", "''")
    st_esc  = status.replace("'", "''")
    try:
        session.sql(f"""
            CALL APP_SCHEMA.LOG_ACTION(
                '{et_esc}', '{ot_esc}', '{on_esc}',
                '{st_esc}', PARSE_JSON('{d_esc}')
            )
        """).collect()
    except Exception:
        pass  # L'audit ne doit jamais bloquer l'action principale


def check_account_privileges() -> bool:
    """Verifie que l'app a les privileges CREATE DATABASE/WAREHOUSE."""
    try:
        session.sql("CREATE DATABASE IF NOT EXISTS _SNOWSLED_PRIV_CHECK_").collect()
        session.sql("DROP DATABASE IF EXISTS _SNOWSLED_PRIV_CHECK_").collect()
        return True
    except Exception:
        return False


_PRIV_OK = None  # cache

def get_priv_ok() -> bool:
    global _PRIV_OK
    if _PRIV_OK is None:
        _PRIV_OK = check_account_privileges()
    return _PRIV_OK


# ── Navigation ────────────────────────────────────────────────
st.sidebar.image(
    "https://upload.wikimedia.org/wikipedia/commons/f/ff/Snowflake_Logo.svg",
    width=160
)
st.sidebar.title("Snowsled Admin")
st.sidebar.caption("Administration & Configuration")
st.sidebar.markdown("---")

pages = {
    "🏠  Tableau de bord":       "dashboard",
    "📐  Convention de nommage": "naming",
    "🗂️  Projets":               "projects",
    "👥  Rôles":                 "roles",
    "🔍  Journal d'audit":       "audit",
    "🤖  Cortex AI Monitor":     "cortex_agent",
}
choice = st.sidebar.radio("", list(pages.keys()))
page = pages[choice]

# ── PAGE : Tableau de bord ────────────────────────────────────
if page == "dashboard":
    st.title("🛠️ Snowsled Admin — Tableau de bord")
    st.markdown("---")

    col1, col2, col3, col4 = st.columns(4)
    projects_df = load_projects()
    roles_df    = load_managed_roles()
    naming_df   = load_naming()

    audit_count = session.sql("""
        SELECT COUNT(*) AS CNT FROM AUDIT_SCHEMA.AUDIT_LOG
    """).collect()[0]["CNT"]

    obj_count = session.sql("""
        SELECT COUNT(*) AS CNT FROM CONFIG_SCHEMA.MANAGED_OBJECTS
    """).collect()[0]["CNT"]

    col1.metric("Projets", len(projects_df))
    col2.metric("Rôles gérés", len(roles_df))
    col3.metric("Objets Snowsled", obj_count)
    col4.metric("Actions auditées", audit_count)

    st.markdown("---")
    st.subheader("Projets actifs")
    if projects_df.empty:
        st.info("Aucun projet configuré. Rendez-vous dans l'onglet **Projets**.")
    else:
        st.dataframe(
            projects_df[["PROJECT_ID","PROJECT_NAME","DSI_DB","DSO_DB","WH_SIZE","STATUS"]],
            use_container_width=True
        )

    st.subheader("Convention de nommage")
    st.dataframe(naming_df, use_container_width=True)

# ── PAGE : Convention de nommage ──────────────────────────────
elif page == "naming":
    st.title("📐 Convention de nommage")
    st.markdown("""
    Définissez les préfixes, suffixes et séparateurs utilisés pour nommer automatiquement
    les objets Snowflake (bases de données, schémas, rôles, warehouses).
    """)

    naming_df = load_naming()

    st.subheader("Configuration actuelle")
    st.dataframe(naming_df, use_container_width=True)

    st.markdown("---")
    with st.expander("➕ Modifier / Ajouter une règle de nommage", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            layer_code = st.selectbox(
                "Couche / Type d'objet",
                options=["DSI", "DSO", "WH", "ROLE", "SCHEMA", "TABLE", "VIEW", "PIPE", "TASK"]
            )
            prefix = st.text_input(
                "Préfixe (ex: DSI)",
                value=naming_df[naming_df["LAYER_CODE"] == layer_code]["PREFIX"].values[0]
                      if layer_code in naming_df["LAYER_CODE"].values else layer_code
            )
        with col2:
            suffix = st.text_input(
                "Suffixe (optionnel)",
                value=naming_df[naming_df["LAYER_CODE"] == layer_code]["SUFFIX"].values[0]
                      if layer_code in naming_df["LAYER_CODE"].values else ""
            )
            separator = st.selectbox("Séparateur", options=["_", "-", "."], index=0)

        description = st.text_input(
            "Description",
            value=naming_df[naming_df["LAYER_CODE"] == layer_code]["DESCRIPTION"].values[0]
                  if layer_code in naming_df["LAYER_CODE"].values else ""
        )
        enabled = st.checkbox("Activer cette règle", value=True)

        st.markdown("**Aperçu :** Le nom généré pour le projet `DEMO` sera :")
        preview_parts = [p for p in [prefix, "DEMO", suffix] if p]
        st.code(separator.join(preview_parts))

        if st.button("Enregistrer la règle", key="btn_save_naming"):
            desc_esc = description.replace("'", "''")
            session.sql(f"""
                MERGE INTO CONFIG_SCHEMA.NAMING_CONVENTION t
                USING (SELECT '{layer_code}' AS LC) s ON t.LAYER_CODE = s.LC
                WHEN MATCHED THEN UPDATE
                    SET t.PREFIX      = '{prefix}',
                        t.SUFFIX      = '{suffix}',
                        t.SEPARATOR   = '{separator}',
                        t.DESCRIPTION = '{desc_esc}',
                        t.ENABLED     = {str(enabled).upper()},
                        t.UPDATED_AT  = CURRENT_TIMESTAMP()
                WHEN NOT MATCHED THEN INSERT
                    (LAYER_CODE, PREFIX, SUFFIX, SEPARATOR, DESCRIPTION, ENABLED)
                    VALUES ('{layer_code}', '{prefix}', '{suffix}', '{separator}',
                            '{desc_esc}', {str(enabled).upper()})
            """).collect()
            log_action("UPDATE", "NAMING_CONVENTION", layer_code, "SUCCESS",
                       {"prefix": prefix, "suffix": suffix, "separator": separator})
            st.success(f"Règle **{layer_code}** enregistrée.")
            st.rerun()

    st.markdown("---")
    st.subheader("Simulateur de nommage")
    sim_project = st.text_input("Nom de projet / domaine", value="RETAIL").upper()
    if sim_project:
        naming_cur = load_naming()
        sim_df = []
        for _, row in naming_cur.iterrows():
            if not row["ENABLED"]:
                continue
            parts = [p for p in [row["PREFIX"], sim_project, row["SUFFIX"]] if p]
            generated = (row["SEPARATOR"] or "_").join(parts)
            sim_df.append({
                "Couche": row["LAYER_CODE"],
                "Nom généré": generated,
                "Description": row["DESCRIPTION"],
            })
        st.dataframe(pd.DataFrame(sim_df), use_container_width=True)

# ── PAGE : Projets ────────────────────────────────────────────
elif page == "projects":
    st.title("🗂️ Gestion des projets")
    st.markdown("""
    Un **projet Snowsled** regroupe un périmètre métier avec ses bases DSI/DSO,
    son warehouse dédié et ses rôles associés.
    """)

    tab_list, tab_create = st.tabs(["📋 Liste des projets", "➕ Nouveau projet"])

    with tab_list:
        projects_df = load_projects()
        if projects_df.empty:
            st.info("Aucun projet créé.")
        else:
            st.dataframe(projects_df, use_container_width=True)

            st.subheader("Actions")
            selected_pid = st.selectbox(
                "Sélectionner un projet",
                options=projects_df["PROJECT_ID"].tolist()
            )
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Désactiver le projet", key="btn_disable"):
                    session.sql(f"""
                        UPDATE CONFIG_SCHEMA.PROJECTS
                        SET STATUS = 'INACTIVE'
                        WHERE PROJECT_ID = '{selected_pid}'
                    """).collect()
                    st.success(f"Projet **{selected_pid}** désactivé.")
                    st.rerun()

    with tab_create:
        st.subheader("Créer un nouveau projet Snowsled")

        if not get_priv_ok():
            st.error(
                "**Privileges manquants sur le compte**\n\n"
                "La creation d'un projet necessite les privileges suivants. "
                "Demandez a un ACCOUNTADMIN d'executer dans un Worksheet Snowflake :\n\n"
                "```sql\n"
                "USE ROLE ACCOUNTADMIN;\n"
                "GRANT CREATE DATABASE  ON ACCOUNT TO APPLICATION SNOWSLED_V2;\n"
                "GRANT CREATE WAREHOUSE ON ACCOUNT TO APPLICATION SNOWSLED_V2;\n"
                "```\n\n"
                "Rechargez ensuite cette page."
            )
            st.stop()

        with st.form("project_form"):
            proj_id   = st.text_input(
                "Identifiant du projet (ex: RETAIL, RH, FINANCE)",
                help="Sera utilisé dans le nommage des objets"
            ).upper().strip()
            proj_name = st.text_input("Nom complet du projet")
            proj_desc = st.text_area("Description", height=80)

            st.markdown("**Ressources Snowflake**")
            col1, col2 = st.columns(2)
            with col1:
                wh_size = st.selectbox(
                    "Taille du warehouse",
                    ["X-SMALL", "SMALL", "MEDIUM", "LARGE"],
                    index=1
                )
                create_wh = st.checkbox("Créer un warehouse dédié", value=True)
            with col2:
                create_dbs   = st.checkbox("Créer les bases DSI + DSO", value=True)
                create_roles = st.checkbox(
                    "Créer les rôles fonctionnels",
                    value=False,
                    disabled=True,
                    help="La création de rôles Snowflake nécessite le privilege CREATE ROLE "
                         "qui n'est pas supporté dans les Native Apps. "
                         "Créez les rôles manuellement après la création du projet."
                )

            data_retention = st.slider("Data Retention (jours)", 0, 90, value=7)
            submitted = st.form_submit_button("Créer le projet")

        if submitted:
            if not proj_id:
                st.warning("L'identifiant du projet est obligatoire.")
            else:
                dsi_db  = build_db_name("DSI", proj_id)
                dso_db  = build_db_name("DSO", proj_id)
                wh_name = f"WH_{proj_id}"

                progress = st.progress(0, text="Initialisation...")
                errors = []

                # Warehouse
                if create_wh:
                    ok = run_sql(f"""
                        CREATE WAREHOUSE IF NOT EXISTS {wh_name}
                          WAREHOUSE_SIZE = '{wh_size}'
                          AUTO_SUSPEND = 120
                          AUTO_RESUME  = TRUE
                          INITIALLY_SUSPENDED = TRUE
                          COMMENT = 'WH projet {proj_id} - Snowsled'
                    """)
                    if not ok:
                        errors.append(f"Warehouse {wh_name}")
                progress.progress(25, text="Warehouse... ✅")

                # Bases de données
                if create_dbs:
                    for db, comment in [
                        (dsi_db, f"DSI brut - {proj_id}"),
                        (dso_db, f"DSO curated - {proj_id}")
                    ]:
                        ok = run_sql(f"""
                            CREATE DATABASE IF NOT EXISTS {db}
                            DATA_RETENTION_TIME_IN_DAYS = {data_retention}
                            COMMENT = '{comment} - Snowsled'
                        """)
                        # Créer schémas de base
                        if ok:
                            for schema in ["RAW", "STAGING", "METADATA"]:
                                run_sql(f"CREATE SCHEMA IF NOT EXISTS {db}.{schema}")
                        else:
                            errors.append(db)
                progress.progress(60, text="Bases de données... ✅")

                # Rôles
                if create_roles:
                    for role_type, desc in [
                        ("ADMIN",     "Accès complet"),
                        ("DEVELOPER", "Dev DSI+DSO"),
                        ("ANALYST",   "Lecture DSO"),
                    ]:
                        rname = f"ROLE_{proj_id}_{role_type}"
                        run_sql(f"""
                            CREATE ROLE IF NOT EXISTS {rname}
                            COMMENT = '{desc} - projet {proj_id} - Snowsled'
                        """)
                        session.sql(f"""
                            MERGE INTO CONFIG_SCHEMA.MANAGED_ROLES t
                            USING (SELECT '{rname}' AS RN) s ON t.ROLE_NAME = s.RN
                            WHEN NOT MATCHED THEN INSERT
                                (ROLE_NAME, ROLE_TYPE, PROJECT_ID)
                                VALUES ('{rname}', '{role_type}', '{proj_id}')
                        """).collect()
                progress.progress(85, text="Rôles... ✅")

                # Enregistrer le projet
                proj_name_esc = proj_name.replace("'", "''")
                proj_desc_esc = proj_desc.replace("'", "''")
                session.sql(f"""
                    MERGE INTO CONFIG_SCHEMA.PROJECTS t
                    USING (SELECT '{proj_id}' AS PID) s ON t.PROJECT_ID = s.PID
                    WHEN MATCHED THEN UPDATE
                        SET t.PROJECT_NAME = '{proj_name_esc}',
                            t.DESCRIPTION  = '{proj_desc_esc}',
                            t.DSI_DB       = '{dsi_db}',
                            t.DSO_DB       = '{dso_db}',
                            t.WH_SIZE      = '{wh_size}'
                    WHEN NOT MATCHED THEN INSERT
                        (PROJECT_ID, PROJECT_NAME, DESCRIPTION, DSI_DB, DSO_DB, WH_SIZE, STATUS)
                        VALUES ('{proj_id}', '{proj_name_esc}', '{proj_desc_esc}',
                                '{dsi_db}', '{dso_db}', '{wh_size}', 'ACTIVE')
                """).collect()

                progress.progress(100, text="Terminé ✅")
                log_action("CREATE", "PROJECT", proj_id, "SUCCESS" if not errors else "PARTIAL",
                           {"dsi_db": dsi_db, "dso_db": dso_db, "wh": wh_name, "errors": errors})

                if errors:
                    st.warning(f"Projet créé avec avertissements sur : {', '.join(errors)}")
                else:
                    st.success(f"""
                    Projet **{proj_id}** créé avec succès !
                    - Warehouse : `{wh_name}`
                    - Base DSI  : `{dsi_db}`
                    - Base DSO  : `{dso_db}`
                    """)
                    st.info(
                        "**Rôles fonctionnels** — à créer manuellement par un ACCOUNTADMIN :\n\n"
                        "```sql\n"
                        f"USE ROLE ACCOUNTADMIN;\n"
                        f"CREATE ROLE IF NOT EXISTS ROLE_{proj_id}_ADMIN     COMMENT = 'Accès complet - {proj_id}';\n"
                        f"CREATE ROLE IF NOT EXISTS ROLE_{proj_id}_DEVELOPER  COMMENT = 'Dev DSI+DSO - {proj_id}';\n"
                        f"CREATE ROLE IF NOT EXISTS ROLE_{proj_id}_ANALYST    COMMENT = 'Lecture DSO - {proj_id}';\n"
                        "```"
                    )

# ── PAGE : Rôles ──────────────────────────────────────────────
elif page == "roles":
    st.title("👥 Gestion des rôles")

    tab_list, tab_grant = st.tabs(["📋 Rôles existants", "🔑 Attribution de privilèges"])

    with tab_list:
        roles_df = load_managed_roles()
        if roles_df.empty:
            st.info("Aucun rôle géré par Snowsled.")
        else:
            st.dataframe(roles_df, use_container_width=True)

        st.subheader("Rôles Snowflake du compte")
        all_roles = session.sql("SHOW ROLES").to_pandas()
        if not all_roles.empty:
            # Snowflake retourne les colonnes en minuscules ou majuscules selon le contexte
            all_roles.columns = [c.lower() for c in all_roles.columns]
            cols_to_show = [c for c in ["name", "owner", "comment", "created_on"] if c in all_roles.columns]
            st.dataframe(all_roles[cols_to_show], use_container_width=True)

    with tab_grant:
        st.subheader("Attribuer des privilèges à un rôle")
        projects_df = load_projects()

        if projects_df.empty:
            st.warning("Créez d'abord un projet dans l'onglet **Projets**.")
        else:
            proj_sel = st.selectbox(
                "Projet", options=projects_df["PROJECT_ID"].tolist(), key="grant_proj"
            )
            proj_row = projects_df[projects_df["PROJECT_ID"] == proj_sel].iloc[0]

            role_sel = st.selectbox(
                "Rôle cible",
                options=[f"ROLE_{proj_sel}_{r}" for r in ["ADMIN", "DEVELOPER", "ANALYST"]],
                key="grant_role"
            )
            priv_template = st.radio(
                "Modèle de privilèges",
                options=["ADMIN (full)", "DEVELOPER (read/write DSI + read DSO)", "ANALYST (read DSO)"],
                key="grant_template"
            )

            dsi = proj_row["DSI_DB"]
            dso = proj_row["DSO_DB"]
            wh  = f"WH_{proj_sel}"

            if "ADMIN" in priv_template:
                grants = [
                    f"GRANT ALL ON DATABASE {dsi} TO ROLE {role_sel}",
                    f"GRANT ALL ON DATABASE {dso} TO ROLE {role_sel}",
                    f"GRANT ALL ON ALL SCHEMAS IN DATABASE {dsi} TO ROLE {role_sel}",
                    f"GRANT ALL ON ALL SCHEMAS IN DATABASE {dso} TO ROLE {role_sel}",
                    f"GRANT USAGE ON WAREHOUSE {wh} TO ROLE {role_sel}",
                ]
            elif "DEVELOPER" in priv_template:
                grants = [
                    f"GRANT ALL    ON DATABASE {dsi} TO ROLE {role_sel}",
                    f"GRANT SELECT ON DATABASE {dso} TO ROLE {role_sel}",
                    f"GRANT ALL    ON ALL SCHEMAS IN DATABASE {dsi} TO ROLE {role_sel}",
                    f"GRANT SELECT ON ALL SCHEMAS IN DATABASE {dso} TO ROLE {role_sel}",
                    f"GRANT USAGE  ON WAREHOUSE {wh} TO ROLE {role_sel}",
                ]
            else:
                grants = [
                    f"GRANT SELECT ON DATABASE {dso} TO ROLE {role_sel}",
                    f"GRANT SELECT ON ALL SCHEMAS IN DATABASE {dso} TO ROLE {role_sel}",
                    f"GRANT USAGE  ON WAREHOUSE {wh} TO ROLE {role_sel}",
                ]

            # SQL toujours visible (CREATE ROLE + GRANTs) — copier/coller pour ACCOUNTADMIN
            full_sql = (
                f"USE ROLE ACCOUNTADMIN;\n"
                f"CREATE ROLE IF NOT EXISTS {role_sel};\n\n"
                + "\n".join(g + ";" for g in grants)
            )
            with st.expander("📋 SQL à exécuter en tant qu'ACCOUNTADMIN", expanded=True):
                st.caption(
                    "Ce bloc contient la création du rôle (si besoin) et l'attribution "
                    f"des privilèges **{priv_template.split('(')[0].strip()}**. "
                    "Copiez et exécutez dans un Worksheet Snowflake si les rôles n'existent pas encore."
                )
                st.code(full_sql, language="sql")

            st.markdown("---")

            # Bouton d'application directe (fonctionne si le rôle existe déjà)
            if st.button("⚡ Appliquer les privilèges directement", key="btn_grant"):
                try:
                    role_exists_df = session.sql(f"SHOW ROLES LIKE '{role_sel}'").to_pandas()
                    role_exists = len(role_exists_df) > 0
                except Exception:
                    role_exists = False

                if not role_exists:
                    st.error(
                        f"Le rôle **{role_sel}** n'existe pas sur ce compte. "
                        "Exécutez d'abord le SQL ci-dessus en tant qu'ACCOUNTADMIN."
                    )
                else:
                    grant_errors = []
                    for g in grants:
                        ok = run_sql(g)
                        if not ok:
                            grant_errors.append(g)

                    if not grant_errors:
                        log_action("GRANT", "ROLE", role_sel, "SUCCESS", {"template": priv_template})
                        st.success(f"Privilèges appliqués sur **{role_sel}**.")
                    else:
                        log_action("GRANT", "ROLE", role_sel, "PARTIAL", {"errors": grant_errors})
                        st.warning(f"{len(grants) - len(grant_errors)}/{len(grants)} privilèges appliqués sur **{role_sel}**.")

# ── PAGE : Journal d'audit ────────────────────────────────────
elif page == "audit":
    st.title("🔍 Journal d'audit")

    col1, col2, col3 = st.columns(3)
    with col1:
        filter_type = st.selectbox(
            "Type d'événement",
            options=["Tous", "CREATE", "UPDATE", "DELETE", "GRANT", "TEST"],
            key="audit_type"
        )
    with col2:
        filter_status = st.selectbox(
            "Statut", options=["Tous", "SUCCESS", "ERROR", "PARTIAL"],
            key="audit_status"
        )
    with col3:
        limit = st.number_input("Nombre de lignes", min_value=10, max_value=500, value=50)

    where_clauses = []
    if filter_type != "Tous":
        where_clauses.append(f"EVENT_TYPE = '{filter_type}'")
    if filter_status != "Tous":
        where_clauses.append(f"STATUS = '{filter_status}'")

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    audit_df = session.sql(f"""
        SELECT LOG_ID, EVENT_TIME, EVENT_TYPE, ACTOR,
               OBJECT_TYPE, OBJECT_NAME, STATUS, DETAILS::STRING AS DETAILS
        FROM AUDIT_SCHEMA.AUDIT_LOG
        {where_sql}
        ORDER BY EVENT_TIME DESC
        LIMIT {limit}
    """).to_pandas()

    if audit_df.empty:
        st.info("Aucune entrée d'audit pour les filtres sélectionnés.")
    else:
        st.dataframe(audit_df, use_container_width=True)
        st.caption(f"{len(audit_df)} entrée(s) affichée(s).")

# ── PAGE : Cortex AI Monitor ──────────────────────────────────
elif page == "cortex_agent":
    st.title("🤖 Cortex AI Monitor")
    st.caption(
        "Powered by Snowflake Cortex AI · "
        "[augustorosa/cortex-snowflake-account-security-agent]("
        "https://github.com/augustorosa/cortex-snowflake-account-security-agent)"
    )
    st.markdown(
        "Posez des questions en **langage naturel** sur votre compte Snowflake — "
        "sans écrire une seule ligne de SQL."
    )
    st.markdown("---")

    # ── Sélecteur d'agent ────────────────────────────────────
    AGENT_MAP = {
        "🎯 Généralist": {
            "fn":    "SNOWFLAKE_INTELLIGENCE.AGENTS.SNOWFLAKE_MAINTENANCE_AGENT",
            "label": "SNOWFLAKE_MAINTENANCE_AGENT",
            "desc":  "Perf · Sécurité · Coûts · Gouvernance · Tâches · Opérations avancées (24 tables)",
            "quick": [
                "What's my overall Snowflake account health?",
                "Show me total costs across all services this month",
                "Which users have failed logins AND expensive queries?",
                "What is my MFA adoption rate?",
                "What's my daily billable credit consumption trend?",
                "Which warehouses are most expensive this month?",
            ],
        },
        "💰 Cost & Performance": {
            "fn":    "SNOWFLAKE_INTELLIGENCE.AGENTS.COST_PERFORMANCE_AGENT",
            "label": "COST_PERFORMANCE_AGENT",
            "desc":  "Analyse requêtes, crédits warehouses, spilling, cache, attribution (2 tables)",
            "quick": [
                "What were the most expensive queries in the last hour?",
                "Which queries are spilling to disk?",
                "Show me failed queries with error details",
                "Which users are running the slowest queries?",
                "Which warehouses are consuming the most credits?",
                "Show queries with low cache hit rates",
            ],
        },
        "🔒 Security": {
            "fn":    "SNOWFLAKE_INTELLIGENCE.AGENTS.SECURITY_MONITORING_AGENT",
            "label": "SECURITY_MONITORING_AGENT",
            "desc":  "Logins, MFA, sessions, politiques mot de passe/session/réseau (6 tables)",
            "quick": [
                "Show me failed login attempts in the last 7 days",
                "Are there suspicious login attempts or brute force attacks?",
                "How many active sessions do we have right now?",
                "What is our MFA adoption rate for users?",
                "Show me users without MFA enabled",
                "Give me an overall security posture summary",
            ],
        },
    }

    agent_choice = st.radio(
        "**Agent :**",
        options=list(AGENT_MAP.keys()),
        horizontal=True,
        key="cortex_agent_choice",
    )
    current_agent = AGENT_MAP[agent_choice]
    st.caption(f'`{current_agent["label"]}` — {current_agent["desc"]}')
    st.markdown("---")

    # ── Vérification du statut de déploiement
    def check_agent_status():
        try:
            dbs = session.sql("SHOW DATABASES LIKE 'SNOWFLAKE_INTELLIGENCE'").collect()
            if not dbs:
                return "not_deployed"
            try:
                agents = session.sql(
                    "SHOW AGENTS IN SCHEMA SNOWFLAKE_INTELLIGENCE.AGENTS"
                ).collect()
                return "ready" if agents else "partial"
            except Exception:
                views = session.sql(
                    "SHOW SEMANTIC VIEWS IN SCHEMA SNOWFLAKE_INTELLIGENCE.TOOLS"
                ).collect()
                return "ready" if views else "partial"
        except Exception:
            return "unknown"

    agent_status = check_agent_status()

    status_col, btn_col = st.columns([4, 1])
    with status_col:
        if agent_status == "ready":
            st.success("✅ Cortex AI Monitor déployé et opérationnel (3 agents)")
        elif agent_status == "partial":
            st.warning("⚠️ Déploiement partiel — relancez le setup")
        else:
            st.error("❌ Agents non déployés — rendez-vous dans l'onglet Déploiement")
    with btn_col:
        if st.button("🔄 Rafraîchir", key="btn_check_agent"):
            st.rerun()

    tab_chat, tab_setup, tab_examples = st.tabs(
        ["💬 Assistant IA", "⚙️ Déploiement", "📚 Exemples de questions"]
    )

    # ────────────────────────────────────────────────────────
    # TAB : Assistant IA
    # ────────────────────────────────────────────────────────
    with tab_chat:
        if agent_status != "ready":
            st.info("👆 Déployez d'abord les agents dans l'onglet **Déploiement**.")
        else:
            history_key = f"cortex_history_{agent_choice}"
            if history_key not in st.session_state:
                st.session_state[history_key] = []

            # Historique de la conversation
            for msg in st.session_state[history_key]:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

            # Boutons de questions rapides
            st.markdown("**Questions rapides :**")
            quick_cols = st.columns(3)
            question = None
            for i, q in enumerate(current_agent["quick"]):
                label = q[:38] + "…" if len(q) > 38 else q
                with quick_cols[i % 3]:
                    if st.button(label, key=f"quick_{agent_choice}_{i}"):
                        question = q

            # Saisie libre
            free_input = st.chat_input("Posez votre question en français ou anglais…")
            if free_input:
                question = free_input

            if question:
                st.session_state[history_key].append(
                    {"role": "user", "content": question}
                )
                with st.chat_message("user"):
                    st.markdown(question)

                with st.chat_message("assistant"):
                    with st.spinner("Analyse en cours…"):
                        response = ""
                        agent_fn = current_agent["fn"]
                        # Essai 1 : agent Cortex natif
                        try:
                            res = session.sql(f"""
                                SELECT {agent_fn}(
                                    '{question.replace("'", "''")}'  
                                ) AS RESPONSE
                            """).collect()
                            response = res[0]["RESPONSE"] if res else ""
                        except Exception:
                            pass

                        # Fallback : CORTEX.COMPLETE avec contexte ACCOUNT_USAGE
                        if not response:
                            try:
                                ctx_row = session.sql("""
                                    SELECT OBJECT_CONSTRUCT(
                                        'failed_logins_24h', (
                                            SELECT COUNT(*)
                                            FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
                                            WHERE EVENT_TIMESTAMP > DATEADD(hour,-24,CURRENT_TIMESTAMP())
                                            AND IS_SUCCESS = 'NO'),
                                        'credits_used_today', (
                                            SELECT ROUND(SUM(CREDITS_USED),2)
                                            FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
                                            WHERE START_TIME >= CURRENT_DATE()),
                                        'total_users', (
                                            SELECT COUNT(*)
                                            FROM SNOWFLAKE.ACCOUNT_USAGE.USERS
                                            WHERE DELETED_ON IS NULL),
                                        'users_without_mfa', (
                                            SELECT COUNT(*)
                                            FROM SNOWFLAKE.ACCOUNT_USAGE.USERS
                                            WHERE DELETED_ON IS NULL AND HAS_MFA = FALSE)
                                    )::STRING AS CTX
                                """).collect()
                                ctx = ctx_row[0]["CTX"] if ctx_row else "{}"
                                prompt = (
                                    f"You are a Snowflake monitoring expert.\n"
                                    f"Current account metrics: {ctx}\n"
                                    f"Question: {question}\n"
                                    f"Provide a clear, concise answer with key metrics and recommendations. "
                                    f"Respond in the same language as the question."
                                )
                                resp = session.sql(f"""
                                    SELECT SNOWFLAKE.CORTEX.COMPLETE(
                                        'mistral-large2',
                                        '{prompt.replace(chr(39), chr(39)+chr(39))}'
                                    ) AS RESPONSE
                                """).collect()
                                response = resp[0]["RESPONSE"] if resp else "Aucune réponse."
                            except Exception as e2:
                                response = f"❌ Erreur lors de l'analyse : {e2}"

                        st.markdown(response)

                st.session_state[history_key].append(
                    {"role": "assistant", "content": response}
                )
                st.rerun()

            if st.session_state.get(history_key):
                if st.button("🗑️ Effacer la conversation", key=f"btn_clear_{agent_choice}"):
                    st.session_state[history_key] = []
                    st.rerun()

    # ────────────────────────────────────────────────────────
    # TAB : Déploiement
    # ────────────────────────────────────────────────────────
    with tab_setup:
        st.subheader("⚙️ Déploiement du Cortex AI Monitor")
        st.markdown("""
        Ce setup installe les composants suivants sur votre compte Snowflake :

        | Composant | Description |
        |---|---|
        | Base `SNOWFLAKE_INTELLIGENCE` | Namespace dédié au monitoring IA |
        | Vue sémantique `SNOWFLAKE_MAINTENANCE_SVW` | Tables `ACCOUNT_USAGE` enrichies (sécurité, coûts, perf, gouvernance) |
        | Agent IA `SNOWFLAKE_MAINTENANCE_AGENT` | Répond à vos questions en langage naturel |

        > **Source :** [augustorosa/cortex-snowflake-account-security-agent](https://github.com/augustorosa/cortex-snowflake-account-security-agent)
        """)

        with st.expander("Prérequis", expanded=(agent_status == "not_deployed")):
            items = [
                "Rôle `ACCOUNTADMIN` actif lors du déploiement",
                "Cortex AI disponible dans votre région "
                "([régions supportées](https://docs.snowflake.com/en/user-guide/ml-powered-features))",
                "Privilege `IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE` ✅ *(déjà déclaré dans le manifest)*",
            ]
            for item in items:
                st.markdown(f"- {item}")

        st.markdown("---")
        st.subheader("Étape 1 — Foundations (ACCOUNTADMIN requis)")
        st.markdown(
            "Exécutez ce script **une seule fois** dans un Worksheet Snowflake avec le rôle `ACCOUNTADMIN`. "
            "Il crée la base `SNOWFLAKE_INTELLIGENCE` et transfère la propriété à `ACCOUNTADMIN` "
            "pour permettre les GRANTs vers les rôles externes."
        )
        with st.expander("📋 Script 1 — Foundations", expanded=(agent_status != "ready")):
            try:
                app_name = session.sql("SELECT CURRENT_APPLICATION()").collect()[0][0]
            except Exception:
                app_name = "SNOWSLED_V2"
            st.code(f"""USE ROLE ACCOUNTADMIN;

-- Activer Cortex cross-region si nécessaire
ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';

-- Créer la base (CREATE OR REPLACE garantit que ACCOUNTADMIN en est propriétaire)
CREATE OR REPLACE DATABASE SNOWFLAKE_INTELLIGENCE;
CREATE SCHEMA SNOWFLAKE_INTELLIGENCE.AGENTS;
CREATE SCHEMA SNOWFLAKE_INTELLIGENCE.TOOLS;

-- Accès public à l'agent (grants possibles car ACCOUNTADMIN est propriétaire)
GRANT USAGE ON DATABASE SNOWFLAKE_INTELLIGENCE          TO ROLE PUBLIC;
GRANT USAGE ON SCHEMA   SNOWFLAKE_INTELLIGENCE.AGENTS   TO ROLE PUBLIC;
GRANT USAGE ON SCHEMA   SNOWFLAKE_INTELLIGENCE.TOOLS    TO ROLE PUBLIC;
GRANT SELECT ON FUTURE SEMANTIC VIEWS
    IN SCHEMA SNOWFLAKE_INTELLIGENCE.TOOLS               TO ROLE PUBLIC;
GRANT USAGE ON FUTURE AGENTS
    IN SCHEMA SNOWFLAKE_INTELLIGENCE.AGENTS              TO ROLE PUBLIC;

-- Permettre à l'application de créer la vue sémantique et l'agent
GRANT USAGE ON DATABASE SNOWFLAKE_INTELLIGENCE              TO APPLICATION {app_name};
GRANT USAGE ON SCHEMA   SNOWFLAKE_INTELLIGENCE.AGENTS       TO APPLICATION {app_name};
GRANT USAGE ON SCHEMA   SNOWFLAKE_INTELLIGENCE.TOOLS        TO APPLICATION {app_name};
GRANT CREATE SEMANTIC VIEW ON SCHEMA SNOWFLAKE_INTELLIGENCE.TOOLS   TO APPLICATION {app_name};
GRANT CREATE AGENT ON SCHEMA SNOWFLAKE_INTELLIGENCE.AGENTS          TO APPLICATION {app_name};
""", language="sql")

        st.markdown("---")
        st.subheader("Étape 2 — Déploiement des vues sémantiques et des agents")
        st.markdown(
            "Une fois le Script 1 exécuté, cliquez sur le bouton ci-dessous pour créer "
            "les **3 vues sémantiques** et les **3 agents Cortex AI**."
        )
        st.markdown("""
        | Vue sémantique | Agent | Domaine |
        |---|---|---|
        | `COST_PERFORMANCE_SVW` | `COST_PERFORMANCE_AGENT` | Perf / Coûts (2 tables) |
        | `SECURITY_MONITORING_SVW` | `SECURITY_MONITORING_AGENT` | Sécurité (6 tables) |
        | `SNOWFLAKE_MAINTENANCE_SVW` | `SNOWFLAKE_MAINTENANCE_AGENT` | Généralist (24 tables) |
        """)

        if agent_status == "ready":
            st.success("Les 3 agents sont déjà déployés. Aucune action requise.")
        else:
            if st.button(
                "🚀 Déployer la vue sémantique + agent",
                key="btn_deploy_cortex",
                type="primary",
            ):
                with st.spinner("Déploiement en cours… (1-3 minutes)"):
                    try:
                        result = session.call("APP_SCHEMA.DEPLOY_CORTEX_AGENT")
                        result = json.loads(result) if isinstance(result, str) else result
                        succeeded = result.get("success", False)

                        if succeeded:
                            st.success("✅ Déploiement terminé avec succès !")
                        else:
                            st.warning("Déploiement terminé avec des avertissements.")

                        for step in result.get("steps", []):
                            st.markdown(f"- ✅ {step}")
                        for err in result.get("errors", []):
                            st.markdown(f"- ❌ {err}")

                        log_action(
                            "DEPLOY", "CORTEX_AGENT",
                            "SNOWFLAKE_INTELLIGENCE",
                            "SUCCESS" if succeeded else "PARTIAL",
                            result,
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur lors du déploiement : {e}")

        st.markdown("---")
        st.markdown(
            "> 💡 Si le déploiement automatique (Étape 2) échoue, vous pouvez déployer manuellement "
            "les vues sémantiques et agents depuis GitHub :"
        )
        with st.expander("Scripts manuels (GitHub)"):
            st.markdown("""
**Vues sémantiques :**
- [Script 2 — Vue Généralist (24 tables)](https://github.com/augustorosa/cortex-snowflake-account-security-agent/blob/main/scripts/2.%20SNOWFLAKE_MAINTENANCE_SVW_GENERALIST.sql)
- [Script 2.2 — Vue Cost & Performance](https://github.com/augustorosa/cortex-snowflake-account-security-agent/blob/main/scripts/2.2%20COST_PERFORMANCE_SVW_SPECIALIST.sql)
- [Script 2.3 — Vue Security Monitoring](https://github.com/augustorosa/cortex-snowflake-account-security-agent/blob/main/scripts/2.3%20SECURITY_MONITORING_SVW_SPECIALIST.sql)

**Agents Cortex :**
- [Script 3 — Agent Généralist](https://github.com/augustorosa/cortex-snowflake-account-security-agent/blob/main/scripts/3.%20SNOWFLAKE_MAINTENANCE_AGENT_GENERALIST.sql)
- [Script 5.2 — Agent Cost & Performance](https://github.com/augustorosa/cortex-snowflake-account-security-agent/blob/main/scripts/5.2%20COST_PERFORMANCE_AGENT_SPECIALIST.sql)
- [Script 5.3 — Agent Security](https://github.com/augustorosa/cortex-snowflake-account-security-agent/blob/main/scripts/5.3%20SECURITY_MONITORING_AGENT_SPECIALIST.sql)
            """)

    # ────────────────────────────────────────────────────────
    # TAB : Exemples
    # ────────────────────────────────────────────────────────
    with tab_examples:
        st.subheader("📚 Exemples de questions par agent")

        agent_examples = {
            "🎯 Généralist — SNOWFLAKE_MAINTENANCE_AGENT": {
                "desc": "Analyses croisées multi-domaines (24 tables ACCOUNT_USAGE)",
                "qs": [
                    "What's my overall Snowflake account health?",
                    "Show me total costs across all services this month",
                    "Which users have both failed logins and expensive queries?",
                    "What is my MFA adoption rate?",
                    "How much data has Snowpipe loaded this month?",
                    "What are my automatic clustering costs?",
                    "What is my daily billable credit consumption trend?",
                    "Which warehouses are most expensive and have the most failed queries?",
                    "Show me storage growth over the last 30 days",
                    "What are my total replication costs?",
                ],
            },
            "💰 Cost & Performance — COST_PERFORMANCE_AGENT": {
                "desc": "Optimisation des requêtes, crédits, spilling, cache (2 tables)",
                "qs": [
                    "What were the most expensive queries in the last hour?",
                    "Which queries are spilling to disk?",
                    "Show me failed queries with error details",
                    "Which users are running the slowest queries?",
                    "Which warehouses are consuming the most credits?",
                    "Show queries with low cache hit rates",
                    "What is the average query execution time by warehouse?",
                    "Show me queries with queued provisioning time > 5 seconds",
                ],
            },
            "🔒 Security — SECURITY_MONITORING_AGENT": {
                "desc": "Logins, MFA, sessions, politiques de sécurité (6 tables)",
                "qs": [
                    "Show me failed login attempts in the last 7 days",
                    "Are there suspicious login attempts or brute force attacks?",
                    "How many active sessions do we have right now?",
                    "What is our MFA adoption rate for users?",
                    "Show me users without MFA enabled",
                    "How strong are our password policies?",
                    "Do we have network policies configured?",
                    "What are our session timeout settings?",
                    "Give me an overall security posture summary",
                    "Which IPs have the most failed login attempts?",
                ],
            },
        }

        for agent_name, data in agent_examples.items():
            st.markdown(f"**{agent_name}**")
            st.caption(data["desc"])
            for q in data["qs"]:
                st.code(q, language="text")
            st.markdown("")
