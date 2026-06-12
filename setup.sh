#!/usr/bin/env bash

# ⚡ BboxPulse - Script de gestion et d'installation interactive
# Conçu pour gérer Docker, configurer l'environnement, planifier des redémarrages (Cron), et mettre à jour le projet.

set -e

# Couleurs
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0;37m' # No Color

# Vérification du système d'exploitation
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo -e "${RED}⚠️ Ce script d'installation automatique est conçu pour Linux uniquement.${NC}"
    echo "Veuillez installer manuellement Docker et Docker Compose sur votre système."
    exit 1
fi

# Fonctions de vérification des prérequis
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

install_docker_if_needed() {
    echo -e "${BLUE}Vérification des prérequis...${NC}"
    
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
}

# Fonctions de chargement et sauvegarde de la configuration .env
load_env() {
    if [ -f .env ]; then
        BBOX_PASSWORD=$(grep "^BBOX_PASSWORD=" .env | cut -d'=' -f2- || echo "")
        BBOX_BASE_URL=$(grep "^BBOX_BASE_URL=" .env | cut -d'=' -f2- || echo "https://mabbox.bytel.fr")
        REDIS_URL=$(grep "^REDIS_URL=" .env | cut -d'=' -f2- || echo "redis://redis:6379/0")
        APP_PORT=$(grep "^APP_PORT=" .env | cut -d'=' -f2- || echo "5000")
        MONITOR_INTERVAL=$(grep "^MONITOR_INTERVAL=" .env | cut -d'=' -f2- || echo "60")
        UPTIME_START_DATE=$(grep "^UPTIME_START_DATE=" .env | cut -d'=' -f2- || echo "$(date +%Y-%m-%d)")
        TARGET_TB=$(grep "^TARGET_TB=" .env | cut -d'=' -f2- || echo "5")
    else
        BBOX_PASSWORD=""
        BBOX_BASE_URL="https://mabbox.bytel.fr"
        REDIS_URL="redis://redis:6379/0"
        APP_PORT="5000"
        MONITOR_INTERVAL="60"
        UPTIME_START_DATE="$(date +%Y-%m-%d)"
        TARGET_TB="5"
    fi
}

save_env() {
    cat <<EOF > .env
# ─── BboxPulse Configuration ───
BBOX_PASSWORD=${BBOX_PASSWORD}
BBOX_BASE_URL=${BBOX_BASE_URL}
REDIS_URL=${REDIS_URL}
APP_PORT=${APP_PORT}
MONITOR_INTERVAL=${MONITOR_INTERVAL}
UPTIME_START_DATE=${UPTIME_START_DATE}
TARGET_TB=${TARGET_TB}
EOF
}

# Configuration initiale complète
setup_initial_env() {
    echo -e "\n${BLUE}Configuration des paramètres de BboxPulse...${NC}"
    
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
    read -rp "🔌 Port de l'application web [Défaut: 5000] : " temp_port
    APP_PORT=${temp_port:-5000}

    # Demande de l'objectif
    read -rp "🎯 Objectif de téléchargement mensuel en To [Défaut: 5] : " temp_target
    TARGET_TB=${temp_target:-5}

    # Intervalle de collecte
    read -rp "⏱ Intervalle de collecte des données en secondes [Défaut: 60] : " temp_interval
    MONITOR_INTERVAL=${temp_interval:-60}

    save_env
    echo -e "${GREEN}✓ Fichier de configuration .env généré avec succès !${NC}"
}

