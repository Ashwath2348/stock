# Stock Sector Dashboard

A Flask-based stock dashboard focused on Indian market sectors.

The app provides:
- Sector-wise views (Automotive, Banking, Energy, Technology, Pharma, Telecom)
- Live stock snapshots using Yahoo Finance data
- Detailed stock pages with charts (1D, 1M, 6M)
- Google News-based stock news feed with simple sentiment tags
- A persistent portfolio watchlist using SQLite

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
  static/
  templates/
```

## Prerequisites

- Python 3.10+ recommended
- Internet connection (for market/news data)

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

## Run the App

From the project root:

```bash
python app.py
```

The server starts at:
- `http://127.0.0.1:10000` (default)

You can override the port:

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

- `/` or `/automotive` - Automotive sector dashboard
- `/banking` - Banking sector dashboard
- `/energy` - Energy sector dashboard
- `/technology` - Technology sector dashboard
- `/pharma` - Pharma sector dashboard
- `/telecom` - Telecom sector dashboard
- `/portfolio` - Portfolio page
- `/dashboard` - Alias of portfolio page
- `/stock/<symbol>` - Detailed stock page
- `/api/portfolio_data` - Portfolio data for UI refresh
- `/api/stock_chart/<symbol>` - Intraday chart data API
- `POST /add_to_portfolio` - Add stock to portfolio
- `POST /remove_from_portfolio` - Remove stock from portfolio

## Screenshots and Demo

Add visuals to help users quickly understand the UI and workflow.

- Home dashboard: `docs/screenshots/home-dashboard.png`
- Sector page (example: banking): `docs/screenshots/sector-banking.png`
- Stock detail view: `docs/screenshots/stock-detail.png`
- Portfolio page: `docs/screenshots/portfolio.png`
- Optional walkthrough GIF: `docs/screenshots/demo.gif`

Markdown template:

```md
## UI Preview

### Home Dashboard
![Home Dashboard](docs/screenshots/home-dashboard.png)

### Sector Page
![Sector Page](docs/screenshots/sector-banking.png)

### Stock Detail
![Stock Detail](docs/screenshots/stock-detail.png)

### Portfolio
![Portfolio](docs/screenshots/portfolio.png)

### Quick Demo
![Demo](docs/screenshots/demo.gif)
```

## Data and Storage

- Portfolio data is stored in `portfolio.db` (auto-created in project root).
- Table used: `portfolio(symbol, name, sector)`.

## Notes

- Tickers are queried with `.NS` suffix for NSE data.
- Some symbols may return partial or empty data if Yahoo Finance has limited coverage.
- News sentiment is keyword-based and intended as a lightweight indicator.

## Development Roadmap

- [ ] Add search/autocomplete for stock symbols across all sectors
- [ ] Add date-range comparison charts (1Y, 3Y, 5Y)
- [ ] Add portfolio performance metrics (PnL, allocation, sector exposure)
- [ ] Cache API responses to reduce repeated Yahoo Finance requests
- [ ] Add loading/empty/error UI states for all async widgets
- [ ] Add unit tests for utility functions and route-level integration tests
- [ ] Add Docker support for reproducible local and deployment environments
- [ ] Add user authentication and multi-user portfolio isolation

## Deployment

`gunicorn` is included in `requirements.txt` for production-style deployment.
Example (Linux/macOS):

```bash
gunicorn -w 2 -b 0.0.0.0:10000 app:app
```
