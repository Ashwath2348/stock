# StockQ - Indian Sector Stock Dashboard

StockQ is a Flask web app for tracking Indian market sectors, viewing top gainers and losers, and opening detailed stock pages with live charts and news.

## Features

- Sector dashboards: Automotive, Banking, Energy, Technology, Pharma, Telecom
- Live price cards with change percent, volume, and market cap
- Market index strip (NIFTY, SENSEX, BANKNIFTY, FINNIFTY)
- Stock detail page with 1D, 1M, and 6M chart views
- Latest news feed with lightweight sentiment labels
- Portfolio watchlist stored in SQLite

## UI Preview

### Sector Dashboard (Automotive)

This screen shows the left sector navigation, market index summary, and stock cards with quick actions.

![Automotive Sector Dashboard](docs/screenshots/Screenshot%202026-04-19%20232624.png)

### Stock Detail Page

This screen shows core fundamentals, time-range chart toggles, and recent news sentiment cards for a selected stock.

![Stock Detail Page](docs/screenshots/Screenshot%202026-04-19%20232807.png)

## Tech Stack

- Python
- Flask
- yfinance
- feedparser
- SQLite
- HTML/CSS/JavaScript (Jinja templates)

## Project Structure

```text
stock/
  app.py
  requirements.txt
  docs/
    screenshots/
  static/
    css/
    js/
    icons/
  templates/
```

## Prerequisites

- Python 3.10 or higher
- Internet access for market data and news feeds

## Setup

1. Create and activate a virtual environment.

Windows (PowerShell):
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

macOS/Linux:
```bash
python -m venv venv
source venv/bin/activate
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

## Run Locally

```bash
python app.py
```

Default URL:
- `http://127.0.0.1:10000`

Custom port examples:

Windows (PowerShell):
```powershell
$env:PORT=5000
python app.py
```

macOS/Linux:
```bash
PORT=5000 python app.py
```

## Main Routes

- `/` or `/automotive`: Automotive dashboard
- `/banking`: Banking dashboard
- `/energy`: Energy dashboard
- `/technology`: Technology dashboard
- `/pharma`: Pharma dashboard
- `/telecom`: Telecom dashboard
- `/portfolio`: Portfolio page
- `/dashboard`: Portfolio alias
- `/stock/<symbol>`: Detailed stock page
- `/api/portfolio_data`: Portfolio API for UI updates
- `/api/stock_chart/<symbol>`: Intraday chart API
- `POST /add_to_portfolio`: Add stock to portfolio
- `POST /remove_from_portfolio`: Remove stock from portfolio

## Data Storage

- Local database: `portfolio.db` (created automatically)
- Table: `portfolio(symbol, name, sector)`

## Notes

- NSE symbols are queried using the `.NS` suffix.
- Some symbols can return empty/partial data based on Yahoo Finance availability.
- News sentiment tags are keyword-based, intended for quick context only.

## Development Roadmap

- [ ] Add symbol search and autocomplete
- [ ] Add longer date ranges (1Y, 3Y, 5Y)
- [ ] Add portfolio analytics (PnL, sector allocation)
- [ ] Add caching to reduce repeated API calls
- [ ] Add robust loading/error states for all async sections
- [ ] Add tests for utility functions and route-level integration
- [ ] Add Docker support for easier deployment
- [ ] Add authentication and multi-user portfolios

## Deployment

`gunicorn` is included in `requirements.txt`.

Example command (Linux/macOS):

```bash
gunicorn -w 2 -b 0.0.0.0:10000 app:app
```
