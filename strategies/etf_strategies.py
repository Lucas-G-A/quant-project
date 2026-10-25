"""
ETF momentum / trend strategies and benchmarks, built exactly to research/etf_momentum_protocol.md.

Shared rules (all strategies and benchmarks):
  - rebalance on the first trading day of each month;
  - signals use closes through the PRIOR day (signal_lag=1), trades execute at today's close;
  - SHY is the cash-parking asset and never part of the risky universe;
  - an ETF is eligible only once it has a full lookback window of its own history;
  - no trading before `earliest_trade_date` (so all configurations share one start date);
  - sells are issued before buys so the portfolio's cash check cannot reject a rebalance.
"""
import numpy as np
import pandas as pd

from backtester.strategy import Strategy

CASH = "SHY"


class ETFRebalancer(Strategy):
    def __init__(self, lookback=252, skip=21, target_total_weight=0.98, signal_lag=1,
                 earliest_trade_date=None, min_eligible=5, band=0.005, cash_ticker=CASH):
        self.lookback = lookback
        self.skip = skip
        self.target_total_weight = target_total_weight
        self.signal_lag = signal_lag
        self.earliest_trade_date = pd.Timestamp(earliest_trade_date) if earliest_trade_date is not None else None
        self.min_eligible = min_eligible
        self.band = band
        self.cash_ticker = cash_ticker

    # ---- gating shared by decide() and the start-date finder -------------------------------
    def _history(self, price_history):
        return price_history.iloc[:-1] if self.signal_lag == 1 else price_history

    def _scores(self, hist):
        """12-1 style score on history `hist`; NaN for ETFs without a full window."""
        need = self.lookback + self.skip + 1
        if len(hist) < need:
            return pd.Series(dtype=float)
        start = hist.iloc[-need]
        end = hist.iloc[-(self.skip + 1)]
        return (end / start - 1).drop(labels=[self.cash_ticker], errors="ignore")

    def rebalance_candidate(self, price_history):
        """True if today is a rebalance day AND the signal can be computed. Used by decide()
        and by the start-date finder so both apply identical rules."""
        if len(price_history) < 2:
            return False
        date = price_history.index[-1]
        if self.earliest_trade_date is not None and date < self.earliest_trade_date:
            return False
        if price_history.index[-2].month == date.month:      # not the first trading day of the month
            return False
        scores = self._scores(self._history(price_history)).dropna()
        today = price_history.iloc[-1]
        scores = scores[today.reindex(scores.index).notna()]  # must be tradable today
        return len(scores) >= self.min_eligible

    def _eligible_scores(self, price_history):
        scores = self._scores(self._history(price_history)).dropna()
        today = price_history.iloc[-1]
        return scores[today.reindex(scores.index).notna()]

    # ---- to be implemented per strategy: weights summing to 1.0 including the cash ticker --
    def target_weights(self, hist, scores) -> pd.Series:
        raise NotImplementedError

    def decide(self, date, price_history, portfolio):
        if not self.rebalance_candidate(price_history):
            return []
        hist = self._history(price_history)
        scores = self._eligible_scores(price_history)
        weights = self.target_weights(hist, scores) * self.target_total_weight
        return self._trades(weights, price_history.iloc[-1].to_dict(), portfolio)

    def _trades(self, targets, prices, portfolio):
        total_value = portfolio.total_value(prices)
        sells, buys = [], []
        for ticker in list(portfolio.positions):
            if ticker not in targets.index or targets[ticker] <= 0:
                sells.append({"ticker": ticker, "shares": portfolio.positions[ticker], "side": "sell"})
        for ticker, w in targets.items():
            if w <= 0:
                continue
            diff = w * total_value / prices[ticker] - portfolio.positions.get(ticker, 0)
            if abs(diff * prices[ticker]) < total_value * self.band:
                continue
            (buys if diff > 0 else sells).append(
                {"ticker": ticker, "shares": abs(diff), "side": "buy" if diff > 0 else "sell"})
        # Cash guard: sells run first, but slippage/commission on the buys can still exceed the cash on
        # hand. Scale all buys down proportionally so a rebalance is never rejected by the cash check.
        slip, comm = portfolio.slippage_pct, portfolio.commission_pct
        proceeds = sum(t["shares"] * prices[t["ticker"]] * (1 - slip) * (1 - comm) for t in sells)
        cost = sum(t["shares"] * prices[t["ticker"]] * (1 + slip) * (1 + comm) for t in buys)
        available = portfolio.cash + proceeds
        if cost > available > 0:
            factor = available / cost * 0.9999
            for t in buys:
                t["shares"] *= factor
        return sells + buys


