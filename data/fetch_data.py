import yfinance as yf
import pandas as pd

TICKERS = ["AAPL", "MSFT", "JPM", "KO", "PEP", "XOM", "JNJ", "PG", "V", "WMT"]

def fetch_prices(tickers, start="2018-01-01", end="2024-12-31"):
    data = yf.download(tickers, start=start, end=end)["Close"]
    return data

if __name__ == "__main__":
    prices = fetch_prices(TICKERS)
    prices.to_csv("data/prices.csv")
    print(prices.head())
    print(prices.tail())
    print(prices.shape)
    print(prices.isna().sum())