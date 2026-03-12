# ❄️ Snowsled v2 — Native Application Snowflake

> Plateforme DataOps native Snowflake pour POC avant-vente.  
> Déployable en **3 clics depuis le Marketplace** ou via **Snowflake CLI** en ~15 minutes.

[![Snowflake Native App](https://img.shields.io/badge/Snowflake-Native%20App-29B5E8?logo=snowflake&logoColor=white)](https://docs.snowflake.com/en/developer-guide/native-apps/native-apps-about)
[![Cloud](https://img.shields.io/badge/Cloud-AWS%20us--east--1-FF9900?logo=amazon-aws)](https://aws.amazon.com)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://python.org)

---

## Table des matières

- [Vue d'ensemble](#vue-densemble)
- [Architecture](#architecture)
- [Déploiement — Mode A : Marketplace (recommandé POC)](#déploiement--mode-a--marketplace-recommandé-poc)
- [Déploiement — Mode B : Snowflake CLI (développeurs)](#déploiement--mode-b--snowflake-cli-développeurs)
- [Publication d'un listing privé (Provider)](#publication-dun-listing-privé-provider)
- [Configuration post-installation](#configuration-post-installation)
- [Applications Streamlit](#applications-streamlit)
- [Convention de nommage](#convention-de-nommage)
- [Structure du projet](#structure-du-projet)
- [Teardown](#teardown)
- [Limitations du compte Trial Snowflake](#limitations-du-compte-trial-snowflake)
- [Dépannage](#dépannage)
- [Commandes de référence](#commandes-de-référence)

---

## Vue d'ensemble

Snowsled v2 est une **Snowflake Native App** qui permet à un ingénieur avant-vente de bootstrapper un POC Snowflake complet depuis l'interface Snowsight, sans aucun outil externe.

| Application | Rôle |
|---|---|
| **Snowsled Platform** | Setup du compte Snowflake + connexions GitHub / dbt Cloud / Fivetran |
| **Snowsled Admin** | Convention de nommage, projets, rôles |
| **Snowsled** | Création et gestion des objets de données (DSI, DSO, pipelines) |
| **FinOps Monitor** | Dashboard coûts, gouvernance et conformité |

---

## Architecture

```
┌─────────────────────────── Snowflake Native App ──────────────────────────┐
│                                                                             │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────┐ │
│  │  Snowsled Platform   │  │   Snowsled Admin     │  │    Snowsled      │ │
│  │  (Setup & Connect)   │  │  (Config & Naming)   │  │  (Objects CRUD)  │ │
│  └──────────┬───────────┘  └──────────┬───────────┘  └────────┬─────────┘ │
│             │                         │                        │           │
│  ┌──────────▼─────────────────────────▼────────────────────────▼─────────┐ │
│  │              CONFIG_SCHEMA              │  AUDIT_SCHEMA               │ │
│  │  ACCOUNT_CONFIG · NAMING_CONVENTION · EXTERNAL_CONNECTIONS            │ │
│  │  PROJECTS · MANAGED_ROLES · MANAGED_OBJECTS · AUDIT_LOG               │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘

Couche DSI (intégration brute)        Couche DSO (présentation curated)
┌──────────────────────────┐          ┌──────────────────────────┐
│  DSI_<PROJET>            │          │  DSO_<PROJET>            │
│  ├── RAW/                │  ──────► │  ├── REPORTING/          │
│  ├── STAGING/            │          │  └── SHARED_VIEWS/       │
│  └── METADATA/           │          └──────────────────────────┘
└──────────────────────────┘

Intégrations externes :
  GitHub ──────────────── PAT stocké en SECRET Snowflake
  dbt Cloud ──────────── Service Account Token
  Fivetran ───────────── API Key + Secret
```

---

## Déploiement — Mode A : Marketplace (recommandé POC)

> ✅ **Aucun outil local requis.** Idéal pour installer Snowsled chez un client en démo.

### Prérequis

- Un compte Snowflake (Trial ou actif) — [créer un trial](https://trial.snowflake.com) si besoin
- Rôle `ACCOUNTADMIN`
- Avoir reçu le **lien de listing privé** de l'ingénieur avant-vente, ou accéder au listing public sur le Marketplace

### Étape 1 — Ouvrir le listing

**Listing privé (POC client) :**  
L'ingénieur avant-vente partage un lien direct vers le listing Snowflake.

**Listing public (Marketplace) :**  
Dans Snowsight : **Data Products → Marketplace** → rechercher `Snowsled v2`.

### Étape 2 — Installer l'application

1. Sur la page du listing, cliquer sur **"Get"**.
2. Laisser le nom `SNOWSLED_V2` (par défaut).
3. Sélectionner un warehouse pour l'installation.
4. Cliquer sur **"Get"** — installation automatique (~1 minute).

### Étape 3 — Accorder les privilèges

Snowsight affiche une popup listant les privilèges demandés. Cliquer **"Grant"** pour chacun, ou exécuter dans un worksheet :

```sql
USE ROLE ACCOUNTADMIN;

GRANT CREATE DATABASE        ON ACCOUNT TO APPLICATION SNOWSLED_V2;
GRANT CREATE WAREHOUSE       ON ACCOUNT TO APPLICATION SNOWSLED_V2;
GRANT CREATE ROLE            ON ACCOUNT TO APPLICATION SNOWSLED_V2;
GRANT EXECUTE TASK           ON ACCOUNT TO APPLICATION SNOWSLED_V2;
GRANT CREATE INTEGRATION     ON ACCOUNT TO APPLICATION SNOWSLED_V2;
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO APPLICATION SNOWSLED_V2;
```

> ⚠️ **FinOps Monitor** : si le dashboard affiche `Database 'SNOWFLAKE' does not exist or not authorized`, c'est que le grant `IMPORTED PRIVILEGES` n'a pas encore été appliqué. Exécutez-le dans un Worksheet Snowflake avec le rôle `ACCOUNTADMIN`, puis lancez :
> ```sql
> CALL SNOWSLED_V2.APP_SCHEMA.INITIALIZE_FINOPS_VIEWS();
> ```
> Cette procédure crée les vues dépendantes de `ACCOUNT_USAGE` et s'exécute automatiquement à chaque déploiement via `post_deploy.sql`.

### Étape 4 — Ouvrir l'application

**Data Products → Apps → SNOWSLED_V2**  
L'application s'ouvre sur **Snowsled Platform**.

---

## Déploiement — Mode B : Snowflake CLI (développeurs)

> Pour publier ou modifier l'application en tant que Provider.

### Prérequis

| Outil | Version | Installation |
|---|---|---|
| Python | ≥ 3.11 | [python.org](https://www.python.org/downloads/) |
| Snowflake CLI | ≥ 3.x | `pip install snowflake-cli-labs` |
| Git | — | [git-scm.com](https://git-scm.com) |

### Étape 1 — Cloner le dépôt

```bash
git clone https://github.com/DevoteamSP/Snowsled-v2.git
cd Snowsled-v2
```

### Étape 2 — Configurer Snowflake CLI

```bash
snow connection add
```

| Champ | Valeur |
|---|---|
| **Name** | `dsp_inno` |
| **Account** | votre Account Identifier (ex : `ABC12345.us-east-1.aws`) |
| **User** | votre utilisateur Snowflake |
| **Password** | votre mot de passe |
| **Role** | `ACCOUNTADMIN` |
| **Warehouse** | `COMPUTE_WH` |

Tester la connexion :

```bash
snow connection test --connection dsp_inno
```

### Étape 3 — Créer les rôles de packaging

Exécuter dans un worksheet Snowflake (rôle `ACCOUNTADMIN`) :

```sql
USE ROLE ACCOUNTADMIN;

CREATE ROLE IF NOT EXISTS SNOWSLED_PKG_ROLE;
GRANT CREATE APPLICATION PACKAGE ON ACCOUNT TO ROLE SNOWSLED_PKG_ROLE;
GRANT CREATE APPLICATION         ON ACCOUNT TO ROLE SNOWSLED_PKG_ROLE;
GRANT CREATE DATABASE            ON ACCOUNT TO ROLE SNOWSLED_PKG_ROLE;
GRANT CREATE WAREHOUSE           ON ACCOUNT TO ROLE SNOWSLED_PKG_ROLE;

-- Remplacer <VOTRE_USERNAME> par votre login Snowflake
GRANT ROLE SNOWSLED_PKG_ROLE TO USER <VOTRE_USERNAME>;
```

### Étape 4 — Déployer l'application

```bash
# Depuis la racine du dépôt
snow app run --connection dsp_inno
```

Cette commande effectue automatiquement :

| Étape | Action |
|---|---|
| 📦 Upload | Copie `app/` dans un stage Snowflake |
| 🏗️ Package | Crée le package `SNOWSLED_V2_PKG` |
| 🔖 Version | Crée / met à jour la version `v2` |
| 🚀 Install | Installe `SNOWSLED_V2` dans votre compte |
| ⚙️ Post-deploy | Exécute `scripts/post_deploy.sql` (initialisation config) |

En cas de succès :
```
Application SNOWSLED_V2 successfully installed.
```

### Étape 5 — Accorder les privilèges

```sql
USE ROLE ACCOUNTADMIN;

GRANT CREATE DATABASE        ON ACCOUNT TO APPLICATION SNOWSLED_V2;
GRANT CREATE WAREHOUSE       ON ACCOUNT TO APPLICATION SNOWSLED_V2;
GRANT CREATE ROLE            ON ACCOUNT TO APPLICATION SNOWSLED_V2;
GRANT EXECUTE TASK           ON ACCOUNT TO APPLICATION SNOWSLED_V2;
GRANT CREATE INTEGRATION     ON ACCOUNT TO APPLICATION SNOWSLED_V2;
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO APPLICATION SNOWSLED_V2;
```

> ⚠️ **FinOps Monitor** : si le dashboard affiche `Database 'SNOWFLAKE' does not exist or not authorized`, c'est que le grant `IMPORTED PRIVILEGES` n'a pas encore été appliqué. Exécutez-le dans un Worksheet Snowflake avec le rôle `ACCOUNTADMIN`, puis lancez :
> ```sql
> CALL SNOWSLED_V2.APP_SCHEMA.INITIALIZE_FINOPS_VIEWS();
> ```

### Étape 6 — Accéder à l'application

**Data Products → Apps → SNOWSLED_V2** dans Snowsight.

### Publication sur le Marketplace

Pour publier en tant que Provider et partager le listing à d'autres comptes, consulter le guide dédié : [`MARKETPLACE_PUBLISH.md`](MARKETPLACE_PUBLISH.md).

---

## Publication d'un listing privé (Provider)

> Cette section s'adresse à l'**ingénieur avant-vente** qui souhaite partager l'application avec un compte client via un listing privé Snowflake.

### Prérequis

- Compte Snowflake avec **Provider Studio activé**  
  *(Snowsight → Admin → Marketplace → Provider Studio)*
- L'application package `SNOWSLED_V2_PKG` créée et une version `v2` déployée (`snow app run` effectué au moins une fois)
- Le **locator du compte consumer** (format `ORGNAME-ACCOUNTNAME` — visible dans Snowsight du client : *Admin → Accounts*)

### Option 1 — Extension Snowflake pour VS Code (recommandée)

1. Installez l'extension **Snowflake** dans VS Code (marketplace VS Code)
2. Connectez-vous à votre compte provider dans la barre latérale Snowflake
3. Ouvrez [scripts/create_listing.sql](scripts/create_listing.sql)
4. Remplacez `<ACCOUNT_LOCATOR_CLIENT_1>` par le locator du compte consumer cible :
   ```yaml
   accounts:
       - "ORGNAME-ACCOUNTNAME"   # ex: MYORG-CLIENT1
   ```
5. Sélectionnez tout le bloc **Option A** (de `USE ROLE ACCOUNTADMIN` jusqu'au dernier `ALTER LISTING`)
6. Clic droit → **Execute in Snowflake** (ou `Ctrl+Shift+P` → *Snowflake: Execute Query*)

### Option 2 — Snowflake CLI depuis le terminal VS Code

```bash
# Vérifier la connexion
snow connection test --connection dsp_inno

# Exécuter le script de création du listing
snow sql -f scripts/create_listing.sql --connection dsp_inno
```

### Vérification

Après exécution, la commande `SHOW LISTINGS;` (incluse en fin de script) retourne une ligne avec `SNOWSLED_V2_PRIVATE_LISTING` en statut `PUBLISHED`.

Le compte consumer reçoit une notification dans son Snowsight : **Data Products → Private Listings**.

### Partager plusieurs comptes

Pour ajouter d'autres comptes consumer, modifier le bloc `targets` dans [scripts/create_listing.sql](scripts/create_listing.sql) :

```yaml
targets:
    accounts:
        - "ORGNAME-CLIENT1"
        - "ORGNAME-CLIENT2"
```

Ou via une instruction SQL après création du listing :

```sql
ALTER LISTING SNOWSLED_V2_PRIVATE_LISTING
    ADD ACCOUNTS = 'ORGNAME-CLIENT2';
```

---

## Configuration post-installation

Quel que soit le mode d'installation, suivre cet ordre dans les applications :

```
1. Snowsled Platform  →  ⚙️ Compte Snowflake
                          Créer un warehouse et les bases DSI / DSO du projet

2. Snowsled Platform  →  🐙 GitHub / 🔵 dbt Cloud / 🔴 Fivetran
                          Renseigner et tester les credentials de chaque outil

3. Snowsled Admin     →  📐 Convention de nommage
                          Vérifier ou personnaliser les préfixes DSI, DSO, WH, ROLE

4. Snowsled Admin     →  🗂️ Projets
                          Créer un projet (ex : RETAIL) → génère automatiquement
                          les bases, le warehouse et les rôles associés

5. Snowsled           →  � Fivetran
                          Créer les connecteurs d'ingestion vers les sources
                          (Salesforce, PostgreSQL, S3, HubSpot…)

6. Snowsled           →  📥 Ingestion (DSI) / 📤 Présentation (DSO)
                          Créer les schémas, tables, vues et pipelines

7. Snowsled           →  🔗 dbt Models
                          Créer un projet dbt Cloud, attacher le dépôt Git
                          et déclencher les premiers runs de transformation

8. FinOps Monitor     →  📊 Dashboard coûts et gouvernance
```

---

## Applications Streamlit

### Snowsled Platform

Point d'entrée pour le setup initial du compte.

| Page | Action |
|---|---|
| ⚙️ Compte Snowflake | Création warehouse, bases DSI/DSO, rôles fonctionnels |
| 🐙 GitHub | Connexion via Personal Access Token (stocké en Secret Snowflake) |
| 🔵 dbt Cloud | Connexion via API Token + Account ID |
| 🔴 Fivetran | Connexion via API Key + API Secret |
| ❄️ Compliance | Vue d'ensemble de la gouvernance du compte |

### Snowsled Admin

Gouvernance et configuration du nommage.

| Page | Action |
|---|---|
| 📐 Convention de nommage | Définir préfixes / suffixes par couche (DSI, DSO, WH…) |
| 🗂️ Projets | Créer un projet → génère DSI_X, DSO_X, WH_X et tous les rôles |
| 👥 Rôles | Templates de privilèges (ADMIN / DEVELOPER / ANALYST / VIEWER) |
| 🔍 Journal d'audit | Toutes les actions Snowsled horodatées |
| 🤖 Cortex AI Monitor | Analyse intelligente du compte via Cortex |

### Snowsled

Création et gestion des objets de données au quotidien.

| Section | Objets / Actions |
|---|---|
| 📥 Ingestion (DSI) | Schémas landing, tables brutes, Snowpipes, Stages |
| 📤 Présentation (DSO) | Schémas métier, Secure Views, Data Sharing |
| 🔄 Pipelines | Snowflake Tasks pour transformation DSI → DSO |
| 🔴 Fivetran | Créer des connecteurs, lister les connecteurs existants, déclencher une sync |
| 🔗 dbt Models | Créer un projet dbt Cloud (repo Git + connexion Snowflake), déclencher des runs |
| 📊 Monitoring | Crédits consommés, historique requêtes, statut des tâches |

### FinOps Monitor

Dashboard de coûts et gouvernance exploitant `ACCOUNT_USAGE`.

> ⏳ Les données `ACCOUNT_USAGE` ont ~2h de latence — normal sur un compte récent.

---

## Convention de nommage

| Couche | Code | Exemple (projet = `RETAIL`) |
|---|---|---|
| Intégration brute | `DSI` | `DSI_RETAIL` |
| Présentation curated | `DSO` | `DSO_RETAIL` |
| Warehouse | `WH` | `WH_RETAIL` |
| Rôle admin | `ROLE` | `ROLE_RETAIL_ADMIN` |
| Rôle développeur | `ROLE` | `ROLE_RETAIL_DEVELOPER` |
| Rôle analyste | `ROLE` | `ROLE_RETAIL_ANALYST` |

> La convention est entièrement personnalisable dans **Snowsled Admin → Convention de nommage**.

---

## Structure du projet

```
Snowsled-v2/
├── snowflake.yml                    # Config Snowflake CLI (Native App + distribution: internal)
├── README.md                        # Ce fichier — guide unique de déploiement
├── MARKETPLACE_PUBLISH.md           # Guide publication Marketplace Snowflake (Provider)
├── requirements-local.txt           # Dépendances pour exécution locale (dev)
│
├── app/
│   ├── manifest.yml                 # Manifest Native App (privileges, secrets, network rules, streamlit)
│   ├── setup_script.sql             # Schémas, tables, procédures, Network Rule, EAI, Streamlit apps
│   ├── README.md                    # README affiché dans le listing Marketplace
│   └── src/
│       ├── snowsled_platform/
│       │   └── snowsled_platform.py # Setup compte, GitHub, dbt Cloud, Fivetran, Compliance
│       ├── snowsled_admin/
│       │   └── snowsled_admin.py    # Convention de nommage, projets, rôles, audit
│       ├── snowsled/
│       │   └── snowsled.py          # DSI, DSO, Pipelines, Fivetran, dbt, Monitoring
│       ├── finops_monitor/
│       │   └── streamlit_app.py
│       └── utils/
│           ├── __init__.py
│           └── session.py           # Gestion session Snowpark (native + local)
│
└── scripts/
    ├── deploy.sql                   # Rôles de packaging + installation manuelle
    ├── post_deploy.sql              # Initialisation config après installation
    ├── package_post_create.sql      # Release directive après création de version
    ├── create_listing.sql           # Création du listing Marketplace (privé / public)
    └── teardown.sql                 # Suppression complète de l'application
```

---

## Teardown

```bash
# Via Snowflake CLI
snow app teardown --connection dsp_inno
```

Ou dans un worksheet Snowflake :

```sql
USE ROLE ACCOUNTADMIN;

DROP APPLICATION IF EXISTS SNOWSLED_V2 CASCADE;
DROP APPLICATION PACKAGE IF EXISTS SNOWSLED_V2_PKG;
DROP ROLE IF EXISTS SNOWSLED_PKG_ROLE;

-- Optionnel : supprimer les secrets créés par Snowsled Platform
-- DROP SECRET IF EXISTS SNOWSLED_GITHUB_PAT;
-- DROP SECRET IF EXISTS SNOWSLED_DBT_TOKEN;
-- DROP SECRET IF EXISTS SNOWSLED_FIVETRAN_CREDS;
```

---

## Limitations du compte Trial Snowflake

| Fonctionnalité | Trial Standard | Trial Enterprise |
|---|---|---|
| `CREATE DATABASE / WAREHOUSE / ROLE` | ✅ | ✅ |
| `ACCOUNT_USAGE` (FinOps Monitor) | ✅ | ✅ |
| `EXECUTE TASK` | ✅ | ✅ |
| `CREATE SHARE` (Data Sharing) | ⚠️ Limité | ✅ |
| Multi-cluster Warehouses | ❌ | ✅ |
| Masking / Row Access Policies | ✅ | ✅ |

> 💡 **Recommandé** : choisir l'édition **Enterprise** à l'inscription pour bénéficier de toutes les vues `ACCOUNT_USAGE`.

> ⏳ **Latence ACCOUNT_USAGE** : les données du dashboard FinOps ont une latence de ~2h. Sur un compte récent, certaines vues seront vides dans un premier temps — c'est normal.

---

## Dépannage

### `snow app run` échoue avec `Insufficient privileges`

Vérifiez que le rôle `SNOWSLED_PKG_ROLE` a bien été attribué à votre utilisateur et que toutes les lignes du script `scripts/deploy.sql` ont été exécutées (étape 3 du mode B).

### L'application ne s'ouvre pas dans Snowsight

```sql
-- Vérifier que l'application est installée
SHOW APPLICATIONS LIKE 'SNOWSLED_V2';
-- La colonne "state" doit être "INSTALLED"
```

### Erreur `VERSION v2 already exists`

```bash
# Forcer le redéploiement
snow app run --connection dsp_inno --force
```

### Account Identifier mal formaté

Le format attendu dans `snow connection add` est l'un des suivants :

```
# Format court (visible dans l'URL Snowsight)
ABC12345

# Format complet (si le format court échoue)
ABC12345.us-east-1.aws
```

### Le dashboard FinOps Monitor affiche des données vides

1. Vérifiez que le grant `IMPORTED PRIVILEGES` a bien été appliqué (voir Étape 3)
2. Exécutez `CALL SNOWSLED_V2.APP_SCHEMA.INITIALIZE_FINOPS_VIEWS();` pour créer les vues dépendantes
3. `ACCOUNT_USAGE` a une latence de ~2h — attendez et générez de l'activité sur le compte

---

## Commandes de référence

```bash
# Installer Snowflake CLI
pip install snowflake-cli-labs

# Configurer la connexion
snow connection add

# Tester la connexion
snow connection test --connection dsp_inno

# Déployer Snowsled (création ou mise a jour)
snow app run --connection dsp_inno

# Supprimer le deploiement
snow app teardown --connection dsp_inno
```

---

*Snowsled v2 — Devoteam SP | AWS us-east-1 | Mars 2026*