# Menu de modification de configuration spécifique
edit_env_menu() {
    while true; do
        load_env
        clear
        echo -e "${BLUE}══════════════════════════════════════════════════════════${NC}"
        echo -e "            ⚙️  MODIFICATION DE LA CONFIGURATION"
        echo -e "${BLUE}══════════════════════════════════════════════════════════${NC}"
        echo -e "  1) Mot de passe Bbox     : ********"
        echo -e "  2) Port de l'application : ${APP_PORT}"
        echo -e "  3) Objectif mensuel (To)  : ${TARGET_TB} To"
        echo -e "  4) Intervalle de collecte : ${MONITOR_INTERVAL}s"
        echo -e "  5) Date début d'infra    : ${UPTIME_START_DATE}"
        echo -e "  6) 💾 Sauvegarder et retourner au menu principal"
        echo -e "  7) 🔙 Annuler et retourner au menu principal"
        echo ""
        echo -ne "Choisissez un paramètre à modifier [1-7] : "
        read -r choice
        
        case "$choice" in
            1)
                echo -ne "${YELLOW}🔑 Nouveau mot de passe BBox (masqué, laissez vide pour ne pas modifier) : ${NC}"
                read -rs temp_pass
                echo ""
                if [ -n "$temp_pass" ]; then
                    BBOX_PASSWORD="$temp_pass"
                    echo -e "${GREEN}✓ Mot de passe mis à jour.${NC}"
                fi
                save_env
                read -rsp "Appuyez sur Entrée pour continuer..."
                ;;
            2)
                read -rp "🔌 Nouveau port de l'application [Actuel: $APP_PORT] : " temp_port
                if [ -n "$temp_port" ]; then
                    APP_PORT="$temp_port"
                    echo -e "${GREEN}✓ Port mis à jour.${NC}"
                fi
                save_env
                read -rsp "Appuyez sur Entrée pour continuer..."
                ;;
            3)
                read -rp "🎯 Nouvel objectif mensuel en To [Actuel: $TARGET_TB] : " temp_target
                if [ -n "$temp_target" ]; then
                    TARGET_TB="$temp_target"
                    echo -e "${GREEN}✓ Objectif mis à jour.${NC}"
                fi
                save_env
                read -rsp "Appuyez sur Entrée pour continuer..."
                ;;
            4)
                read -rp "⏱️ Nouvel intervalle de collecte en secondes [Actuel: $MONITOR_INTERVAL] : " temp_interval
                if [ -n "$temp_interval" ]; then
                    MONITOR_INTERVAL="$temp_interval"
                    echo -e "${GREEN}✓ Intervalle mis à jour.${NC}"
                fi
                save_env
                read -rsp "Appuyez sur Entrée pour continuer..."
                ;;
            5)
                read -rp "📅 Nouvelle date début d'infra (YYYY-MM-DD) [Actuel: $UPTIME_START_DATE] : " temp_date
                if [ -n "$temp_date" ]; then
                    UPTIME_START_DATE="$temp_date"
                    echo -e "${GREEN}✓ Date mise à jour.${NC}"
                fi
                save_env
                read -rsp "Appuyez sur Entrée pour continuer..."
                ;;
            6)
                save_env
                echo -e "${GREEN}✓ Configuration enregistrée dans le fichier .env.${NC}"
                read -rp "🚀 Voulez-vous redémarrer le conteneur pour appliquer les changements ? [O/n] : " restart_now
                restart_now=${restart_now:-O}
                if [[ "$restart_now" =~ ^[OoYy] ]]; then
                    echo -e "${BLUE}Redémarrage des conteneurs...${NC}"
                    docker compose up -d --build
                fi
                break
                ;;
            7)
                break
                ;;
            *)
                echo -e "${RED}Option invalide !${NC}"
                sleep 1
                ;;
        esac
    done
}

