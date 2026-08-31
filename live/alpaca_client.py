# live/alpaca_client.py
import os
import time
import pandas as pd
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta

load_dotenv()

trading_client = TradingClient(
    os.getenv("ALPACA_API_KEY"),
    os.getenv("ALPACA_SECRET_KEY"),
    paper=True
)
data_client = StockHistoricalDataClient(
    os.getenv("ALPACA_API_KEY"),
    os.getenv("ALPACA_SECRET_KEY")
)

def submit_order(ticker: str, shares: float, side: str):
    order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
    order = MarketOrderRequest(
        symbol=ticker,
        qty=round(shares, 4),
        side=order_side,
        time_in_force=TimeInForce.DAY
    )
    return trading_client.submit_order(order)

def get_recent_bars(tickers: list, lookback_days: int, batch_size: int = 20, max_retries: int = 3):
    start = datetime.now() - timedelta(days=int(lookback_days * 1.6))
    all_bars = []

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]

        for attempt in range(max_retries):
            try:
                request = StockBarsRequest(
                    symbol_or_symbols=batch,
                    timeframe=TimeFrame.Day,
                    start=start
                )
                bars = data_client.get_stock_bars(request)
                all_bars.append(bars.df)
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"Batch {i}-{i+batch_size} failed (attempt {attempt+1}), retrying...")
                    time.sleep(2)
                else:
                    print(f"Batch {i}-{i+batch_size} failed after {max_retries} attempts: {e}")
                    raise

    return pd.concat(all_bars)