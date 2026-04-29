import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
FRED_API_KEY = os.getenv("FRED_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

CLAUDE_MODEL = "claude-sonnet-4-6"

TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"
FRED_BASE_URL = "https://api.stlouisfed.org/fred"

ANALYSIS_INTERVAL_MIN = 60       # analyse IA toutes les heures
PRICE_REFRESH_INTERVAL_MIN = 15  # prix toutes les 15 min
NEWS_REFRESH_INTERVAL_MIN = 240  # news toutes les 4h

VOLATILITY_ALERT_THRESHOLD = 0.8  # ATR% > 0.8% → alerte

RISK_LEVELS = {
    "low": 0.005,       # 0.5%
    "normal": 0.01,     # 1%
    "aggressive": 0.02, # 2%
}

LOT_SIZE_USD = 100_000   # 1 lot standard = 100 000 USD
GOLD_CONTRACT_SIZE = 100 # 1 lot gold = 100 oz
