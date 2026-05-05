import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "xauusd.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            direction TEXT,
            entry REAL,
            stop_loss REAL,
            take_profit_1 REAL,
            take_profit_2 REAL,
            risk_reward REAL,
            confidence INTEGER,
            timeframe TEXT,
            main_arguments TEXT,
            main_risks TEXT,
            alternative_scenario TEXT,
            market_summary TEXT,
            dangerous_period INTEGER DEFAULT 0,
            dangerous_reason TEXT,
            raw_json TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS market_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            price REAL,
            open REAL,
            high REAL,
            low REAL,
            volume REAL,
            rsi REAL,
            macd REAL,
            macd_signal REAL,
            ema20 REAL,
            ema50 REAL,
            ema200 REAL,
            bb_upper REAL,
            bb_lower REAL,
            atr REAL,
            trend_short TEXT,
            trend_medium TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS news_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at TEXT NOT NULL,
            articles TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL
        )
    """)

    # Trade journal
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT (datetime('now')),
            trade_date TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL NOT NULL,
            stop_loss REAL,
            take_profit_1 REAL,
            take_profit_2 REAL,
            exit_price REAL,
            status TEXT DEFAULT 'OPEN',
            profit_eur REAL DEFAULT 0,
            lot_size REAL DEFAULT 0.01,
            notes TEXT,
            rsi_at_entry REAL,
            trend_at_entry TEXT,
            confluence_score INTEGER,
            patterns_at_entry TEXT
        )
    """)

    # Migrate trades table: add new columns if they don't exist yet
    for col_def in [
        "session_at_entry TEXT",
        "trade_score INTEGER",
        "wyckoff_phase TEXT",
        "mtf_aligned INTEGER",
    ]:
        col_name = col_def.split()[0]
        try:
            cur.execute(f"ALTER TABLE trades ADD COLUMN {col_def}")
        except Exception:
            pass  # Column already exists

    # COT cache
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cot_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at TEXT DEFAULT (datetime('now')),
            data TEXT NOT NULL
        )
    """)

    # Sentiment cache
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sentiment_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at TEXT DEFAULT (datetime('now')),
            data TEXT NOT NULL
        )
    """)

    # Interactive Telegram signal confirmations
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            signal_json TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            handled INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# ANALYSES
# ─────────────────────────────────────────────

def save_analysis(data: dict):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO analyses (
            created_at, direction, entry, stop_loss, take_profit_1, take_profit_2,
            risk_reward, confidence, timeframe, main_arguments, main_risks,
            alternative_scenario, market_summary, dangerous_period, dangerous_reason, raw_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        datetime.utcnow().isoformat(),
        data.get("direction"),
        data.get("entry"),
        data.get("stop_loss"),
        data.get("take_profit_1"),
        data.get("take_profit_2"),
        data.get("risk_reward"),
        data.get("confidence"),
        data.get("timeframe"),
        json.dumps(data.get("main_arguments", [])),
        json.dumps(data.get("main_risks", [])),
        data.get("alternative_scenario"),
        data.get("market_summary"),
        1 if data.get("dangerous_period") else 0,
        data.get("dangerous_reason"),
        json.dumps(data),
    ))
    conn.commit()
    conn.close()


def get_latest_analysis() -> dict | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT raw_json, created_at FROM analyses ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if row:
        data = json.loads(row["raw_json"])
        data["created_at"] = row["created_at"]
        return data
    return None


