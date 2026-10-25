"""Known-answer tests for strategies/etf_strategies.py. Run: python analysis/test_etf_strategies.py"""
import contextlib, io, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
from backtester.engine import Backtester
from backtester.portfolio import Portfolio
from strategies.etf_strategies import (CrossSectionalMomentum, TimeSeriesTrend, DualMomentum,
    RiskManagedDualMomentum, SixtyForty, BuyAndHold, EqualWeightUniverse, first_rebalance_date)

rng = np.random.default_rng(1)
n = 700
idx = pd.bdate_range("2020-01-01", periods=n)
# 10 risky ETFs with known drifts (E0 best ... E9 worst, E7-E9 negative), different noise, plus SPY/IEF/SHY
drift = np.array([0.0020, 0.0016, 0.0013, 0.0010, 0.0007, 0.0004, 0.0001, -0.0003, -0.0007, -0.0012])
noise = np.array([0.002, 0.010, 0.004, 0.008, 0.003, 0.006, 0.005, 0.004, 0.003, 0.002])
cols = {f"E{i}": 100 * np.exp(np.cumsum(drift[i] + noise[i] * rng.standard_normal(n))) for i in range(10)}
cols["SPY"] = 100 * np.exp(np.cumsum(0.0004 + 0.008 * rng.standard_normal(n)))
cols["IEF"] = 100 * np.exp(np.cumsum(0.0001 + 0.003 * rng.standard_normal(n)))
cols["SHY"] = 100 * np.exp(np.cumsum(0.00005 + 0.0005 * rng.standard_normal(n)))
prices = pd.DataFrame(cols, index=idx)
risky = [c for c in prices.columns if c != "SHY"]

def probe(strategy_cls, prices=prices, row=None, **kw):
    s = strategy_cls(**kw)
    d = first_rebalance_date(prices) if row is None else prices.index[row]
    ph = prices.loc[:d]
    scores = s._eligible_scores(ph)
    return s, ph, scores, s.target_weights(s._history(ph), scores) * s.target_total_weight

# 1. S1: top 5 by 12-1 score, equal weights summing to 98%
s, ph, scores, w = probe(CrossSectionalMomentum)
top5 = list(scores.sort_values(ascending=False).index[:5])
w = w[w > 0]   # SHY is present with weight 0.0 when nothing is left over; zero weights are ignored by the trade logic
assert set(w.index) == set(top5) and np.allclose(w.values, 0.98 / 5) and abs(w.sum() - 0.98) < 1e-12
print("1. S1 picks the 5 highest 12-1 scores, 19.6% each:", top5)

# 2. No look-ahead: with lag=1, changing TODAY's prices cannot change the selection; with lag=0 it can
s1 = CrossSectionalMomentum(signal_lag=1); s0 = CrossSectionalMomentum(signal_lag=0)
d = first_rebalance_date(prices); ph = prices.loc[:d].copy()
base1 = set(s1.target_weights(s1._history(ph), s1._eligible_scores(ph)).index)
ph2 = ph.copy(); ph2.iloc[-1] = ph2.iloc[-1] * np.where(np.arange(ph2.shape[1]) % 2 == 0, 3.0, 0.2)   # crazy last day
alt1 = set(s1.target_weights(s1._history(ph2), s1._eligible_scores(ph2)).index)
assert base1 == alt1, "lag=1 signal changed when only today's prices changed (LOOK-AHEAD)"
print("2. lag=1 selection is invariant to today's prices (no look-ahead)")

# 3. Rebalances only on the first trading day of a month, and never before enough history
s = CrossSectionalMomentum()
cands = [prices.index[i - 1] for i in range(2, len(prices) + 1) if s.rebalance_candidate(prices.iloc[:i])]
assert all(prices.index.get_loc(c) > 0 and prices.index[prices.index.get_loc(c) - 1].month != c.month for c in cands)
assert len(cands) == len(set((c.year, c.month) for c in cands)) and cands[0] == first_rebalance_date(prices)
print("3. rebalance days are all first-trading-days-of-month, one per month, first =", cands[0].date())

# 4. S2: equal slices per eligible ETF; losers' slices go to SHY
s, ph, scores, w = probe(TimeSeriesTrend)
winners = scores[scores > 0].index
assert np.allclose(w[winners].values, 0.98 / len(scores)) and abs(w.sum() - 0.98) < 1e-12
assert abs(w["SHY"] - 0.98 * (len(scores) - len(winners)) / len(scores)) < 1e-12
print(f"4. S2: {len(winners)}/{len(scores)} ETFs in uptrend, each {0.98/len(scores):.3f}; SHY holds the rest ({w['SHY']:.3f})")

# 5. S3: the top 5 with the absolute filter; a failing name is replaced by SHY (use a late row where E-names diverge)
s, ph, scores, w = probe(DualMomentum, row=len(prices) - 1)
top = scores.sort_values(ascending=False).iloc[:5]
assert set(w.index) - {"SHY"} == set(top[top > 0].index) and abs(w.sum() - 0.98) < 1e-12
# force failure: make the top-5 ETFs all negative-trend
bad = prices.copy()
for c in list(top.index):
    bad[c] = bad[c] * np.exp(-0.004 * np.arange(n))          # strong decay -> negative 12-1 return
s, ph, scores, w = probe(DualMomentum, prices=bad, row=len(bad) - 1)
top = scores.sort_values(ascending=False).iloc[:5]
assert abs(w["SHY"] - 0.98 * (top <= 0).sum() / 5) < 1e-12
print("5. S3: failed trend slices move to SHY (SHY weight %.3f with %d of 5 failing)" % (w["SHY"], (top <= 0).sum()))

# 6. S4: weights inversely proportional to 63-day vol
s, ph, scores, w = probe(RiskManagedDualMomentum, row=len(prices) - 1)
held = [t for t in w.index if t != "SHY"]
vol = ph.iloc[:-1][held].pct_change().iloc[-63:].std()
ratio = (w[held] * vol)
assert np.allclose(ratio, ratio.iloc[0]), "S4 weights are not proportional to 1/vol"
print("6. S4: weight x vol is constant across holdings -> inverse-volatility weighting verified")

# 7. Benchmarks
s, ph, scores, w = probe(SixtyForty)
assert np.allclose(w[["SPY", "IEF"]].values, [0.588, 0.392])
s, ph, scores, w = probe(EqualWeightUniverse)
assert np.allclose(w.values, 0.98 / len(scores))
print("7. B2 = 58.8%/39.2% SPY/IEF, B3 = equal weight across eligible ETFs")

# 8. Full backtests: no rejected trades, ~98% invested after the first rebalance, sells-before-buys works, no NaNs
for name, cls in [("S1", CrossSectionalMomentum), ("S2", TimeSeriesTrend), ("S3", DualMomentum),
                  ("S4", RiskManagedDualMomentum), ("B1", BuyAndHold), ("B2", SixtyForty), ("B3", EqualWeightUniverse)]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        h = Backtester(prices, cls(), starting_cash=100_000, commission_pct=0.0, slippage_pct=0.0005).run()
    d0 = first_rebalance_date(prices)
    expo = (h["positions_value"] / h["total_value"]).loc[d0:]
    assert "Insufficient" not in buf.getvalue(), f"{name}: rejected trades"
    assert h["total_value"].notna().all() and expo.iloc[0] > 0.97, (name, expo.iloc[0])
    print(f"8. {name}: runs clean, no rejected trades, invested {expo.iloc[0]:.3f} after first rebalance, mean {expo.mean():.3f}")
print("ALL STRATEGY TESTS PASSED")
