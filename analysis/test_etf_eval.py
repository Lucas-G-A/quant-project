"""Known-answer tests for analysis/etf_eval.py. Run: python analysis/test_etf_eval.py"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from statistics import NormalDist
from analysis.etf_eval import (alpha_regression, bootstrap_sharpe_diff, expected_max_sharpe,
                               deflated_sharpe, moments, evidence_of_alpha, sharpe)

rng = np.random.default_rng(7)
n = 3000
idx = pd.bdate_range("2010-01-04", periods=n)

# 1. alpha_regression recovers known alpha and betas
X = pd.DataFrame({"spy": rng.normal(0.0003, 0.010, n), "ief": rng.normal(0.0001, 0.004, n)}, index=idx)
y = 0.0004 + 0.8 * X["spy"] + 0.3 * X["ief"] + rng.normal(0, 0.002, n)
r = alpha_regression(pd.Series(y, index=idx), X)
assert abs(r["beta_spy"] - 0.8) < 0.03 and abs(r["beta_ief"] - 0.3) < 0.08 and abs(r["alpha"] - 0.0004 * 252) < 0.03
print("1. alpha_regression: alpha %.3f (true %.3f), betas %.2f/%.2f (true 0.8/0.3), t=%.1f" %
      (r["alpha"], 0.0004 * 252, r["beta_spy"], r["beta_ief"], r["alpha_t"]))
# zero-alpha series should NOT show significant alpha
y0 = 0.8 * X["spy"] + 0.3 * X["ief"] + rng.normal(0, 0.002, n)
assert abs(alpha_regression(pd.Series(y0, index=idx), X)["alpha_t"]) < 2.5
print("   zero-alpha series: |t| < 2.5 as expected")

# 2. bootstrap: paired identical series -> diff exactly 0; independent iid -> SE matches analytic formula
a = pd.Series(rng.normal(0.0006, 0.01, n), index=idx)
b = pd.Series(rng.normal(0.0002, 0.01, n), index=idx)
t0 = time.time()
bs = bootstrap_sharpe_diff({"A": a, "same": a}, {"B": b, "A2": a}, n_boot=4000, seed=1)
print("2. bootstrap runtime %.1fs for 4000 resamples x %d days" % (time.time() - t0, n))
same = bs[(bs.strategy == "same") & (bs.benchmark == "A2")].iloc[0]
assert abs(same.sharpe_diff) < 1e-12 and abs(same.ci_low) < 1e-9 and abs(same.ci_high) < 1e-9
ab = bs[(bs.strategy == "A") & (bs.benchmark == "B")].iloc[0]
true_diff = (0.0006 - 0.0002) / 0.01 * np.sqrt(252)
analytic_se = np.sqrt(2 * (1 + 0.5 * (0.0004 / 0.01) ** 2) / n) * np.sqrt(252)
width_se = (ab.ci_high - ab.ci_low) / (2 * 1.96)
print("   A vs B: observed diff %.2f (true %.2f) | CI [%.2f, %.2f] | bootstrap SE %.2f vs analytic %.2f" %
      (ab.sharpe_diff, true_diff, ab.ci_low, ab.ci_high, width_se, analytic_se))
assert ab.ci_low <= true_diff <= ab.ci_high and 0.8 < width_se / analytic_se < 1.25

# 3. expected_max_sharpe against a hand calculation (N=13): z1=Phi^-1(1-1/13), z2=Phi^-1(1-1/(13e))
nd = NormalDist(); g = 0.5772156649015329
v = 0.0001 ** 2 * 4
srs = np.array([0.0, 0.0002, 0.0002, 0.0, 0.0002, 0.0, 0.0001, 0.0001, 0.0002, 0.0, 0.0001, 0.0001, 0.0002])
hand = np.sqrt(np.var(srs, ddof=1)) * ((1 - g) * nd.inv_cdf(1 - 1 / 13) + g * nd.inv_cdf(1 - 1 / (13 * np.e)))
assert abs(expected_max_sharpe(srs, 13) - hand) < 1e-15 and abs(nd.inv_cdf(1 - 1 / 13) - 1.4261) < 1e-3
print("3. expected_max_sharpe matches hand calc (z1=%.4f, SR0=%.6f); N=1 -> %.1f" %
      (nd.inv_cdf(1 - 1 / 13), hand, expected_max_sharpe(srs, 1)))

# 4. deflated_sharpe properties: =0.5 when SR==SR0 (normal returns); falls as n_trials rises; rises with sample length
sr0 = expected_max_sharpe(srs, 13)
assert abs(deflated_sharpe(sr0, 2500, 0.0, 3.0, srs, 13) - 0.5) < 1e-9
hi = 0.08
p13, p100 = deflated_sharpe(hi, 2500, 0.0, 3.0, srs, 13), deflated_sharpe(hi, 2500, 0.0, 3.0, srs, 100)
assert p13 > p100 and deflated_sharpe(hi, 5000, 0.0, 3.0, srs, 13) > p13
assert deflated_sharpe(0.0, 2500, 0.0, 3.0, srs, 13) < 0.5
# negative skew / fat tails reduce confidence
assert deflated_sharpe(hi, 2500, -1.0, 8.0, srs, 13) < p13
print("4. deflated_sharpe: =0.5 at SR0, decreases with more trials (%.3f -> %.3f), penalises skew/kurtosis" % (p13, p100))
sk, ku = moments(rng.standard_normal(200000)); assert abs(sk) < 0.05 and abs(ku - 3) < 0.1
print("   moments(normal) skew %.3f kurt %.3f" % (sk, ku))

# 5. criterion logic
good = {"alpha": 0.05, "alpha_t": 3.0}; weak = {"alpha": 0.05, "alpha_t": 1.2}; neg = {"alpha": -0.01, "alpha_t": -0.5}
assert evidence_of_alpha(good, good, good, 0.97, good)["passes_all"]
assert not evidence_of_alpha(good, good, neg, 0.97, good)["passes_all"]      # holdout negative
assert not evidence_of_alpha(good, good, good, 0.90, good)["passes_all"]     # DSR too low
assert not evidence_of_alpha(good, good, good, 0.97, weak)["passes_all"]     # dies at 10bps
assert not evidence_of_alpha(weak, good, good, 0.97, good)["passes_all"]     # t < 2
print("5. evidence_of_alpha: requires ALL four conditions")

# 6. deflated_sharpe at a realistic scale (daily Sharpes of 0.02-0.06, i.e. annual 0.3-1.0) -> results strictly inside (0, 1)
real = np.array([0.020, 0.025, 0.030, 0.035, 0.028, 0.040, 0.045, 0.032, 0.038, 0.050, 0.022, 0.030, 0.042])
best = 0.050
vals = [deflated_sharpe(best, 5500, -0.3, 8.0, real, k) for k in (1, 5, 13, 50, 200)]
print("6. realistic-scale DSR for trials 1/5/13/50/200:", [round(v, 3) for v in vals])
assert all(0.0 < v < 1.0 for v in vals) and all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))
assert deflated_sharpe(0.075, 5500, -0.3, 8.0, real, 13) > deflated_sharpe(0.050, 5500, -0.3, 8.0, real, 13)
print("   monotone: fewer trials / higher Sharpe -> higher DSR")
print("ALL EVAL TESTS PASSED")
