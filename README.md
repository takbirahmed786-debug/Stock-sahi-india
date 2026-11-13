# StockSahi India

**Personal research website** for Indian NSE/BSE listed shares. Search company names or tickers, read a fundamentals report, get a transparent rules-based **Consider / Wait / Avoid / Incomplete** screening signal, view annual financials, and print the report to PDF.

> This is *not* personalized investment advice or a predictive trading algorithm. Figures are from Yahoo Finance through `yfinance`; quotes may be delayed and some statements unavailable. yfinance/Yahoo data is documented for personal/research use. For a public commercial website, obtain licensed market and financial data and review the applicable redistribution rights.

## Start on a Windows computer

1. Install **Python 3.11 or 3.12** from https://www.python.org/downloads/ (tick "Add Python to PATH").
2. Open Command Prompt inside this folder.
3. Double-click `START_WINDOWS.bat`, or run manually:

   ```bat
   python -m pip install -r requirements.txt
   python app.py
   ```

4. Open **http://127.0.0.1:5000** in a browser.

Mac/Linux: use `python3 -m pip install -r requirements.txt` and `python3 app.py`.

## Make it a live website, from GitHub to Render

1. Create a new GitHub repository and upload **all these project files**, keeping the `templates` and `static` folders.
2. Open https://dashboard.render.com/ → **New → Web Service** → connect the repository.
3. Render should read `render.yaml`. If you configure manually, use **Python 3**, build command `pip install -r requirements.txt`, start command `gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 app:app`.
4. Deploy and use the assigned `onrender.com` URL. Free plans can go to sleep after 15 min of inactivity and may take time to wake up. External Yahoo data requests can be rate limited/blocked; deploying does not guarantee their availability.

### How to search

- Name: `Reliance`, `HDFC Bank`, `TCS`
- NSE ticker: `RELIANCE.NS`, `ITC.NS`, `TCS.NS`
- BSE ticker: `500325.BO` (verify the code with BSE)
- Select the correct company from suggestions if names are similar. Ticker/exchange conventions and corporate actions can change.

### How recommendations work

| Factor | Weight |
| --- | ---: |
| Sales / profit growth | 25% |
| Profitability (ROE, ROCE, margin) | 20% |
| Debt / liquidity | 20% |
| Operating/free cash flow | 15% |
| P/E valuation | 20% |

**Missing figures are excluded rather than assumed.** Insufficient coverage, stale quotes or under 2 annual periods -> **INCOMPLETE**. Financial companies such as banks, NBFCs, insurers -> **REVIEW** because general manufacturing ratios are not enough. Low score / several risk flags -> **AVOID**. High score with a reasonable P/E and no flagged concerns -> **CONSIDER**; otherwise **WAIT**. This scoring is a basic heuristic and cannot account for changes in management, cyclicality, promoter pledging, contingent liabilities, peer valuation or recent material news.

The 3-year examples are **what-if models** based on historical EPS and assumed P/E, **not forecasts or price targets**. Read the underlying results on NSE/BSE before investing.

## API

- `GET /api/health` health check
- `GET /api/search?q=Reliance` company lookup
- `GET /api/report?symbol=RELIANCE.NS` live fundamental report

Reports cached 15 min and suggestions cached 1 hour per server instance. There is no database or login. For production use, add licensing, rate limits, authentication, logging/monitoring, stronger data validation, corporate-action adjustment and sector-specific models.

## Files

- `app.py` Flask application and API
- `provider.py` ticker search and `yfinance` financial statement adapter
- `analysis.py` deterministic scoring / coverage / risk evaluation
- `templates/index.html`, `static/` responsive website
- `tests/` synthetic **test fixtures only**, never displayed as live company data

## Android mobile / installable app (PWA)

Mobile setup is documented in **`MOBILE_SETUP_HINDI.txt`**. After deployment on HTTPS, open the URL in Android Chrome and select **Menu → Add to Home screen → Install**. The app icon comes from `static/manifest.webmanifest`. **Internet is mandatory for stock reports**. The service worker caches only the site shell, never financial reports. A shared report URL uses `?symbol=RELIANCE.NS`; do not treat it as a stored snapshot.

**GitHub account:** do not upload this project into an unrelated existing repository. Use a dedicated repository. Deployment has not been performed and no live public URL is included in the package.
