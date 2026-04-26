import os
import logging
from flask import Flask, render_template, jsonify, request
import yfinance as yf
import feedparser
import sqlite3
import re
from datetime import datetime
import math
import html
import urllib.parse

try:
    import psycopg2
except ImportError:
    psycopg2 = None

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_NAME = os.environ.get("DB_NAME", "portfolio.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()


def using_postgres():
    return bool(DATABASE_URL)


def normalized_database_url():
    if not DATABASE_URL:
        return ""

    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    if "sslmode=" not in url:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}sslmode=require"

    return url


def get_db_connection():
    if using_postgres():
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is required when DATABASE_URL is set")
        return psycopg2.connect(normalized_database_url())

    try:
        return sqlite3.connect(DB_NAME)
    except sqlite3.OperationalError as exc:
        fallback = os.path.join("/tmp", "portfolio.db")
        logger.warning("SQLite connect failed for %s (%s). Falling back to %s", DB_NAME, exc, fallback)
        return sqlite3.connect(fallback)


def safe_number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def safe_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def fetch_ticker_snapshot(symbol, suffix=".NS"):
    ticker = yf.Ticker(f"{symbol}{suffix}")
    info = {}
    history = None

    try:
        info = ticker.fast_info or {}
    except Exception:
        info = {}

    try:
        history = ticker.history(period="5d", interval="1d")
    except Exception:
        history = None

    last_close = None
    previous_close = None
    latest_volume = None

    if history is not None and not history.empty:
        closes = history["Close"].dropna().tolist()
        volumes = history["Volume"].dropna().tolist() if "Volume" in history.columns else []
        if closes:
            last_close = safe_number(closes[-1], default=0.0)
        if len(closes) >= 2:
            previous_close = safe_number(closes[-2], default=0.0)
        if volumes:
            latest_volume = safe_int(volumes[-1], default=0)

    current_price = safe_number(
        getattr(info, "lastPrice", None)
        or getattr(info, "regularMarketPrice", None)
        or info.get("lastPrice")
        or info.get("regularMarketPrice")
        or info.get("currentPrice")
        or last_close,
        default=0.0,
    )

    if not current_price and last_close:
        current_price = last_close

    if previous_close is None:
        previous_close = safe_number(
            info.get("previousClose") or info.get("regularMarketPreviousClose"),
            default=0.0,
        )

    change_value = 0.0
    change_percent = 0.0
    if current_price and previous_close:
        change_value = current_price - previous_close
        change_percent = (change_value / previous_close) * 100 if previous_close else 0.0
    else:
        change_value = safe_number(info.get("regularMarketChange") or 0.0)
        change_percent = safe_number(info.get("regularMarketChangePercent") or 0.0)

    volume = latest_volume if latest_volume is not None else safe_int(info.get("volume") or info.get("lastVolume") or 0)
    market_cap = safe_number(info.get("marketCap") or 0)

    if not market_cap and current_price:
        shares = safe_number(info.get("shares") or info.get("sharesOutstanding") or 0)
        if shares:
            market_cap = current_price * shares

    company_name = (
        info.get("longName")
        or info.get("shortName")
        or f"{symbol} Ltd"
    )

    return {
        "symbol": symbol,
        "name": company_name,
        "price": round(current_price, 2),
        "change_percent": round(change_percent, 2),
        "change_value": round(change_value, 2),
        "volume": f"{volume:,}" if volume else "N/A",
        "market_cap": f"₹{(market_cap / 1_000_000_000):.2f}B" if market_cap else "N/A",
        "_raw_info": info,
    }

