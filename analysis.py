"""Transparent, rules-based stock screening. Not investment advice.

Metrics are calculated from the provided provider snapshot. Missing figures are never
substituted with invented values and financial-sector businesses are not scored like
industrial companies.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional


def valid(x):
    if x is None or isinstance(x, bool):
        return None
    try:
        result = float(x)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError, OverflowError):
        return None


def pct(x):
    x = valid(x)
    return None if x is None else round(x * 100, 2)


def growth_cagr(current, previous, years):
    current, previous = valid(current), valid(previous)
    if current is None or previous is None or current <= 0 or previous <= 0 or years <= 0:
        return None
    return round(((current / previous) ** (1 / years) - 1) * 100, 2)


def band(value, thresholds):
    """Return rating 0 to 100 for numeric x based on ascending lower bounds."""
    if value is None:
        return None
    match = thresholds[0][1]
    for floor, score in thresholds:
        if value >= floor:
            match = score
    return match


def average(values):
    numbers = [v for v in values if v is not None]
    return round(sum(numbers) / len(numbers), 1) if numbers else None


def derive_report(raw):
    info = raw.get('info') or {}
    annual = raw.get('annual') or []
    quarterly = raw.get('quarterly') or []
    prices = raw.get('price_history') or []
    last = annual[0] if annual else {}
    old = annual[-1] if len(annual) > 1 else {}
    years = max(1, len(annual) - 1)

    revenue_cagr = growth_cagr(last.get('revenue'), old.get('revenue'), years) if len(annual) > 1 else None
    profit_cagr = growth_cagr(last.get('profit'), old.get('profit'), years) if len(annual) > 1 else None

    revenue_growth = pct(info.get('revenueGrowth'))
    roe = pct(info.get('returnOnEquity'))
    if roe is None and len(annual) >= 2:
        e1, e2 = valid(annual[0].get('equity')), valid(annual[1].get('equity'))
        net = valid(annual[0].get('profit'))
        if net is not None and e1 is not None and e2 is not None and (e1 + e2) > 0:
            roe = round(net / ((e1 + e2) / 2) * 100, 2)

    op_margin = pct(info.get('operatingMargins'))
    if op_margin is None:
        ebit, revenue = valid(last.get('ebit')), valid(last.get('revenue'))
        if ebit is not None and revenue is not None and revenue > 0:
            op_margin = round(ebit / revenue * 100, 2)

    roce = None
    ebit, total_assets, current_liabilities = (valid(last.get(k)) for k in ('ebit', 'total_assets', 'current_liabilities'))
    if ebit is not None and total_assets is not None and current_liabilities is not None and total_assets > current_liabilities:
        roce = round(ebit / (total_assets - current_liabilities) * 100, 2)

    debt_equity = valid(info.get('debtToEquity'))
    if debt_equity is not None:
        debt_equity = round(debt_equity / 100, 2)  # Yahoo expresses this figure as a percentage.
    else:
        debt, equity = valid(last.get('debt')), valid(last.get('equity'))
        if debt is not None and equity is not None and equity > 0:
            debt_equity = round(debt / equity, 2)

    current_ratio = valid(info.get('currentRatio'))
    if current_ratio is None:
        ca, cl = valid(last.get('current_assets')), valid(last.get('current_liabilities'))
        if ca is not None and cl is not None and cl > 0:
            current_ratio = round(ca / cl, 2)

    cfo = valid(last.get('cfo'))
    fcf = valid(last.get('fcf'))
    net = valid(last.get('profit'))
    cfo_conversion = round(cfo / net, 2) if cfo is not None and net is not None and net > 0 else None
    trailing_eps = valid(info.get('trailingEps'))
    trailing_pe = valid(info.get('trailingPE'))
    pb = valid(info.get('priceToBook'))
    if trailing_pe is None and trailing_eps is not None and trailing_eps > 0 and valid(raw.get('price')):
        trailing_pe = round(raw['price'] / trailing_eps, 2)
    if trailing_pe is not None and trailing_pe <= 0:
        trailing_pe = None

    sector_text = ((info.get('sector') or '') + ' ' + (info.get('industry') or '')).lower()
    financial = any(k in sector_text for k in ('financial service', 'bank', 'insurance', 'credit service', 'asset management', 'capital market', 'mortgage', 'financial data'))

    metrics = {
        'revenue_cagr': revenue_cagr,
        'profit_cagr': profit_cagr,
        'revenue_growth': revenue_growth,
        'roe': roe,
        'roce': None if financial else roce,
        'operating_margin': op_margin,
        'debt_equity': None if financial else debt_equity,
        'current_ratio': None if financial else current_ratio,
        'operating_cash_flow': cfo,
        'free_cash_flow': fcf,
        'cash_conversion': None if financial else cfo_conversion,
        'trailing_pe': trailing_pe,
        'forward_pe': valid(info.get('forwardPE')),
        'eps': trailing_eps,
        'price_to_book': pb,
        'dividend_yield': pct(info.get('dividendYield')),
        'market_cap': valid(info.get('marketCap')),
    }
    # Categories weighted across the metrics that are actually available. No fake zeros.
    groups = [
        ('Growth', 'Business growth', 25, [
            ('Sales CAGR', revenue_cagr, [(-999, 5), (-5, 20), (0, 40), (8, 60), (12, 78), (18, 95)]),
            ('Profit CAGR', profit_cagr, [(-999, 0), (-5, 15), (0, 35), (10, 65), (15, 80), (22, 100)]),
            ('Latest revenue growth', revenue_growth, [(-999, 5), (-10, 15), (0, 40), (8, 65), (15, 85), (25, 100)]),
        ]),
        ('Profitability', 'Profit quality', 20, [
            ('ROE', roe, [(-999, 0), (0, 20), (8, 45), (12, 65), (16, 82), (22, 100)]),
            ('ROCE', None if financial else roce, [(-999, 0), (0, 20), (10, 50), (15, 72), (20, 90), (28, 100)]),
            ('Operating margin', op_margin, [(-999, 0), (0, 25), (5, 48), (10, 65), (18, 88), (28, 100)]),
        ]),
        ('Balance', 'Debt & liquidity', 20, [
            ('Debt/equity', None if financial or debt_equity is None else -debt_equity,
             [(-999, 0), (-2, 15), (-1, 48), (-0.5, 78), (-0.15, 100)]),
            ('Current ratio', None if financial else current_ratio,
             [(-999, 0), (0.7, 30), (1.0, 60), (1.5, 88), (2.5, 100)]),
        ]),
        ('Cashflow', 'Cash flow', 15, [
            ('Operating cash flow positive', None if financial or cfo is None else (1 if cfo > 0 else 0),
             [(-999, 0), (1, 100)]),
            ('Free cash flow positive', None if financial or fcf is None else (1 if fcf > 0 else 0),
             [(-999, 0), (1, 100)]),
            ('Cash conversion', None if financial else cfo_conversion,
             [(-999, 0), (0, 20), (0.5, 55), (1.0, 85), (1.5, 100)]),
        ]),
        ('Valuation', 'Share valuation', 20, [
            ('P/E', None if trailing_pe is None else -trailing_pe,
             [(-9999, 5), (-75, 18), (-50, 35), (-35, 55), (-25, 78), (-15, 90), (-9, 100)]),
        ])
    ]
    categories = []
    total_weight = 0
    weighted_score = 0
    for key, label, weight, inputs in groups:
        evaluations = []
        for name, value, bands in inputs:
            score = band(value, bands)
            if score is not None:
                evaluations.append({'name': name, 'score': score})
        group_score = average([i['score'] for i in evaluations])
        categories.append({'key': key, 'label': label, 'score': group_score, 'weight': weight,
                           'checked': len(evaluations), 'possible': len(inputs)})
        if group_score is not None:
            weighted_score += group_score * weight
            total_weight += weight
    overall = round(weighted_score / total_weight) if total_weight else None

    # Confidence is constrained by availability and by the applicability of the model.
    core = [revenue_cagr, profit_cagr, roe, op_margin, debt_equity if not financial else None,
            cfo if not financial else None, fcf if not financial else None, trailing_pe, trailing_eps, roce if not financial else None]
    count = sum(v is not None for v in core)
    coverage = round(count / len(core) * 100)
    stale = False
    if raw.get('quote_date'):
        try:
            date = datetime.fromisoformat(raw['quote_date']).date()
            stale = (datetime.now(timezone.utc).date() - date).days > 10
        except ValueError:
            pass

    positives, concerns, cautions = [], [], []
    if revenue_cagr is not None:
        if revenue_cagr >= 12: positives.append(f'Sales {years}-year CAGR {revenue_cagr}%: demand growth achhi rahi hai.')
        elif revenue_cagr < 0: concerns.append(f'Sales {years}-year CAGR {revenue_cagr}%: business revenue ghata hai.')
    if profit_cagr is not None:
        if profit_cagr >= 15: positives.append(f'Profit {years}-year CAGR {profit_cagr}%: earnings growth achhi rahi hai.')
        elif profit_cagr < 0: concerns.append(f'Profit CAGR {profit_cagr}%: earnings pressure mein hain.')
    if roe is not None:
        if roe >= 16: positives.append(f'ROE {roe}%: equity par achha return.')
        elif roe < 8: concerns.append(f'ROE {roe}%: returns weak hain.')
    if not financial and roce is not None:
        if roce >= 18: positives.append(f'ROCE {roce}%: capital efficiency achhi hai.')
        elif roce < 8: concerns.append(f'ROCE {roce}%: capital efficiency low hai.')
    if debt_equity is not None and not financial:
        if debt_equity < 0.4: positives.append(f'Debt/equity {debt_equity}: debt control mein hai.')
        elif debt_equity > 1.5: concerns.append(f'Debt/equity {debt_equity}: debt risk zyada hai.')
    if not financial and cfo is not None:
        if cfo > 0: positives.append('Operating cash flow positive hai.')
        else: concerns.append('Operating cash flow negative hai, cash earnings check karein.')
    if not financial and fcf is not None and fcf < 0: concerns.append('Free cash flow negative hai, capital spending aur funding check karein.')
    if net is not None and net < 0: concerns.append('Latest annual result mein company loss mein thi.')
    if trailing_pe is not None:
        if trailing_pe > 50: concerns.append(f'P/E {trailing_pe:.1f}: valuation high hai, growth disappoint hui toh risk hai.')
        elif 0 < trailing_pe <= 18: positives.append(f'P/E {trailing_pe:.1f}: headline multiple comparatively low hai, par value trap check karein.')

    if financial:
        cautions.append('Bank/NBFC/financial business ke liye NPA, NIM, capital adequacy aur asset quality check karna zaroori hai. Ye general score uske liye valid nahi.')
    if not info.get('sector'):
        cautions.append('Sector data missing: industry-specific checks complete nahi hue.')
    cautions.append('Promoter pledging, auditor remarks, management quality, corporate actions aur latest exchange filings independently verify karein.')
    cautions.append('P/E ka cutoff har industry mein alag ho sakta hai; peer comparison aur historical valuations ke bina final buy decision na lein.')
    if stale:
        cautions.append('Available share-price quote 10 din se purana ho sakta hai, market data update verify karein.')
    if len(annual) < 3:
        cautions.append('3 saal ke annual financial results nahi mile, historical trend incomplete hai.')

    if financial:
        signal = 'REVIEW'; signal_hi = 'Special analysis chahiye'
    elif coverage < 60 or overall is None or stale or len(annual) < 2:
        signal = 'INCOMPLETE'; signal_hi = 'Data kam hai, abhi decision nahi'
    elif net is not None and net < 0 and cfo is not None and cfo < 0:
        signal = 'AVOID'; signal_hi = 'Abhi avoid karein'
    elif overall < 48 or len(concerns) >= 3:
        signal = 'AVOID'; signal_hi = 'Abhi avoid karein'
    elif overall >= 75 and not concerns and trailing_pe is not None and trailing_pe <= 35:
        signal = 'CONSIDER'; signal_hi = 'Buy ke liye research karein'
    else:
        signal = 'WAIT'; signal_hi = 'Rukkar check karein'

    confidence = 'Low' if coverage < 70 else ('Medium' if coverage < 90 else 'High')
    if financial: confidence = 'Specialist review needed'

    # Illustrative stress test only, intentionally not a price forecast or price target.
    scenarios = []
    price = valid(raw.get('price'))
    if trailing_eps is not None and trailing_eps > 0 and trailing_pe is not None and price is not None and trailing_pe < 120 and (revenue_cagr is not None or profit_cagr is not None):
        base_growth = average([v for v in (revenue_cagr, profit_cagr) if v is not None])
        base_growth = max(-8, min(22, base_growth))
        for name, growth, multiple in (
            ('Conservative', max(-15, base_growth - 9), trailing_pe * 0.65),
            ('Base case', base_growth, trailing_pe * 0.85),
            ('Optimistic', min(30, base_growth + 8), trailing_pe * 1.05)
        ):
            future_eps = trailing_eps * (1 + growth / 100) ** 3
            projected = round(future_eps * multiple, 2)
            scenarios.append({'name': name, 'eps_growth': round(growth, 1), 'future_pe': round(multiple, 1),
                              'price': projected, 'change_pct': round((projected / price - 1) * 100, 1)})

    summary = {
        'CONSIDER': 'Numbers achhe lag rahe hain aur basic valuation filter pass hua hai. Phir bhi filing aur peer comparison dekhkar hi position plan karein.',
        'WAIT': 'Growth, risk ya valuation mein kuch questions hain. Agle quarterly result, better entry price ya extra verification ka wait sensible hai.',
        'AVOID': 'Available financial figures mein multiple weaknesses hain. Risk samjhe bina entry lena sahi nahi hoga.',
        'INCOMPLETE': 'Reliable numbers poore nahi mile. Incomplete data se buy/avoid conclusion dena misleading hoga.',
        'REVIEW': 'Financial companies ke liye alag model chahiye. Bank/NBFC ke general business ratios se lena ya avoid ka verdict nahi denge.'
    }[signal]

    return {**raw, 'metrics': metrics, 'score': {'total': overall, 'coverage': coverage, 'confidence': confidence,
              'signal': signal, 'signal_hi': signal_hi, 'summary': summary, 'categories': categories},
            'positive': positives, 'concerns': concerns, 'cautions': cautions,
            'scenarios': scenarios, 'scenario_note': 'Ye 3-year WHAT-IF calculations hain, price targets ya guaranteed predictions nahi. EPS growth aur future P/E ke assumed combinations hain.',
            'methodology': 'Rules-based research screener: growth 25%, profitability 20%, balance 20%, cashflow 15%, valuation 20%. Missing categories reweighted. Financial companies par auto-verdict disabled.'}
