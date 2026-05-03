# AGENTS.md

## Cursor Cloud specific instructions

### Product overview

Snowsled v2 is a **Snowflake Native Application** for bootstrapping DataOps POCs. It contains 4 Streamlit sub-applications (Snowsled Platform, Snowsled Admin, Snowsled, FinOps Monitor) that run inside Snowflake. The entire application is written in Python 3.11+ / Streamlit + SQL.

### Running locally

- **Streamlit apps** can be started locally via `streamlit run app/src/<app_dir>/<main_file>.py --server.port 8501 --server.headless true`.
  - Without Snowflake credentials, apps will start but show a `RuntimeError` about missing session — this is expected.
  - To connect locally, copy `.env.example` to `.env` and fill in Snowflake credentials, or configure a Snowflake CLI connection named `dsp_inno`.
- **Snowflake CLI** (`snow`) is used to bundle and deploy the Native App: `snow app bundle` (local packaging), `snow app run --connection <name>` (deploy to Snowflake account).

### Key dev commands

| Action | Command |
|---|---|
| Install deps | `pip install -r requirements-local.txt` |
| Run Snowsled Platform | `streamlit run app/src/snowsled_platform/snowsled_platform.py` |
| Run Snowsled Admin | `streamlit run app/src/snowsled_admin/snowsled_admin.py` |
| Run Snowsled | `streamlit run app/src/snowsled/snowsled.py` |
| Run FinOps Monitor | `streamlit run app/src/finops_monitor/streamlit_app.py` |
| Bundle for Snowflake | `snow app bundle` |
| Deploy to Snowflake | `snow app run --connection dsp_inno` |
| Syntax-check all files | `python3 -c "import py_compile; py_compile.compile('<file>', doraise=True)"` |

### Gotchas

- The system-installed `PyJWT` on Ubuntu cannot be uninstalled normally. Use `pip install --ignore-installed PyJWT` when installing deps.
- There are no automated tests (unit/integration) in this repository. Validation is done via syntax checks and manual Streamlit app testing.
- The `utils/` module uses path manipulation (`sys.path.insert`) to resolve both the Snowflake-native and local development import contexts — see `app/src/utils/session.py`.
- `snow app bundle` validates the project config (`snowflake.yml`) and packages artifacts into `output/deploy/` without needing a Snowflake connection.
- End-to-end testing requires a **Snowflake account** with `ACCOUNTADMIN` role. External integrations (GitHub, dbt Cloud, Fivetran) are optional.
