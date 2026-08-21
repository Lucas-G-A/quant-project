import pandas as pd
from backtester.engine import Backtester
from strategies.momentum import MomentumStrategy
from analysis.metrics import summarize_performance

prices = pd.read_csv("data/prices.csv", index_col=0, parse_dates=True)

results_summary = []

for scheme in ["inverse_vol", "equal", "momentum_score"]:
    strategy = MomentumStrategy(lookback_days=252, skip_days=21, top_pct=0.15,
                                 target_total_weight=0.90, weighting=scheme)
    bt = Backtester(price_data=prices, strategy=strategy, starting_cash=100_000)
    results = bt.run()
    results_summary.append(summarize_performance(results["total_value"], label=f"Momentum ({scheme})"))

# Benchmark
initial_prices = prices.iloc[0]
shares_per_ticker = (100_000 / len(prices.columns)) / initial_prices
benchmark_value = (prices * shares_per_ticker).sum(axis=1)
results_summary.append(summarize_performance(benchmark_value, label="Buy & Hold (equal-weight)"))

comparison = pd.DataFrame(results_summary).set_index("label")
print(comparison)