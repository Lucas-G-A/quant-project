import pandas as pd
import numpy as np
from backtester.strategy import Strategy


class MomentumStrategy(Strategy):
    def __init__(self, lookback_days=252, skip_days=21, top_pct=0.15,
                 target_total_weight=0.90, vol_lookback=63, weighting="inverse_vol",
                 max_position_weight=None, max_sector_weight=None, sector_map=None,
                 drawdown_trigger=None, drawdown_scale=0.5, drawdown_reentry=0.05):
        """
        weighting: "inverse_vol" | "equal" | "momentum_score"

        Risk controls (all OFF by default, so default behavior is unchanged):
        max_position_weight: cap on any single stock, as a fraction of portfolio value.
        max_sector_weight:   cap on total weight in one sector (requires sector_map).
        sector_map:          dict of ticker -> sector name (see data/sectors.py).
        drawdown_trigger:    if the portfolio falls this far below its peak value (e.g. 0.10),
                             scale target exposure down by drawdown_scale. Checked every day.
        drawdown_scale:      fraction of normal exposure held while de-risked.
        drawdown_reentry:    return to full exposure once within this distance of the peak.
        """
        self.lookback_days = lookback_days
        self.skip_days = skip_days
        self.top_pct = top_pct
        self.target_total_weight = target_total_weight
        self.vol_lookback = vol_lookback
        self.weighting = weighting
        self.last_rebalance_month = None

        if max_sector_weight is not None and sector_map is None:
            raise ValueError("max_sector_weight requires a sector_map")
        if drawdown_trigger is not None:
            if not 0 < drawdown_trigger < 1:
                raise ValueError("drawdown_trigger must be between 0 and 1")
            if drawdown_reentry >= drawdown_trigger:
                raise ValueError("drawdown_reentry must be smaller than drawdown_trigger")

        self.max_position_weight = max_position_weight
        self.max_sector_weight = max_sector_weight
        self.sector_map = {self._norm(k): v for k, v in (sector_map or {}).items()}
        self.drawdown_trigger = drawdown_trigger
        self.drawdown_scale = drawdown_scale
        self.drawdown_reentry = drawdown_reentry

        # Drawdown-rule state (NOTE: not persisted by the live runner; see README before deploying)
        self.peak_value = None
        self.de_risked = False
        self.base_weights = None   # weights chosen at the last monthly rebalance (after caps)
        self.derisk_days = 0       # instrumentation: days spent de-risked
        self.derisk_events = 0     # instrumentation: number of times the rule triggered

    @staticmethod
    def _norm(ticker):
        return ticker.replace(".", "-")

    def _sector(self, ticker):
        # Unmapped tickers get their own unique "sector" so they are never lumped together
        return self.sector_map.get(self._norm(ticker), ticker)

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

    def _apply_caps(self, weights):
        """
        Enforces the position and sector caps by iterative water-filling: clip/scale down
        anything over a cap, then hand the freed weight to names that still have room
        (proportional to their current weight). If no name has room, the leftover stays in cash.
        """
        pos_cap, sec_cap = self.max_position_weight, self.max_sector_weight
        if pos_cap is None and sec_cap is None:
            return weights

        w = weights.astype(float).copy()
        target = w.sum()
        sectors = pd.Series({t: self._sector(t) for t in w.index})

        for _ in range(100):
            if pos_cap is not None:
                w = w.clip(upper=pos_cap)
            if sec_cap is not None:
                sec_total = w.groupby(sectors).transform("sum")
                w = w * (sec_cap / sec_total).clip(upper=1.0)

            leftover = target - w.sum()
            if leftover <= 1e-9:
                break

            room = pd.Series(np.inf, index=w.index)
            if pos_cap is not None:
                room = np.minimum(room, pos_cap - w)
            if sec_cap is not None:
                sec_total = w.groupby(sectors).transform("sum")
                room = np.minimum(room, (sec_cap - sec_total).clip(lower=0))
            room = room.clip(lower=0)

            eligible = room > 1e-9
            if not eligible.any():
                break
            add = (w[eligible] / w[eligible].sum()) * leftover
            add = np.minimum(add, room[eligible])
            if add.sum() < 1e-12:
                break
            w[eligible] = w[eligible] + add

        return w

    def _update_drawdown_state(self, total_value):
        """Updates peak/de-risk state. Returns True if the state flipped today."""
        if self.peak_value is None or total_value > self.peak_value:
            self.peak_value = total_value
        drawdown = 1 - total_value / self.peak_value

        flipped = False
        if not self.de_risked and drawdown >= self.drawdown_trigger:
            self.de_risked = True
            self.derisk_events += 1
            flipped = True
        elif self.de_risked and drawdown <= self.drawdown_reentry:
            self.de_risked = False
            flipped = True

        if self.de_risked:
            self.derisk_days += 1
        return flipped

    def _trades_to_targets(self, targets, current_prices, total_value, portfolio):
        selected = list(targets.index)
        trades = []

        for ticker in list(portfolio.positions.keys()):
            if ticker not in selected:
                trades.append({"ticker": ticker, "shares": portfolio.positions[ticker], "side": "sell"})

        for ticker in selected:
            target_dollars = total_value * targets[ticker]
            target_shares = target_dollars / current_prices[ticker]
            current_shares = portfolio.positions.get(ticker, 0)
            diff = target_shares - current_shares

            # No-trade band: skip adjustments smaller than 0.5% of portfolio value
            if abs(diff * current_prices[ticker]) < total_value * 0.005:
                continue

            if diff > 0:
                trades.append({"ticker": ticker, "shares": diff, "side": "buy"})
            elif diff < 0:
                trades.append({"ticker": ticker, "shares": abs(diff), "side": "sell"})

        return trades

    def decide(self, date, price_history, portfolio):
        min_required = self.lookback_days + self.skip_days + 1
        if len(price_history) < min_required:
            return []

        current_prices = price_history.iloc[-1].to_dict()
        total_value = portfolio.total_value(current_prices)

        # Drawdown rule is checked every day, not just on rebalance days
        flipped = False
        if self.drawdown_trigger is not None:
            flipped = self._update_drawdown_state(total_value)

        is_rebalance = self._is_rebalance_day(date)
        if not is_rebalance and not flipped:
            return []

        if is_rebalance:
            price_start = price_history.iloc[-(self.lookback_days + self.skip_days + 1)]
            price_end = price_history.iloc[-(self.skip_days + 1)]
            momentum_score = ((price_end / price_start) - 1).dropna()

            n_holdings = max(1, int(len(momentum_score) * self.top_pct))
            selected = momentum_score.sort_values(ascending=False).index[:n_holdings].tolist()

            weights = self._compute_weights(selected, momentum_score, price_history)
            weights = self._apply_caps(weights)
            self.base_weights = weights
        else:
            # Non-rebalance day where only the de-risk state changed: rescale existing book
            if self.base_weights is None:
                return []
            weights = self.base_weights

        scale = self.drawdown_scale if self.de_risked else 1.0
        return self._trades_to_targets(weights * scale, current_prices, total_value, portfolio)
