from analysis import derive_report, growth_cagr


def example(**changes):
    data = {
        'name':'TEST COMPANY (SYNTHETIC DATA)', 'symbol':'TEST.NS','currency':'INR',
        'sector':'Industrials','industry':'Machinery', 'price': 200,
        'quote_date': '2099-01-01',
        'info': {'returnOnEquity':0.20, 'operatingMargins':0.17, 'debtToEquity':20,
                 'currentRatio':1.8,'trailingPE':24,'trailingEps':8.33,'marketCap':1e10,'revenueGrowth':0.16},
        'annual': [
            {'year':'2098','revenue':140,'profit':19,'ebit':25,'total_assets':130,'current_liabilities':30,'equity':90,'debt':18,'cfo':21,'fcf':14},
            {'year':'2097','revenue':120,'profit':16,'ebit':22,'equity':85},
            {'year':'2096','revenue':100,'profit':13,'ebit':18,'equity':80},
        ],
        'quarterly':[],'price_history':[]
    }
    data.update(changes)
    return data


def test_growth_rate():
    assert growth_cagr(121,100,2)==10
    assert growth_cagr(-10,100,2) is None
    assert growth_cagr(100,0,2) is None


def test_positive_example_and_scenarios():
    r=derive_report(example())
    assert r['metrics']['revenue_cagr'] > 10
    assert r['metrics']['debt_equity']==0.2
    assert 0 <= r['score']['total'] <= 100
    assert r['score']['signal'] in ('CONSIDER','WAIT')
    assert len(r['scenarios'])==3


def test_missing_info_never_auto_buy():
    r=derive_report(example(info={}, annual=[]))
    assert r['score']['signal']=='INCOMPLETE'
    assert r['metrics']['trailing_pe'] is None
    assert not r['scenarios']


def test_bank_requires_review():
    r=derive_report(example(info={**example()['info'],'sector':'Financial Services', 'industry':'Banks - Regional'}))
    assert r['score']['signal']=='REVIEW'
    assert r['metrics']['debt_equity'] is None


def test_losses_and_negative_cashflow_flagged():
    d=example()
    d['annual'][0]['profit']=-5
    d['annual'][0]['cfo']=-4
    r=derive_report(d)
    assert r['score']['signal']=='AVOID'
    assert any('negative' in line for line in r['concerns'])


def test_stale_quote_disables_recommendation():
    r=derive_report(example(quote_date='2000-01-01'))
    assert r['score']['signal']=='INCOMPLETE'
