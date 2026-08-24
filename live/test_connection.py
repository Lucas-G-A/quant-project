# live/test_connection.py
from live.alpaca_client import trading_client, get_recent_bars

def test_connection():
    account = trading_client.get_account()
    print("--- Account Info ---")
    print(f"Status: {account.status}")
    print(f"Cash: ${account.cash}")
    print(f"Buying power: ${account.buying_power}")
    print(f"Paper trading: {account.pattern_day_trader is not None}")

    print("\n--- Data API test ---")
    bars = get_recent_bars(["AAPL", "MSFT"], lookback_days=5)
    print(bars.tail())

if __name__ == "__main__":
    test_connection()