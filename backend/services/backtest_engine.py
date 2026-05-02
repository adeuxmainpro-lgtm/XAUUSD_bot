"""
Backtesting Engine — SMC/ICT Strategy Simulation on XAUUSD.

Data: yfinance GC=F
  - 1H interval: max 730 days (yfinance API limit)
  - 1D interval: up to 10 years for long-term view

Strategy applied (SMC/ICT):
  - Primary bias: EMA20/50/200 alignment
  - RSI filter: no BUY if RSI >= 70, no SELL if RSI <= 30
  - Entry trigger: RSI zone cross + MACD crossover + candlestick pattern
  - SL: recent swing high/low ± ATR×0.5
  - TP: partial exit model (50% at TP1=1.5R, 50% at TP2=3R)
  - Per-year breakdown: win rate, profit factor, max drawdown, Sharpe, trades
"""
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_data(years: int, interval: str) -> pd.DataFrame | None:
    try:
        import yfinance as yf
        yf_period = f"{years}y"
        ticker = yf.Ticker("GC=F")
        df = ticker.history(period=yf_period, interval=interval, auto_adjust=True)
        if df.empty:
            return None
        df = df.rename(columns=str.lower)
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                df[col] = df[col].astype(float)
        df = df.dropna(subset=["close"])
        return df
    except ImportError:
        raise ImportError("yfinance non installé")
    except Exception as e:
        logger.error(f"_fetch_data({interval}, {years}y): {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# INDICATORS
# ─────────────────────────────────────────────────────────────────────────────

def _add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c, h, l = df["close"], df["high"], df["low"]

    df["ema20"]  = c.ewm(span=20,  adjust=False).mean()
    df["ema50"]  = c.ewm(span=50,  adjust=False).mean()
    df["ema200"] = c.ewm(span=200, adjust=False).mean()

    delta = c.diff()
    gain  = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    loss  = (-delta).clip(lower=0).ewm(com=13, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - 100 / (1 + rs)

    ema12  = c.ewm(span=12, adjust=False).mean()
    ema26  = c.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df["macd_hist"] = macd - signal

    hl = h - l
    hc = (h - c.shift()).abs()
    lc = (l - c.shift()).abs()
    df["atr"] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()

    return df


# ─────────────────────────────────────────────────────────────────────────────
# CANDLESTICK PATTERNS
# ─────────────────────────────────────────────────────────────────────────────

def _pattern(o: float, h: float, l: float, c: float,
             po: float, ph: float, pl: float, pc: float) -> str:
    """Returns the most significant pattern: bullish_engulfing, bearish_engulfing,
    hammer, shooting_star, doji, or '' for none."""
    body      = abs(c - o)
    prev_body = abs(pc - po)
    rng       = h - l if h > l else 1e-6

    # Doji
    if body <= rng * 0.08:
        return "doji"

    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l

    # Bullish engulfing
    if (c > o                         # bullish candle
            and pc < po               # previous bearish
            and o <= pc               # opened at or below prev close
            and c >= po               # closed at or above prev open
            and body >= prev_body * 0.9):
        return "bullish_engulfing"

    # Bearish engulfing
    if (c < o                         # bearish candle
            and pc > po               # previous bullish
            and o >= pc               # opened at or above prev close
            and c <= po               # closed at or below prev open
            and body >= prev_body * 0.9):
        return "bearish_engulfing"

    # Hammer (bullish): small body at top, long lower wick
    if (c > o
            and lower_wick >= body * 1.8
            and upper_wick <= body * 0.5):
        return "hammer"

    # Shooting star (bearish): small body at bottom, long upper wick
    if (c < o
            and upper_wick >= body * 1.8
            and lower_wick <= body * 0.5):
        return "shooting_star"

    return ""


BULLISH_PATTERNS = {"bullish_engulfing", "hammer", "doji"}
BEARISH_PATTERNS = {"bearish_engulfing", "shooting_star", "doji"}


# ─────────────────────────────────────────────────────────────────────────────
# SWING HIGH / LOW  (lookback window)
# ─────────────────────────────────────────────────────────────────────────────

def _swing_low(lows: np.ndarray, idx: int, lookback: int = 15) -> float:
    start = max(0, idx - lookback)
    return float(np.min(lows[start:idx]))


def _swing_high(highs: np.ndarray, idx: int, lookback: int = 15) -> float:
    start = max(0, idx - lookback)
    return float(np.max(highs[start:idx]))


# ─────────────────────────────────────────────────────────────────────────────
# BACKTEST CORE
# ─────────────────────────────────────────────────────────────────────────────

def _run_on_df(df: pd.DataFrame) -> list[dict]:
    """
    Core backtest loop.  Returns a list of closed trade dicts.
    """
    df = df.dropna(subset=["ema200", "rsi", "atr", "macd_hist"])
    if len(df) < 50:
        return []

    highs  = df["high"].values.astype(float)
    lows   = df["low"].values.astype(float)
    opens  = df["open"].values.astype(float)
    closes = df["close"].values.astype(float)
    ema20  = df["ema20"].values.astype(float)
    ema50  = df["ema50"].values.astype(float)
    ema200 = df["ema200"].values.astype(float)
    rsi    = df["rsi"].values.astype(float)
    macd_h = df["macd_hist"].values.astype(float)
    atr    = df["atr"].values.astype(float)
    dates  = df.index

    trades: list[dict] = []
    in_trade    = False
    direction   = ""
    entry_price = sl = tp1 = tp2 = 0.0
    entry_date  = ""
    sl_dist     = 0.0

    for i in range(2, len(df)):
        if not in_trade:
            bias = ""
            # Full EMA stack = strong bias
            if ema20[i] > ema50[i] > ema200[i]:
                bias = "BULLISH"
            elif ema20[i] < ema50[i] < ema200[i]:
                bias = "BEARISH"
            elif ema50[i] > ema200[i]:
                bias = "BULLISH"
            elif ema50[i] < ema200[i]:
                bias = "BEARISH"
            else:
                continue

            rsi_c = rsi[i]
            rsi_p = rsi[i - 1]
            mh_c  = macd_h[i]
            mh_p  = macd_h[i - 1]
            atr_v = atr[i]
            pat   = _pattern(opens[i], highs[i], lows[i], closes[i],
                              opens[i-1], highs[i-1], lows[i-1], closes[i-1])

            # BUY entry
            if (bias == "BULLISH"
                    and rsi_c < 70          # RSI filter
                    and rsi_p < 40 <= rsi_c # RSI cross above 40
                    and mh_c > 0 > mh_p     # MACD crossover up
                    and pat in BULLISH_PATTERNS | {""}):

                swing_sl = _swing_low(lows, i, 20)
                sl_val   = round(swing_sl - atr_v * 0.5, 2)
                dist     = closes[i] - sl_val
                if dist <= 0 or dist > closes[i] * 0.05:
                    continue

                in_trade    = True
                direction   = "BUY"
                entry_price = closes[i]
                sl          = sl_val
                sl_dist     = dist
                tp1         = round(entry_price + sl_dist * 1.5, 2)
                tp2         = round(entry_price + sl_dist * 3.0, 2)
                entry_date  = dates[i].strftime("%Y-%m-%d")

            # SELL entry
            elif (bias == "BEARISH"
                    and rsi_c > 30          # RSI filter
                    and rsi_p > 60 >= rsi_c # RSI cross below 60
                    and mh_c < 0 < mh_p     # MACD crossover down
                    and pat in BEARISH_PATTERNS | {""}):

                swing_sl = _swing_high(highs, i, 20)
                sl_val   = round(swing_sl + atr_v * 0.5, 2)
                dist     = sl_val - closes[i]
                if dist <= 0 or dist > closes[i] * 0.05:
                    continue

                in_trade    = True
                direction   = "SELL"
                entry_price = closes[i]
                sl          = sl_val
                sl_dist     = dist
                tp1         = round(entry_price - sl_dist * 1.5, 2)
                tp2         = round(entry_price - sl_dist * 3.0, 2)
                entry_date  = dates[i].strftime("%Y-%m-%d")

        else:
            hi = highs[i]
            lo = lows[i]
            rr2 = round(sl_dist * 3.0 / sl_dist, 2) if sl_dist else 0  # always 3.0

            if direction == "BUY":
                hit_sl  = lo <= sl
                hit_tp1 = hi >= tp1
                hit_tp2 = hi >= tp2
                worse_first = hit_sl and not hit_tp2
            else:
                hit_sl  = hi >= sl
                hit_tp1 = lo <= tp1
                hit_tp2 = lo <= tp2
                worse_first = hit_sl and not hit_tp2

            if worse_first:
                trades.append({
                    "date":       dates[i].strftime("%Y-%m-%d"),
                    "entry_date": entry_date,
                    "direction":  direction,
                    "entry":      entry_price,
                    "exit":       sl,
                    "result":     "LOSS",
                    "pnl_rr":    -1.0,
                })
                in_trade = False

            elif hit_tp2:
                pnl = round(0.5 * 1.5 + 0.5 * 3.0, 2)   # 50% at TP1, 50% at TP2
                trades.append({
                    "date":       dates[i].strftime("%Y-%m-%d"),
                    "entry_date": entry_date,
                    "direction":  direction,
                    "entry":      entry_price,
                    "exit":       tp2,
                    "result":     "WIN",
                    "pnl_rr":    pnl,
                })
                in_trade = False

            elif hit_tp1:
                # SL moves to BE → only 50% realized at TP1, rest assumed BE
                trades.append({
                    "date":       dates[i].strftime("%Y-%m-%d"),
                    "entry_date": entry_date,
                    "direction":  direction,
                    "entry":      entry_price,
                    "exit":       tp1,
                    "result":     "WIN",
                    "pnl_rr":    0.75,  # 50% × 1.5R
                })
                in_trade = False

    return trades


# ─────────────────────────────────────────────────────────────────────────────
# METRICS
# ─────────────────────────────────────────────────────────────────────────────

def _metrics(trades: list[dict], years_count: float) -> dict:
    if not trades:
        return {}

    wins   = [t for t in trades if t["result"] == "WIN"]
    losses = [t for t in trades if t["result"] == "LOSS"]

    total_pnl   = sum(t["pnl_rr"] for t in trades)
    gross_win   = sum(t["pnl_rr"] for t in wins)
    gross_loss  = abs(sum(t["pnl_rr"] for t in losses))
    win_rate    = round(len(wins) / len(trades) * 100, 1)
    pf          = round(gross_win / gross_loss, 2) if gross_loss > 0 else None
    avg_win_rr  = round(float(np.mean([t["pnl_rr"] for t in wins])), 2)   if wins   else 0
    avg_loss_rr = round(float(np.mean([t["pnl_rr"] for t in losses])), 2) if losses else 0

    # Sharpe (annualized on R-per-trade units)
    pnl_arr = np.array([t["pnl_rr"] for t in trades])
    mean_p  = float(pnl_arr.mean())
    std_p   = float(pnl_arr.std())
    tpy     = len(trades) / max(years_count, 0.1)
    sharpe  = round(mean_p / std_p * (tpy ** 0.5), 2) if std_p > 0 else 0

    # Max drawdown in R
    running = peak = dd_max = 0.0
    for t in trades:
        running += t["pnl_rr"]
        if running > peak:
            peak = running
        dd = peak - running
        if dd > dd_max:
            dd_max = dd

    buy_t  = [t for t in trades if t["direction"] == "BUY"]
    sell_t = [t for t in trades if t["direction"] == "SELL"]
    buy_wr  = round(sum(1 for t in buy_t  if t["result"] == "WIN") / len(buy_t)  * 100, 1) if buy_t  else None
    sell_wr = round(sum(1 for t in sell_t if t["result"] == "WIN") / len(sell_t) * 100, 1) if sell_t else None

    by_year: dict = {}
    for t in trades:
        yr = t["date"][:4]
        by_year.setdefault(yr, []).append(t)
    annual: dict = {}
    for yr, yt in sorted(by_year.items()):
        yw = [t for t in yt if t["result"] == "WIN"]
        yp = sum(t["pnl_rr"] for t in yt)
        yl = [t for t in yt if t["result"] == "LOSS"]
        yg = sum(t["pnl_rr"] for t in yw)
        yloss = abs(sum(t["pnl_rr"] for t in yl))
        annual[yr] = {
            "trades":        len(yt),
            "win_rate":      round(len(yw) / len(yt) * 100, 1),
            "total_rr":      round(yp, 2),
            "profit_factor": round(yg / yloss, 2) if yloss > 0 else None,
        }

    # Running equity series (cumulative)
    running_pnl = 0.0
    equity_curve: list[dict] = []
    for t in trades:
        running_pnl = round(running_pnl + t["pnl_rr"], 3)
        equity_curve.append({"date": t["date"], "equity_r": running_pnl})

    return {
        "total_trades":    len(trades),
        "wins":            len(wins),
        "losses":          len(losses),
        "win_rate":        win_rate,
        "profit_factor":   pf,
        "total_pnl_rr":   round(total_pnl, 2),
        "avg_win_rr":      avg_win_rr,
        "avg_loss_rr":     avg_loss_rr,
        "max_drawdown_rr": round(dd_max, 2),
        "sharpe_ratio":    sharpe,
        "trades_per_year": round(len(trades) / max(years_count, 0.1), 1),
        "by_direction": {
            "BUY":  {"trades": len(buy_t),  "win_rate": buy_wr},
            "SELL": {"trades": len(sell_t), "win_rate": sell_wr},
        },
        "annual_breakdown": annual,
        "equity_curve":    equity_curve[-200:],   # last 200 points for UI
    }


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def run_backtest(years: int = 5) -> dict:
    """
    Run the SMC/ICT strategy backtest.

    Tries 1H data first (max 730 days via yfinance).
    Falls back to 1D for longer requested periods.
    Returns metrics + annual breakdown + equity curve.
    """
    try:
        import yfinance as yf  # noqa — just to trigger ImportError early
    except ImportError:
        return {"error": "yfinance non installé — pip install yfinance"}

    # ── Attempt 1H data (yfinance caps at ~730 days) ──────────────────────
    df_1h = _fetch_data(min(years, 2), "1h")
    if df_1h is not None and len(df_1h) >= 200:
        df_1h = _add_indicators(df_1h)
        trades_1h = _run_on_df(df_1h)
        actual_years = (df_1h.index[-1] - df_1h.index[0]).days / 365.25
        m1h = _metrics(trades_1h, actual_years)
        if trades_1h:
            result_1h = {
                "generated_at":     datetime.now(timezone.utc).isoformat(),
                "years":            round(actual_years, 1),
                "interval":         "1H",
                "candles_analyzed": len(df_1h),
                "note": "Données 1H — max 730 jours disponibles via yfinance.",
                **m1h,
            }
        else:
            result_1h = None
    else:
        result_1h = None

    # ── 1D data for the full requested period ────────────────────────────
    df_1d = _fetch_data(years, "1d")
    if df_1d is None or len(df_1d) < 250:
        if result_1h:
            return result_1h
        return {
            "error": f"Données insuffisantes pour le backtest ({len(df_1d) if df_1d is not None else 0} candles)"
        }

    df_1d = _add_indicators(df_1d)
    trades_1d = _run_on_df(df_1d)

    if not trades_1d:
        if result_1h:
            return result_1h
        return {
            "error": "Aucun trade simulé — conditions jamais remplies",
            "candles_analyzed": len(df_1d),
            "years": years,
        }

    actual_years_1d = (df_1d.index[-1] - df_1d.index[0]).days / 365.25
    m1d = _metrics(trades_1d, actual_years_1d)

    return {
        "generated_at":     datetime.now(timezone.utc).isoformat(),
        "years":            round(actual_years_1d, 1),
        "interval":         "1D",
        "candles_analyzed": len(df_1d),
        "note": (
            f"Simulation sur données journalières 1D ({round(actual_years_1d,1)} ans). "
            "Les performances passées ne garantissent pas les résultats futurs. "
            "Usage éducatif uniquement."
        ),
        **m1d,
        # Attach 1H short-term results if available
        "result_1h": result_1h,
    }
