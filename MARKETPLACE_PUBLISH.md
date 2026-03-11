# 📦 Publier Snowsled v2 sur le Snowflake Marketplace

> Ce guide couvre l'intégralité du processus de publication d'une **Snowflake Native App** sur le Marketplace, de la préparation du package jusqu'à la mise en ligne publique (ou listing privé).

---

## Table des matières

1. [Prérequis](#1-prérequis)
2. [Devenir Provider Snowflake](#2-devenir-provider-snowflake)
3. [Préparer le package applicatif](#3-préparer-le-package-applicatif)
4. [Versionner l'application](#4-versionner-lapplication)
5. [Tester en tant que consumer](#5-tester-en-tant-que-consumer)
6. [Créer le listing Marketplace](#6-créer-le-listing-marketplace)
7. [Soumettre à la revue Snowflake](#7-soumettre-à-la-revue-snowflake)
8. [Gérer les versions et mises à jour](#8-gérer-les-versions-et-mises-à-jour)
9. [Commandes de référence](#9-commandes-de-référence)

---

## 1. Prérequis

| Prérequis | Détail |
|---|---|
| Compte Snowflake dédié Provider | Compte **Business Critical** ou **Enterprise** recommandé |
| Rôle `ACCOUNTADMIN` | Pour créer le package et le listing |
| Snowflake CLI (`snow`) ≥ 3.x | `pip install snowflake-cli-labs` |
| Python ≥ 3.11 | — |
| Accès à [Partner Network / Provider Portal](https://app.snowflake.com) | Activation requise (cf. §2) |

> **Important** : le compte Provider doit être distinct du compte de développement. Ne jamais publier depuis un compte de test.

---

## 2. Devenir Provider Snowflake

### 2.1 Activer le Provider Profile

1. Connectez-vous à [Snowsight](https://app.snowflake.com) avec le compte Provider.
2. Naviguez vers **Data Products → Provider Studio**.
3. Cliquez sur **Become a Provider** et remplissez le profil :
   - Nom de l'organisation
   - Logo (PNG, 200×200 px minimum)
   - Description courte et longue
   - URL du site web et documentation
   - Adresse e-mail de support

4. Soumettez la demande — Snowflake valide le profil sous **2 à 5 jours ouvrés**.

### 2.2 Vérifier le statut

```sql
-- Vérifier que le profil provider est actif
SELECT SYSTEM$SHOW_PROVIDER_PROFILE();
```

---

## 3. Préparer le package applicatif

### 3.1 Créer le rôle dédié au package

```sql
-- Exécuter en ACCOUNTADMIN sur le compte Provider
USE ROLE ACCOUNTADMIN;

CREATE ROLE IF NOT EXISTS SNOWSLED_PKG_ROLE;
GRANT CREATE APPLICATION PACKAGE ON ACCOUNT TO ROLE SNOWSLED_PKG_ROLE;
GRANT CREATE APPLICATION          ON ACCOUNT TO ROLE SNOWSLED_PKG_ROLE;
GRANT CREATE DATABASE             ON ACCOUNT TO ROLE SNOWSLED_PKG_ROLE;
GRANT CREATE WAREHOUSE            ON ACCOUNT TO ROLE SNOWSLED_PKG_ROLE;

GRANT ROLE SNOWSLED_PKG_ROLE TO USER <your_user>;
```

### 3.2 Vérifier le manifest

Le fichier [app/manifest.yml](app/manifest.yml) doit déclarer :

- `manifest_version: 1`
- La version `name` / `label` / `comment`
- Les `privileges` demandées (justifiées et minimales)
- Les `references` pour les Secrets externes (GitHub, dbt, Fivetran)
- Le `default_streamlit` pointant vers `src/snowsled_platform`

> Chaque privilège demandé sera visible par le consumer avant installation. Justifiez-les précisément dans le champ `description`.

### 3.3 Vérifier le snowflake.yml

Le fichier [snowflake.yml](snowflake.yml) doit référencer :

```yaml
native_app:
  package:
    name: SNOWSLED_V2_PKG
    role: SNOWSLED_PKG_ROLE          # rôle créé en §3.1
    scripts:
      post_version_create: scripts/package_post_create.sql
```

### 3.4 Déployer le package sur le compte Provider

```bash
# Depuis la racine du projet
snow app bundle --connection <provider_connection>

# Créer le stage et uploader les artefacts
snow app run --connection <provider_connection>
```

Cette commande crée l'`APPLICATION PACKAGE SNOWSLED_V2_PKG` sur le compte Provider, avec le stage `stage_content` qui héberge tout le code source.

---

## 4. Versionner l'application

Le Marketplace nécessite qu'une **version publiée** soit rattachée au package (pas une `DEBUG` install).

### 4.1 Créer une version

```sql
USE ROLE SNOWSLED_PKG_ROLE;

ALTER APPLICATION PACKAGE SNOWSLED_V2_PKG
  ADD VERSION v2_0
  USING '@SNOWSLED_V2_PKG.APP_SCHEMA.stage_content'
  LABEL = 'Snowsled v2.0 — Initial Release';
```

Ou via Snowflake CLI :

```bash
snow app version create v2_0 \
  --label "Snowsled v2.0 — Initial Release" \
  --connection <provider_connection>
```

### 4.2 Définir la version par défaut du package

```sql
ALTER APPLICATION PACKAGE SNOWSLED_V2_PKG
  SET DEFAULT RELEASE DIRECTIVE
  VERSION = v2_0
  PATCH   = 0;
```

### 4.3 Vérifier les versions disponibles

```sql
SHOW VERSIONS IN APPLICATION PACKAGE SNOWSLED_V2_PKG;
```

---

## 5. Tester en tant que consumer

Avant toute publication, effectuez un **test end-to-end** depuis un compte consumer test (secondaire) :

```sql
-- Sur le compte consumer test, en ACCOUNTADMIN
CREATE APPLICATION SNOWSLED_V2_TEST
  FROM APPLICATION PACKAGE SNOWSLED_V2_PKG
  USING VERSION v2_0 PATCH 0;
```

Vérifiez :
- [ ] Les 3 apps Streamlit s'ouvrent sans erreur
- [ ] Le pop-up de permissions s'affiche correctement
- [ ] Chaque privilège demandé est justifié
- [ ] Les références aux Secrets (GitHub, dbt, Fivetran) fonctionnent
- [ ] L'initialisation (`setup_script.sql`) se termine sans erreur
- [ ] Le script `post_deploy.sql` s'exécute proprement
- [ ] Le teardown (`snow app teardown`) nettoie toutes les ressources

---

## 6. Créer le listing Marketplace

### 6.1 Depuis Provider Studio (UI recommandée)

1. Dans **Snowsight → Data Products → Provider Studio**, cliquez sur **+ New Listing**.
2. Choisissez le type :
   - **Public** : visible par tous les comptes Snowflake
   - **Private** : accessible uniquement via invitation (URL partagée ou whitelist)
3. Remplissez les métadonnées du listing :

| Champ | Valeur recommandée |
|---|---|
| Listing name | `Snowsled — Data Platform Governance` |
| Short description | `Native App Snowflake pour gouverner vos bases DSI/DSO, conventions de nommage et intégrations externes.` |
| Categories | `Data Management`, `Productivity & Collaboration` |
| Supported clouds & regions | Sélectionnez `AWS us-east-1` (et autres régions testées) |
| App package | `SNOWSLED_V2_PKG` |
| Version | `v2_0` |

4. Ajoutez des **screenshots** (1280×720 px) des 3 apps Streamlit.
5. Rédigez la documentation dans le champ **About** (Markdown supporté).
6. Configurez le **support e-mail** et l'**URL de documentation**.

### 6.2 Via SQL (listing privé uniquement)

```sql
-- Création d'un listing privé
USE ROLE ACCOUNTADMIN;

CALL SYSTEM$CREATE_LISTING(
  '{
    "title": "Snowsled — Data Platform Governance",
    "description": "Native App pour gouvernance DSI/DSO, naming, rôles et intégrations.",
    "categories": ["DATA_MANAGEMENT"],
    "listing_type": "PRIVATE",
    "package": {
      "name": "SNOWSLED_V2_PKG",
      "default_version": "v2_0"
    }
  }'
);
```

---

## 7. Soumettre à la revue Snowflake

Les listings **publics** passent par un processus de validation Snowflake (sécurité, conformité, UX).

### 7.1 Checklist avant soumission

- [ ] Le `manifest.yml` ne demande que les privilèges strictement nécessaires
- [ ] Aucun credential n'est stocké en clair (tout via `SECRETS`)
- [ ] Le `README.md` applicatif (dans `app/`) explique clairement l'usage
- [ ] L'application fonctionne sans `debug: true`
- [ ] Le `setup_script.sql` est idempotent (relançable sans erreur)
- [ ] Toutes les procédures stockées définissent un `EXECUTE AS OWNER` ou `CALLER` explicite
- [ ] Les erreurs sont catchées et retournent des messages exploitables

### 7.2 Soumettre le listing

Dans **Provider Studio → [votre listing] → Submit for Review**.

La revue Snowflake dure généralement **5 à 15 jours ouvrés**.

### 7.3 Suivre l'état de la revue

```sql
SHOW LISTINGS;
-- Colonne STATUS : DRAFT | IN_REVIEW | PUBLISHED | REJECTED
```

---

## 8. Gérer les versions et mises à jour

### 8.1 Publier un patch (correctif)

```bash
# Modifier le code, puis :
snow app version create v2_0 \
  --patch \
  --label "Snowsled v2.0.1 — Bug fixes" \
  --connection <provider_connection>
```

### 8.2 Publier une version majeure

```bash
snow app version create v2_1 \
  --label "Snowsled v2.1 — Nouvelles fonctionnalités" \
  --connection <provider_connection>

# Mettre à jour le release directive
snow app release-directive set \
  --version v2_1 --patch 0 \
  --connection <provider_connection>
```

Les consumers existants recevront une **notification de mise à jour** dans Snowsight.

### 8.3 Rollback

```sql
-- Revenir à la version précédente
ALTER APPLICATION PACKAGE SNOWSLED_V2_PKG
  SET DEFAULT RELEASE DIRECTIVE
  VERSION = v2_0
  PATCH   = 0;
```

---

## 9. Commandes de référence

```bash
# Tester la connexion Provider
snow connection test --connection <provider_connection>

# Bundler les artefacts sans déployer
snow app bundle --connection <provider_connection>

# Déployer le package (upload + install pour test)
snow app run --connection <provider_connection>

# Créer une version publiable
snow app version create <version_name> --connection <provider_connection>

# Lister les versions
snow app version list --connection <provider_connection>

# Supprimer une version
snow app version drop <version_name> --connection <provider_connection>

# Teardown complet (dev/test uniquement)
snow app teardown --connection <provider_connection>
```

---

## Ressources officielles

- [Snowflake Native App Framework — Documentation](https://docs.snowflake.com/en/developer-guide/native-apps/native-apps-about)
- [Publishing to the Snowflake Marketplace](https://docs.snowflake.com/en/developer-guide/native-apps/publishing-to-marketplace)
- [Provider Studio Guide](https://docs.snowflake.com/en/user-guide/data-marketplace-provider)
- [Application Package — Versioning](https://docs.snowflake.com/en/developer-guide/native-apps/versioning-application-packages)
- [Snowflake CLI Reference](https://docs.snowflake.com/en/developer-guide/snowflake-cli/index)

---

*Snowsled v2 — Guide de publication Marketplace | Février 2026*
