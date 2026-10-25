"""
Downloads Ken French daily FF5 + momentum factors and saves them as data/ff_factors_daily.csv
(values in PERCENT, as published). Run from the project root:   python data/fetch_factors.py
Needs internet access; only pandas/numpy required.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from analysis.factor_attribution import FF5_URL, MOM_URL, load_french

ff5 = load_french(FF5_URL)
mom = load_french(MOM_URL)
mom.columns = ["MOM"]
factors = ff5.join(mom, how="inner")
out = os.path.join(ROOT, "data", "ff_factors_daily.csv")
factors.to_csv(out)
print(f"Saved {out}\n{factors.shape} | {factors.index[0].date()} -> {factors.index[-1].date()}")
print(f"Columns: {list(factors.columns)}")
