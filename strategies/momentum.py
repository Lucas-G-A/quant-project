import pandas as pd
from backtester.strategy import Strategy

class MomentumStrategy(Strategy):
    def __init__(self, lookback_days=126, top_n=3, target_total_weight=0.95):
        """
        lookback_days: how far back to measure "recent performance" (126 trading days ≈ 6 months)
        top_n: how many stocks to hold at once
        target_total_weight: fraction of portfolio to keep invested (e.g. 0.95 = keep 5% cash buffer)
        """
        self.lookback_days = lookback_days
        self.top_n = top_n
        self.target_total_weight = target_total_weight
        self.last_rebalance_month = None

    def _is_rebalance_day(self, date):
        # Rebalance on the first trading day we see in a new month
        current_month = (date.year, date.month)
        if current_month != self.last_rebalance_month:
            self.last_rebalance_month = current_month
            return True
        return False

    def decide(self, date, price_history, portfolio):
        # Not enough history yet to compute lookback returns — do nothing
        if len(price_history) < self.lookback_days + 1:
            return []

        if not self._is_rebalance_day(date):
            return []

        # Rank tickers by return over the lookback window
        past_prices = price_history.iloc[-self.lookback_days - 1]
        current_prices = price_history.iloc[-1]
        lookback_returns = (current_prices / past_prices) - 1
        ranked = lookback_returns.sort_values(ascending=False)
        selected = ranked.index[: self.top_n].tolist()

        prices_today = current_prices.to_dict()
        total_value = portfolio.total_value(prices_today)
        weight_per_position = self.target_total_weight / self.top_n

        trades = []

        # Sell anything we hold that's no longer in the selected list
        for ticker in list(portfolio.positions.keys()):
            if ticker not in selected:
                trades.append({"ticker": ticker, "shares": portfolio.positions[ticker], "side": "sell"})

        # Buy/adjust into the selected list
        for ticker in selected:
            target_dollars = total_value * weight_per_position
            target_shares = target_dollars / prices_today[ticker]
            current_shares = portfolio.positions.get(ticker, 0)
            diff = target_shares - current_shares

            if diff > 0:
                trades.append({"ticker": ticker, "shares": diff, "side": "buy"})
            elif diff < 0:
                trades.append({"ticker": ticker, "shares": abs(diff), "side": "sell"})

        return trades