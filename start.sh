#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

# Couleurs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}"
echo "  ██╗  ██╗ █████╗ ██╗   ██╗███████╗██████╗     ██████╗  ██████╗ ████████╗"
echo "  ╚██╗██╔╝██╔══██╗██║   ██║██╔════╝██╔══██╗    ██╔══██╗██╔═══██╗╚══██╔══╝"
echo "   ╚███╔╝ ███████║██║   ██║███████╗██║  ██║    ██████╔╝██║   ██║   ██║   "
echo "   ██╔██╗ ██╔══██║██║   ██║╚════██║██║  ██║    ██╔══██╗██║   ██║   ██║   "
echo "  ██╔╝ ██╗██║  ██║╚██████╔╝███████║██████╔╝    ██████╔╝╚██████╔╝   ██║   "
echo "  ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═════╝     ╚═════╝  ╚═════╝    ╚═╝   "
echo -e "${NC}"
echo -e "${CYAN}XAUUSD AI Trading Bot — Démarrage...${NC}"
echo ""

# --- Vérification du fichier .env ---
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ Fichier .env manquant !${NC}"
    echo -e "Copiez .env.example et remplissez vos clés :"
    echo -e "  ${YELLOW}cp .env.example .env${NC}"
    echo -e "  puis éditez .env avec vos clés API"
    exit 1
fi

# Charger les variables d'env
export $(grep -v '^#' .env | xargs) 2>/dev/null || true

# --- Vérification des clés API ---
MISSING_KEYS=()
[ -z "$ANTHROPIC_API_KEY" ] || [ "$ANTHROPIC_API_KEY" = "your_anthropic_key" ] && MISSING_KEYS+=("ANTHROPIC_API_KEY")
[ -z "$TWELVE_DATA_API_KEY" ] || [ "$TWELVE_DATA_API_KEY" = "your_twelve_data_key" ] && MISSING_KEYS+=("TWELVE_DATA_API_KEY")

if [ ${#MISSING_KEYS[@]} -gt 0 ]; then
    echo -e "${RED}❌ Clés API manquantes dans .env :${NC}"
    for key in "${MISSING_KEYS[@]}"; do
        echo -e "  • ${key}"
    done
    echo ""
    echo "Ces clés sont obligatoires. Les autres (FRED, Telegram) sont optionnelles."
    exit 1
fi

# --- Créer le dossier logs ---
mkdir -p logs

# --- Python venv ---
echo -e "${CYAN}[1/4] Vérification de l'environnement Python...${NC}"
if [ ! -d ".venv" ]; then
    echo "  Création du virtualenv..."
    python3 -m venv .venv || python -m venv .venv
fi

# Activer le venv
if [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate  # Windows Git Bash
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

echo "  Installation des dépendances Python..."
pip install -q -r requirements.txt

echo -e "${GREEN}  ✓ Python OK${NC}"

# --- Node.js / npm ---
echo -e "${CYAN}[2/4] Vérification de l'environnement Node.js...${NC}"
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js non trouvé. Installez Node.js 18+${NC}"
    exit 1
fi

cd frontend
if [ ! -d "node_modules" ]; then
    echo "  Installation des dépendances npm..."
    npm install --silent
fi
echo -e "${GREEN}  ✓ Node.js OK${NC}"
cd "$ROOT_DIR"

# --- Lancement des services ---
echo -e "${CYAN}[3/4] Démarrage des services...${NC}"

# Backend FastAPI
echo "  Démarrage du backend (port 8000)..."
if [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload \
    > logs/backend.log 2>&1 &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"

sleep 2

# Frontend Vite
echo "  Démarrage du frontend (port 5173)..."
cd frontend
npm run dev > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
cd "$ROOT_DIR"
echo "  Frontend PID: $FRONTEND_PID"

# Telegram Bot (optionnel)
if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ "$TELEGRAM_BOT_TOKEN" != "your_telegram_token" ]; then
    echo "  Démarrage du bot Telegram..."
    if [ -f ".venv/Scripts/activate" ]; then
        source .venv/Scripts/activate
    elif [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    fi
    python -m telegram_bot.bot > logs/telegram.log 2>&1 &
    TELEGRAM_PID=$!
    echo "  Telegram PID: $TELEGRAM_PID"
else
    echo -e "  ${YELLOW}⚠ Bot Telegram ignoré (TELEGRAM_BOT_TOKEN non configuré)${NC}"
    TELEGRAM_PID=""
fi

echo ""
echo -e "${GREEN}[4/4] Tous les services sont démarrés !${NC}"
echo ""
echo -e "  ${GREEN}▶ Dashboard :${NC}  http://localhost:5173"
echo -e "  ${GREEN}▶ API :${NC}       http://localhost:8000"
echo -e "  ${GREEN}▶ Docs API :${NC}  http://localhost:8000/docs"
echo ""
echo -e "  Logs : ./logs/"
echo ""
echo -e "${YELLOW}Appuyez sur Ctrl+C pour arrêter tous les services${NC}"

# Cleanup à la fermeture
cleanup() {
    echo ""
    echo -e "${CYAN}Arrêt des services...${NC}"
    [ -n "$BACKEND_PID" ] && kill $BACKEND_PID 2>/dev/null
    [ -n "$FRONTEND_PID" ] && kill $FRONTEND_PID 2>/dev/null
    [ -n "$TELEGRAM_PID" ] && kill $TELEGRAM_PID 2>/dev/null
    echo -e "${GREEN}✓ Tous les services arrêtés.${NC}"
    exit 0
}

trap cleanup INT TERM

# Attendre
wait
