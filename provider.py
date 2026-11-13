"""Yahoo Finance data adapter via yfinance (personal/research use only)."""
from __future__ import annotations

import re
from datetime import datetime, timezone

import pandas as pd

SYMBOL_PATTERN = re.compile(r'^[A-Z0-9.\-^=]{1,30}$')
COMMON = {
    'RELIANCE': ('RELIANCE.NS','Reliance Industries'),
    'TCS': ('TCS.NS', 'Tata Consultancy Services'),
    'INFOSYS': ('INFY.NS', 'Infosys'),
    'INFY': ('INFY.NS','Infosys'),
    'ITC': ('ITC.NS','ITC'),
    'HDFC BANK': ('HDFCBANK.NS','HDFC Bank'),
    'HDFCBANK': ('HDFCBANK.NS','HDFC Bank'),
    'ICICI BANK': ('ICICIBANK.NS','ICICI Bank'),
    'ICICIBANK': ('ICICIBANK.NS','ICICI Bank'),
    'SBI': ('SBIN.NS','State Bank of India'),
    'SBIN': ('SBIN.NS','State Bank of India'),
    'WIPRO': ('WIPRO.NS','Wipro'),
    'LT': ('LT.NS','Larsen & Toubro'),
    'L&T': ('LT.NS','Larsen & Toubro'),
    'BHARTI AIRTEL': ('BHARTIARTL.NS','Bharti Airtel'),
    'AIRTEL': ('BHARTIARTL.NS','Bharti Airtel'),
    'HINDUSTAN UNILEVER': ('HINDUNILVR.NS','Hindustan Unilever'),
    'HUL': ('HINDUNILVR.NS','Hindustan Unilever'),
    'ADANI ENTERPRISES': ('ADANIENT.NS','Adani Enterprises'),
    'ADANIENT': ('ADANIENT.NS','Adani Enterprises'),
    'ASIAN PAINTS': ('ASIANPAINT.NS','Asian Paints'),
    'TITAN': ('TITAN.NS','Titan Company'),
    'SUN PHARMA': ('SUNPHARMA.NS','Sun Pharmaceutical'),
    'SUNPHARMA': ('SUNPHARMA.NS','Sun Pharmaceutical'),
    'BAJAJ FINANCE': ('BAJFINANCE.NS','Bajaj Finance'),
    'AXIS BANK': ('AXISBANK.NS','Axis Bank'),
    'KOTAK BANK': ('KOTAKBANK.NS','Kotak Mahindra Bank'),
    'MARUTI': ('MARUTI.NS','Maruti Suzuki'),
    'NTPC': ('NTPC.NS','NTPC'),
    'ONGC': ('ONGC.NS','ONGC'),
    'TATA STEEL': ('TATASTEEL.NS','Tata Steel'),
    'TATASTEEL': ('TATASTEEL.NS','Tata Steel'),
    'TATA POWER': ('TATAPOWER.NS','Tata Power'),
    'TATAPOWER': ('TATAPOWER.NS','Tata Power'),
    'COAL INDIA': ('COALINDIA.NS','Coal India'),
    'PIDILITE': ('PIDILITIND.NS','Pidilite Industries'),
    'HAL': ('HAL.NS','Hindustan Aeronautics'),
    'BEL': ('BEL.NS','Bharat Electronics'),
    'TRENT': ('TRENT.NS','Trent'),
    'DMART': ('DMART.NS','Avenue Supermarts'),
}


def norm(s):
    return ' '.join((s or '').strip().upper().split())


def _has_yf():
    try:
        import yfinance as yf
        return yf
    except ImportError:
        raise RuntimeError('yfinance install nahi hai. pip install -r requirements.txt chalayein.')


def find_stocks(query):
    if not query or len(query) > 60:
        return []
    key = norm(query)
    picks = []
    seen = set()
    if key in COMMON:
        sym, name = COMMON[key]
        picks.append({'symbol': sym, 'name': name, 'exchange': 'NSE', 'type': 'EQUITY'})
        seen.add(sym)
    # Exact NSE or BSE ticker should still be usable if search is blocked.
    if SYMBOL_PATTERN.fullmatch(key):
        sym = key if key.endswith(('.NS', '.BO')) else key + '.NS'
        if sym not in seen and key not in COMMON:
            picks.append({'symbol': sym, 'name': key + ' (NSE ticker, verify)', 'exchange': 'NSE', 'type': 'EQUITY'})
            seen.add(sym)
    try:
        yf = _has_yf()
        response = yf.Search(query, max_results=12, news_count=0, lists_count=0, raise_errors=False)
        records = response.quotes
        for entry in sorted(records, key=lambda r: not str(r.get('symbol', '')).endswith(('.NS', '.BO'))):
            sym = str(entry.get('symbol', '')).upper()
            if sym in seen or not SYMBOL_PATTERN.fullmatch(sym) or not sym.endswith(('.NS', '.BO')):
                continue
            if str(entry.get('quoteType', '')).upper() not in ('EQUITY', ''):
                continue
            picks.append({
                'symbol': sym,
                'name': entry.get('shortname') or entry.get('longname') or sym,
                'exchange': entry.get('exchange') or '',
                'type': entry.get('quoteType') or 'EQUITY',
            })
            seen.add(sym)
    except Exception:
        pass
    return picks[:12]


