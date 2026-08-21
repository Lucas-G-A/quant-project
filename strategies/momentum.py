import pandas as pd
import numpy as np
from backtester.strategy import Strategy

class MomentumStrategy(Strategy):
    def __init__(self, lookback_days=252, skip_days=21, top_pct=0.15,
                 target_total_weight=0.90, vol_lookback=63, weighting="inverse_vol"):
        """
        weighting: "inverse_vol" | "equal" | "momentum_score"
        """
        self.lookback_days = lookback_days
        self.skip_days = skip_days
        self.top_pct = top_pct
        self.target_total_weight = target_total_weight
        self.vol_lookback = vol_lookback
        self.weighting = weighting
        self.last_rebalance_month = None

    def _is_rebalance_day(self, date):
        current_month = (date.year, date.month)
        if current_month != self.last_rebalance_month:
            self.last_rebalance_month = current_month
            return True
        return False

    def _compute_weights(self, selected, momentum_score, price_history):
        if self.weighting == "equal":
            w = pd.Series(1.0, index=selected)
            return (w / w.sum()) * self.target_total_weight

        elif self.weighting == "inverse_vol":
            recent_returns = price_history[selected].pct_change().iloc[-self.vol_lookback:]
            volatility = recent_returns.std()
            inv_vol = 1 / volatility
            return (inv_vol / inv_vol.sum()) * self.target_total_weight

        elif self.weighting == "momentum_score":
            # Weight proportional to how strong the momentum signal is (must be positive)
            scores = momentum_score[selected].clip(lower=0.0001)  # guard against negative/zero
            return (scores / scores.sum()) * self.target_total_weight

        else:
            raise ValueError(f"Unknown weighting scheme: {self.weighting}")

    def decide(self, date, price_history, portfolio):
        min_required = self.lookback_days + self.skip_days + 1
        if len(price_history) < min_required:
            return []

        if not self._is_rebalance_day(date):
            return []

        price_start = price_history.iloc[-(self.lookback_days + self.skip_days + 1)]
        price_end = price_history.iloc[-(self.skip_days + 1)]
        momentum_score = ((price_end / price_start) - 1).dropna()

        n_holdings = max(1, int(len(momentum_score) * self.top_pct))
        selected = momentum_score.sort_values(ascending=False).index[:n_holdings].tolist()

        weights = self._compute_weights(selected, momentum_score, price_history)

        current_prices = price_history.iloc[-1].to_dict()
        total_value = portfolio.total_value(current_prices)

        trades = []

        for ticker in list(portfolio.positions.keys()):
            if ticker not in selected:
                trades.append({"ticker": ticker, "shares": portfolio.positions[ticker], "side": "sell"})

        for ticker in selected:
            target_dollars = total_value * weights[ticker]
            target_shares = target_dollars / current_prices[ticker]
            current_shares = portfolio.positions.get(ticker, 0)
            diff = target_shares - current_shares

            if abs(diff * current_prices[ticker]) < total_value * 0.005:
                continue

            if diff > 0:
                trades.append({"ticker": ticker, "shares": diff, "side": "buy"})
            elif diff < 0:
                trades.append({"ticker": ticker, "shares": abs(diff), "side": "sell"})

        return trades