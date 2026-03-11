# Snowsled v2

Plateforme DataOps native Snowflake pour POC avant-vente.

## Applications incluses

| Application | Role |
|---|---|
| **Snowsled Platform** | Setup du compte Snowflake et connexions GitHub / dbt Cloud / Fivetran |
| **Snowsled Admin** | Convention de nommage, gestion des projets et des roles |
| **Snowsled** | Creation et gestion des objets de donnees (DSI, DSO, Pipelines) |
| **FinOps Monitor** | Dashboard couts, gouvernance et conformite |

## Privileges requis

- `CREATE DATABASE` — creation des bases DSI et DSO
- `CREATE WAREHOUSE` — creation des warehouses de traitement
- `CREATE ROLE` — creation des roles fonctionnels
- `EXECUTE TASK` — pipelines de transformation
- `IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE` — tableau de bord FinOps

## Apres installation

Accordez les privileges via Snowsight ou en SQL, puis ouvrez l'application depuis **Data Products → Apps → SNOWSLED_V2**.

Commencez par **Snowsled Platform** pour configurer le compte.
