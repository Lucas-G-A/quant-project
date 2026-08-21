import pandas as pd
import yfinance as yf

# Snapshot of ~100 large-cap S&P 500 tickers as of Aug 2026, spread across sectors
# (hardcoded intentionally for reproducibility — index membership changes over time)
SP500_SAMPLE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "AVGO", "JPM",
    "V", "MA", "UNH", "HD", "PG", "XOM", "JNJ", "COST", "ABBV", "MRK",
    "CVX", "BAC", "KO", "PEP", "WMT", "ADBE", "CRM", "ORCL", "AMD", "NFLX",
    "TMO", "ABT", "ACN", "MCD", "LIN", "CSCO", "DHR", "WFC", "TXN", "PM",
    "INTU", "AMGN", "IBM", "CAT", "GE", "NOW", "QCOM", "NEE", "UNP", "LOW",
    "ISRG", "AMAT", "SPGI", "BKNG", "HON", "DE", "GS", "BLK", "SYK", "MDT",
    "T", "ELV", "PLD", "ADI", "VRTX", "SCHW", "MU", "LRCX", "ADP", "GILD",
    "CB", "PANW", "MDLZ", "REGN", "CI", "SO", "BSX", "ZTS", "MMC", "TJX",
    "FI", "DUK", "PGR", "SLB", "ETN", "AON", "CME", "USB", "APD", "EQIX",
    "ITW", "WM", "PYPL", "CSX", "FDX", "MO", "NOC", "EOG", "HUM", "SHW",
]

def fetch_prices(tickers, start="2015-01-01", end="2024-12-31"):
    data = yf.download(tickers, start=start, end=end)["Close"]
    # Drop any tickers with too much missing data (delisted mid-period, IPO'd late, etc.)
    data = data.dropna(axis=1, thresh=int(len(data) * 0.95))
    return data

if __name__ == "__main__":
    tickers = SP500_SAMPLE
    print(f"Pulling {len(tickers)} tickers...")
    prices = fetch_prices(tickers)
    print(f"Kept {prices.shape[1]} tickers after dropping incomplete ones")
    prices.to_csv("data/prices.csv")
    print(prices.shape)