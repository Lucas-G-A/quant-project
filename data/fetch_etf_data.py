"""
Downloads adjusted daily closes (dividends reinvested) for the ETF research universe.
Run from the project root inside the venv:   python data/fetch_etf_data.py
Writes data/prices_etf.csv and prints each ETF's first available date.
"""
import os
import pandas as pd
import yfinance as yf

ETF_UNIVERSE = {
    "US sectors": ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"],
    "US size/style": ["SPY", "QQQ", "IWM", "MDY", "IWD", "IWF"],
    "International": ["EFA", "EEM", "EWJ", "EWZ", "EWW", "EWG", "EWU", "EWC", "EWA", "FXI", "EWY"],
    "Bonds": ["TLT", "IEF", "SHY", "LQD", "AGG", "TIP", "HYG"],
    "Real assets": ["GLD", "SLV", "DBC", "USO", "VNQ"],
}
TICKERS = [t for group in ETF_UNIVERSE.values() for t in group]
START = "2004-01-01"


def main():
    print(f"Downloading {len(TICKERS)} ETFs from {START}...")
    data = yf.download(TICKERS, start=START, auto_adjust=True, progress=False)["Close"]
    data = data[TICKERS].dropna(how="all")
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "prices_etf.csv")
    data.to_csv(out)

    print(f"\nSaved {out}")
    print(f"Shape: {data.shape} | {data.index[0].date()} -> {data.index[-1].date()}\n")
    print(f"{'ETF':6s} {'first date':12s} {'missing days after start':>26s}")
    for t in TICKERS:
        s = data[t]
        first = s.first_valid_index()
        if first is None:
            print(f"{t:6s} NO DATA")
            continue
        print(f"{t:6s} {first.date()!s:12s} {int(s.loc[first:].isna().sum()):>26d}")


if __name__ == "__main__":
    main()
