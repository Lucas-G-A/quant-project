"""
Downloads adjusted daily closes for the ETF universe from 1993 to 2004-12-31: the CONFIRMATORY sample
for the v2 regime study (contains the 2000-2002 bear market). Saved separately from data/prices_etf.csv
so the v1 study's data is never touched.

Run from the project root inside the venv:   python data/fetch_etf_history.py
Writes data/prices_etf_pre2005.csv and prints each ETF's first date. ETFs that did not exist yet are NaN.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import yfinance as yf
from data.fetch_etf_data import TICKERS

END = "2005-01-01"      # exclusive: last row is 2004-12-31

data = yf.download(TICKERS, start="1993-01-01", end=END, auto_adjust=True, progress=False)["Close"]
data = data[TICKERS].dropna(how="all")
out = os.path.join(ROOT, "data", "prices_etf_pre2005.csv")
data.to_csv(out)
print(f"Saved {out}\nShape {data.shape} | {data.index[0].date()} -> {data.index[-1].date()}\n")
print(f"{'ETF':6s} {'first date':12s}")
for t in TICKERS:
    first = data[t].first_valid_index()
    print(f"{t:6s} {first.date() if first is not None else 'not listed yet'}")