# Menu de planification automatique (Cron)
manage_cron() {
    clear
    echo -e "${BLUE}══════════════════════════════════════════════════════════${NC}"
    echo -e "        ⏱️  PLANIFICATION DU REDÉMARRAGE AUTOMATIQUE"
    echo -e "${BLUE}══════════════════════════════════════════════════════════${NC}"
    
    CURRENT_CRON=$(crontab -l 2>/dev/null | grep "bbox-pulse-restart" || true)
    
    if [ -n "$CURRENT_CRON" ]; then
        echo -e "${GREEN}✓ Une tâche Cron est actuellement configurée :${NC}"
        echo -e "${YELLOW}$CURRENT_CRON${NC}"
        echo ""
        echo "  1) Modifier l'intervalle"
        echo "  2) Supprimer la planification automatique"
        echo "  3) Retour au menu principal"
        echo ""
        echo -ne "Choisissez une option [1-3] : "
        read -r cron_choice
    else
        echo -e "${YELLOW}ℹ Aucune planification automatique n'est configurée pour le moment.${NC}"
        echo ""
        echo "  1) Activer le redémarrage automatique (Cron)"
        echo "  2) Retour au menu principal"
        echo ""
        echo -ne "Choisissez une option [1-2] : "
        read -r cron_choice
        if [ "$cron_choice" = "1" ]; then
            cron_choice="1"
        else
            cron_choice="3"
        fi
    fi
    
    case "$cron_choice" in
        1)
            echo ""
            read -rp "⏱️ Spécifiez l'intervalle de redémarrage en minutes (ex: 30 pour 30min, 60 pour 1h) : " CRON_MINUTES
            
            if ! [[ "$CRON_MINUTES" =~ ^[0-9]+$ ]] || [ "$CRON_MINUTES" -le 0 ]; then
                echo -e "${RED}Intervalle invalide. Doit être un nombre entier supérieur à 0.${NC}"
                read -rsp "Appuyez sur Entrée pour revenir..."
                return 1
            fi
            
            DOCKER_BIN=$(command -v docker || echo "/usr/bin/docker")
            
            if [ "$CRON_MINUTES" -lt 60 ]; then
                CRON_EXPR="*/$CRON_MINUTES * * * *"
            else
                HOURS=$((CRON_MINUTES / 60))
                MINS=$((CRON_MINUTES % 60))
                if [ "$MINS" -eq 0 ]; then
                    CRON_EXPR="0 */$HOURS * * *"
                else
                    CRON_EXPR="*/$CRON_MINUTES * * * *"
                    if [ "$CRON_MINUTES" -gt 59 ]; then
                        echo -e "${YELLOW}⚠ Note: Votre intervalle dépasse 59 minutes et n'est pas un multiple de 60.${NC}"
                        echo -e "${YELLOW}Nous allons utiliser la tâche toutes les heures (0 * * * *).${NC}"
                        CRON_EXPR="0 * * * *"
                    fi
                fi
            fi
            
            CRON_CMD="$DOCKER_BIN restart bbox-pulse"
            
            # Mise à jour de la crontab
            (crontab -l 2>/dev/null | grep -v "bbox-pulse-restart" ; echo "$CRON_EXPR $CRON_CMD >/dev/null 2>&1 # bbox-pulse-restart") | crontab -
            
            echo -e "\n${GREEN}✓ Redémarrage automatique activé avec succès !${NC}"
            echo -e "Règle ajoutée à la crontab : ${YELLOW}$CRON_EXPR $CRON_CMD${NC}"
            read -rsp "Appuyez sur Entrée pour continuer..."
            ;;
        2)
            (crontab -l 2>/dev/null | grep -v "bbox-pulse-restart") | crontab -
            echo -e "${GREEN}✓ Redémarrage automatique désactivé (tâche Cron supprimée).${NC}"
            read -rsp "Appuyez sur Entrée pour continuer..."
            ;;
        3)
            return 0
            ;;
        *)
            echo -e "${RED}Option invalide !${NC}"
            sleep 1
            ;;
    esac
}

# Mise à jour depuis Git
update_project() {
    echo -e "\n${BLUE}🔄 Mise à jour de BboxPulse depuis Git...${NC}"
    if [ -d .git ]; then
        if command -v git >/dev/null 2>&1; then
            git pull || echo -e "${YELLOW}⚠️ Impossible de récupérer automatiquement via Git (peut-être des modifications locales).${NC}"
        else
            echo -e "${RED}⚠ Git n'est pas installé.${NC}"
        fi
    else
        echo -e "${YELLOW}ℹ Le répertoire n'est pas un dépôt Git. Étape ignorée.${NC}"
    fi
    echo -e "${BLUE}🔨 Reconstruction et démarrage des conteneurs...${NC}"
    docker compose up -d --build
    echo -e "${GREEN}✓ BboxPulse a été mis à jour et relancé !${NC}"
    read -rsp "Appuyez sur Entrée pour continuer..."
}

