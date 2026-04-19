import os
from flask import Flask, render_template, jsonify, request
import yfinance as yf
import feedparser
import sqlite3
import re
from datetime import datetime
import math
import html
import urllib.parse

app = Flask(__name__)

DB_NAME = "portfolio.db"


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def format_volume(value):
    v = safe_float(value, default=-1)
    if v < 0:
        return "N/A"
    return f"{int(v):,}"


def format_market_cap(value):
    cap = safe_float(value, default=-1)
    if cap < 0:
        return "N/A"
    if cap >= 1_000_000_000_000:
        return f"Rs{cap / 1_000_000_000_000:.2f}T"
    if cap >= 1_000_000_000:
        return f"Rs{cap / 1_000_000_000:.2f}B"
    if cap >= 10_000_000:
        return f"Rs{cap / 10_000_000:.2f}Cr"
    return f"Rs{cap:,.0f}"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS portfolio (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                sector TEXT
            )
        """)

init_db()



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

    for e in getattr(feed, "entries", [])[:max_items]:
        title = clean_html(getattr(e, "title", ""))
        text = title.lower()
        if any(x in text for x in ["gain", "up", "profit", "jump"]):
            sentiment = "positive"
        elif any(x in text for x in ["loss", "fall", "drop", "down"]):
            sentiment = "negative"
        else:
            sentiment = "neutral"

        source = getattr(getattr(e, "source", None), "title", "Google News")

        news_list.append({
            "title": title,
            "summary": clean_html(getattr(e, "summary", "")),
            "url": getattr(e, "link", "#"),
            "source": source,
            "sentiment": sentiment
        })

    return news_list

def get_indices():
    indices = {
        "NIFTY": "^NSEI",
        "SENSEX": "^BSESN",
        "BANKNIFTY": "^NSEBANK",
        "FINNIFTY": "^CNXFIN"
    }

    result = []
    for name, symbol in indices.items():
        try:
            t = yf.Ticker(symbol)
            info = t.info

            result.append({
                "name": name,
                "price": round(safe_float(info.get("regularMarketPrice", 0)), 2),
                "change": round(safe_float(info.get("regularMarketChange", 0)), 2),
                "change_percent": round(safe_float(info.get("regularMarketChangePercent", 0)), 2)
            })
        except Exception:
            continue

    return result

def get_live_data(symbols):
    data = []
    for s in symbols:
        try:
            t = yf.Ticker(s + ".NS")
            info = t.info or {}

            data.append({
                "symbol": s,
                "name": info.get("longName", f"{s} Ltd"),
                "price": round(safe_float(info.get("currentPrice", 0)), 2),
                "change_percent": round(safe_float(info.get("regularMarketChangePercent", 0)), 2),
                "change_value": round(safe_float(info.get("regularMarketChange", 0)), 2),
                "volume": format_volume(info.get("volume")),
                "market_cap": format_market_cap(info.get("marketCap")),
                "_raw_info": info
            })
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
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("SELECT symbol FROM portfolio")
        return [row[0] for row in cur.fetchall()]


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
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("SELECT symbol, name, sector FROM portfolio ORDER BY sector, name")
        rows = cur.fetchall()

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
        except Exception:
            pass

        meta_row = meta.get(sym, {"name": item["name"], "sector": "Unknown"})

        enriched.append({
            "symbol": sym,
            "name": meta_row["name"],
            "sector": meta_row["sector"],
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
    data = request.get_json(silent=True) or {}
    symbol = str(data.get("symbol", "")).strip().upper()
    name = str(data.get("name", "")).strip()
    sector = str(data.get("sector", "")).strip()

    if not symbol or not name or not sector:
        return jsonify({"added": False, "error": "symbol, name and sector are required"}), 400

    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR IGNORE INTO portfolio(symbol, name, sector)
            VALUES (?, ?, ?)
        """, (symbol, name, sector))
        inserted = cur.rowcount > 0

    return jsonify({"added": inserted})

@app.post("/remove_from_portfolio")
def remove_from_portfolio():
    data = request.get_json(silent=True) or {}
    symbol = str(data.get("symbol", "")).strip().upper()
    if not symbol:
        return jsonify({"removed": False, "error": "symbol is required"}), 400

    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM portfolio WHERE symbol=?", (symbol,))
        removed = cur.rowcount > 0

    return jsonify({"removed": removed})

@app.route("/dashboard")
def dashboard_page():
    return portfolio_page()

@app.route("/portfolio")
def portfolio_page():
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("SELECT symbol, name, sector FROM portfolio ORDER BY sector, name")
        rows = cur.fetchall()
    return render_template("portfolio.html", stocks=rows)

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

    except Exception:
        return jsonify({"dates": [], "prices": []})

@app.route("/stock/<symbol>")
def stock_detail(symbol):
    symbol = symbol.upper()
    ticker = yf.Ticker(symbol + ".NS")

    def safe_history(period, interval):
        try:
            df = ticker.history(period=period, interval=interval)
            if df.empty:
                return [], []
            df = df.reset_index()
            idx = "Datetime" if "Datetime" in df.columns else "Date"
            return df[idx].dt.strftime("%d %b").tolist(), df["Close"].round(2).tolist()
        except Exception:
            return [], []

    # intraday
    try:
        d1_df = ticker.history(period="1d", interval="15m")
        if d1_df.empty:
            d1_df = ticker.history(period="5d", interval="15m")
        d1_df = d1_df.reset_index()
        idx = "Datetime" if "Datetime" in d1_df.columns else "Date"
        d1 = d1_df[idx].dt.strftime("%H:%M").tolist()
        p1 = d1_df["Close"].round(2).tolist()
    except Exception:
        d1, p1 = [], []

    d30, p30 = safe_history("1mo", "1d")
    d180, p180 = safe_history("6mo", "1wk")

    try:
        info = ticker.info or {}
    except Exception:
        info = {}
    news = get_stock_news(symbol)

    stock_data = {
        "symbol": symbol,
        "company_name": info.get("longName", f"{symbol} Ltd"),
        "price": round(safe_float(info.get("currentPrice", 0)), 2),
        "change_percent": round(safe_float(info.get("regularMarketChangePercent", 0)), 2),
        "change_value": round(safe_float(info.get("regularMarketChange", 0)), 2),
        "volume": format_volume(info.get("volume")),
        "market_cap": format_market_cap(info.get("marketCap")),
        "pe_ratio": info.get("trailingPE"),

        "chart_1d": {"dates": d1, "prices": p1},
        "chart_1m": {"dates": d30, "prices": p30},
        "chart_6m": {"dates": d180, "prices": p180},

        "latest_news": news
    }

    return render_template("stock_detail.html", stock=stock_data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
