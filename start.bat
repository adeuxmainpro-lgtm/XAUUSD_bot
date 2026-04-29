@echo off
chcp 65001 > nul
setlocal EnableDelayedExpansion

echo.
echo  ██╗  ██╗ █████╗ ██╗   ██╗███████╗██████╗     ██████╗  ██████╗ ████████╗
echo  ╚██╗██╔╝██╔══██╗██║   ██║██╔════╝██╔══██╗    ██╔══██╗██╔═══██╗╚══██╔══╝
echo   ╚███╔╝ ███████║██║   ██║███████╗██║  ██║    ██████╔╝██║   ██║   ██║
echo   ██╔██╗ ██╔══██║██║   ██║╚════██║██║  ██║    ██╔══██╗██║   ██║   ██║
echo  ██╔╝ ██╗██║  ██║╚██████╔╝███████║██████╔╝    ██████╔╝╚██████╔╝   ██║
echo  ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═════╝     ╚═════╝  ╚═════╝    ╚═╝
echo.
echo XAUUSD AI Trading Bot - Demarrage...
echo.

:: Vérifier .env
if not exist ".env" (
    echo [ERREUR] Fichier .env manquant !
    echo Copiez .env.example en .env et remplissez vos cles API.
    echo     copy .env.example .env
    pause
    exit /b 1
)

:: Créer le dossier logs
if not exist "logs" mkdir logs

:: Vérifier Python
python --version > nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python non trouve. Installez Python 3.11+
    pause
    exit /b 1
)

:: Créer venv si nécessaire
if not exist ".venv" (
    echo [1/4] Creation du virtualenv Python...
    python -m venv .venv
)

:: Activer venv
call .venv\Scripts\activate.bat

:: Installer dépendances Python
echo [1/4] Installation des dependances Python...
pip install -q -r requirements.txt
echo     OK

:: Vérifier Node.js
node --version > nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Node.js non trouve. Installez Node.js 18+
    pause
    exit /b 1
)

:: Installer dépendances npm
echo [2/4] Installation des dependances npm...
cd frontend
if not exist "node_modules" (
    npm install --silent
)
cd ..
echo     OK

echo [3/4] Demarrage des services...

:: Backend FastAPI
echo     Backend FastAPI (port 8000)...
start "XAUUSD Backend" /min cmd /c "call .venv\Scripts\activate.bat && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload > logs\backend.log 2>&1"

timeout /t 3 /nobreak > nul

:: Frontend Vite
echo     Frontend Vite (port 5173)...
start "XAUUSD Frontend" /min cmd /c "cd frontend && npm run dev > ..\logs\frontend.log 2>&1"

:: Telegram Bot (si configuré)
for /f "tokens=2 delims==" %%a in ('findstr "TELEGRAM_BOT_TOKEN" .env 2^>nul') do set TG_TOKEN=%%a
if defined TG_TOKEN (
    if not "!TG_TOKEN!"=="your_telegram_token" (
        echo     Bot Telegram...
        start "XAUUSD Telegram" /min cmd /c "call .venv\Scripts\activate.bat && python -m telegram_bot.bot > logs\telegram.log 2>&1"
    ) else (
        echo     Bot Telegram ignore (token non configure)
    )
)

echo.
echo [4/4] Tous les services sont lances !
echo.
echo   Dashboard : http://localhost:5173
echo   API       : http://localhost:8000
echo   Docs API  : http://localhost:8000/docs
echo.
echo   Logs dans : .\logs\
echo.
echo Fermez cette fenetre pour arreter tous les services (ou fermez les fenetres individuelles).
echo.

:: Ouvrir le navigateur après 5 secondes
timeout /t 5 /nobreak > nul
start "" "http://localhost:5173"

pause