# Réparation
repair_project() {
    echo -e "\n${BLUE}🛠️  Réparation de BboxPulse...${NC}"
    install_docker_if_needed
    echo -e "${BLUE}Arrêt des conteneurs existants...${NC}"
    docker compose down || true
    echo -e "${BLUE}Reconstruction complète et démarrage sans cache...${NC}"
    docker compose build --no-cache
    docker compose up -d --force-recreate
    echo -e "${GREEN}✓ Réparation terminée avec succès !${NC}"
    read -rsp "Appuyez sur Entrée pour continuer..."
}

# Désinstallation
uninstall_project() {
    echo -e "\n${RED}⚠ DÉSINSTALLATION DE BBOXPULSE ⚠${NC}"
    read -rp "Voulez-vous vraiment désinstaller BboxPulse ? Les volumes Docker et les données seront supprimés. [o/N] : " confirm
    if [[ "$confirm" =~ ^[OoYy] ]]; then
        echo -e "${BLUE}Arrêt des conteneurs et suppression des volumes Docker...${NC}"
        docker compose down -v || true
        
        echo -e "Suppression de la tâche Cron de redémarrage..."
        (crontab -l 2>/dev/null | grep -v "bbox-pulse-restart") | crontab - || true
        
        read -rp "Voulez-vous également supprimer le fichier de configuration .env ? [o/N] : " del_env
        if [[ "$del_env" =~ ^[OoYy] ]]; then
            rm -f .env
            echo -e "Fichier .env supprimé."
        fi
        
        echo -e "${GREEN}✓ Désinstallation terminée.${NC}"
    else
        echo -e "${YELLOW}Désinstallation annulée.${NC}"
    fi
    read -rsp "Appuyez sur Entrée pour continuer..."
}

# Lancement classique d'installation
install_and_start() {
    install_docker_if_needed
    
    if [ ! -f .env ]; then
        setup_initial_env
    else
        load_env
        echo -e "${GREEN}✓ Configuration .env existante chargée.${NC}"
    fi
    
    echo -e "${BLUE}Lancement des conteneurs BboxPulse...${NC}"
    docker compose up -d --build
    
    echo -e "\n${GREEN}══════════════════════════════════════════════════════════"
    echo -e "  🎉 BboxPulse a démarré avec succès. 🎉"
    echo -e "══════════════════════════════════════════════════════════${NC}"
    echo -e "Dashboard accessible sur : ${BLUE}http://localhost:${APP_PORT}${NC}"
    echo -e "Pour voir les logs, lancez : ${YELLOW}docker compose logs -f bbox-pulse${NC}"
    read -rsp "Appuyez sur Entrée pour continuer..."
}

# Boucle principale du script
while true; do
    clear
    echo -e "${BLUE}"
    echo "  ══════════════════════════════════════════════════════════"
    echo "    ⚡ BboxPulse - Assistant de Gestion & Installation ⚡"
    echo "  ══════════════════════════════════════════════════════════"
    echo -e "${NC}"
    echo -e "  1) 🚀 Installer / Démarrer BboxPulse"
    echo -e "  2) ⚙️  Modifier la configuration (.env)"
    echo -e "  3) 🔄 Mettre à jour BboxPulse (depuis Git)"
    echo -e "  4) ⏱️  Planifier le redémarrage automatique (Cron)"
    echo -e "  5) 🛠️  Réparer / Reconstruire les conteneurs"
    echo -e "  6) 🗑️  Désinstaller l'application"
    echo -e "  7) ❌ Quitter"
    echo ""
    echo -ne "Choisissez une option [1-7] : "
    read -r main_choice
    
    case "$main_choice" in
        1)
            install_and_start
            ;;
        2)
            edit_env_menu
            ;;
        3)
            update_project
            ;;
        4)
            manage_cron
            ;;
        5)
            repair_project
            ;;
        6)
            uninstall_project
            ;;
        7)
            echo -e "${GREEN}Au revoir !${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}Option invalide !${NC}"
            sleep 1
            ;;
    esac
done
