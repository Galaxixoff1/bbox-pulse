#!/usr/bin/env bash

# ⚡ BboxPulse - Script d'installation automatique et interactif
# Conçu pour installer Docker, configurer l'environnement et lancer le dashboard.

set -e

# Couleurs
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0;37m' # No Color

echo -e "${BLUE}"
echo "  ══════════════════════════════════════════════════════════"
echo "    ⚡ BboxPulse - Assistant d'installation interactive ⚡"
echo "  ══════════════════════════════════════════════════════════"
echo -e "${NC}"

# 1. Vérification du système d'exploitation
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo -e "${RED}⚠️ Ce script d'installation automatique est conçu pour Linux uniquement.${NC}"
    echo "Veuillez installer manuellement Docker et Docker Compose sur votre système."
    exit 1
fi

# 2. Vérification / Installation de Docker
check_docker() {
    if command -v docker >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

check_compose() {
    if docker compose version >/dev/null 2>&1 || command -v docker-compose >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

echo -e "${BLUE}[1/4] Vérification des prérequis...${NC}"

if check_docker; then
    echo -e "${GREEN}✓ Docker est installé ($(docker --version))${NC}"
else
    echo -e "${YELLOW}⚠ Docker n'est pas installé sur ce système.${NC}"
    read -rp "Voulez-vous installer Docker automatiquement ? (Nécessite les droits sudo) [O/n] : " install_docker
    install_docker=${install_docker:-O}
    
    if [[ "$install_docker" =~ ^[OoYy] ]]; then
        echo -e "${BLUE}Téléchargement et exécution du script officiel d'installation de Docker...${NC}"
        curl -fsSL https://get.docker.com -o get-docker.sh
        sudo sh get-docker.sh
        rm get-docker.sh
        
        # Ajout de l'utilisateur au groupe docker
        echo -e "${BLUE}Ajout de l'utilisateur actuel au groupe 'docker' pour éviter d'utiliser sudo...${NC}"
        sudo usermod -aG docker "$USER"
        echo -e "${YELLOW}ℹ Note : Vous devrez peut-être vous déconnecter et vous reconnecter pour que l'accès sans sudo soit actif.${NC}"
    else
        echo -e "${RED}L'installation a été annulée car Docker est obligatoire.${NC}"
        exit 1
    fi
fi

if check_compose; then
    echo -e "${GREEN}✓ Docker Compose est installé${NC}"
else
    echo -e "${YELLOW}⚠ Docker Compose est manquant.${NC}"
    read -rp "Voulez-vous installer le plugin Docker Compose ? [O/n] : " install_compose
    install_compose=${install_compose:-O}
    
    if [[ "$install_compose" =~ ^[OoYy] ]]; then
        # Installation du plugin compose selon la distribution
        if command -v apt-get >/dev/null 2>&1; then
            sudo apt-get update && sudo apt-get install -y docker-compose-plugin
        elif command -v dnf >/dev/null 2>&1; then
            sudo dnf install -y docker-compose-plugin
        else
            echo -e "${RED}Impossible d'installer docker-compose-plugin automatiquement sur cette distribution.${NC}"
            echo "Veuillez l'installer manuellement depuis : https://docs.docker.com/compose/install/"
            exit 1
        fi
        echo -e "${GREEN}✓ Docker Compose installé avec succès.${NC}"
    else
        echo -e "${RED}L'installation a été annulée car Docker Compose est obligatoire.${NC}"
        exit 1
    fi
fi

# 3. Configuration interactive (.env)
echo -e "\n${BLUE}[2/4] Configuration des paramètres de BboxPulse...${NC}"

if [ -f .env ]; then
    echo -e "${YELLOW}⚠ Un fichier de configuration (.env) existe déjà.${NC}"
    read -rp "Voulez-vous le remplacer ? [o/N] : " overwrite_env
    overwrite_env=${overwrite_env:-N}
else
    overwrite_env="O"
fi

if [[ "$overwrite_env" =~ ^[OoYy] ]]; then
    # Demande du mot de passe de la Bbox
    BBOX_PASSWORD=""
    while [ -z "$BBOX_PASSWORD" ]; do
        echo -ne "${YELLOW}🔑 Entrez le mot de passe de votre BBox (saisie masquée) : ${NC}"
        read -rs BBOX_PASSWORD
        echo ""
        if [ -z "$BBOX_PASSWORD" ]; then
            echo -e "${RED}Le mot de passe ne peut pas être vide !${NC}"
        fi
    done

    # Demande du port
    read -rp "🔌 Port de l'application web [Défaut: 5000] : " APP_PORT
    APP_PORT=${APP_PORT:-5000}

    # Demande de l'objectif
    read -rp "🎯 Objectif de téléchargement mensuel en To [Défaut: 5] : " TARGET_TB
    TARGET_TB=${TARGET_TB:-5}

    # Intervalle de collecte
    read -rp "⏱ Intervalle de collecte des données en secondes [Défaut: 60] : " MONITOR_INTERVAL
    MONITOR_INTERVAL=${MONITOR_INTERVAL:-60}

    # Création du fichier .env
    cat <<EOF > .env
# ─── BboxPulse Configuration ───
BBOX_PASSWORD=${BBOX_PASSWORD}
BBOX_BASE_URL=https://mabbox.bytel.fr
REDIS_URL=redis://redis:6379/0
APP_PORT=${APP_PORT}
MONITOR_INTERVAL=${MONITOR_INTERVAL}
TARGET_TB=${TARGET_TB}
UPTIME_START_DATE=$(date +%Y-%m-%d)
EOF

    echo -e "${GREEN}✓ Fichier de configuration .env généré avec succès !${NC}"
fi

# 4. Lancement
echo -e "\n${BLUE}[3/4] Préparation du démarrage...${NC}"
read -rp "🚀 Voulez-vous démarrer BboxPulse maintenant ? [O/n] : " launch_now
launch_now=${launch_now:-O}

if [[ "$launch_now" =~ ^[OoYy] ]]; then
    echo -e "${BLUE}Téléchargement des images et construction du conteneur en arrière-plan...${NC}"
    docker compose up -d --build
    
    echo -e "\n${GREEN}══════════════════════════════════════════════════════════"
    echo -e "  🎉 Félicitations ! BboxPulse a démarré avec succès. 🎉"
    echo -e "══════════════════════════════════════════════════════════${NC}"
    echo -e "Dashboard accessible sur : ${BLUE}http://localhost:${APP_PORT}${NC}"
    echo -e "Pour voir les logs, lancez : ${YELLOW}docker compose logs -f bbox-pulse${NC}"
else
    echo -e "${YELLOW}Configuration terminée. Vous pourrez lancer l'application plus tard en faisant :${NC}"
    echo -e "👉 ${BLUE}docker compose up -d --build${NC}"
fi
