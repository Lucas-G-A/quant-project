import os
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

def get_recent_bars(tickers: list, lookback_days: int):
    # Pull extra calendar days to comfortably cover lookback_days worth of
    # TRADING days (weekends/holidays mean calendar days > trading days needed)
    start = datetime.now() - timedelta(days=int(lookback_days * 1.6))

    request = StockBarsRequest(
        symbol_or_symbols=tickers,
        timeframe=TimeFrame.Day,
        start=start
    )
    bars = data_client.get_stock_bars(request)
    return bars.df