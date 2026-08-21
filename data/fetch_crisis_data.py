# data/fetch_crisis_data.py
import pandas as pd
from fetch_data import SP500_SAMPLE, fetch_prices  # reuse the same ticker list + function

if __name__ == "__main__":
    print(f"Pulling {len(SP500_SAMPLE)} tickers for 2007-2012...")
    prices = fetch_prices(SP500_SAMPLE, start="2007-01-01", end="2012-12-31")
    print(f"Kept {prices.shape[1]} tickers after dropping incomplete ones")
    prices.to_csv("data/prices_crisis.csv")
    print(prices.shape)