def get_recent_analyses(limit: int = 5) -> list[dict]:
    """Returns lightweight signal history for the last N analyses."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT direction, confidence, created_at, raw_json FROM analyses ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()
    result = []
    for row in rows:
        raw = json.loads(row["raw_json"]) if row["raw_json"] else {}
        result.append({
            "direction":       row["direction"],
            "confidence":      row["confidence"],
            "signal_level":    raw.get("signal_level", "WAIT"),
            "confluence_score": raw.get("confluence_score", 0),
            "created_at":      row["created_at"],
        })
    return result


# ─────────────────────────────────────────────
# MARKET SNAPSHOTS
# ─────────────────────────────────────────────

def save_market_snapshot(data: dict):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO market_snapshots (
            created_at, price, open, high, low, volume,
            rsi, macd, macd_signal, ema20, ema50, ema200,
            bb_upper, bb_lower, atr, trend_short, trend_medium
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        datetime.utcnow().isoformat(),
        data.get("price"), data.get("open"), data.get("high"),
        data.get("low"), data.get("volume"),
        data.get("rsi"), data.get("macd"), data.get("macd_signal"),
        data.get("ema20"), data.get("ema50"), data.get("ema200"),
        data.get("bb_upper"), data.get("bb_lower"), data.get("atr"),
        data.get("trend_short"), data.get("trend_medium"),
    ))
    conn.commit()
    conn.close()


def get_latest_snapshot() -> dict | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM market_snapshots ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


# ─────────────────────────────────────────────
# NEWS
# ─────────────────────────────────────────────

def save_news(articles: list):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO news_cache (fetched_at, articles) VALUES (?,?)",
                (datetime.utcnow().isoformat(), json.dumps(articles)))
    conn.commit()
    conn.close()


def get_latest_news() -> list:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT articles FROM news_cache ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if row:
        return json.loads(row["articles"])
    return []


# ─────────────────────────────────────────────
# CHAT
# ─────────────────────────────────────────────

def save_chat_message(role: str, content: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO chat_history (created_at, role, content) VALUES (?,?,?)",
                (datetime.utcnow().isoformat(), role, content))
    conn.commit()
    conn.close()


def get_chat_history(limit: int = 20) -> list:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT role, content FROM chat_history ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


# ─────────────────────────────────────────────
# TRADES JOURNAL
# ─────────────────────────────────────────────

def save_trade(data: dict) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO trades (
            trade_date, direction, entry_price, stop_loss, take_profit_1, take_profit_2,
            exit_price, status, profit_eur, lot_size, notes,
            rsi_at_entry, trend_at_entry, confluence_score, patterns_at_entry,
            session_at_entry, trade_score, wyckoff_phase, mtf_aligned
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        data.get("trade_date"),
        data.get("direction"),
        data.get("entry_price"),
        data.get("stop_loss"),
        data.get("take_profit_1"),
        data.get("take_profit_2"),
        data.get("exit_price"),
        data.get("status", "OPEN"),
        data.get("profit_eur", 0),
        data.get("lot_size", 0.01),
        data.get("notes"),
        data.get("rsi_at_entry"),
        data.get("trend_at_entry"),
        data.get("confluence_score"),
        json.dumps(data.get("patterns_at_entry", [])),
        data.get("session_at_entry"),
        data.get("trade_score"),
        data.get("wyckoff_phase"),
        data.get("mtf_aligned"),
    ))
    conn.commit()
    trade_id = cur.lastrowid
    conn.close()
    return trade_id


def update_trade(trade_id: int, data: dict):
    conn = get_connection()
    cur = conn.cursor()

    # Auto-compute P&L when exit_price is provided and profit_eur is not explicit
    if "exit_price" in data and data["exit_price"] is not None and "profit_eur" not in data:
        cur.execute(
            "SELECT direction, entry_price, lot_size FROM trades WHERE id = ?", (trade_id,)
        )
        row = cur.fetchone()
        if row:
            direction  = row["direction"] or "BUY"
            entry      = row["entry_price"] or 0
            lot        = row["lot_size"] or 0.01
            exit_price = data["exit_price"]
            if direction == "BUY":
                data["profit_eur"] = round((exit_price - entry) * lot * 100, 2)
            else:
                data["profit_eur"] = round((entry - exit_price) * lot * 100, 2)

    fields = []
    values = []
    allowed = [
        "trade_date", "direction", "entry_price", "stop_loss", "take_profit_1",
        "take_profit_2", "exit_price", "status", "profit_eur", "lot_size", "notes",
        "rsi_at_entry", "trend_at_entry", "confluence_score",
    ]
    for k in allowed:
        if k in data:
            fields.append(f"{k} = ?")
            values.append(data[k])
    if not fields:
        conn.close()
        return
    values.append(trade_id)
    cur.execute(f"UPDATE trades SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()


def delete_trade(trade_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
    conn.commit()
    conn.close()


def get_trades(limit: int = 100) -> list[dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trades ORDER BY trade_date DESC, id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["patterns_at_entry"] = json.loads(d.get("patterns_at_entry") or "[]")
        except Exception:
            d["patterns_at_entry"] = []
        result.append(d)
    return result


def get_trade_by_id(trade_id: int) -> dict | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trades WHERE id = ?", (trade_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        d = dict(row)
        try:
            d["patterns_at_entry"] = json.loads(d.get("patterns_at_entry") or "[]")
        except Exception:
            d["patterns_at_entry"] = []
        return d
    return None


def get_trade_stats() -> dict:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trades WHERE status IN ('WIN','LOSS','BE') ORDER BY trade_date ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows:
        return {
            "total_trades": 0, "wins": 0, "losses": 0, "be": 0,
            "win_rate": 0, "profit_factor": 0,
            "total_pnl": 0, "avg_win": 0, "avg_loss": 0,
            "max_drawdown": 0, "best_streak": 0, "worst_streak": 0,
            "bankroll_history": [],
        }

    wins = [t for t in rows if t["status"] == "WIN"]
    losses = [t for t in rows if t["status"] == "LOSS"]
    bes = [t for t in rows if t["status"] == "BE"]

    gross_profit = sum(t["profit_eur"] for t in wins)
    gross_loss = abs(sum(t["profit_eur"] for t in losses))

    win_rate = round(len(wins) / len(rows) * 100, 1) if rows else 0
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0)
    avg_win = round(gross_profit / len(wins), 2) if wins else 0
    avg_loss = round(gross_loss / len(losses), 2) if losses else 0
    total_pnl = round(sum(t["profit_eur"] for t in rows), 2)

    # Drawdown & streaks
    running = 0.0
    peak = 0.0
    max_dd = 0.0
    bankroll_history = []
    cur_streak = 0
    best_streak = 0
    worst_streak = 0
    last_result = None

    for t in rows:
        running += t["profit_eur"]
        bankroll_history.append({"date": t["trade_date"], "pnl": round(running, 2)})
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd

        if t["status"] == "WIN":
            if last_result == "WIN":
                cur_streak += 1
            else:
                cur_streak = 1
            best_streak = max(best_streak, cur_streak)
            last_result = "WIN"
        elif t["status"] == "LOSS":
            if last_result == "LOSS":
                cur_streak -= 1
            else:
                cur_streak = -1
            worst_streak = min(worst_streak, cur_streak)
            last_result = "LOSS"

    return {
        "total_trades": len(rows),
        "wins": len(wins),
        "losses": len(losses),
        "be": len(bes),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "total_pnl": total_pnl,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "max_drawdown": round(max_dd, 2),
        "best_streak": best_streak,
        "worst_streak": abs(worst_streak),
        "bankroll_history": bankroll_history,
    }


def get_consecutive_losses() -> int:
    """Return number of consecutive LOSS trades (most recent first) before a WIN."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT status FROM trades WHERE status IN ('WIN','LOSS') ORDER BY id DESC LIMIT 10"
    )
    rows = cur.fetchall()
    conn.close()
    count = 0
    for r in rows:
        if r["status"] == "LOSS":
            count += 1
        else:
            break
    return count


