import streamlit as st
import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
import os
from snowflake.snowpark.functions import col, lit

# utils/ is copied into this directory by snowflake.yml artifacts mapping
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
# local dev fallback: utils is one level up under src/
_src = os.path.join(_here, "..")
if _src not in sys.path:
    sys.path.insert(0, _src)
from utils.session import get_session

# --------- CONFIGURATION ---------
APP_TITLE = "Snowflake FinOps Monitor"
CREDIT_COST_USD = 4  # Coût par crédit en USD (à ajuster selon votre contrat)

# Schéma de monitoring (tables créées par setup_script.sql dans l'app)
MONITORING_SCHEMA = "CONFIG_SCHEMA"


# --------- UTILS ---------
_ACCOUNT_USAGE_OK = None  # cache du résultat de la vérification du grant


def check_account_usage(session) -> bool:
    """Vérifie que SNOWFLAKE.ACCOUNT_USAGE est accessible."""
    global _ACCOUNT_USAGE_OK
    if _ACCOUNT_USAGE_OK is not None:
        return _ACCOUNT_USAGE_OK
    try:
        session.sql("SELECT 1 FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY LIMIT 1").collect()
        _ACCOUNT_USAGE_OK = True
    except Exception:
        _ACCOUNT_USAGE_OK = False
    return _ACCOUNT_USAGE_OK


def run_query(_session, sql):
    """Exécute une requête SQL et retourne un DataFrame pandas.
    Les erreurs liées à SNOWFLAKE.ACCOUNT_USAGE non autorisé sont silencieuses
    (le bandeau d'avertissement en haut de page suffit)."""
    try:
        return _session.sql(sql).to_pandas()
    except Exception as e:
        msg = str(e)
        if "not authorized" in msg or "does not exist or not authorized" in msg:
            return pd.DataFrame()
        st.error(f"Erreur lors de l'execution de la requete: {e}")
        return pd.DataFrame()


def format_datetime_for_sql(dt):
    """Formate un datetime pour utilisation dans une requête SQL Snowflake"""
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def get_period_filter(start_dt, end_dt, date_column="start_time"):
    """Génère la clause WHERE pour filtrer sur une période"""
    start_str = format_datetime_for_sql(start_dt)
    end_str = format_datetime_for_sql(end_dt)
    return f"{date_column} >= '{start_str}' AND {date_column} <= '{end_str}'"


def get_status_color(status):
    """Retourne la couleur associée à un statut"""
    if 'OK' in status or '✅' in status:
        return 'green'
    elif 'MONITORING' in status or '⚠️' in status:
        return 'orange'
    elif 'ACTION' in status or '🟠' in status:
        return 'darkorange'
    elif 'CRITICAL' in status or '🔴' in status:
        return 'red'
    elif 'SUSPENDED' in status or 'EXCEEDED' in status or '🛑' in status:
        return 'darkred'
    return 'gray'


def quote_list_for_sql(str_list: list[str]) -> str:
    """
    Convertit ["XSMALL", "LARGE"] en "'XSMALL','LARGE'"
    en échappant correctement les quotes simples.
    """
    safe = []
    for s in str_list:
        s = "" if s is None else str(s)
        s = s.replace("'", "''")  # escape SQL pour ' -> ''
        safe.append(f"'{s}'")
    return ", ".join(safe)


# --------- FONCTIONS DE REQUÊTES ---------
def get_warehouse_status(session):
    """Récupère le statut des warehouses depuis ACCOUNT_USAGE"""
    sql = f"""
        SELECT 
            wc.warehouse_name,
            wc.frequency,
            wc.credit_limit,
            COALESCE(u.credits_used, 0) AS credits_used,
            ROUND(COALESCE(u.credits_used, 0) / wc.credit_limit * 100, 1) AS pct_used,
            wc.auto_suspend_at_100,
            CASE 
                WHEN COALESCE(u.credits_used, 0) / wc.credit_limit >= 1 THEN '🛑 SUSPENDED'
                WHEN COALESCE(u.credits_used, 0) / wc.credit_limit >= 0.95 THEN '🔴 CRITICAL'
                WHEN COALESCE(u.credits_used, 0) / wc.credit_limit >= 0.85 THEN '🟠 ACTION REQUIRED'
                WHEN COALESCE(u.credits_used, 0) / wc.credit_limit >= 0.70 THEN '⚠️ MONITORING'
                ELSE '✅ OK'
            END AS status,
            wc.credit_limit - COALESCE(u.credits_used, 0) AS credits_remaining,
            ARRAY_TO_STRING(wc.alert_emails, ', ') AS alert_recipients,
            COALESCE(u.max_time, CURRENT_TIMESTAMP()) AS data_as_of
        FROM {MONITORING_SCHEMA}.WAREHOUSE_CONFIG wc
        LEFT JOIN (
            SELECT 
                warehouse_name, 
                SUM(credits_used) AS credits_used,
                MAX(end_time) AS max_time
            FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
            WHERE start_time >= CURRENT_DATE()
            GROUP BY warehouse_name
        ) u ON wc.warehouse_name = u.warehouse_name
        WHERE wc.is_active = TRUE
        ORDER BY pct_used DESC
    """
    return run_query(session, sql)


def get_warehouse_credits(session, start_dt, end_dt):
    """Récupère les crédits warehouses depuis ACCOUNT_USAGE"""
    start_str = format_datetime_for_sql(start_dt)
    end_str = format_datetime_for_sql(end_dt)

    sql = f"""
        SELECT 
            warehouse_name,
            DATE_TRUNC('hour', start_time) AS period,
            ROUND(SUM(credits_used), 4) AS credits_used
        FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
        WHERE start_time >= '{start_str}'
          AND start_time <= '{end_str}'
        GROUP BY warehouse_name, DATE_TRUNC('hour', start_time)
        ORDER BY period
    """
    return run_query(session, sql)


def get_warehouse_total_credits(session, start_dt, end_dt):
    """Récupère le total des crédits warehouses"""
    start_str = format_datetime_for_sql(start_dt)
    end_str = format_datetime_for_sql(end_dt)

    sql = f"""
        SELECT COALESCE(SUM(credits_used), 0) AS total
        FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
        WHERE start_time >= '{start_str}'
          AND start_time <= '{end_str}'
    """
    return run_query(session, sql)


