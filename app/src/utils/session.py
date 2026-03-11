# ============================================================
# SESSION HELPER — Snowflake Snowpark
# Détecte automatiquement l'environnement d'exécution :
#   • Snowflake (Native App / Streamlit in Snowflake) → get_active_session()
#   • Local (développement) → connexion via variables d'environnement ou .env
# ============================================================

import os
import sys


def get_session():
    """
    Retourne une session Snowpark active.

    Priorité :
    1. get_active_session()  → contexte Snowflake natif (Native App / SiS)
    2. Variables d'environnement SNOWFLAKE_*  → mode local
    3. Profil Snowflake CLI ~/.snowflake/config.toml → mode local (fallback)
    """

    # ── Tentative 1 : contexte Snowflake natif ────────────────
    try:
        from snowflake.snowpark.context import get_active_session
        session = get_active_session()
        # Vérification rapide que la session est réellement active
        session.sql("SELECT 1").collect()
        return session
    except Exception:
        pass

    # ── Tentative 2 : fichier .env local ─────────────────────
    _load_dotenv()

    account   = os.environ.get("SNOWFLAKE_ACCOUNT")
    user      = os.environ.get("SNOWFLAKE_USER")
    password  = os.environ.get("SNOWFLAKE_PASSWORD")
    role      = os.environ.get("SNOWFLAKE_ROLE",      "ACCOUNTADMIN")
    warehouse = os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
    database  = os.environ.get("SNOWFLAKE_DATABASE",  "SNOWSLED_V2")
    schema    = os.environ.get("SNOWFLAKE_SCHEMA",    "APP_SCHEMA")

    if account and user and password:
        from snowflake.snowpark import Session
        return Session.builder.configs({
            "account":   account,
            "user":      user,
            "password":  password,
            "role":      role,
            "warehouse": warehouse,
            "database":  database,
            "schema":    schema,
        }).create()

    # ── Tentative 3 : profil Snowflake CLI ───────────────────
    # Snowpark lit nativement les connexions de ~/.snowflake/config.toml
    # configurées via `snow connection add`
    connection_name = os.environ.get("SNOWFLAKE_CONNECTION", "dsp_inno")
    try:
        from snowflake.snowpark import Session
        return Session.builder.config("connection_name", connection_name).create()
    except Exception:
        pass

    raise RuntimeError(
        "Impossible de créer une session Snowflake.\n"
        "→ En local : copiez .env.example → .env et renseignez vos credentials.\n"
        "→ Ou configurez la connexion 'dsp_inno' dans ~/.snowflake/config.toml"
    )


def _load_dotenv():
    """Charge .env depuis la racine du projet si python-dotenv est installé."""
    try:
        from dotenv import load_dotenv
        # Remonte depuis app/src/utils/ jusqu'à la racine du projet
        root = os.path.dirname(  # DSP_INNO/
            os.path.dirname(         # app/
                os.path.dirname(         # src/
                    os.path.abspath(__file__)  # utils/session.py
                )
            )
        )
        env_file = os.path.join(root, ".env")
        if os.path.exists(env_file):
            load_dotenv(env_file)
    except ImportError:
        pass  # python-dotenv non installé → on passe aux variables d'environnement système