def init_db():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS portfolio (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                sector TEXT
            )
        """)

        conn.commit()
    finally:
        if conn:
            conn.close()

try:
    init_db()
except Exception:
    # Keep app booting so platform logs remain accessible instead of immediate worker crash.
    logger.exception("Database initialization failed during startup")



COMPANY_MAP = {
    "M&M": "Mahindra and Mahindra Limited",
    "TVSMOTOR": "TVS Motor Company Limited",

    "MARUTI": "Maruti Suzuki India Limited",
    "HDFCBANK": "HDFC Bank Limited",
    "ICICIBANK": "ICICI Bank Limited",
    "RELIANCE": "Reliance Industries Limited",
    "INFY": "Infosys Limited",
    "TCS": "Tata Consultancy Services",
    "SBIN": "State Bank of India",
    "AXISBANK": "Axis Bank Limited",
    "KOTAKBANK": "Kotak Mahindra Bank Limited",

    "HEROMOTOCO": "Hero MotoCorp Limited",
    "EICHERMOT": "Eicher Motors Limited",
    "ASHOKLEY": "Ashok Leyland Limited",
    "BAJAJ-AUTO": "Bajaj Auto Limited",

    "INDUSINDBK": "IndusInd Bank Limited",
    "WIPRO": "Wipro Limited",
    "HCLTECH": "HCL Technologies Limited",
    "TECHM": "Tech Mahindra Limited",

    "SUNPHARMA": "Sun Pharmaceutical Industries Limited",
    "CIPLA": "Cipla Limited",
    "DRREDDY": "Dr. Reddy's Laboratories Limited",

    "BHARTIARTL": "Bharti Airtel Limited"
}

# CLEAN HTML
def clean_html(raw):
    if not raw:
        return ""
    text = re.sub(re.compile("<.*?>"), "", raw)
    text = html.unescape(text)
    return text.replace("\xa0", " ")

# NEWS SCRAPER
def get_stock_news(symbol, max_items=8):
    company = COMPANY_MAP.get(symbol.upper(), symbol)
    encoded_query = urllib.parse.quote(f"{company} stock share price NSE India")

    url = (
        "https://news.google.com/rss/search?"
        f"q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
    )

    feed = feedparser.parse(url)
    news_list = []

    for e in feed.entries[:max_items]:
        text = e.title.lower()
        if any(x in text for x in ["gain", "up", "profit", "jump"]):
            sentiment = "positive"
        elif any(x in text for x in ["loss", "fall", "drop", "down"]):
            sentiment = "negative"
        else:
            sentiment = "neutral"

        source = getattr(getattr(e, "source", None), "title", "Google News")

        news_list.append({
            "title": clean_html(e.title),
            "summary": clean_html(getattr(e, "summary", "")),
            "url": e.link,
            "source": source,
            "sentiment": sentiment
        })

    return news_list

def get_indices():
    indices = {
        "NIFTY": ["^NSEI"],
        "SENSEX": ["^BSESN"],
        "BANKNIFTY": ["^NSEBANK"],
        "FINNIFTY": ["^CNXFIN", "NIFTY_FIN_SERVICE.NS"],
    }

    def from_history_frame(df):
        try:
            if df is None or df.empty or "Close" not in df.columns:
                return None

            closes = df["Close"].dropna().tolist()
            if not closes:
                return None

            price = safe_number(closes[-1], 0.0)
            prev = safe_number(closes[-2], price) if len(closes) >= 2 else price
            if price <= 0:
                return None

            change = price - prev
            change_percent = (change / prev * 100) if prev else 0.0

            return {
                "price": round(price, 2),
                "change": round(change, 2),
                "change_percent": round(change_percent, 2),
            }
        except Exception:
            return None

    # Prefer bulk history download first since it is generally more reliable for index symbols.
    symbol_to_snapshot = {}
    all_symbols = sorted({sym for candidates in indices.values() for sym in candidates})

    try:
        bulk = yf.download(
            tickers=" ".join(all_symbols),
            period="5d",
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
        )

        if bulk is not None and not bulk.empty:
            for sym in all_symbols:
                frame = None
                try:
                    if hasattr(bulk.columns, "levels") and len(bulk.columns.levels) > 1:
                        frame = bulk.get(sym)
                    else:
                        frame = bulk
                except Exception:
                    frame = None

                snap = from_history_frame(frame)
                if snap:
                    symbol_to_snapshot[sym] = snap
    except Exception:
        logger.exception("Bulk index fetch failed; falling back to per-symbol fetch")

    result = []
    for name, symbol_candidates in indices.items():
        chosen = None

        for symbol in symbol_candidates:
            snap = symbol_to_snapshot.get(symbol)
            if snap:
                chosen = snap
                break

        # Per-symbol fallback if bulk path does not return a usable snapshot.
        if not chosen:
            for symbol in symbol_candidates:
                try:
                    snapshot = fetch_ticker_snapshot(symbol, suffix="")
                    if snapshot["price"] > 0:
                        chosen = {
                            "price": snapshot["price"],
                            "change": snapshot["change_value"],
                            "change_percent": snapshot["change_percent"],
                        }
                        break
                except Exception:
                    continue

        if not chosen:
            # Keep UI stable even if provider is temporarily unavailable.
            chosen = {"price": "N/A", "change": 0, "change_percent": 0}

        result.append({"name": name, **chosen})

    return result

def get_live_data(symbols):
    data = []
    for s in symbols:
        try:
            data.append(fetch_ticker_snapshot(s))
        except Exception:
            data.append({
                "symbol": s,
                "name": f"{s} Ltd",
                "price": 0,
                "change_percent": 0,
                "change_value": 0,
                "volume": "N/A",
                "market_cap": "N/A",
                "_raw_info": {}
            })
    return data

def get_portfolio_symbols():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM portfolio")
    out = [row[0] for row in cur.fetchall()]
    conn.close()
    return out


def sparkline_from_prices(prices, max_points=36):
    if not prices:
        return []
    prices = [float(x) for x in prices]
    if len(prices) > max_points:
        step = math.ceil(len(prices) / max_points)
        prices = prices[::step]
    return [round(x, 2) for x in prices]

# ============================================
# PORTFOLIO API
# ============================================
@app.route("/api/portfolio_data")
def api_portfolio_data():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT symbol, name, sector FROM portfolio")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return jsonify({"data": []})

    meta = {r[0]: {"name": r[1], "sector": r[2]} for r in rows}
    symbols = list(meta)
    base_live = get_live_data(symbols)

    enriched = []

    for item in base_live:
        sym = item["symbol"]
        raw = item["_raw_info"]

        spark_prices = []
        try:
            df = yf.Ticker(sym + ".NS").history(period="1mo", interval="1d")
            if not df.empty:
                spark_prices = df["Close"].dropna().tolist()
        except:
            pass

        enriched.append({
            "symbol": sym,
            "name": meta[sym]["name"],
            "sector": meta[sym]["sector"],
            "price": item["price"],
            "change_value": item["change_value"],
            "change_percent": item["change_percent"],
            "volume": item["volume"],
            "market_cap": item["market_cap"],
            "spark": sparkline_from_prices(spark_prices),
            "logo": raw.get("logo_url")
        })

    return jsonify({"data": enriched})

def render_sector(symbols, template, sector):
    portfolio = set(get_portfolio_symbols())
    data = get_live_data(symbols)

    for d in data:
        d["added"] = d["symbol"] in portfolio

    return render_template(
        template,
        gainers=sorted(data, key=lambda x: x["change_percent"], reverse=True)[:5],
        losers=sorted(data, key=lambda x: x["change_percent"])[:5],
        sector=sector,
        last_updated=datetime.now().strftime("%I:%M %p"),
        indices=get_indices()
    )

@app.route("/")
@app.route("/automotive")
def automotive():
    return render_sector(
        ["TVSMOTOR", "MARUTI", "HEROMOTOCO", "EICHERMOT",
         "BAJAJ-AUTO", "ASHOKLEY", "M&M", "TIINDIA", "BOSCHLTD", "ESCORTS"],
        "automotive.html",
        "Automotive"
    )

@app.route("/banking")
def banking():
    return render_sector(
        ["HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "SBIN",
         "PNB", "BANKBARODA", "IDFCFIRSTB", "INDUSINDBK", "FEDERALBNK"],
        "banking.html",
        "Banking"
    )

@app.route("/energy")
def energy():
    return render_sector(
        ["RELIANCE", "ONGC", "COALINDIA", "NTPC", "POWERGRID",
         "BPCL", "IOC", "TATAPOWER", "ADANIGREEN", "JSWENERGY"],
        "energy.html",
        "Energy"
    )

@app.route("/technology")
def technology():
    return render_sector(
        ["INFY", "TCS", "WIPRO", "HCLTECH", "TECHM",
         "LTIM", "COFORGE", "MPHASIS", "PERSISTENT"],
        "technology.html",
        "Technology"
    )

@app.route("/pharma")
def pharma():
    return render_sector(
        ["SUNPHARMA", "CIPLA", "DRREDDY", "AUROPHARMA",
         "DIVISLAB", "BIOCON", "LUPIN", "ZYDUSLIFE", "ALKEM", "TORNTPHARM"],
        "pharma.html",
        "Pharma"
    )

@app.route("/telecom")
def telecom():
    return render_sector(
        ["BHARTIARTL", "IDEA", "TATACOMM", "ROUTE", "STLTECH",
         "HFCL", "ITI", "TEJASNET", "NELCO", "GTPL"],
        "telecom.html",
        "Telecom"
    )

# ADD / REMOVE PORTFOLIO
@app.post("/add_to_portfolio")
def add_to_portfolio():
    data = request.json or {}
    symbol = str(data.get("symbol", "")).strip().upper()
    name = str(data.get("name", "")).strip()
    sector = str(data.get("sector", "")).strip()

    if not symbol or not name or not sector:
        return jsonify({"added": False, "error": "symbol, name and sector are required"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    if using_postgres():
        cur.execute(
            """
            INSERT INTO portfolio(symbol, name, sector)
            VALUES (%s, %s, %s)
            ON CONFLICT (symbol) DO NOTHING
            """,
            (symbol, name, sector),
        )
    else:
        cur.execute("""
            INSERT OR IGNORE INTO portfolio(symbol, name, sector)
            VALUES (?, ?, ?)
        """, (symbol, name, sector))

    conn.commit()
    conn.close()
    return jsonify({"added": True})

@app.post("/remove_from_portfolio")
def remove_from_portfolio():
    data = request.json or {}
    symbol = str(data.get("symbol", "")).strip().upper()

    if not symbol:
        return jsonify({"removed": False, "error": "symbol is required"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    if using_postgres():
        cur.execute("DELETE FROM portfolio WHERE symbol=%s", (symbol,))
    else:
        cur.execute("DELETE FROM portfolio WHERE symbol=?", (symbol,))

    conn.commit()
    conn.close()
    return jsonify({"removed": True})

@app.route("/dashboard")
def dashboard_page():
    return portfolio_page()

@app.route("/portfolio")
def portfolio_page():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT symbol, name, sector FROM portfolio")
    rows = cur.fetchall()
    conn.close()
    return render_template("portfolio.html", stocks=rows)


@app.route("/health")
def health():
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({"ok": True}), 200
    except Exception as exc:
        logger.exception("Health check failed")
        return jsonify({"ok": False, "error": str(exc)}), 500

# API: AUTO REFRESH 1D CHART
@app.route("/api/stock_chart/<symbol>")
def api_stock_chart(symbol):
    symbol = symbol.upper()
    ticker = yf.Ticker(symbol + ".NS")

    try:
        df = ticker.history(period="1d", interval="15m")
        if df.empty:
            df = ticker.history(period="5d", interval="15m")

        if df.empty:
            return jsonify({"dates": [], "prices": []})

        df = df.reset_index()
        idx = "Datetime" if "Datetime" in df.columns else "Date"

        dates = df[idx].dt.strftime("%H:%M").tolist()
        prices = df["Close"].round(2).tolist()

        return jsonify({"dates": dates, "prices": prices})

    except:
        return jsonify({"dates": [], "prices": []})


@app.route("/api/live_quotes")
def api_live_quotes():
    raw_symbols = request.args.get("symbols", "")
    symbols = [s.strip().upper() for s in raw_symbols.split(",") if s.strip()]

    # Prevent overly large quote batches from one request.
    symbols = symbols[:30]

    if not symbols:
        return jsonify({"quotes": {}})

    quotes = {}
    for item in get_live_data(symbols):
        quotes[item["symbol"]] = {
            "price": item["price"],
            "change_percent": item["change_percent"],
            "volume": item["volume"],
            "market_cap": item["market_cap"],
        }

    return jsonify({"quotes": quotes})

@app.route("/stock/<symbol>")
def stock_detail(symbol):
    symbol = symbol.upper()
    ticker = yf.Ticker(symbol + ".NS")

    def extract_chart_points(df, date_fmt):
        if df is None or df.empty:
            return [], []

        idx = "Datetime" if "Datetime" in df.columns else "Date"
        if idx not in df.columns or "Close" not in df.columns:
            return [], []

        cleaned = df[[idx, "Close"]].dropna(subset=["Close"]).copy()
        if cleaned.empty:
            return [], []

        dates = cleaned[idx].dt.strftime(date_fmt).tolist()
        prices = [round(safe_number(p, 0.0), 2) for p in cleaned["Close"].tolist()]
        return dates, prices

    def safe_history(period, interval):
        try:
            df = ticker.history(period=period, interval=interval)
            df = df.reset_index()
            return extract_chart_points(df, "%d %b")
        except:
            return [], []

    # intraday
    try:
        d1_df = ticker.history(period="1d", interval="15m")
        if d1_df.empty:
            d1_df = ticker.history(period="5d", interval="15m")
        d1_df = d1_df.reset_index()
        d1, p1 = extract_chart_points(d1_df, "%H:%M")
    except:
        d1, p1 = [], []

    d30, p30 = safe_history("1mo", "1d")
    d180, p180 = safe_history("6mo", "1wk")

    try:
        info = ticker.fast_info or {}
    except Exception:
        info = {}

    try:
        full_info = ticker.info or {}
    except Exception:
        full_info = {}

    if not full_info:
        full_info = info

    snapshot = fetch_ticker_snapshot(symbol)
    news = get_stock_news(symbol)

    stock_data = {
        "symbol": symbol,
        "company_name": full_info.get("longName") or full_info.get("shortName") or f"{symbol} Ltd",
        "price": snapshot["price"],
        "change_percent": snapshot["change_percent"],
        "change_value": snapshot["change_value"],
        "volume": snapshot["volume"],
        "market_cap": snapshot["market_cap"],
        "pe_ratio": full_info.get("trailingPE"),

        "chart_1d": {"dates": d1, "prices": p1},
        "chart_1m": {"dates": d30, "prices": p30},
        "chart_6m": {"dates": d180, "prices": p180},

        "latest_news": news
    }

    return render_template("stock_detail.html", stock=stock_data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
