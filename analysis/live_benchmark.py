"""
Compares the LIVE momentum sleeve against benchmarks over the same dates:
  - SPY (buy & hold)
  - equal-weight buy & hold of the whole 100-stock universe
  - equal-weight semiconductor basket (the sector the live book is concentrated in)

Run on your Mac, from the project root, inside the venv (needs your Alpaca keys in .env):
    python analysis/live_benchmark.py
Read-only: it only downloads price bars. It places no orders and writes only
analysis/output/live_vs_benchmarks.csv.
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd

SEMIS = ["AMD", "AMAT", "ADI", "LRCX", "MU", "NVDA", "AVGO", "QCOM", "TXN"]


def to_naive_date_index(idx):
    return pd.DatetimeIndex(pd.to_datetime(idx, utc=True)).tz_localize(None).normalize()


def load_sleeve(path):
    df = pd.read_csv(path)
    s = pd.Series(df["total_value"].values, index=to_naive_date_index(df["date"]))
    return s[~s.index.duplicated(keep="last")].sort_index()      # manual re-runs create duplicate days


def compare(sleeve: pd.Series, closes: pd.DataFrame, universe: list) -> pd.DataFrame:
    """All series are rebased to 100 at the sleeve's first date (using that day's close)."""
    closes = closes.reindex(sleeve.index).ffill()
    base = closes.iloc[0]
    out = pd.DataFrame(index=sleeve.index)
    out["Momentum sleeve"] = sleeve / sleeve.iloc[0] * 100
    out["SPY"] = closes["SPY"] / base["SPY"] * 100
    uni = [t for t in universe if t in closes.columns and pd.notna(base[t])]
    out["Equal-weight universe"] = (closes[uni] / base[uni]).mean(axis=1) * 100
    semis = [t for t in SEMIS if t in closes.columns and pd.notna(base[t])]
    out["Semis basket"] = (closes[semis] / base[semis]).mean(axis=1) * 100
    return out


def main():
    from live.alpaca_client import get_recent_bars          # imported here so tests don't need alpaca
    src = open(os.path.join(ROOT, "data", "fetch_data.py")).read()
    universe_yf = next(ast.literal_eval(n.value) for n in ast.parse(src).body
                       if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "SP500_SAMPLE")
    universe = [t.replace("-", ".") for t in universe_yf]       # Alpaca symbol format

    sleeve = load_sleeve(os.path.join(ROOT, "live", "state", "momentum_history.csv"))
    span_days = (pd.Timestamp.today().normalize() - sleeve.index[0]).days
    bars = get_recent_bars(["SPY"] + universe, lookback_days=max(30, int(span_days / 1.6) + 10))
    closes = bars["close"].unstack(level=0)
    closes.index = to_naive_date_index(closes.index)
    closes = closes[~closes.index.duplicated(keep="last")]

    table = compare(sleeve, closes, universe)
    table.to_csv(os.path.join(ROOT, "analysis", "output", "live_vs_benchmarks.csv"))

    print(f"Window: {table.index[0].date()} -> {table.index[-1].date()}  (rebased to 100)\n")
    print(table.round(1).to_string())
    last = table.iloc[-1] - 100
    print("\nTotal return over the window:")
    for k, v in last.items():
        print(f"  {k:24s}{v:8.1f}%")
    peak_day = table["Momentum sleeve"].idxmax()
    after = table.loc[peak_day:]
    print(f"\nSince the sleeve's peak ({peak_day.date()}):")
    for k in table.columns:
        print(f"  {k:24s}{(after[k].iloc[-1] / after[k].iloc[0] - 1) * 100:8.1f}%")


if __name__ == "__main__":
    main()