def _with_cash(weights: pd.Series, cash_ticker=CASH) -> pd.Series:
    """Anything not allocated (failed trend slices) goes to the cash ticker."""
    w = weights.copy()
    w[cash_ticker] = w.get(cash_ticker, 0.0) + max(0.0, 1.0 - w.sum())
    return w


class CrossSectionalMomentum(ETFRebalancer):      # S1
    def __init__(self, top_k=5, **kw):
        super().__init__(**kw)
        self.top_k = top_k

    def target_weights(self, hist, scores):
        top = scores.sort_values(ascending=False).index[: self.top_k]
        return _with_cash(pd.Series(1.0 / self.top_k, index=top))


class TimeSeriesTrend(ETFRebalancer):             # S2
    def target_weights(self, hist, scores):
        slice_ = 1.0 / len(scores)                          # equal slice per eligible ETF
        held = scores[scores > 0].index
        return _with_cash(pd.Series(slice_, index=held))


class DualMomentum(ETFRebalancer):                # S3
    def __init__(self, top_k=5, **kw):
        super().__init__(**kw)
        self.top_k = top_k

    def target_weights(self, hist, scores):
        top = scores.sort_values(ascending=False).iloc[: self.top_k]
        held = top[top > 0].index
        return _with_cash(pd.Series(1.0 / self.top_k, index=held))


class RiskManagedDualMomentum(ETFRebalancer):     # S4
    def __init__(self, top_k=5, vol_lookback=63, **kw):
        super().__init__(**kw)
        self.top_k = top_k
        self.vol_lookback = vol_lookback

    def target_weights(self, hist, scores):
        top = scores.sort_values(ascending=False).iloc[: self.top_k]
        vol = hist[top.index].pct_change().iloc[-self.vol_lookback:].std()
        inv = (1.0 / vol.replace(0, np.nan)).fillna(0.0)
        w = inv / inv.sum() if inv.sum() > 0 else pd.Series(1.0 / len(top), index=top.index)
        return _with_cash(w[top[top > 0].index])


# ---- benchmarks ---------------------------------------------------------------------------
class BuyAndHold(ETFRebalancer):                  # B1 (SPY), invests once at the first rebalance
    def __init__(self, ticker="SPY", **kw):
        super().__init__(**kw)
        self.ticker = ticker
        self.done = False

    def decide(self, date, price_history, portfolio):
        if self.done or not self.rebalance_candidate(price_history):
            return []
        self.done = True
        return self._trades(pd.Series({self.ticker: 1.0}) * self.target_total_weight,
                            price_history.iloc[-1].to_dict(), portfolio)


class SixtyForty(ETFRebalancer):                  # B2
    def target_weights(self, hist, scores):
        return pd.Series({"SPY": 0.6, "IEF": 0.4})


class EqualWeightUniverse(ETFRebalancer):         # B3
    def target_weights(self, hist, scores):
        return pd.Series(1.0 / len(scores), index=scores.index)


def first_rebalance_date(prices: pd.DataFrame, **kw):
    """First date at which the 12-month core configuration can rebalance."""
    probe = ETFRebalancer(**kw)
    for i in range(2, len(prices) + 1):
        if probe.rebalance_candidate(prices.iloc[:i]):
            return prices.index[i - 1]
    raise ValueError("no valid rebalance date")
