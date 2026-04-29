# XAUUSD Trading Bot

Bot d'analyse trading Gold/Dollar (XAUUSD) alimenté par l'IA Claude, avec dashboard React, bot Telegram et scheduler automatique.

---

## Fonctionnalités

- **Analyse IA** : Recommandations BUY/SELL/HOLD avec niveaux d'entrée, stop loss, take profit et ratio R/R
- **Dashboard React** : Interface dark mode professionnelle avec graphique TradingView
- **Données temps réel** : Prix XAUUSD via Twelve Data + indicateurs techniques (RSI, MACD, EMA, BB, ATR)
- **Macro** : Taux FED, CPI, NFP, DXY via FRED API
- **Actualités** : Récupération intelligente via Claude web search
- **Calculateur de risque** : Dimensionnement de position en lots
- **Bot Telegram** : Commandes `/analyse`, `/news`, `/risk`, `/chat`, `/alerte`
- **Scheduler** : Rafraîchissement automatique (15min prix, 1h analyse, 4h news)

---

## Prérequis

- Python 3.11+
- Node.js 18+
- Clés API (voir ci-dessous)

---

## Clés API à obtenir

### 1. Anthropic (Claude) — OBLIGATOIRE
- Créez un compte sur https://console.anthropic.com
- Allez dans "API Keys" → "Create Key"
- Copiez la clé → `ANTHROPIC_API_KEY`

### 2. Twelve Data — OBLIGATOIRE
- Créez un compte sur https://twelvedata.com
- Plan gratuit : 800 requêtes/jour (suffisant)
- Copiez la clé → `TWELVE_DATA_API_KEY`

### 3. FRED API — OPTIONNEL (données macro)
- Créez un compte sur https://fred.stlouisfed.org/docs/api/api_key.html
- Gratuit, instantané
- Copiez la clé → `FRED_API_KEY`

### 4. Telegram Bot — OPTIONNEL
- Ouvrez Telegram, cherchez `@BotFather`
- Envoyez `/newbot`, suivez les instructions
- Copiez le token → `TELEGRAM_BOT_TOKEN`
- Pour votre `TELEGRAM_CHAT_ID` : parlez à `@userinfobot`

---

## Installation

### Étape 1 : Configurer les clés API

```bash
cp .env.example .env
# Éditez .env avec vos clés
```

### Étape 2 (Windows) : Double-cliquez sur `start.bat`

Le script :
1. Crée automatiquement le virtualenv Python
2. Installe toutes les dépendances Python et npm
3. Lance le backend (port 8000), le frontend (port 5173) et le bot Telegram
4. Ouvre automatiquement le dashboard dans votre navigateur

### Étape 2 (Linux/Mac) :

```bash
chmod +x start.sh
./start.sh
```

---

## Lancement manuel (si start.bat/sh échoue)

### Terminal 1 — Backend
```bash
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Terminal 2 — Frontend
```bash
cd frontend
npm install
npm run dev
```

### Terminal 3 — Telegram Bot (optionnel)
```bash
.venv\Scripts\activate
python -m telegram_bot.bot
```

---

## Accès

| Service    | URL                           |
|------------|-------------------------------|
| Dashboard  | http://localhost:5173         |
| API REST   | http://localhost:8000         |
| Docs API   | http://localhost:8000/docs    |

---

## Endpoints API principaux

```
GET  /api/market/price          → Prix + indicateurs actuels
GET  /api/market/ohlc/{interval} → Données OHLC (1h, 4h, 1day...)
POST /api/analysis/run/sync     → Lance une analyse IA (attend le résultat)
GET  /api/analysis/latest       → Dernière recommandation
GET  /api/news                  → Actualités or du jour
POST /api/chat                  → Chat avec l'IA
POST /api/risk/calculate        → Calcul de position
```

---

## Commandes Telegram

| Commande          | Description                                   |
|-------------------|-----------------------------------------------|
| `/start`          | Message de bienvenue                          |
| `/analyse`        | Lance une analyse complète (~30s)             |
| `/news`           | 5 actualités importantes du jour              |
| `/risk 1000`      | Calcul position pour bankroll 1000€           |
| `/risk 1000 low`  | Même chose avec risque faible (0.5%)          |
| `/chat Pourquoi acheter ?` | Question libre à l'IA             |
| `/alerte`         | Active/désactive les alertes automatiques     |
| `/status`         | Statut rapide du marché                       |

---

## Structure des fichiers

```
xauusd-bot/
├── backend/              # API FastAPI
│   ├── main.py           # Point d'entrée + CORS
│   ├── config.py         # Variables d'environnement
│   ├── database.py       # SQLite (analyses, snapshots, news, chat)
│   ├── scheduler.py      # Tâches automatiques (APScheduler)
│   ├── services/         # Logique métier
│   │   ├── market_data.py    # Twelve Data + indicateurs pandas-ta
│   │   ├── macro_data.py     # FRED API
│   │   ├── news_service.py   # Claude web search
│   │   ├── analysis_engine.py # Assemblage du contexte
│   │   ├── ai_analyst.py     # Claude API (analyse + chat)
│   │   └── risk_manager.py   # Calcul lots/levier
│   └── routers/          # Endpoints FastAPI
├── telegram_bot/         # Bot Telegram
├── frontend/             # React + Vite + TailwindCSS
│   └── src/
│       ├── App.jsx
│       ├── components/   # PriceChart, RecommendationCard, etc.
│       └── services/api.js
├── logs/                 # Logs des services
├── .env                  # Clés API (à créer depuis .env.example)
├── requirements.txt      # Dépendances Python
├── start.bat             # Lancement Windows
└── start.sh              # Lancement Linux/Mac
```

---

## Avertissement

> Ce bot est un **outil d'analyse éducatif**. Il ne constitue pas un conseil financier.  
> Le trading de l'or implique des risques de perte en capital.  
> Ne tradez jamais avec de l'argent que vous ne pouvez pas vous permettre de perdre.

---

## Dépannage

**Le backend ne démarre pas :**
```bash
# Vérifiez que Python 3.11+ est installé
python --version
# Réinstallez les dépendances
pip install -r requirements.txt
```

**pandas-ta ne s'installe pas :**
```bash
pip install pandas-ta --no-build-isolation
# ou
pip install git+https://github.com/twopirllc/pandas-ta.git@development
```

**Le graphique est vide :**
- Vérifiez que `TWELVE_DATA_API_KEY` est correct dans `.env`
- Le plan gratuit Twelve Data a une limite de débit — attendez quelques secondes

**Le bot Telegram ne répond pas :**
- Vérifiez `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID` dans `.env`
- Assurez-vous d'avoir démarré une conversation avec votre bot (`/start`)
