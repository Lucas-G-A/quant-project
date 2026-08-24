import pandas as pd
from backtester.engine import Backtester
from strategies.pairs_trading import PairsTradingStrategy
from analysis.metrics import summarize_performance

prices = pd.read_csv("data/prices.csv", index_col=0, parse_dates=True)

strategy = PairsTradingStrategy(ticker_a="MA", ticker_b="V")
bt = Backtester(price_data=prices, strategy=strategy, starting_cash=100_000)
results = bt.run()

print(results.tail())
summary = summarize_performance(results["total_value"], label="Pairs Trading (MA-V)")
print(pd.Series(summary))
print(f"\nNumber of trade events: {strategy.trade_count}")
trade_df = pd.DataFrame(strategy.trade_log)
print(trade_df)
print("\nAverage holding period (days):", 
      (pd.to_datetime(trade_df["exit_date"]) - pd.to_datetime(trade_df["entry_date"])).dt.days.mean())
print("Average |entry z|:", trade_df["entry_z"].abs().mean())