# --------- MAIN APP ---------
def main():
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="❄️",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    session = get_session()

    # --------- SIDEBAR : FILTRES GLOBAUX ---------
    with st.sidebar:
        st.title("⚙️ Filtres globaux")
        st.markdown("---")

        # Avertissement latence
        st.info("ℹ️ **Source: ACCOUNT_USAGE**\nLatence des données: 1-3h")

        st.markdown("---")

        # Dates par défaut
        today = datetime.date.today()
        now = datetime.datetime.now()

        # Initialiser les valeurs par défaut
        if 'period_shortcut' not in st.session_state:
            st.session_state.period_shortcut = None

        # Appliquer le raccourci si un a été sélectionné
        shortcut = st.session_state.period_shortcut
        if shortcut == "last_hour":
            default_start_date = today
            default_start_time = (now - datetime.timedelta(hours=1)).time()
            default_end_date = today
            default_end_time = now.time()
            st.session_state.period_shortcut = None  # Reset après application
        elif shortcut == "last_24h":
            default_start_date = today - datetime.timedelta(days=1)
            default_start_time = now.time()
            default_end_date = today
            default_end_time = now.time()
            st.session_state.period_shortcut = None
        elif shortcut == "last_7d":
            default_start_date = today - datetime.timedelta(days=7)
            default_start_time = datetime.time(0, 0)
            default_end_date = today
            default_end_time = datetime.time(23, 59)
            st.session_state.period_shortcut = None
        elif shortcut == "last_30d":
            default_start_date = today - datetime.timedelta(days=30)
            default_start_time = datetime.time(0, 0)
            default_end_date = today
            default_end_time = datetime.time(23, 59)
            st.session_state.period_shortcut = None
        else:
            # Valeurs par défaut (7 derniers jours)
            default_start_date = today - datetime.timedelta(days=7)
            default_start_time = datetime.time(0, 0)
            default_end_date = today
            default_end_time = datetime.time(23, 59)

        st.subheader("📅 Période d'analyse")

        # Date et heure de DÉBUT
        st.markdown("**Début**")
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input(
                "Date début",
                value=default_start_date,
                key="start_date_input",
                label_visibility="collapsed"
            )
        with col2:
            start_time = st.time_input(
                "Heure début",
                value=default_start_time,
                key="start_time_input",
                label_visibility="collapsed"
            )

        # Date et heure de FIN
        st.markdown("**Fin**")
        col3, col4 = st.columns(2)
        with col3:
            end_date = st.date_input(
                "Date fin",
                value=default_end_date,
                key="end_date_input",
                label_visibility="collapsed"
            )
        with col4:
            end_time = st.time_input(
                "Heure fin",
                value=default_end_time,
                key="end_time_input",
                label_visibility="collapsed"
            )

        # Combiner date et heure
        start_datetime = datetime.datetime.combine(start_date, start_time)
        end_datetime = datetime.datetime.combine(end_date, end_time)

        # Validation
        if start_datetime >= end_datetime:
            st.error("⚠️ La date de début doit être antérieure à la date de fin")
            return

        # Afficher la période sélectionnée
        duration = end_datetime - start_datetime
        st.info(f"📊 Période: **{duration.days}j {duration.seconds // 3600}h**")

        st.markdown("---")

        # Raccourcis de période
        st.subheader("⏱️ Raccourcis")

        if 'period_shortcut' not in st.session_state:
            st.session_state.period_shortcut = None

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Dernière heure", key="btn_last_hour"):
                st.session_state.period_shortcut = "last_hour"
                st.rerun()
            if st.button("Dernières 24h", key="btn_last_24h"):
                st.session_state.period_shortcut = "last_24h"
                st.rerun()
        with col_b:
            if st.button("7 derniers jours", key="btn_last_7d"):
                st.session_state.period_shortcut = "last_7d"
                st.rerun()
            if st.button("30 derniers jours", key="btn_last_30d"):
                st.session_state.period_shortcut = "last_30d"
                st.rerun()

        st.markdown("---")
        st.markdown(f"💰 **Coût crédit:** ${CREDIT_COST_USD}/crédit")

    # Vérification du grant ACCOUNT_USAGE dès l'entrée dans main()
    if not check_account_usage(session):
        st.error(
            "**Accès SNOWFLAKE.ACCOUNT_USAGE non autorisé**\n\n"
            "Le dashboard FinOps nécessite le privilege suivant. "
            "Demandez a un ACCOUNTADMIN d'executer dans un Worksheet Snowflake :\n\n"
            "```sql\n"
            "USE ROLE ACCOUNTADMIN;\n"
            "GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO APPLICATION SNOWSLED_V2;\n"
            "```\n\n"
            "Rechargez ensuite cette page."
        )
        st.stop()

    # Générer le filtre de période pour les requêtes
    period_filter = get_period_filter(start_datetime, end_datetime)
    start_str = format_datetime_for_sql(start_datetime)
    end_str = format_datetime_for_sql(end_datetime)

    # ----------------- MENUS PAR THÉMATIQUE -----------------
    main_tabs = st.tabs([
        "🏠 Vue d'ensemble",
        "🏭 Monitoring Warehouses",
        "⚡ Monitoring Serverless",
        "💰 Consommation & Coût",
        "🚀 Performance & Requêtes",
        "🔐 Sécurité & Connexions",
        "💾 Stockage & Données"
    ])

    # ----------- VUE D'ENSEMBLE -----------
    with main_tabs[0]:
        st.header("🏠 Vue d'ensemble")
        st.markdown(
            f"**Période analysée:** {start_datetime.strftime('%d/%m/%Y %H:%M')} → {end_datetime.strftime('%d/%m/%Y %H:%M')}")
        st.caption("📊 Source: ACCOUNT_USAGE (latence 1-3h)")

        st.markdown("---")

        # KPIs principaux
        col1, col2, col3, col4 = st.columns(4)

        # Total crédits warehouses
        wh_credits_df = get_warehouse_total_credits(session, start_datetime, end_datetime)
        total_wh_credits = float(wh_credits_df['TOTAL'].iloc[0]) if not wh_credits_df.empty else 0

        # Total crédits serverless
        sql_sl_credits = f"""
            SELECT COALESCE(SUM(credits_used), 0) as total
            FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
            WHERE {period_filter}
              AND service_type NOT IN ('WAREHOUSE_METERING')
        """
        sl_credits = run_query(session, sql_sl_credits)
        total_sl_credits = float(sl_credits['TOTAL'].iloc[0]) if not sl_credits.empty else 0

        # Total requêtes
        sql_queries = f"""
            SELECT COUNT(*) as total
            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
            WHERE {period_filter}
        """
        queries = run_query(session, sql_queries)
        total_queries = int(queries['TOTAL'].iloc[0]) if not queries.empty else 0

        # Coût total estimé
        total_credits = total_wh_credits + total_sl_credits
        total_cost = total_credits * CREDIT_COST_USD

        with col1:
            st.metric(
                "💳 Crédits Warehouses",
                f"{total_wh_credits:,.2f}",
                help="Crédits consommés par les warehouses"
            )
        with col2:
            st.metric(
                "⚡ Crédits Serverless",
                f"{total_sl_credits:,.2f}",
                help="Crédits consommés par les services serverless"
            )
        with col3:
            st.metric(
                "📊 Requêtes exécutées",
                f"{total_queries:,}",
                help="Nombre total de requêtes"
            )
        with col4:
            st.metric(
                "💰 Coût estimé",
                f"${total_cost:,.2f}",
                help=f"Basé sur ${CREDIT_COST_USD}/crédit"
            )

        st.markdown("---")

        # Statut rapide des warehouses monitorés
        st.subheader("🚦 Statut des Warehouses Monitorés")

        wh_status_df = get_warehouse_status(session)

        if not wh_status_df.empty:
            if 'DATA_AS_OF' in wh_status_df.columns:
                data_time = wh_status_df['DATA_AS_OF'].iloc[0]
                st.caption(f"📅 Données jusqu'à: {data_time}")

            col_a, col_b, col_c, col_d = st.columns(4)

            with col_a:
                ok_count = len(wh_status_df[wh_status_df['STATUS'].str.contains('OK', na=False)])
                st.metric("✅ OK", ok_count)
            with col_b:
                monitoring_count = len(wh_status_df[wh_status_df['STATUS'].str.contains('MONITORING', na=False)])
                st.metric("⚠️ Monitoring", monitoring_count)
            with col_c:
                action_count = len(wh_status_df[wh_status_df['STATUS'].str.contains('ACTION', na=False)])
                st.metric("🟠 Action requise", action_count)
            with col_d:
                critical_count = len(wh_status_df[
                                         wh_status_df['STATUS'].str.contains('CRITICAL|SUSPENDED|EXCEEDED', na=False,
                                                                             regex=True)])
                st.metric("🔴 Critique", critical_count)

            display_cols = ['WAREHOUSE_NAME', 'FREQUENCY', 'CREDITS_USED', 'CREDIT_LIMIT', 'PCT_USED', 'STATUS',
                            'CREDITS_REMAINING']
            st.dataframe(
                wh_status_df[[c for c in display_cols if c in wh_status_df.columns]],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Aucun warehouse configuré dans le monitoring")

        st.markdown("---")

        col_left, col_right = st.columns(2)

        with col_left:
            st.subheader("📊 Répartition Warehouse vs Serverless")

            if total_credits > 0:
                pie_data = pd.DataFrame({
                    'Category': ['Warehouses', 'Serverless'],
                    'Credits': [total_wh_credits, total_sl_credits]
                })
                fig = px.pie(
                    pie_data,
                    values='Credits',
                    names='Category',
                    color_discrete_sequence=['#1f77b4', '#ff7f0e']
                )
                st.plotly_chart(fig, use_container_width=True, key="overview_pie_wh_vs_sl")
            else:
                st.info("Aucune donnée pour cette période")

        with col_right:
            st.subheader("📈 Évolution des crédits")

            wh_evolution = get_warehouse_credits(session, start_datetime, end_datetime)

            if not wh_evolution.empty:
                wh_hourly = wh_evolution.groupby('PERIOD')['CREDITS_USED'].sum().reset_index()
                wh_hourly['CATEGORY'] = 'Warehouse'

                sql_sl_evolution = f"""
                    SELECT 
                        DATE_TRUNC('hour', start_time) as PERIOD,
                        'Serverless' as CATEGORY,
                        SUM(credits_used) as CREDITS_USED
                    FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
                    WHERE {period_filter}
                      AND service_type NOT IN ('WAREHOUSE_METERING')
                    GROUP BY 1, 2
                    ORDER BY PERIOD
                """
                sl_evolution = run_query(session, sql_sl_evolution)

                if not sl_evolution.empty:
                    combined_df = pd.concat([wh_hourly, sl_evolution], ignore_index=True)
                else:
                    combined_df = wh_hourly

                fig = px.line(
                    combined_df,
                    x='PERIOD',
                    y='CREDITS_USED',
                    color='CATEGORY',
                    title="Crédits par heure"
                )
                st.plotly_chart(fig, use_container_width=True, key="overview_line_evolution")
            else:
                st.info("Aucune donnée pour cette période")

    # ----------- MONITORING WAREHOUSES -----------
    with main_tabs[1]:
        st.header("🏭 Monitoring des Warehouses")
        st.caption("📊 Source: ACCOUNT_USAGE (latence 1-3h)")

        sub_tabs = st.tabs([
            "📊 Statut actuel",
            "🚨 Historique Alertes",
            "📈 Consommation",
            "⚙️ Exécutions Monitoring",
            "🔧 Configuration"
        ])

        # Statut actuel
        with sub_tabs[0]:
            st.subheader("📊 Statut des Warehouses")

            df = get_warehouse_status(session)

            if not df.empty:
                if 'DATA_AS_OF' in df.columns:
                    st.info(f"📅 Données jusqu'à: {df['DATA_AS_OF'].iloc[0]}")

                num_warehouses = len(df)
                cols_per_row = min(4, num_warehouses)

                for idx, row in df.iterrows():
                    if idx % cols_per_row == 0:
                        cols = st.columns(cols_per_row)

                    col_idx = idx % cols_per_row
                    with cols[col_idx]:
                        pct = float(row['PCT_USED']) if row['PCT_USED'] else 0

                        if pct >= 100:
                            color = "red"
                        elif pct >= 85:
                            color = "orange"
                        elif pct >= 70:
                            color = "yellow"
                        else:
                            color = "green"

                        fig = go.Figure(go.Indicator(
                            mode="gauge+number",
                            value=pct,
                            title={'text': row['WAREHOUSE_NAME'][:20]},
                            gauge={
                                'axis': {'range': [0, 120]},
                                'bar': {'color': color},
                                'steps': [
                                    {'range': [0, 70], 'color': "lightgreen"},
                                    {'range': [70, 85], 'color': "lightyellow"},
                                    {'range': [85, 100], 'color': "lightsalmon"},
                                    {'range': [100, 120], 'color': "lightcoral"}
                                ],
                                'threshold': {
                                    'line': {'color': "red", 'width': 4},
                                    'thickness': 0.75,
                                    'value': 100
                                }
                            }
                        ))
                        fig.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=20))
                        st.plotly_chart(fig, use_container_width=True, key=f"wh_gauge_{idx}")

                st.markdown("---")
                st.subheader("📋 Détail")
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info(
                    "Aucun warehouse configuré.\n\n"
                    "Ajoutez des warehouses à monitorer dans l'onglet **⚙️ Configuration**."
                )

        # Historique Alertes
        with sub_tabs[1]:
            st.subheader("🚨 Historique des Alertes Warehouses")

            sql = f"""
                SELECT * FROM {MONITORING_SCHEMA}.V_ALERT_HISTORY
                WHERE event_time >= '{start_str}'
                  AND event_time <= '{end_str}'
                ORDER BY event_time DESC
                LIMIT 200
            """
            df = run_query(session, sql)

            if not df.empty:
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total alertes", len(df))
                with col2:
                    sent_count = df[df['SENT'] == '✓'].shape[0] if 'SENT' in df.columns else 0
                    st.metric("Emails envoyés", sent_count)
                with col3:
                    critical_count = \
                    df[df['ALERT_TYPE'].str.contains('CRITICAL|SUSPENDED|95|100', na=False, regex=True)].shape[0]
                    st.metric("Alertes critiques", critical_count)
                with col4:
                    wh_count = df['WAREHOUSE_NAME'].nunique()
                    st.metric("Warehouses alertés", wh_count)

                alert_counts = df.groupby('ALERT_TYPE').size().reset_index(name='count')
                fig = px.pie(alert_counts, values='count', names='ALERT_TYPE', title="Répartition par type d'alerte")
                st.plotly_chart(fig, use_container_width=True, key="wh_alert_pie")

                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.success("✅ Aucune alerte pour cette période")

        # Consommation
        with sub_tabs[2]:
            st.subheader("📈 Consommation par Warehouse")

            granularity = st.radio(
                "Granularité",
                ["Horaire", "Journalière", "Mensuelle"],
                horizontal=True,
                key="wh_consumption_granularity"
            )

            if granularity == "Horaire":
                df = get_warehouse_credits(session, start_datetime, end_datetime)
                x_col = 'PERIOD'
            elif granularity == "Journalière":
                sql = f"""
                    SELECT 
                        warehouse_name,
                        DATE_TRUNC('day', start_time) AS day_date,
                        ROUND(SUM(credits_used), 4) AS credits_used
                    FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
                    WHERE start_time >= '{start_str}'
                      AND start_time <= '{end_str}'
                    GROUP BY warehouse_name, DATE_TRUNC('day', start_time)
                    ORDER BY warehouse_name, day_date
                """
                df = run_query(session, sql)
                x_col = 'DAY_DATE'
            else:
                sql = f"""
                    SELECT 
                        warehouse_name,
                        DATE_TRUNC('month', start_time) AS month_date,
                        ROUND(SUM(credits_used), 2) AS credits_used
                    FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
                    WHERE start_time >= DATEADD('month', -12, CURRENT_DATE())
                    GROUP BY warehouse_name, DATE_TRUNC('month', start_time)
                    ORDER BY warehouse_name, month_date
                """
                df = run_query(session, sql)
                x_col = 'MONTH_DATE'

            if not df.empty:
                fig = px.line(
                    df,
                    x=x_col,
                    y='CREDITS_USED',
                    color='WAREHOUSE_NAME',
                    title=f"Évolution ({granularity.lower()})",
                    markers=True
                )
                st.plotly_chart(fig, use_container_width=True, key="wh_consumption_line")

                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Aucune donnée de consommation")

        # Historique exécutions monitoring
        with sub_tabs[3]:
            st.subheader("⚙️ Historique des Exécutions du Monitoring")

            sql = f"""
                SELECT * FROM {MONITORING_SCHEMA}.V_EXECUTION_HISTORY
                WHERE execution_time >= '{start_str}'
                  AND execution_time <= '{end_str}'
                ORDER BY execution_time DESC
                LIMIT 100
            """
            df = run_query(session, sql)

            if not df.empty:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total exécutions", len(df))
                with col2:
                    success_count = df[df['STATUS'] == 'SUCCESS'].shape[0]
                    st.metric("Succès", success_count)
                with col3:
                    error_count = df[df['STATUS'] == 'ERROR'].shape[0]
                    st.metric("Erreurs", error_count)

                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Aucune exécution enregistrée pour cette période")

        # Configuration
        with sub_tabs[4]:
            st.subheader("🔧 Configuration des Warehouses Monitorés")

            sql = f"SELECT * FROM {MONITORING_SCHEMA}.WAREHOUSE_CONFIG ORDER BY warehouse_name"

            if 'old_df' not in st.session_state:
                st.session_state.old_df = run_query(session, sql)

            df = st.session_state.old_df

            if not df.empty:
                edited_df = st.data_editor(df, key="config_editor", column_config={
                    "WAREHOUSE_NAME": st.column_config.TextColumn(disabled=True),
                    "CREATED_AT": st.column_config.DatetimeColumn(disabled=True),
                    "FREQUENCY": st.column_config.SelectboxColumn(
                        "FREQUENCY",
                        options=["DAILY", "WEEKLY", "MONTHLY", "YEARLY", "NEVER"],
                        required=True
                    )
                }, hide_index=True)

                if st.button("💾 Save"):
                    diff = edited_df.merge(df, how='outer', indicator=True).query('_merge == "left_only"').drop(
                        '_merge', axis=1)

                    # FIX: initialiser avant le bloc conditionnel pour éviter un NameError
                    updates = 0
                    updated_wh = []

                    if not diff.empty:
                        for _, r in diff.iterrows():
                            quota = int(r["CREDIT_LIMIT"])
                            if quota < 0:
                                st.error(f"Quota invalide pour {r['WAREHOUSE_NAME']}")
                                continue

                            session.table(f"{MONITORING_SCHEMA}.WAREHOUSE_CONFIG").update(
                                assignments={
                                    "CREDIT_LIMIT": lit(quota),
                                    "AUTO_SUSPEND_AT_100": lit(bool(r["AUTO_SUSPEND_AT_100"])),
                                    "ALERT_THRESHOLD_70": lit(bool(r["ALERT_THRESHOLD_70"])),
                                    "ALERT_THRESHOLD_85": lit(bool(r["ALERT_THRESHOLD_85"])),
                                    "ALERT_THRESHOLD_95": lit(bool(r["ALERT_THRESHOLD_95"])),
                                    "ALERT_EMAILS": lit(r["ALERT_EMAILS"]),
                                    "IS_ACTIVE": lit(bool(r["IS_ACTIVE"])),
                                    "FREQUENCY": lit(str(r["FREQUENCY"]))
                                },
                                condition=col("WAREHOUSE_NAME") == lit(r["WAREHOUSE_NAME"])
                            )
                            updated_wh.append(r["WAREHOUSE_NAME"])
                            updates += 1

                        # Synchroniser les limites Snowflake RESOURCE MONITORs
                        for wh in updated_wh:
                            wh_row = updated_df[updated_df["WAREHOUSE_NAME"] == wh].iloc[0]
                            monitor_name = f"RM_{wh}"
                            credit_lim   = int(wh_row["CREDIT_LIMIT"])
                            try:
                                session.sql(f"""
                                    CREATE OR REPLACE RESOURCE MONITOR {monitor_name}
                                    WITH CREDIT_QUOTA = {credit_lim}
                                    TRIGGERS ON {int(wh_row.get('ALERT_THRESHOLD_85', True) and 85 or 95)} PERCENT DO NOTIFY
                                             ON 100 PERCENT DO {'SUSPEND' if wh_row.get('AUTO_SUSPEND_AT_100') else 'NOTIFY'}
                                """).collect()
                                session.sql(f"""
                                    ALTER WAREHOUSE {wh} SET RESOURCE_MONITOR = {monitor_name}
                                """).collect()
                            except Exception as e:
                                st.warning(
                                    f"⚠️ Resource Monitor `{monitor_name}` non appliqué sur `{wh}` : {e}\n\n"
                                    "Les quotas Snowsled sont sauvegardés, mais le Resource Monitor "
                                    "Snowflake natif nécessite le privilège `MONITOR USAGE` sur le compte."
                                )

                    st.success(f"{updates} ligne(s) mise(s) à jour.")
                    if updated_wh:
                        st.info("Warehouses modifiés :")
                        for wh in updated_wh:
                            st.write(f"- **{wh}**")

                else:
                    st.info("Aucun changement détecté.")
            else:
                st.warning("Table WAREHOUSE_CONFIG non trouvée ou vide")

    # ----------- MONITORING SERVERLESS -----------
    with main_tabs[2]:
        st.header("⚡ Monitoring Serverless")
        st.caption("📊 Source: ACCOUNT_USAGE (latence 1-3h)")

        sub_tabs = st.tabs([
            "📊 Statut",
            "🔍 Par Service",
            "🏆 Top Consumers",
            "🚨 Historique Alertes",
            "📈 Tendances",
            "🔧 Configuration"
        ])

        with sub_tabs[0]:
            st.subheader("📊 Statut Serverless")

            sql = f"""
                SELECT 
                    sc.service_type,
                    sc.frequency,
                    sc.credit_limit,
                    COALESCE(u.credits_used, 0),
                    ROUND(COALESCE(u.credits_used, 0) / sc.credit_limit * 100, 1) AS pct_used,
                    CASE 
                        WHEN COALESCE(u.credits_used, 0) / sc.credit_limit >= 1 THEN '🛑 EXCEEDED'
                        WHEN COALESCE(u.credits_used, 0) / sc.credit_limit >= 0.95 THEN '🔴 CRITICAL'
                        WHEN COALESCE(u.credits_used, 0) / sc.credit_limit >= 0.85 THEN '🟠 ACTION REQUIRED'
                        WHEN COALESCE(u.credits_used, 0) / sc.credit_limit >= 0.70 THEN '⚠️ MONITORING'
                        ELSE '✅ OK'
                    END AS status,
                    sc.credit_limit - COALESCE(u.credits_used, 0) AS credits_remaining,
                    ARRAY_TO_STRING(sc.alert_emails, ', ') AS alert_recipients
                FROM {MONITORING_SCHEMA}.SERVERLESS_CONFIG sc
                LEFT JOIN (
                    SELECT service_type, SUM(credits_used) AS credits_used
                    FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
                    WHERE start_time >= CURRENT_DATE()
                    GROUP BY service_type
                ) u ON sc.service_type = u.service_type
                WHERE sc.is_active = TRUE
                ORDER BY pct_used DESC
            """
            df = run_query(session, sql)

            if not df.empty:
                num_services = len(df)
                cols_per_row = min(4, num_services)

                for idx, row in df.iterrows():
                    if idx % cols_per_row == 0:
                        cols = st.columns(cols_per_row)

                    col_idx = idx % cols_per_row
                    with cols[col_idx]:
                        pct = float(row['PCT_USED']) if row['PCT_USED'] else 0

                        if pct >= 100:
                            color = "red"
                        elif pct >= 85:
                            color = "orange"
                        elif pct >= 70:
                            color = "yellow"
                        else:
                            color = "green"

                        fig = go.Figure(go.Indicator(
                            mode="gauge+number",
                            value=pct,
                            title={'text': row['SERVICE_TYPE'][:15]},
                            gauge={
                                'axis': {'range': [0, 120]},
                                'bar': {'color': color},
                                'steps': [
                                    {'range': [0, 70], 'color': "lightgreen"},
                                    {'range': [70, 85], 'color': "lightyellow"},
                                    {'range': [85, 100], 'color': "lightsalmon"},
                                    {'range': [100, 120], 'color': "lightcoral"}
                                ],
                                'threshold': {
                                    'line': {'color': "red", 'width': 4},
                                    'thickness': 0.75,
                                    'value': 100
                                }
                            }
                        ))
                        fig.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=20))
                        st.plotly_chart(fig, use_container_width=True, key=f"sl_gauge_{idx}")

                st.markdown("---")
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Aucun service serverless configuré")

        with sub_tabs[1]:
            st.subheader("🔍 Détail par Service")

            sql_services = f"""
                SELECT DISTINCT service_type
                FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
                WHERE {period_filter}
                  AND service_type NOT IN ('WAREHOUSE_METERING')
                ORDER BY 1
            """
            services_df = run_query(session, sql_services)

            if not services_df.empty:
                selected_service = st.selectbox(
                    "Sélectionner un service",
                    services_df['SERVICE_TYPE'].tolist(),
                    key="sl_service_select"
                )

                sql = f"""
                    SELECT 
                        DATE_TRUNC('hour', start_time) as period,
                        ROUND(SUM(credits_used), 4) as credits_used
                    FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
                    WHERE {period_filter}
                      AND service_type = '{selected_service}'
                    GROUP BY 1
                    ORDER BY 1
                """
                df = run_query(session, sql)

                if not df.empty:
                    fig = px.line(df, x='PERIOD', y='CREDITS_USED', title=f"Évolution {selected_service}", markers=True)
                    st.plotly_chart(fig, use_container_width=True, key="sl_service_line")

                    total = df['CREDITS_USED'].sum()
                    st.metric(f"Total {selected_service}", f"{total:,.4f} crédits", f"${total * CREDIT_COST_USD:,.2f}")
            else:
                st.info("Aucun service serverless actif pour cette période")

        with sub_tabs[2]:
            st.subheader("🏆 Top Consumers Serverless")

            sql = f"SELECT * FROM {MONITORING_SCHEMA}.V_SERVERLESS_TOP_CONSUMERS LIMIT 50"
            df = run_query(session, sql)

            if not df.empty:
                service_types = df['SERVICE_TYPE'].unique().tolist()
                selected_service = st.selectbox("Filtrer par service", ["Tous"] + service_types, key="sl_top_filter")

                if selected_service != "Tous":
                    df = df[df['SERVICE_TYPE'] == selected_service]

                fig = px.bar(df.head(20), x='SERVICE_TYPE', y='TOTAL_CREDITS',
                             title="Crédits par service serverless (30 derniers jours)")
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True, key="sl_top_bar")

                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Aucune donnée de consommation serverless")

        with sub_tabs[3]:
            st.subheader("🚨 Historique des Alertes Serverless")

            sql = f"""
                SELECT * FROM {MONITORING_SCHEMA}.V_SERVERLESS_ALERT_HISTORY
                WHERE event_time >= '{start_str}'
                  AND event_time <= '{end_str}'
                ORDER BY event_time DESC
                LIMIT 200
            """
            df = run_query(session, sql)

            if not df.empty:
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.success("✅ Aucune alerte serverless pour cette période")

        with sub_tabs[4]:
            st.subheader("📈 Tendances Serverless")

            sql = f"""
                SELECT 
                    DATE_TRUNC('day', start_time) AS day_date,
                    service_type,
                    ROUND(SUM(credits_used), 4) AS credits_used
                FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
                WHERE start_time >= DATEADD('day', -30, CURRENT_DATE())
                  AND service_type NOT IN ('WAREHOUSE_METERING')
                GROUP BY 1, 2
                ORDER BY 1 DESC, 3 DESC
            """
            df = run_query(session, sql)

            if not df.empty:
                fig = px.line(df, x='DAY_DATE', y='CREDITS_USED', color='SERVICE_TYPE',
                              title="Évolution journalière (30 jours)")
                st.plotly_chart(fig, use_container_width=True, key="sl_trend_line")
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Aucune donnée de tendance")

        with sub_tabs[5]:
            st.subheader("🔧 Configuration Serverless")

            sql = f"SELECT * FROM {MONITORING_SCHEMA}.SERVERLESS_CONFIG ORDER BY service_type"
            df = run_query(session, sql)

            if not df.empty:
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.warning("Table SERVERLESS_CONFIG non trouvée ou vide")

    # ----------- CONSOMMATION & COÛT -----------
    with main_tabs[3]:
        sub_tabs = st.tabs([
            "Par Warehouse",
            "Par Heure",
            "Par Personne",
            "Tendances",
            "Coût Stockage"
        ])

        with sub_tabs[0]:
            st.subheader("💳 Crédits par Warehouse")

            sql = f"""
                SELECT 
                    warehouse_name,
                    ROUND(SUM(credits_used), 2) as total_credits,
                    ROUND(SUM(credits_used) * {CREDIT_COST_USD}, 2) as estimated_cost_usd,
                    COUNT(*) as metering_events
                FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
                WHERE {period_filter}
                GROUP BY 1
                ORDER BY 2 DESC
            """
            df = run_query(session, sql)

            if not df.empty:
                col1, col2 = st.columns([2, 1])
                with col1:
                    fig = px.bar(
                        df,
                        x='WAREHOUSE_NAME',
                        y='TOTAL_CREDITS',
                        color='TOTAL_CREDITS',
                        color_continuous_scale='Blues',
                        title="Crédits par Warehouse"
                    )
                    fig.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig, use_container_width=True, key="cost_wh_bar")

                with col2:
                    fig = px.pie(
                        df.head(10),
                        values='TOTAL_CREDITS',
                        names='WAREHOUSE_NAME',
                        title="Top 10 Warehouses"
                    )
                    st.plotly_chart(fig, use_container_width=True, key="cost_wh_pie")

                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Aucune donnée pour cette période")

        with sub_tabs[1]:
            st.subheader("⏰ Consommation par Heure")

            df = get_warehouse_credits(session, start_datetime, end_datetime)

            if not df.empty:
                df['HOUR'] = pd.to_datetime(df['PERIOD']).dt.hour
                df['DATE'] = pd.to_datetime(df['PERIOD']).dt.date

                pivot = df.pivot_table(
                    index='WAREHOUSE_NAME',
                    columns='HOUR',
                    values='CREDITS_USED',
                    aggfunc='sum',
                    fill_value=0
                )

                fig = px.imshow(
                    pivot,
                    title="Heatmap Consommation par Heure",
                    labels=dict(x="Heure", y="Warehouse", color="Crédits"),
                    color_continuous_scale='YlOrRd'
                )
                st.plotly_chart(fig, use_container_width=True, key="cost_heatmap")
            else:
                st.info("Aucune donnée pour cette période")

        with sub_tabs[2]:
            st.subheader("Consommation par Utilisateur")

            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                periode = st.selectbox(
                    "Période",
                    options=["7 jours", "30 jours", "90 jours"],
                    index=1
                )
            with col2:
                top_n = st.number_input("Top N utilisateurs", min_value=5, max_value=50, value=10, step=5)

            sql_wh_list = """
                SELECT DISTINCT WAREHOUSE_NAME
                FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
                ORDER BY 1
            """
            df_wh = run_query(session, sql_wh_list)
            wh_options = df_wh["WAREHOUSE_NAME"].dropna().astype(str).tolist() if not df_wh.empty else []
            with col3:
                wh_selected = st.multiselect(
                    "Sélectionner un ou plusieurs Warehouses",
                    options=wh_options,
                    default=wh_options[:4] if len(wh_options) >= 4 else wh_options
                )

            jours_map = {"7 jours": 7, "30 jours": 30, "90 jours": 90}
            nb_jours = jours_map[periode]

            wh_clause = ""
            if wh_selected:
                wh_in_literals = quote_list_for_sql(wh_selected)
                wh_clause = f"AND WAREHOUSE_NAME IN ({wh_in_literals})"

            TOP_K = 8

            sql_share = f"""
            WITH BASE AS (
                SELECT 
                    WAREHOUSE_NAME,
                    USER_NAME,
                    SUM(TOTAL_ELAPSED_TIME) / 60000.0 AS TOTAL_MIN
                FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
                WHERE START_TIME >= DATEADD(day, -{nb_jours}, CURRENT_TIMESTAMP())
                  {wh_clause}
                GROUP BY WAREHOUSE_NAME, USER_NAME
            ),
            TOP_USERS AS (
                SELECT USER_NAME
                FROM BASE
                GROUP BY USER_NAME
                ORDER BY SUM(TOTAL_MIN) DESC
                LIMIT {TOP_K}
            ),
            LABELED AS (
                SELECT 
                    WAREHOUSE_NAME,
                    CASE WHEN USER_NAME IN (SELECT USER_NAME FROM TOP_USERS) THEN USER_NAME ELSE 'Other' END AS USER_GROUP,
                    SUM(TOTAL_MIN) AS TOTAL_MIN
                FROM BASE
                GROUP BY WAREHOUSE_NAME, USER_GROUP
            ),
            WH_TOTALS AS (
                SELECT WAREHOUSE_NAME, SUM(TOTAL_MIN) AS TOTAL_WH_MIN
                FROM LABELED
                GROUP BY WAREHOUSE_NAME
            )
            SELECT 
                l.WAREHOUSE_NAME,
                l.USER_GROUP      AS USER_NAME,
                l.TOTAL_MIN,
                l.TOTAL_MIN / NULLIF(t.TOTAL_WH_MIN, 0) AS SHARE
            FROM LABELED l
            JOIN WH_TOTALS t USING (WAREHOUSE_NAME)
            WHERE t.TOTAL_WH_MIN > 0 
            ORDER BY l.WAREHOUSE_NAME, SHARE DESC;
            """

            df_share = run_query(session, sql_share)

            if not df_share.empty:
                df_share["SHARE_PCT"] = (df_share["SHARE"].astype(float) * 100.0)

                wh_order = (
                    df_share.groupby("WAREHOUSE_NAME")["TOTAL_MIN"]
                    .sum()
                    .sort_values(ascending=False)
                    .index
                    .tolist()
                )

                if not wh_selected:
                    title_suffix = ""
                elif len(wh_selected) <= 5:
                    title_suffix = " – WH: " + ", ".join(wh_selected)
                else:
                    title_suffix = f" – {len(wh_selected)} WH sélectionnés"

                fig_100 = px.bar(
                    df_share,
                    x="WAREHOUSE_NAME",
                    y="SHARE_PCT",
                    color="USER_NAME",
                    labels={
                        "WAREHOUSE_NAME": "Warehouse",
                        "SHARE_PCT": "Part (%)",
                        "USER_NAME": "Utilisateur"
                    },
                    title=f"Répartition par Warehouse sur {periode}{title_suffix}",
                    text=df_share["SHARE_PCT"].round(0).astype(int).astype(str) + " %"
                )

                fig_100.update_layout(
                    barmode="stack",
                    yaxis=dict(range=[0, 100], ticksuffix=" %"),
                    margin=dict(l=40, r=20, t=70, b=80),
                    height=520,
                    legend_title="Utilisateur"
                )
                fig_100.update_xaxes(categoryorder="array", categoryarray=wh_order, tickangle=-45)

                st.plotly_chart(fig_100, use_container_width=True, key="stacked_100_wh_user")

                with st.expander("Voir les données (parts par warehouse)"):
                    st.dataframe(
                        df_share
                        .sort_values(["WAREHOUSE_NAME", "SHARE_PCT"], ascending=[True, False])
                        .rename(columns={
                            "WAREHOUSE_NAME": "Warehouse",
                            "USER_NAME": "Utilisateur",
                            "TOTAL_MIN": "Minutes",
                            "SHARE_PCT": "Part (%)"
                        })
                    )

            sql = f"""
                SELECT 
                    USER_NAME,
                    SUM(TOTAL_ELAPSED_TIME) / 60000.0 AS TOTAL_MIN
                FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
                WHERE START_TIME >= DATEADD(day, -{nb_jours}, CURRENT_TIMESTAMP())
                  {wh_clause}
                GROUP BY USER_NAME
                HAVING TOTAL_MIN > 0
                ORDER BY TOTAL_MIN DESC
                LIMIT {int(top_n)};
            """

            df = run_query(session, sql)

            if not df.empty:
                df["TOTAL_MIN"] = df["TOTAL_MIN"].astype(float)
                df["USER_NAME"] = df["USER_NAME"].astype(str)
                df = df.sort_values("TOTAL_MIN", ascending=True)

                if not wh_selected:
                    title_suffix = ""
                elif len(wh_selected) <= 5:
                    title_suffix = " – WH: " + ", ".join(wh_selected)
                else:
                    title_suffix = f" – {len(wh_selected)} WH sélectionnés"

                fig = px.bar(
                    df,
                    x="TOTAL_MIN",
                    y="USER_NAME",
                    orientation="h",
                    labels={"TOTAL_MIN": "Minutes consommées", "USER_NAME": "Utilisateur"},
                    title=f"Top {len(df)} utilisateurs par temps total sur {periode}{title_suffix}",
                    text=df["TOTAL_MIN"].round(2)
                )

                fig.update_traces(marker_color="#1f77b4", textposition="outside", cliponaxis=False)
                fig.update_layout(
                    xaxis_title="Minutes",
                    yaxis_title="",
                    margin=dict(l=120, r=30, t=70, b=40),
                    height=500
                )

                st.plotly_chart(fig, use_container_width=True, key="bar_top_users")

            if not df.empty:
                top_users = df["USER_NAME"].astype(str).tolist()
                if top_users:
                    user_in_literals = quote_list_for_sql(top_users)

                    wh_clause_stack = ""
                    if wh_selected:
                        wh_in_literals2 = quote_list_for_sql(wh_selected)
                        wh_clause_stack = f"AND WAREHOUSE_NAME IN ({wh_in_literals2})"

                    sql_stack = f"""
                        WITH BASE AS (
                            SELECT 
                                WAREHOUSE_NAME,
                                USER_NAME,
                                SUM(TOTAL_ELAPSED_TIME) / 60000.0 AS TOTAL_MIN
                            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
                            WHERE START_TIME >= DATEADD(day, -{nb_jours}, CURRENT_TIMESTAMP())
                              {wh_clause_stack}
                              AND USER_NAME IN ({user_in_literals})
                            GROUP BY WAREHOUSE_NAME, USER_NAME
                        ),
                        WH_TOTALS AS (
                            SELECT WAREHOUSE_NAME, SUM(TOTAL_MIN) AS TOTAL_WH_MIN
                            FROM BASE
                            GROUP BY WAREHOUSE_NAME
                        )
                        SELECT 
                            b.WAREHOUSE_NAME,
                            b.USER_NAME,
                            b.TOTAL_MIN
                        FROM BASE b
                        JOIN WH_TOTALS t
                          ON b.WAREHOUSE_NAME = t.WAREHOUSE_NAME
                        WHERE t.TOTAL_WH_MIN > 20
                        ORDER BY b.WAREHOUSE_NAME
                    """

                    df_stack = run_query(session, sql_stack)

                    if not df_stack.empty:
                        df_stack["WAREHOUSE_NAME"] = df_stack["WAREHOUSE_NAME"].astype(str)
                        df_stack["USER_NAME"] = df_stack["USER_NAME"].astype(str)
                        df_stack["TOTAL_MIN"] = df_stack["TOTAL_MIN"].astype(float)

                        pivot = df_stack.pivot_table(
                            index='WAREHOUSE_NAME',
                            columns='USER_NAME',
                            values='TOTAL_MIN',
                            aggfunc='sum',
                            fill_value=0
                        )

                        fig = px.imshow(
                            pivot,
                            title="Heatmap Consommation par Utilisateur",
                            labels=dict(x="Utilisateur", y="Warehouse", color="Time"),
                            color_continuous_scale='YlOrRd'
                        )

                        fig.update_layout(
                            height=700,
                            margin=dict(l=140, r=30, t=60, b=120),
                        )

                        fig.update_xaxes(tickangle=-45, automargin=True, tickfont=dict(size=10))
                        fig.update_yaxes(automargin=True, tickfont=dict(size=10))

                        st.plotly_chart(fig, use_container_width=True, key="time_heatmap")

                with st.expander("Voir les données"):
                    st.dataframe(df.rename(columns={"USER_NAME": "Utilisateur", "TOTAL_MIN": "Minutes"}))

            else:
                st.info("Aucune donnée trouvée pour la période sélectionnée.")

        with sub_tabs[3]:
            st.subheader("📈 Tendances de Consommation")

            sql = """
                SELECT warehouse_name,
                       DATE_TRUNC('month', start_time) AS month_date,
                       ROUND(SUM(credits_used), 2)     AS credits_used
                FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
                WHERE start_time >= DATEADD('month', -12, CURRENT_DATE())
                GROUP BY warehouse_name, DATE_TRUNC('month', start_time)
                ORDER BY warehouse_name, month_date
            """
            df = run_query(session, sql)

            if not df.empty:
                fig = px.line(
                    df,
                    x='MONTH_DATE',
                    y='CREDITS_USED',
                    color='WAREHOUSE_NAME',
                    title="Évolution mensuelle (12 derniers mois)",
                    markers=True
                )
                st.plotly_chart(fig, use_container_width=True, key="cost_monthly_line")

                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Aucune donnée de tendance mensuelle")

        with sub_tabs[4]:
            st.subheader("💾 Coût du Stockage")

            sql = """
                SELECT DATE_TRUNC('day', usage_date)                                                as usage_day,
                       ROUND(AVG(storage_bytes + stage_bytes + failsafe_bytes) / POWER(1024, 4), 4) as total_tb,
                       ROUND(AVG(storage_bytes) / POWER(1024, 4), 4)                                as storage_tb,
                       ROUND(AVG(stage_bytes) / POWER(1024, 4), 4)                                  as stage_tb,
                       ROUND(AVG(failsafe_bytes) / POWER(1024, 4), 4)                               as failsafe_tb
                FROM SNOWFLAKE.ACCOUNT_USAGE.STORAGE_USAGE
                WHERE usage_date >= DATEADD('day', -30, CURRENT_DATE())
                GROUP BY 1
                ORDER BY 1
            """
            df = run_query(session, sql)

            if not df.empty:
                fig = px.area(
                    df,
                    x='USAGE_DAY',
                    y=['STORAGE_TB', 'STAGE_TB', 'FAILSAFE_TB'],
                    title="Évolution du stockage (30 derniers jours)"
                )
                st.plotly_chart(fig, use_container_width=True, key="storage_area")
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Aucune donnée de stockage")

    # ----------- PERFORMANCE & REQUÊTES -----------
    with main_tabs[4]:
        st.header("🚀 Performance & Requêtes")
        st.caption("📊 Source: ACCOUNT_USAGE (latence 1-3h)")

        sub_tabs = st.tabs([
            "Vue globale",
            "Requêtes lentes",
            "Par utilisateur"
        ])

        with sub_tabs[0]:
            st.subheader("📊 Vue Globale des Performances")

            sql = f"""
                SELECT 
                    COUNT(*) as total_queries,
                    ROUND(AVG(total_elapsed_time)/1000, 2) as avg_duration_sec,
                    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_elapsed_time)/1000, 2) as median_duration_sec,
                    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_elapsed_time)/1000, 2) as p95_duration_sec,
                    COUNT(CASE WHEN total_elapsed_time > 60000 THEN 1 END) as slow_queries
                FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
                WHERE {period_filter}
            """
            df = run_query(session, sql)

            if not df.empty and df['TOTAL_QUERIES'].iloc[0] > 0:
                col1, col2, col3, col4, col5 = st.columns(5)
                with col1:
                    st.metric("Total requêtes", f"{df['TOTAL_QUERIES'].iloc[0]:,}")
                with col2:
                    st.metric("Durée moyenne", f"{df['AVG_DURATION_SEC'].iloc[0]:.1f}s")
                with col3:
                    st.metric("Médiane", f"{df['MEDIAN_DURATION_SEC'].iloc[0]:.1f}s")
                with col4:
                    st.metric("P95", f"{df['P95_DURATION_SEC'].iloc[0]:.1f}s")
                with col5:
                    st.metric("Requêtes >1min", df['SLOW_QUERIES'].iloc[0])
            else:
                st.info("Aucune requête pour cette période")

        with sub_tabs[1]:
            st.subheader("🐢 Requêtes les Plus Lentes")

            sql = f"""
                SELECT 
                    query_id,
                    user_name,
                    warehouse_name,
                    ROUND(total_elapsed_time/1000, 2) as duration_sec,
                    execution_status,
                    LEFT(query_text, 200) as query_preview,
                    start_time
                FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
                WHERE {period_filter}
                  AND total_elapsed_time > 0
                ORDER BY total_elapsed_time DESC
                LIMIT 50
            """
            df = run_query(session, sql)

            if not df.empty:
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Aucune requête lente")

        with sub_tabs[2]:
            st.subheader("👤 Consommation par Utilisateur")

            sql = f"""
                SELECT 
                    user_name,
                    COUNT(*) as query_count,
                    ROUND(AVG(total_elapsed_time)/1000, 2) as avg_duration_sec,
                    ROUND(SUM(credits_used_cloud_services), 4) as cloud_credits
                FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
                WHERE {period_filter}
                GROUP BY 1
                ORDER BY 2 DESC
                LIMIT 50
            """
            df = run_query(session, sql)

            if not df.empty:
                fig = px.bar(df.head(20), x='USER_NAME', y='QUERY_COUNT', title="Top 20 Utilisateurs par Requêtes")
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True, key="perf_users_bar")
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Aucune donnée utilisateur")

    # ----------- SÉCURITÉ & CONNEXIONS -----------
    with main_tabs[5]:
        st.header("🔐 Sécurité & Connexions")
        st.caption("📊 Source: ACCOUNT_USAGE (latence 1-3h)")

        sub_tabs = st.tabs([
            "Connexions échouées",
            "Historique connexions"
        ])

        with sub_tabs[0]:
            st.subheader("🚫 Connexions échouées")

            sql = f"""
                SELECT 
                    user_name,
                    client_ip,
                    reported_client_type,
                    error_message,
                    COUNT(*) as failed_attempts,
                    MIN(event_timestamp) as first_attempt,
                    MAX(event_timestamp) as last_attempt
                FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
                WHERE is_success = 'NO'
                  AND event_timestamp >= '{start_str}'
                  AND event_timestamp <= '{end_str}'
                GROUP BY 1, 2, 3, 4
                ORDER BY 5 DESC
            """
            df = run_query(session, sql)

            if not df.empty:
                total_failed = df['FAILED_ATTEMPTS'].sum()
                st.metric("Total tentatives échouées", total_failed)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.success("✅ Aucune connexion échouée pour cette période")

        with sub_tabs[1]:
            st.subheader("📋 Historique des connexions")

            sql = f"""
                SELECT
                    event_timestamp,
                    user_name,
                    client_ip,
                    reported_client_type,
                    first_authentication_factor,
                    is_success,
                    error_message
                FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
                WHERE event_timestamp >= '{start_str}'
                  AND event_timestamp <= '{end_str}'
                ORDER BY event_timestamp DESC
                LIMIT 500
            """
            df = run_query(session, sql)

            if not df.empty:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total connexions", len(df))
                with col2:
                    success = df[df['IS_SUCCESS'] == 'YES'].shape[0]
                    st.metric("Réussies", success)
                with col3:
                    failed = df[df['IS_SUCCESS'] == 'NO'].shape[0]
                    st.metric("Échouées", failed)

                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Aucune connexion pour cette période")

    # ----------- STOCKAGE & DONNÉES -----------
    with main_tabs[6]:
        st.header("💾 Stockage & Données")
        st.caption("📊 Source: ACCOUNT_USAGE")

        sub_tabs = st.tabs([
            "Évolution stockage",
            "Chargements de données",
            "Tables volumineuses",
            "Stages volumineux"
        ])

        with sub_tabs[0]:
            st.subheader("📈 Évolution du stockage")

            sql = f"""
                SELECT 
                    DATE_TRUNC('day', usage_date) as usage_day,
                    ROUND(AVG(storage_bytes + stage_bytes + failsafe_bytes)/POWER(1024,4), 4) as total_tb,
                    ROUND(AVG(storage_bytes)/POWER(1024,4), 4) as storage_tb,
                    ROUND(AVG(stage_bytes)/POWER(1024,4), 4) as stage_tb,
                    ROUND(AVG(failsafe_bytes)/POWER(1024,4), 4) as failsafe_tb
                FROM SNOWFLAKE.ACCOUNT_USAGE.STORAGE_USAGE
                WHERE usage_date >= '{start_str}'::DATE
                  AND usage_date <= '{end_str}'::DATE
                GROUP BY 1
                ORDER BY 1
            """
            df = run_query(session, sql)

            if not df.empty:
                fig = px.area(df, x='USAGE_DAY', y=['STORAGE_TB', 'STAGE_TB', 'FAILSAFE_TB'],
                              title="Évolution du stockage par type")
                st.plotly_chart(fig, use_container_width=True, key="storage_evolution")
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Aucune donnée pour cette période")

        with sub_tabs[1]:
            st.subheader("📥 Chargements de données")

            sql = f"""
                SELECT
                    pipe_name,
                    file_name,
                    stage_location,
                    last_load_time,
                    row_count,
                    row_parsed,
                    error_count,
                    status
                FROM SNOWFLAKE.ACCOUNT_USAGE.COPY_HISTORY
                WHERE last_load_time >= '{start_str}'
                  AND last_load_time <= '{end_str}'
                ORDER BY last_load_time DESC
                LIMIT 200
            """
            df = run_query(session, sql)

            if not df.empty:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total chargements", len(df))
                with col2:
                    total_rows = df['ROW_COUNT'].sum() if 'ROW_COUNT' in df.columns else 0
                    st.metric("Lignes chargées", f"{total_rows:,}")
                with col3:
                    errors = df['ERROR_COUNT'].sum() if 'ERROR_COUNT' in df.columns else 0
                    st.metric("Erreurs", errors)

                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Aucun chargement pour cette période")

        with sub_tabs[2]:
            st.subheader("📊 Tables les plus volumineuses")

            sql = """
                SELECT table_catalog                    AS database_name,
                       table_schema                     AS schema_name,
                       table_name,
                       row_count,
                       ROUND(bytes / POWER(1024, 3), 4) AS size_gb,
                       created,
                       last_altered
                FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
                WHERE deleted IS NULL
                  AND bytes > 0
                  AND table_type = 'BASE TABLE'
                ORDER BY bytes DESC LIMIT 50
            """
            df = run_query(session, sql)

            if not df.empty:
                col1, col2, col3 = st.columns(3)
                with col1:
                    total_storage = df['SIZE_GB'].sum()
                    st.metric("Stockage total (Top 50)", f"{total_storage:,.2f} GB")
                with col2:
                    st.metric("Nombre de tables", len(df))
                with col3:
                    total_rows = df['ROW_COUNT'].sum() if 'ROW_COUNT' in df.columns and df[
                        'ROW_COUNT'].notna().any() else 0
                    st.metric("Total lignes", f"{total_rows:,.0f}")

                fig = px.bar(
                    df.head(20),
                    x='TABLE_NAME',
                    y='SIZE_GB',
                    title="Top 20 tables par taille",
                    color='SIZE_GB',
                    color_continuous_scale='Blues'
                )
                fig.update_layout(xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True, key="tables_bar")

                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("Aucune donnée de stockage de tables")

        with sub_tabs[3]:
            st.subheader("📦 Stages les plus volumineux")

            sql = """
                SELECT stage_catalog AS database_name,
                       stage_schema  AS schema_name,
                       stage_name,
                       stage_type,
                       stage_url,
                       created,
                       last_altered,
                       stage_owner
                FROM SNOWFLAKE.ACCOUNT_USAGE.STAGES
                WHERE deleted IS NULL
                ORDER BY stage_name LIMIT 100
            """
            df = run_query(session, sql)

            if not df.empty:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Nombre de stages", len(df))
                with col2:
                    if 'STAGE_TYPE' in df.columns:
                        internal_count = len(df[df['STAGE_TYPE'].str.contains('Internal', na=False, case=False)])
                        st.metric("Stages internes", internal_count)
                with col3:
                    if 'STAGE_TYPE' in df.columns:
                        external_count = len(df[df['STAGE_TYPE'].str.contains('External', na=False, case=False)])
                        st.metric("Stages externes", external_count)

                if 'STAGE_TYPE' in df.columns:
                    type_summary = df.groupby('STAGE_TYPE').size().reset_index(name='count')
                    fig = px.pie(
                        type_summary,
                        values='count',
                        names='STAGE_TYPE',
                        title="Répartition par type de stage"
                    )
                    st.plotly_chart(fig, use_container_width=True, key="stages_pie_type")

                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                sql_alt = """
                    SELECT *
                    FROM SNOWFLAKE.ACCOUNT_USAGE.STAGE_STORAGE_USAGE_HISTORY
                    WHERE usage_date >= DATEADD('day', -1, CURRENT_DATE())
                    ORDER BY average_stage_bytes DESC NULLS LAST LIMIT 50
                """
                df_alt = run_query(session, sql_alt)

                if not df_alt.empty:
                    st.dataframe(df_alt, use_container_width=True, hide_index=True)
                else:
                    st.info("Aucune donnée de stages disponible")


# Snowflake Streamlit exécute le fichier directement (pas via __main__)
main()
