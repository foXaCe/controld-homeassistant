# ControlD Home Assistant Integration

[English](#english) | [Français](#français)

---

## English

A comprehensive ControlD integration that allows you to control your DNS profiles, filters, and settings directly from Home Assistant.

### Features

- **Sensors**: Monitor profiles, devices, active clients, and statistics
- **Switches**: Control filters, services, and options per profile
- **Number Entities**: Configure numeric thresholds (e.g., AI malware detection)
- **Services**: Device management and bulk modifications

### Installation

1. Copy the `custom_components/controld` folder to your `config/custom_components/` directory
2. Restart Home Assistant
3. Add the integration via Configuration > Integrations > Add Integration > ControlD
4. Enter your ControlD API token with read/write permissions

### ⚠️ Known Issue with ControlD API

**Switches (filters/services/options) do not apply their changes to ControlD despite positive API responses.**

#### Observed Symptoms:
- Home Assistant interface shows state change temporarily
- ControlD API responds with `HTTP 200` and `"success": true`
- **BUT** changes never appear on the ControlD website
- Switch state reverts to original value after 30 seconds

#### Tests Performed:
```bash
# Direct API test - Action format
curl -X PUT "https://api.controld.com/profiles/{PROFILE_ID}/native/filters/{FILTER_ID}" \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"action": {"do": 0, "status": 1}}'

# Response: HTTP 200 + "success": true
# Result: No change on ControlD
```

#### Tested Configurations:
- ✅ Token with write permissions
- ✅ Endpoints `/native/filters/`, `/services/`, `/options/`
- ✅ Data formats `{"status": 1}` and `{"action": {"do": 0, "status": 1}}`
- ✅ Different profiles and filters
- ❌ **No modifications are ever applied**

#### Working Endpoints (read-only):
- ✅ `GET /profiles` - List profiles
- ✅ `GET /devices` - List devices
- ✅ `GET /profiles/{id}/filters` - Filter details
- ✅ `GET /profiles/{id}/services` - Service details
- ✅ `GET /profiles/{id}/options` - Option details

#### Failing Endpoints (write):
- ❌ `PUT /profiles/{id}/native/filters/{filter_id}` - Changes ignored
- ❌ `PUT /profiles/{id}/services/{service_id}` - Changes ignored
- ❌ `PUT /profiles/{id}/options/{option_id}` - Changes ignored

### Temporary Solutions

1. **Disable switches**: If you don't want to see temporary states
2. **Use ControlD interface**: For manual modifications
3. **Monitoring only**: Use sensors to monitor state

### Support and Contribution

If you have information about the correct ControlD API format or observe different behaviors, please share your findings.

This integration is technically ready - the issue lies within the ControlD API itself which does not properly handle modification requests.

---

## Français

Une intégration complète pour ControlD qui permet de contrôler vos profils DNS, filtres et paramètres directement depuis Home Assistant.

### Fonctionnalités

- **Sensors** : Surveillance des profils, appareils, clients actifs et statistiques
- **Switches** : Contrôle des filtres, services et options par profil
- **Number Entities** : Configuration des seuils numériques (ex: détection malware IA)
- **Services** : Gestion des appareils et modifications en masse

### Installation

1. Copiez le dossier `custom_components/controld` dans votre répertoire `config/custom_components/`
2. Redémarrez Home Assistant
3. Ajoutez l'intégration via Configuration > Intégrations > Ajouter une intégration > ControlD
4. Entrez votre token API ControlD avec permissions de lecture/écriture

### ⚠️ Problème connu avec l'API ControlD

**Les switches (filtres/services/options) n'appliquent pas leurs modifications sur ControlD malgré une réponse API positive.**

#### Symptômes observés :
- L'interface Home Assistant montre le changement d'état temporairement
- L'API ControlD répond avec `HTTP 200` et `"success": true`
- **MAIS** les modifications n'apparaissent jamais sur le site ControlD
- L'état du switch revient à sa valeur d'origine après 30 secondes

#### Tests effectués :
```bash
# Test direct de l'API - Format avec action
curl -X PUT "https://api.controld.com/profiles/{PROFILE_ID}/native/filters/{FILTER_ID}" \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"action": {"do": 0, "status": 1}}'

# Réponse : HTTP 200 + "success": true
# Résultat : Aucun changement sur ControlD
```

#### Configurations testées :
- ✅ Token avec permissions write
- ✅ Endpoints `/native/filters/`, `/services/`, `/options/`
- ✅ Format de données `{"status": 1}` et `{"action": {"do": 0, "status": 1}}`
- ✅ Différents profils et filtres
- ❌ **Aucune modification n'est jamais appliquée**

#### Endpoints fonctionnels (lecture seule) :
- ✅ `GET /profiles` - Liste des profils
- ✅ `GET /devices` - Liste des appareils
- ✅ `GET /profiles/{id}/filters` - Détails des filtres
- ✅ `GET /profiles/{id}/services` - Détails des services
- ✅ `GET /profiles/{id}/options` - Détails des options

#### Endpoints défaillants (écriture) :
- ❌ `PUT /profiles/{id}/native/filters/{filter_id}` - Modifications ignorées
- ❌ `PUT /profiles/{id}/services/{service_id}` - Modifications ignorées
- ❌ `PUT /profiles/{id}/options/{option_id}` - Modifications ignorées

### Solutions temporaires

1. **Désactiver les switches** : Si vous ne voulez pas voir les états temporaires
2. **Utiliser l'interface ControlD** : Pour les modifications manuelles
3. **Monitoring uniquement** : Utiliser les sensors pour surveiller l'état

### Support et Contribution

Si vous avez des informations sur le bon format d'API ControlD ou si vous observez des comportements différents, merci de partager vos découvertes.

Cette intégration est prête techniquement - le problème réside dans l'API ControlD elle-même qui ne traite pas correctement les requêtes de modification.