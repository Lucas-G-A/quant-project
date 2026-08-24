# live/shadow_portfolio.py
import json
import os

class ShadowPortfolio:
    """
    Mirrors backtester.Portfolio's interface (positions dict, total_value method)
    so existing Strategy.decide() code works unmodified — but persists to disk
    between runs, since live trading happens across many separate script executions.
    """
    def __init__(self, name: str, starting_cash: float, state_dir="live/state"):
        self.name = name
        self.state_path = os.path.join(state_dir, f"{name}.json")
        os.makedirs(state_dir, exist_ok=True)

        if os.path.exists(self.state_path):
            with open(self.state_path) as f:
                state = json.load(f)
            self.cash = state["cash"]
            self.positions = state["positions"]
        else:
            self.cash = starting_cash
            self.positions = {}
            self._save()

    def total_value(self, prices_today: dict) -> float:
        positions_value = sum(
            shares * prices_today[ticker]
            for ticker, shares in self.positions.items()
            if ticker in prices_today
        )
        return self.cash + positions_value

    def execute_trade(self, ticker, shares, price, side, commission_pct=0.001, slippage_pct=0.0005):
        # Same accounting logic as the backtester's Portfolio, kept consistent
        # so shadow P&L stays comparable to backtest expectations.
        exec_price = price * (1 + slippage_pct) if side == "buy" else price * (1 - slippage_pct)
        trade_value = shares * exec_price
        commission = trade_value * commission_pct

        if side == "buy":
            self.cash -= (trade_value + commission)
            self.positions[ticker] = self.positions.get(ticker, 0) + shares
        else:
            self.cash += (trade_value - commission)
            self.positions[ticker] = self.positions.get(ticker, 0) - shares
            if abs(self.positions[ticker]) < 1e-6:
                del self.positions[ticker]

        self._save()

    def _save(self):
        with open(self.state_path, "w") as f:
            json.dump({"cash": self.cash, "positions": self.positions}, f, indent=2)