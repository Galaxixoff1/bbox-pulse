# ⚡ BboxPulse

Un dashboard de monitoring réseau moderne et premium pour votre BBox Bouygues Telecom. Visualisez vos débits, gérez vos objectifs de téléchargement, surveillez vos équipements connectés et conservez votre historique grâce à une stack ultra-légère basée sur Docker et Redis/Valkey.

![Version](https://img.shields.io/badge/version-2.0-blue?style=for-the-badge)
![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)
![Docker](https://img.shields.io/badge/docker-ready-cyan?style=for-the-badge)
![Database](https://img.shields.io/badge/database-redis%20%7C%20valkey-red?style=for-the-badge)

> [!NOTE]
> **💡 Origine du projet** : N'étant pas développeur de base, j'avais pour mon domicile un besoin spécifique de dashboard personnalisé connecté à ma BBox que je ne trouvais nulle part ailleurs. Ce projet a donc été entièrement conçu à l'aide d'une IA (**Antigravity avec Gemini**). Aujourd'hui, je partage ce code pour que d'autres puissent l'utiliser et le personnaliser !

---

## ✨ Fonctionnalités

*   **⚡ Débits en temps réel** : Graphiques sparkline réactifs pour suivre vos débits descendants (download) et ascendants (upload).
*   **🎯 Suivi d'objectif personnalisé** : Calculez dynamiquement votre progression par rapport à un objectif mensuel (ex: 5 To) avec estimation de l'ETA.
*   **📱 Gestion du réseau local** : Visualisez d'un coup d'œil le nombre d'équipements connectés actifs et connus sur votre réseau.
*   **📶 Statut Wi-Fi détaillé** : État d'activation et standards des bandes 2.4 GHz, 5 GHz, 6 GHz et Wi-Fi 7 (MLO).
*   **📈 Graphiques historiques** : Analyse de l'évolution sur plusieurs périodes (Live, 1H, 24H, 7 jours).
*   **⚙️ Page de configuration intégrée** : Ajustez le mot de passe, l'url Bbox, les fréquences de rafraîchissement et l'historique directement depuis l'interface web.
*   **fallback intelligent** : Fonctionne de manière autonome avec des fichiers JSON si Redis est indisponible.

---

## 🚀 Déploiement Rapide

### Prérequis

*   [Docker](https://docs.docker.com/get-docker/) + [Docker Compose](https://docs.docker.com/compose/install/)

### 1. Cloner le projet

```bash
git clone https://github.com/votre-username/bbox-pulse.git
cd bbox-pulse
```

### 2. Configurer les variables d'environnement

Copiez le fichier d'exemple et renseignez vos informations :

```bash
cp .env.example .env
```

Éditez le fichier `.env` :

```env
# Mot de passe de votre Bbox (Requis)
BBOX_PASSWORD=votre_mot_de_passe

# Port de l'application (Par défaut: 5000)
APP_PORT=5000

# Intervalle de collecte en secondes (Par défaut: 60)
MONITOR_INTERVAL=60

# Objectif cible en To (Par défaut: 5)
TARGET_TB=5

# Date de début de mesure (Format: YYYY-MM-DD)
UPTIME_START_DATE=2026-05-18
```

### 3. Démarrer l'application

Lancez la stack avec Docker Compose :

```bash
docker compose up -d --build
```

L'interface est accessible sur **http://localhost:5000** (ou sur l'IP de votre machine).

---

## 🛠 Structure du Projet

```text
bbox-pulse/
├── app.py                 # Serveur Flask, collecteur de données & API
├── requirements.txt       # Dépendances Python
├── Dockerfile             # Image Docker optimisée et sécurisée (non-root)
├── docker-compose.yml     # Orchestration des conteneurs (App + Redis)
├── .env.example           # Template de configuration
├── static/                # Interface Frontend
│   ├── index.html         # Dashboard principal
│   ├── graph.html         # Visualisation historique
│   ├── setting.html       # Page de configuration
│   ├── style.css          # Design sombre premium et moderne
│   └── app.js             # Logique frontend (Chart.js)
└── README.md
```

---

## 📐 Architecture & Fonctionnement

L'application est composée de deux parties principales qui tournent en parallèle :

1.  **Background Monitor (Collecteur)** : Un thread en arrière-plan interroge l'API de votre Bbox à intervalles réguliers (ex: 60s), traite les données de trafic WAN, de Wi-Fi, des hôtes réseau et stocke ces métriques temporelles dans Redis (ou fichiers JSON).
2.  **Web API (Flask/Gunicorn)** : Expose les points de terminaison pour alimenter l'interface web moderne.

```text
┌─────────────────┐       ┌──────────────────┐
│   Navigateur    │ ◀───▶ │  Gunicorn / Flask│
│   (Dashboard)   │       │   (Port 5000)    │
└─────────────────┘       └────────┬─────────┘
                                   │
                          ┌────────▼─────────┐
                          │   Redis/Valkey   │ ◀─── Stockage des états/historiques
                          └────────┬─────────┘
                                   │
                          ┌────────▼─────────┐
                          │     BBox API     │ ◀─── Collecte des statistiques WAN/WiFi
                          │(mabbox.bytel.fr) │
                          └──────────────────┘
```

---

## ⚙️ REST API Endpoints

| Endpoint | Méthode | Description |
| :--- | :--- | :--- |
| `/` | GET | Interface du Dashboard |
| `/graph` | GET | Page des graphiques historiques |
| `/setting` | GET | Page de configuration des paramètres |
| `/api/stats` | GET | Métriques de débit et d'état en temps réel |
| `/api/history` | GET | Historique décimé (`?timeframe=live,1h,24h,7d`) |
| `/api/config` | GET/POST| Récupérer ou mettre à jour la configuration |
| `/api/health` | GET | Healthcheck pour la supervision Docker |
| `/api/set_total`| GET | Ajuster manuellement les valeurs du total cumulé |

---

## 🧰 Commandes Utiles

**Visualiser les logs en temps réel :**
```bash
docker compose logs -f bbox-pulse
```

**Redémarrer l'application :**
```bash
docker compose restart bbox-pulse
```

**Arrêter la stack et conserver les données :**
```bash
docker compose down
```

**Accéder au shell de la base de données Redis :**
```bash
docker exec -it bbox-pulse-redis redis-cli
```

---

## 🛡️ Sécurité
*   Le conteneur applicatif tourne sous un utilisateur non-privilégié (`appuser`, UID `10001`).
*   Le conteneur utilise l'option `no-new-privileges:true` pour empêcher toute élévation de privilèges.
*   Un système d'initialisation (`init: true`) est configuré pour gérer correctement les signaux système (SIGTERM) et éviter les processus zombies.

---

## 📄 Licence

Ce projet est sous licence MIT. N'hésitez pas à l'utiliser et à l'améliorer !
