import logging
import sys
import os

# Ajouter la racine du projet au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from backend.database import init_db
from backend.scheduler import start_scheduler
from backend.routers import market, analysis, news, chat, risk
from backend.routers import journal, patterns, sentiment, macro

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing database...")
    init_db()
    logger.info("Starting scheduler...")
    start_scheduler()
    logger.info("XAUUSD Bot backend ready.")
    yield
    # Shutdown
    from backend.scheduler import scheduler
    if scheduler.running:
        scheduler.shutdown()
    logger.info("Scheduler stopped.")


app = FastAPI(
    title="XAUUSD Trading Bot API",
    description="API d'analyse trading Gold/Dollar avec IA Claude",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router)
app.include_router(analysis.router)
app.include_router(news.router)
app.include_router(chat.router)
app.include_router(risk.router)
app.include_router(journal.router)
app.include_router(patterns.router)
app.include_router(sentiment.router)
app.include_router(macro.router)


@app.get("/")
async def root():
    return {
        "name": "XAUUSD Trading Bot",
        "version": "1.0.0",
        "status": "running",
        "endpoints": [
            "GET  /api/market/price",
            "GET  /api/market/ohlc/{interval}",
            "GET  /api/market/indicators",
            "POST /api/analysis/run",
            "POST /api/analysis/run/sync",
            "GET  /api/analysis/latest",
            "GET  /api/news",
            "POST /api/chat",
            "GET  /api/chat/history",
            "POST /api/risk/calculate",
            "GET  /api/risk/from-analysis",
        ],
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
