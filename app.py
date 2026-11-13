"""StockSahi India - financial research dashboard."""
from __future__ import annotations

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


@app.get('/api/report')
def report():
    symbol = (request.args.get('symbol') or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9.\-^=]{1,30}', symbol):
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
