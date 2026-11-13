import pandas as pd
from provider import source_rows, find_stocks, SYMBOL_PATTERN


def test_statements_join_by_fiscal_period():
    old = pd.Timestamp('2024-03-31')
    new = pd.Timestamp('2025-03-31')
    income = pd.DataFrame({new:[150,25,30],old:[100,15,20]}, index=['Total Revenue','Net Income','EBIT'])
    balance = pd.DataFrame({new:[80,20,120,30],old:[70,25,100,25]}, index=['Stockholders Equity','Total Debt','Total Assets','Current Liabilities'])
    # Deliberately reversed columns to validate timestamp joining.
    cashflow = pd.DataFrame({old:[22,-8],new:[32,-10]}, index=['Operating Cash Flow','Capital Expenditure'])
    result=source_rows(income,balance,cashflow)
    assert result[0]['year']=='2025'
    assert result[0]['revenue']==150
    assert result[0]['cfo']==32
    assert result[0]['fcf']==22
    assert result[1]['fcf']==14


def test_ticker_validation():
    assert SYMBOL_PATTERN.fullmatch('RELIANCE.NS')
    assert SYMBOL_PATTERN.fullmatch('500325.BO')
    assert not SYMBOL_PATTERN.fullmatch('AB/../../secret')
