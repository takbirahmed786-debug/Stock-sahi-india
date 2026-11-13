"""StockSahi India - financial research dashboard."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from statistics import median
import json
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
        return jsonify({'error': 'NSE deal feed abhi available nahi hai. Official NSE report kholein.'}), 503


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