def get_closed_trades_for_learning(limit: int = 30) -> list[dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT direction, entry_price, exit_price, status, profit_eur,
               rsi_at_entry, trend_at_entry, confluence_score, trade_date
        FROM trades WHERE status IN ('WIN','LOSS')
        ORDER BY trade_date DESC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_trade_stats_detailed() -> dict:
    """Extended stats: per session, per regime, per day-of-week, current streak."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT direction, status, profit_eur, trade_date,
               session_at_entry, trade_score, wyckoff_phase,
               confluence_score, rsi_at_entry
        FROM trades
        WHERE status IN ('WIN','LOSS','BE')
        ORDER BY trade_date ASC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows:
        return {"by_session": {}, "by_regime": {}, "by_weekday": {}, "streak": 0}

    closed = [r for r in rows if r["status"] in ("WIN", "LOSS")]

    def _wr(trades):
        w = [t for t in trades if t["status"] == "WIN"]
        return round(len(w) / len(trades) * 100, 1) if trades else None

    # ── By session ───────────────────────────────────────────────────
    by_session: dict = {}
    for t in closed:
        s = t.get("session_at_entry") or "Inconnu"
        by_session.setdefault(s, []).append(t)
    by_session_stats = {
        s: {"win_rate": _wr(v), "count": len(v),
            "pnl": round(sum(t.get("profit_eur", 0) or 0 for t in v), 2)}
        for s, v in by_session.items()
    }

    # ── By day of week ───────────────────────────────────────────────
    _DAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    by_day: dict = {}
    for t in closed:
        try:
            from datetime import date as _date
            d = _date.fromisoformat(t["trade_date"][:10])
            day_name = _DAYS[d.weekday()]
        except Exception:
            day_name = "Inconnu"
        by_day.setdefault(day_name, []).append(t)
    by_day_stats = {
        d: {"win_rate": _wr(v), "count": len(v),
            "pnl": round(sum(t.get("profit_eur", 0) or 0 for t in v), 2)}
        for d, v in by_day.items()
    }

    # ── By trade score bucket ─────────────────────────────────────────
    by_score: dict = {}
    for t in closed:
        sc = t.get("trade_score")
        if sc is None:
            bucket = "Inconnu"
        elif sc >= 90:
            bucket = "≥90 (Très fort)"
        elif sc >= 80:
            bucket = "80-89 (Fort)"
        elif sc >= 70:
            bucket = "70-79 (Modéré)"
        else:
            bucket = "<70 (Faible)"
        by_score.setdefault(bucket, []).append(t)
    by_score_stats = {
        b: {"win_rate": _wr(v), "count": len(v)}
        for b, v in by_score.items()
    }

    # ── Current streak ────────────────────────────────────────────────
    streak = 0
    for t in reversed(closed):
        if streak == 0:
            streak = 1 if t["status"] == "WIN" else -1
        elif streak > 0 and t["status"] == "WIN":
            streak += 1
        elif streak < 0 and t["status"] == "LOSS":
            streak -= 1
        else:
            break

    return {
        "by_session":   by_session_stats,
        "by_weekday":   by_day_stats,
        "by_score":     by_score_stats,
        "streak":       streak,
        "total_closed": len(closed),
    }


def export_trades_csv() -> str:
    """Export all trades as CSV string."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, trade_date, direction, entry_price, stop_loss, take_profit_1,
               take_profit_2, exit_price, status, profit_eur, lot_size, notes,
               rsi_at_entry, trend_at_entry, confluence_score,
               session_at_entry, trade_score, wyckoff_phase, mtf_aligned
        FROM trades ORDER BY trade_date ASC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not rows:
        return "id,trade_date,direction,entry_price,status,profit_eur\n"

    headers = list(rows[0].keys())
    lines   = [",".join(headers)]
    for r in rows:
        line = ",".join(
            str(r.get(h, "") or "").replace(",", ";").replace("\n", " ")
            for h in headers
        )
        lines.append(line)
    return "\n".join(lines)


# ─────────────────────────────────────────────
# COT CACHE
# ─────────────────────────────────────────────

def save_cot(data: dict):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO cot_cache (data) VALUES (?)", (json.dumps(data),))
    conn.commit()
    conn.close()


def get_latest_cot() -> dict | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT data, fetched_at FROM cot_cache ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if row:
        d = json.loads(row["data"])
        d["_fetched_at"] = row["fetched_at"]
        return d
    return None


# ─────────────────────────────────────────────
# SENTIMENT CACHE
# ─────────────────────────────────────────────

def save_sentiment(data: dict):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO sentiment_cache (data) VALUES (?)", (json.dumps(data),))
    conn.commit()
    conn.close()


def get_latest_sentiment() -> dict | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT data FROM sentiment_cache ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return json.loads(row["data"]) if row else None


# ─────────────────────────────────────────────
# PENDING SIGNALS (interactive Telegram alerts)
# ─────────────────────────────────────────────

def save_pending_signal(chat_id: int, signal: dict, timeout_minutes: int = 30) -> int:
    """Persist a signal waiting for OUI/NON confirmation. Returns the row id."""
    from datetime import timedelta
    now     = datetime.utcnow()
    expires = now + timedelta(minutes=timeout_minutes)
    conn = get_connection()
    cur  = conn.cursor()
    # Expire any previous unhandled signals for this chat
    cur.execute(
        "UPDATE pending_signals SET handled = 1 WHERE chat_id = ? AND handled = 0",
        (chat_id,)
    )
    cur.execute(
        "INSERT INTO pending_signals (chat_id, signal_json, sent_at, expires_at) VALUES (?,?,?,?)",
        (chat_id, json.dumps(signal), now.isoformat(), expires.isoformat()),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def get_pending_signal(chat_id: int) -> dict | None:
    """Return the latest unhandled, non-expired signal for a chat_id."""
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(
        """SELECT id, signal_json, expires_at FROM pending_signals
           WHERE chat_id = ? AND handled = 0
           ORDER BY id DESC LIMIT 1""",
        (chat_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    # Check expiry
    expires_at = datetime.fromisoformat(row["expires_at"])
    if datetime.utcnow() > expires_at:
        mark_signal_handled(row["id"])
        return None
    return {"id": row["id"], **json.loads(row["signal_json"])}


def mark_signal_handled(signal_id: int):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("UPDATE pending_signals SET handled = 1 WHERE id = ?", (signal_id,))
    conn.commit()
    conn.close()
