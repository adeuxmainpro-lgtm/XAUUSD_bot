# XAUUSD Trading Bot — Project Context for Claude Code

## Project Description
An AI-powered XAUUSD (Gold/USD) trading analysis bot with a FastAPI backend, React/Vite frontend, Telegram alerts, and multi-timeframe SMC/ICT strategy engine.

**Purpose:** Educational trading assistant. Provides signals, analysis, and performance tracking for gold futures trading. NOT financial advice.

## Stack
- **Backend:** Python 3.11, FastAPI, APScheduler, SQLite, httpx, pandas, numpy, ta
- **Frontend:** React 18, Vite, Tailwind CSS, lightweight-charts, axios
- **AI:** Anthropic Claude API (claude-opus-4-6 model)
- **Data sources:** Twelve Data (primary), Yahoo Finance/yfinance (fallback), FRED API, COT CFTC

## Architecture
```
backend/
  main.py              — FastAPI app, lifespan startup
  config.py            — env vars, constants, intervals
  database.py          — SQLite helpers (trades, snapshots, news, COT, sentiment)
  scheduler.py         — APScheduler jobs (price, analysis, news, COT, sentiment, daily briefing)
  routers/
    market.py          — /api/market/* (price, live, ohlc, indicators, quota)
    analysis.py        — /api/analysis/* (run, latest, signal-history, composite)
    journal.py         — /api/journal/* (CRUD trades, stats, detailed, export CSV)
    news.py            — /api/news
    chat.py            — /api/chat (Claude chat with context)
    risk.py            — /api/risk/calculate, /from-analysis
    sentiment.py       — /api/sentiment
    macro.py           — /api/macro/context
    patterns.py        — /api/patterns
    performance.py     — /api/performance, /api/performance/backtest
  services/
    market_data.py     — Twelve Data + Yahoo Finance fallback, fetch_api_quota()
    analysis_engine.py — Builds market context for AI prompt
    ai_analyst.py      — Claude AI analysis, run_analysis(), SYSTEM_PROMPT
    smc_engine.py      — SMC/ICT: MTF bias, kill zones, liquidity sweep, Wyckoff, RSI divergence, trade score
    regime_detector.py — Market regime: Risk-Off/On/Stagflation/Deflation/Quality Flight
    ml_engine.py       — Trade outcome analysis, weight adjustments, weekly report
    backtest_engine.py — Historical backtest (1D/1H), SMC/ICT strategy simulation
    news_service.py    — RSS gold news aggregator
    telegram_service.py — Telegram send helpers
    sentiment_service.py — Fear & Greed index
    cot_service.py     — CFTC COT data for gold
    macro_service.py   — FRED macro indicators (CPI, Fed rate, etc.)

frontend/src/
  App.jsx              — Main app, tabs (Dashboard/Journal/Performances/Backtesting)
  services/api.js      — All API calls
  components/
    MarketOverview      — Price, indicators, key levels
    PriceChart          — Candlestick chart (lightweight-charts), EMA overlay
    RecommendationCard  — AI signal, SMC/ICT checklist, MTF panel, Wyckoff, regime
    TradeJournal        — CRUD trades, stats, heatmap, CSV export
    PerformancePanel    — ML win rate analysis, equity curve
    BacktestPanel       — Historical backtest results, equity curve
    NewsPanel, ChatAssistant, RiskCalculator, MacroPanel, SentimentPanel, PatternPanel
```

## Key Constants (backend/config.py)
- `PRICE_REFRESH_INTERVAL_MIN = 10` — full market refresh (Twelve Data)
- `ANALYSIS_INTERVAL_MIN = 60` — AI analysis scheduled interval
- `VOLATILITY_ALERT_THRESHOLD = 0.8` — ATR% for Telegram alert
- `CLAUDE_MODEL = "claude-opus-4-6"`

## Frontend Intervals (App.jsx)
- Live price: every **30 seconds** (`setInterval 30_000`)
- Full market indicators: every **10 minutes** (`REFRESH_INTERVAL_MS = 600_000`)
- OHLC chart: every **60 seconds** (`LIVE_INTERVAL_MS = 60000` in PriceChart)

## SMC/ICT Trade Score System (smc_engine.py)
0-100 score. Trade only if score ≥ 70.
- MTF ≥ 3/4 aligned: +30
- Kill Zone active (London/NY): +20
- Liquidity Sweep detected: +20
- OB + FVG in direction: +15
- RSI divergence: +15

Signal levels: ≥90 VERY_STRONG, ≥80 STRONG, ≥70 MODERATE, <70 WEAK (no trade)

## Kill Zones (UTC)
- London Open: 08:00–10:00 → best
- NY Open: 13:30–15:30 → best
- London Close: 16:00–17:00 → good
- Asian: 00:00–07:00 → avoid

## Pre-trade Checklist (RecommendationCard.jsx — 7 conditions)
1. Biais 4H confirmé (MTF alignment)
2. Kill Zone London/NY active
3. RSI zone valide (30-70)
4. Confluence ≥ 65%
5. Pas d'annonce imminente (no dangerous_period)
6. R/R ≥ 1:2
7. Liquidity Sweep confirmé
→ 7/7 = CONDITIONS OPTIMALES (vert), 5-6/7 = BONNES CONDITIONS (orange), <5 = INSUFFISANTES (rouge)

## Telegram Notifications
- **Daily briefing** at 08:00 UTC: price, regime, MTF bias, key levels, sessions, macro
- **Analysis signals** (BUY/SELL ≥ 65% confidence)
- **Smart notifications** (max 5/day): regime change, MTF 4/4 aligned, RSI extreme (<20/>80), VIX >25
- **Volatility alert**: ATR% > 0.8%
- **Quota alert**: Twelve Data remaining < 100 calls
- **Weekly ML report**: trade performance analysis

## Database Schema (SQLite — trading.db)
```sql
trades: id, trade_date, direction, entry_price, stop_loss, take_profit_1/2,
        exit_price, status (OPEN/WIN/LOSS/BE), profit_eur, lot_size, notes,
        rsi_at_entry, trend_at_entry, confluence_score, patterns_at_entry,
        session_at_entry, trade_score, wyckoff_phase, mtf_aligned
market_snapshots: ...price, indicators, ohlc
news: id, title, url, source, published_at, sentiment, summary
cot_data, sentiment_data
```

## Development Rules (user preferences)
- **Language:** French in UI, comments optional (write sparingly)
- **Style:** Dark terminal aesthetic — colors from tailwind config (terminal-*, gold-*)
- **No emoji** in code unless user asks
- **Responses:** Concise, no trailing summaries
- **Frontend:** Tailwind CSS with terminal design system (bg `#080c14`, card `#0d1420`, etc.)
- **Never commit** without explicit user request
- **Test APIs** — always consider Twelve Data quota; Yahoo Finance is the fallback

## Design System (Tailwind custom tokens)
```
bg: terminal-bg (#080c14), terminal-card (#0d1420), terminal-border (#1a2535)
text: terminal-base, terminal-text-muted, terminal-text-dim
gold-400 (#d4a82a) — primary accent
```

## Planned / Known Limitations
- Order flow analysis: requires paid API (not implemented)
- Twitter/X sentiment: requires paid API (not implemented)
- 1H backtest: yfinance caps at 730 days; 10-year backtest uses 1D data
- COT data: published weekly by CFTC on Fridays, refreshed every 24h