def safe_float(x):
    try:
        if x is None or pd.isna(x): return None
        result = float(x)
        if not pd.notna(result): return None
        return result
    except (TypeError, ValueError):
        return None


def take_row(df, candidates):
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []
    for candidate in candidates:
        for idx in df.index:
            if str(idx).lower().replace(' ', '').replace('_', '') == candidate.lower().replace(' ', '').replace('_', ''):
                return [safe_float(df.loc[idx, column]) for column in df.columns]
    return []


def dataframe(safecall):
    try:
        df = safecall()
        return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def source_rows(income, balance, cashflow):
    """Join statement values by exact fiscal period (never by column position)."""
    keys = {
        'revenue': (income, ['Total Revenue','Operating Revenue']),
        'profit': (income, ['Net Income','Net Income Common Stockholders','Net Income From Continuing Operation Net Minority Interest']),
        'ebit': (income, ['EBIT','Operating Income']),
        'eps': (income, ['Diluted EPS','Basic EPS']),
        'equity': (balance, ['Stockholders Equity', 'Total Equity Gross Minority Interest','Common Stock Equity']),
        'debt': (balance, ['Total Debt']),
        'total_assets': (balance, ['Total Assets']),
        'current_assets': (balance, ['Current Assets']),
        'current_liabilities': (balance, ['Current Liabilities']),
        'cfo': (cashflow, ['Operating Cash Flow','Cash Flow From Continuing Operating Activities']),
        'capex': (cashflow, ['Capital Expenditure']),
        'fcf_direct': (cashflow, ['Free Cash Flow']),
    }
    by_key = {}
    for name, (frame, candidates) in keys.items():
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            by_key[name] = {}
            continue
        values = take_row(frame, candidates)
        by_key[name] = {pd.Timestamp(c).strftime('%Y-%m-%d'): v for c, v in zip(frame.columns, values)}
    dates = sorted(set(by_key['revenue']) | set(by_key['profit']), reverse=True)
    rows = []
    for date in dates:
        row = {'year': date[:4], 'period_end': date}
        for key in keys:
            row[key] = by_key[key].get(date)
        if row['fcf_direct'] is not None:
            row['fcf'] = row['fcf_direct']
        elif row['cfo'] is not None and row['capex'] is not None:
            row['fcf'] = row['cfo'] - abs(row['capex'])
        else:
            row['fcf'] = None
        row.pop('fcf_direct', None)
        rows.append(row)
    return rows[:6]


def fetch_stock(symbol):
    import yfinance as yf
    symbol = norm(symbol)
    if not SYMBOL_PATTERN.fullmatch(symbol):
        raise ValueError('Invalid share symbol. Valid example: RELIANCE.NS')
    ticker = yf.Ticker(symbol)
    try: history = ticker.history(period='5y', auto_adjust=False, raise_errors=False)
    except Exception: history = pd.DataFrame()
    if history.empty or 'Close' not in history.columns:
        raise ValueError('Is symbol ka price data nahi mila. NSE symbol .NS aur BSE symbol .BO check karein.')
    valid_prices = history['Close'].dropna()
    if valid_prices.empty:
        raise ValueError('Is share ka valid closing price nahi mila.')
    latest_price = round(float(valid_prices.iloc[-1]), 2)
    last_time = valid_prices.index[-1]
    last_date = pd.Timestamp(last_time).date().isoformat()
    one_year = valid_prices.loc[valid_prices.index >= valid_prices.index[-1] - pd.Timedelta(days=365)]
    one_year_return = round((float(one_year.iloc[-1]) / float(one_year.iloc[0]) - 1) * 100, 2) if len(one_year) > 1 and one_year.iloc[0] > 0 else None
    try: info = ticker.info or {}
    except Exception: info = {}

    # Individual request failures must not silently generate invented financial data.
    income = dataframe(lambda: ticker.income_stmt)
    balance = dataframe(lambda: ticker.balance_sheet)
    cashflow = dataframe(lambda: ticker.cashflow)
    q_income = dataframe(lambda: ticker.quarterly_income_stmt)
    annual = source_rows(income, balance, cashflow)
    quarterly = source_rows(q_income, pd.DataFrame(), pd.DataFrame())[:5]
    # Price history reduced to roughly weekly points; use original closing prices.
    price_history = [{'date': pd.Timestamp(idx).date().isoformat(), 'close': round(float(v), 2)}
                     for idx, v in valid_prices.iloc[::5].items()]
    if not price_history or price_history[-1]['date'] != last_date:
        price_history.append({'date': last_date, 'close': latest_price})
    record = {
        'symbol': symbol,
        'name': info.get('longName') or info.get('shortName') or symbol,
        'exchange': 'NSE' if symbol.endswith('.NS') else ('BSE' if symbol.endswith('.BO') else info.get('exchange','')),
        'currency': info.get('currency') or ('INR' if symbol.endswith(('.NS','.BO')) else 'USD'),
        'sector': info.get('sector') or 'Not available',
        'industry': info.get('industry') or 'Not available',
        'info': info,
        'price': latest_price,
        'quote_date': last_date,
        'one_year_return': one_year_return,
        'annual': annual,
        'quarterly': quarterly,
        'price_history': price_history,
        'fetched_at': datetime.now(timezone.utc).isoformat(),
        'source': 'Yahoo Finance via yfinance (quotes may be delayed)',
        'source_url': 'https://finance.yahoo.com/quote/' + symbol.replace('^', '%5E') + '/',
    }
    return record
