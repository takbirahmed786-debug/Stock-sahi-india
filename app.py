"""StockSahi India - financial research dashboard."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from statistics import median
import json
from pathlib import Path
from urllib.request import urlopen
import os
import re
import threading
import time
from flask import Flask, jsonify, render_template, request
from analysis import derive_report
from provider import fetch_stock, find_stocks

app = Flask(__name__)
app.json.sort_keys = False
app.config['JSON_AS_ASCII'] = False
_cache = {}
_lock = threading.Lock()


def cached(key, expiry, func):
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    result = func()
    with _lock:
        _cache[key] = (now + expiry, result)
        if len(_cache) > 200:
            for k in list(_cache):
                if _cache[k][0] <= now:
                    del _cache[k]
    return result


@app.get('/')
def home():
    return render_template('index.html')


@app.get('/api/health')
def health():
    return jsonify({'ok': True, 'name': 'StockSahi India'})


@app.get('/api/search')
def search():
    q = (request.args.get('q') or '').strip()
    if not 2 <= len(q) <= 60:
        return jsonify({'error': 'Kam se kam 2 letters likhein, maximum 60.'}), 400
    try:
        stocks = cached(('search', q.upper()), 3600, lambda: find_stocks(q))
        return jsonify({'results': stocks})
    except Exception:
        return jsonify({'error': 'Company lookup temporarily unavailable. NSE symbol .NS use karein.'}), 503


@app.get('/api/market-statistics')
def market_statistics():
    def fetch():
        with urlopen('https://www.nseindia.com/api/NextApi/apiClient?functionName=getMarketStatistics', timeout=8) as response:
            data = json.load(response)['data']
        if not data.get('asOnDate') or not data.get('snapshotCapitalMarket'):
            raise ValueError('Incomplete NSE market statistics')
        return data

    try:
        return jsonify(cached('market-statistics', 60, fetch))
    except (OSError, ValueError, KeyError, TypeError):
        return jsonify({'error': 'NSE feed temporarily unavailable'}), 503


@app.get('/api/nse-deals')
def nse_deals():
    def fetch():
        with urlopen('https://www.nseindia.com/api/snapshot-capital-market-largedeal', timeout=8) as response:
            snapshot = json.load(response)
        return {
            'date': snapshot['as_on_date'],
            'bulk': snapshot['BULK_DEALS_DATA'],
            'block': snapshot['BLOCK_DEALS_DATA'],
            'short': snapshot['SHORT_DEALS_DATA'],
        }

    try:
        return jsonify(cached('nse-deals', 300, fetch))
    except (OSError, ValueError, KeyError):
        return jsonify(json.loads(Path(__file__).with_name('nse_snapshot.json').read_text(encoding='utf-8')))


INDICES = {
    'Nifty 50': '^NSEI',
    'Nifty Bank': '^NSEBANK',
    'Nifty IT': '^CNXIT',
    'Sensex': '^BSESN',
}


def index_history(item):
    name, symbol = item
    try:
        import yfinance as yf
        frame = yf.Ticker(symbol).history(period='1y', interval='1d', auto_adjust=False, timeout=8)
        rows = frame.dropna(subset=['Close', 'Open', 'High', 'Low'])
        points = [{'date': date.date().isoformat(), 'close': round(float(row.Close), 2)}
                  for date, row in rows.iterrows()]
        if len(points) < 2:
            return {'name': name, 'points': []}
        last = rows.iloc[-1]
        return {'name': name, 'points': points, 'open': round(float(last.Open), 2),
                'high': round(float(last.High), 2), 'low': round(float(last.Low), 2)}
    except Exception:
        app.logger.warning('Index history unavailable for %s', symbol)
        return {'name': name, 'points': []}


@app.get('/api/market-overview')
def market_overview():
    def build():
        with ThreadPoolExecutor(max_workers=4) as pool:
            return list(pool.map(index_history, INDICES.items()))
    return jsonify(cached('market-overview', 300, build))


@app.get('/api/report')
def report():
    symbol = (request.args.get('symbol') or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9.\-^=_]{1,30}', symbol):
        return jsonify({'error': 'Valid symbol dijiye, jaise RELIANCE.NS.'}), 400
    try:
        def build():
            result = derive_report(fetch_stock(symbol))
            result.pop('info', None)  # Keep API small and avoid serializing provider internals.
            return result
        return jsonify(cached(('report', symbol), 900, build))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404
    except Exception:
        app.logger.exception('Data provider failed for %s', symbol)
        return jsonify({'error': 'Data provider se details nahi mil rahi. Rate limit / network issue ho sakta hai. Baad mein try karein.'}), 503


# Selected NSE comparables, grouped by principal business.
PEER_GROUPS = {
    'IT services': 'TCS INFY WIPRO HCLTECH TECHM LTIM',
    'Private sector banks': 'HDFCBANK ICICIBANK AXISBANK KOTAKBANK INDUSINDBK',
    'Public sector banks': 'SBIN BANKBARODA PNB CANBK UNIONBANK',
    'Integrated steel': 'TATASTEEL JSWSTEEL SAIL JINDALSTEL',
    'Passenger vehicles': 'MARUTI HYUNDAI M&M TMPV',
    'Decorative paints': 'ASIANPAINT BERGERPAINT KANSAINER INDIGOPNTS',
    'Pharmaceuticals': 'SUNPHARMA DRREDDY CIPLA LUPIN AUROPHARMA',
    'Cement': 'ULTRACEMCO SHREECEM AMBUJACEM ACC DALBHARAT',
    'Integrated oil and refining': 'RELIANCE IOC BPCL HINDPETRO',
    'Diversified FMCG': 'HINDUNILVR ITC DABUR MARICO GODREJCP',
    'Defence electronics': 'BEL DATA_PATTERNS ASTRAMICRO',
}


def peer_metrics(symbol):
    try:
        return cached(('peer-metrics', symbol), 3600, lambda: derive_report(fetch_stock(symbol))['metrics'])
    except Exception:
        app.logger.warning('Peer data unavailable for %s', symbol)
        return {}


@app.get('/api/peers')
def peers():
    symbol = (request.args.get('symbol') or '').strip().upper()
    ticker = symbol.removesuffix('.NS')
    for industry, members in PEER_GROUPS.items():
        group = members.split()
        if ticker in group:
            break
    else:
        return jsonify({'industry': None, 'peers': [], 'benchmarks': {}})
    def build():
        symbols = [item + '.NS' for item in group if item != ticker]
        with ThreadPoolExecutor(max_workers=3) as pool:
            reports = list(pool.map(peer_metrics, symbols))
        benchmarks = {}
        for key in set().union(*(report.keys() for report in reports)):
            valid_peers = {
                name: report[key] for name, report in zip(symbols, reports)
                if report.get(key) is not None
                and (key not in ('trailing_pe', 'price_to_book') or report[key] > 0)
            }
            if len(valid_peers) >= 2:
                benchmarks[key] = {'median': median(valid_peers.values()), 'values': valid_peers}
        return {'industry': industry, 'peers': symbols, 'benchmarks': benchmarks}
    return jsonify(cached(('peer-group', ticker), 900, build))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
