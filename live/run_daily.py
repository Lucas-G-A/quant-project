import os
import json
import pandas as pd
from datetime import datetime
from live.alpaca_client import submit_order, get_recent_bars
from live.shadow_portfolio import ShadowPortfolio
from live.strategy_state import save_strategy_state, load_strategy_state
from strategies.momentum import MomentumStrategy
from strategies.pairs_trading import PairsTradingStrategy
from data.fetch_data import SP500_SAMPLE

def to_alpaca_format(ticker: str) -> str:
    return ticker.replace("-", ".")

MOMENTUM_UNIVERSE = [to_alpaca_format(t) for t in SP500_SAMPLE]
PAIRS_TICKERS = ["MA", "V"]

def _execute_and_log(name, decisions, price_history, portfolio):
    current_prices = price_history.iloc[-1].to_dict()
    for trade in decisions:
        ticker, shares, side = trade["ticker"], trade["shares"], trade["side"]
        price = current_prices[ticker]
        submit_order(ticker, shares, side)
        portfolio.execute_trade(ticker, shares, price, side)
        print(f"[{name}] {side.upper()} {shares:.2f} {ticker} @ ~{price:.2f}")

    value = portfolio.total_value(current_prices)
    print(f"[{name}] Portfolio value: {value:.2f}")

    # Append to running history log, used by the dashboard later
    log_path = f"live/state/{name}_history.csv"
    row = pd.DataFrame([{"date": price_history.index[-1], "total_value": value}])
    if os.path.exists(log_path):
        row.to_csv(log_path, mode="a", header=False, index=False)
    else:
        row.to_csv(log_path, mode="w", header=True, index=False)

def run_momentum():
    name = "momentum"
    portfolio = ShadowPortfolio(name, starting_cash=50_000)
    strategy = MomentumStrategy(lookback_days=252, skip_days=21, top_pct=0.15, weighting="momentum_score")

    saved = load_strategy_state(name)
    if saved.get("last_rebalance_month") is not None:
        strategy.last_rebalance_month = tuple(saved["last_rebalance_month"])

    bars = get_recent_bars(MOMENTUM_UNIVERSE, lookback_days=280)
    price_history = bars["close"].unstack(level=0)
    print(f"Tickers requested: {len(MOMENTUM_UNIVERSE)} | Tickers received: {price_history.shape[1]}")

    date = price_history.index[-1]
    decisions = strategy.decide(date, price_history, portfolio)
    _execute_and_log(name, decisions, price_history, portfolio)

    save_strategy_state(name, {
        "last_rebalance_month": list(strategy.last_rebalance_month) if strategy.last_rebalance_month else None
    })

def run_pairs():
    name = "pairs"
    portfolio = ShadowPortfolio(name, starting_cash=50_000)
    strategy = PairsTradingStrategy(ticker_a="MA", ticker_b="V")

    saved = load_strategy_state(name)
    strategy.hedge_ratio = saved.get("hedge_ratio")
    strategy.days_since_recalc = saved.get("days_since_recalc", 0)
    strategy.in_position = saved.get("in_position", False)
    strategy.position_direction = saved.get("position_direction")

    bars = get_recent_bars(PAIRS_TICKERS, lookback_days=270)
    price_history = bars["close"].unstack(level=0)

    date = price_history.index[-1]
    decisions = strategy.decide(date, price_history, portfolio)
    _execute_and_log(name, decisions, price_history, portfolio)

    save_strategy_state(name, {
        "hedge_ratio": strategy.hedge_ratio,
        "days_since_recalc": strategy.days_since_recalc,
        "in_position": strategy.in_position,
        "position_direction": strategy.position_direction,
    })

if __name__ == "__main__":
    run_momentum()
    run_pairs()

    with open("live/state/last_successful_run.json", "w") as f:
        json.dump({"timestamp": datetime.now().isoformat()}, f)
    print("Heartbeat updated.")