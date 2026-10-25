"""
Downloads macro and market-regime series from FRED (free, no API key needed for the CSV endpoint)
and saves them side by side in data/macro_fred.csv. Run from the project root:  python data/fetch_macro.py

IMPORTANT, read before using any of these in a backtest:
  MARKET-BASED (no revisions, known the same day; safe to use as a regime signal with a 1-day lag):
      T10Y2Y, T10Y3M, DGS10, DGS2, DGS3MO, BAA10Y, VIXCLS, T10YIE (breakevens start 2003)
  REVISED / PUBLISHED WITH A LAG (the values here are TODAY'S revised numbers, so using them for a past
  date leaks the future; only use for descriptive labels, or replace with vintage data from ALFRED):
      CPIAUCNS (not seasonally adjusted, so rarely revised; still published ~2 weeks after month end),
      UNRATE, GDPC1 (quarterly, heavily revised), INDPRO, USREC (NBER recession flag; dated months
      to years after the fact, so it is a DESCRIPTION of the past, never a tradable signal)
"""
import io
import os

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERIES = {
    "T10Y2Y": "10y minus 2y Treasury spread (daily)",
    "T10Y3M": "10y minus 3m Treasury spread (daily)",
    "DGS10": "10y Treasury yield (daily)",
    "DGS2": "2y Treasury yield (daily)",
    "DGS3MO": "3m Treasury yield (daily)",
    "BAA10Y": "Moody's Baa corporate minus 10y Treasury (daily)",
    "VIXCLS": "CBOE VIX (daily)",
    "T10YIE": "10y breakeven inflation (daily, from 2003)",
    "CPIAUCNS": "CPI all items, not seasonally adjusted (monthly)",
    "UNRATE": "Unemployment rate (monthly)",
    "GDPC1": "Real GDP (quarterly)",
    "INDPRO": "Industrial production (monthly)",
    "USREC": "NBER recession indicator (monthly, descriptive only)",
}


def fetch(series_id: str, retries: int = 4) -> pd.Series:
    """Uses the FRED API if FRED_API_KEY is set (free key: https://fred.stlouisfed.org/docs/api/api_key.html,
    put it in your local .env, never commit it); otherwise the public CSV endpoint. Retries with backoff."""
    import time
    import requests
    key = os.getenv("FRED_API_KEY")
    last = None
    for attempt in range(retries):
        try:
            if key:
                r = requests.get("https://api.stlouisfed.org/fred/series/observations",
                                 params={"series_id": series_id, "api_key": key, "file_type": "json"}, timeout=90)
                r.raise_for_status()
                obs = r.json()["observations"]
                return pd.Series(pd.to_numeric([o["value"] for o in obs], errors="coerce"),
                                 index=pd.to_datetime([o["date"] for o in obs]), name=series_id).dropna()
            r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}",
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=90)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            return pd.Series(pd.to_numeric(df.iloc[:, 1], errors="coerce").values,
                             index=pd.to_datetime(df.iloc[:, 0]), name=series_id).dropna()
        except Exception as e:      # noqa: BLE001
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(last)


frames = {}
for sid, desc in SERIES.items():
    try:
        s = fetch(sid)
        frames[sid] = s
        print(f"{sid:9s} {s.index[0].date()} -> {s.index[-1].date()}  n={len(s):6d}  {desc}")
    except Exception as e:
        print(f"{sid:9s} FAILED ({e})")

if not frames:
    raise SystemExit("No series downloaded; see the notes at the top of this file.")
out = os.path.join(ROOT, "data", "macro_fred.csv")
pd.concat(frames.values(), axis=1).sort_index().to_csv(out)
print(f"\nSaved {out}")
