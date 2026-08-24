import pandas as pd
import numpy as np
from backtester.strategy import Strategy

class PairsTradingStrategy(Strategy):
    def __init__(self, ticker_a: str, ticker_b: str,
                 hedge_lookback=252, recalc_every=63,
                 zscore_window=63, entry_z=2.0, exit_z=0.5,
                 target_gross_exposure=0.90):
        """
        ticker_a, ticker_b: the pair to trade
        hedge_lookback: window (days) used to estimate the hedge ratio via regression
        recalc_every: how often (days) to recompute the hedge ratio
        zscore_window: window (days) used to compute the rolling mean/std of the spread
        entry_z: enter a trade when |z-score| exceeds this
        exit_z: close the trade when |z-score| falls back below this (not necessarily 0 — 
                 exiting a bit before dead-center avoids "flickering" trades near the mean)
        target_gross_exposure: total capital committed to the pair (long + short combined)
        """
        self.ticker_a = ticker_a
        self.ticker_b = ticker_b
        self.hedge_lookback = hedge_lookback
        self.recalc_every = recalc_every
        self.zscore_window = zscore_window
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.target_gross_exposure = target_gross_exposure

        self.hedge_ratio = None
        self.days_since_recalc = 0
        self.in_position = False
        self.position_direction = None  # "long_a_short_b" or "short_a_long_b"
        self.trade_count = 0
        self.trade_log = []  # will store dicts: entry_z, exit_z, entry_date, exit_date, direction
        self._current_trade = None

    def _estimate_hedge_ratio(self, price_history):
        window = price_history[[self.ticker_a, self.ticker_b]].iloc[-self.hedge_lookback:]
        a = window[self.ticker_a].values
        b = window[self.ticker_b].values
        # Simple linear regression: a = hedge_ratio * b + intercept
        hedge_ratio, intercept = np.polyfit(b, a, 1)
        return hedge_ratio

    def _compute_zscore(self, price_history):
        window = price_history[[self.ticker_a, self.ticker_b]].iloc[-self.zscore_window:]
        spread = window[self.ticker_a] - self.hedge_ratio * window[self.ticker_b]
        current_spread = spread.iloc[-1]
        mean = spread.mean()
        std = spread.std()
        if std == 0:
            return 0.0
        return (current_spread - mean) / std

    def decide(self, date, price_history, portfolio):
        min_required = max(self.hedge_lookback, self.zscore_window) + 1
        if len(price_history) < min_required:
            return []

        # Recalculate hedge ratio periodically (or on the very first valid day)
        if not self.in_position:
            if self.hedge_ratio is None or self.days_since_recalc >= self.recalc_every:
                self.hedge_ratio = self._estimate_hedge_ratio(price_history)
                self.days_since_recalc = 0
            self.days_since_recalc += 1

        z = self._compute_zscore(price_history)
        current_prices = price_history.iloc[-1].to_dict()
        total_value = portfolio.total_value(current_prices)
        trades = []

        # --- Exit logic: close position if z-score has reverted ---
        if self.in_position and abs(z) < self.exit_z:
            shares_a = portfolio.positions.get(self.ticker_a, 0)
            shares_b = portfolio.positions.get(self.ticker_b, 0)
            if shares_a > 0:
                trades.append({"ticker": self.ticker_a, "shares": shares_a, "side": "sell"})
            elif shares_a < 0:
                trades.append({"ticker": self.ticker_a, "shares": abs(shares_a), "side": "buy"})
            if shares_b > 0:
                trades.append({"ticker": self.ticker_b, "shares": shares_b, "side": "sell"})
            elif shares_b < 0:
                trades.append({"ticker": self.ticker_b, "shares": abs(shares_b), "side": "buy"})
            self.in_position = False
            self.position_direction = None
            if self._current_trade:
                self._current_trade["exit_date"] = date
                self._current_trade["exit_z"] = z
                self.trade_log.append(self._current_trade)
                self._current_trade = None
            if trades:
                self.trade_count += 1
            return trades

        # --- Entry logic: open a position if z-score crosses threshold ---
        if not self.in_position:
            dollars_per_leg = (total_value * self.target_gross_exposure) / 2

            if z > self.entry_z:
                # Spread too wide: A is relatively expensive -> short A, long B
                shares_a = dollars_per_leg / current_prices[self.ticker_a]
                shares_b = dollars_per_leg / current_prices[self.ticker_b]
                trades.append({"ticker": self.ticker_a, "shares": shares_a, "side": "sell"})  # short
                trades.append({"ticker": self.ticker_b, "shares": shares_b, "side": "buy"})   # long
                self.in_position = True
                self.position_direction = "short_a_long_b"
                self._current_trade = {"entry_date": date, "entry_z": z, "direction": self.position_direction}

            elif z < -self.entry_z:
                # Spread too narrow: A is relatively cheap -> long A, short B
                shares_a = dollars_per_leg / current_prices[self.ticker_a]
                shares_b = dollars_per_leg / current_prices[self.ticker_b]
                trades.append({"ticker": self.ticker_a, "shares": shares_a, "side": "buy"})   # long
                trades.append({"ticker": self.ticker_b, "shares": shares_b, "side": "sell"})  # short
                self.in_position = True
                self.position_direction = "long_a_short_b"
                self._current_trade = {"entry_date": date, "entry_z": z, "direction": self.position_direction}

        if trades:
            self.trade_count += 1
        return trades