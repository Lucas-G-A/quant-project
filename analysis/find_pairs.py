import pandas as pd
import itertools
from statsmodels.tsa.stattools import coint

def find_cointegrated_pairs(prices: pd.DataFrame, significance: float = 0.05):
    """
    Tests every pair of tickers for cointegration using the Engle-Granger test.
    Returns a list of (ticker1, ticker2, p_value) sorted by strength of cointegration.

    NOTE: this tests the FULL price history at once, purely for pair DISCOVERY.
    This is fine here because we're just selecting candidate pairs to trade —
    the actual trading decisions later will only ever use data up to "today,"
    same as momentum. Worth understanding this distinction: discovering pairs 
    can use the full sample, but TRADING them cannot peek ahead.
    """
    tickers = prices.columns
    pairs_found = []

    for ticker1, ticker2 in itertools.combinations(tickers, 2):
        series1 = prices[ticker1].dropna()
        series2 = prices[ticker2].dropna()

        # Align dates
        combined = pd.concat([series1, series2], axis=1, join="inner")
        if len(combined) < 250:  # need reasonable history
            continue

        score, p_value, _ = coint(combined.iloc[:, 0], combined.iloc[:, 1])

        if p_value < significance:
            pairs_found.append((ticker1, ticker2, p_value))

    pairs_found.sort(key=lambda x: x[2])  # lowest p-value = strongest cointegration
    return pairs_found

if __name__ == "__main__":
    prices = pd.read_csv("data/prices.csv", index_col=0, parse_dates=True)
    pairs = find_cointegrated_pairs(prices)
    print(f"Found {len(pairs)} cointegrated pairs (p < 0.05)")
    for t1, t2, p in pairs[:20]:
        print(f"{t1} - {t2}: p-value = {p:.4f}")