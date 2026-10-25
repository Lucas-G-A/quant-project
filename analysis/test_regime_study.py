"""Known-answer tests for analysis/run_regime_study.py. Run: python analysis/test_regime_study.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, pandas as pd
from analysis.run_regime_study import (month_end, monthly_returns, monthly_rf, bear_flags, rates_up_flags,
                                       h1_convexity, h2_regime_diff, describe)
from strategies.etf_regime_benchmarks import SixtyFortyCash

rng = np.random.default_rng(3)

# 1. bear_flags vs an independent brute-force implementation (loops, no pandas shortcuts)
idx = pd.bdate_range("2010-01-04", periods=1500)
r = rng.normal(0.0004, 0.01, len(idx)); r[700:900] = rng.normal(-0.003, 0.015, 200); r[900:1100] = rng.normal(0.002, 0.01, 200)
spy = pd.Series(100 * np.exp(np.cumsum(r)), index=idx)
got = bear_flags(spy)
ends = [d for i, d in enumerate(idx) if i == len(idx) - 1 or idx[i + 1].month != d.month]
flag_at_end = {}
peak = -np.inf
pos = {d: i for i, d in enumerate(idx)}
for d in ends:
    i = pos[d]
    peak = spy.iloc[: i + 1].max()
    dd = spy.iloc[i] / peak - 1
    r12 = spy.iloc[i] / spy.iloc[i - 252] - 1 if i >= 252 else np.nan
    flag_at_end[d + pd.offsets.MonthEnd(0)] = bool(dd <= -0.10 and r12 < 0)
months = sorted(flag_at_end)
expected = pd.Series({months[k + 1]: flag_at_end[months[k]] for k in range(len(months) - 1)})   # applied to the NEXT month
common = got.index.intersection(expected.index)
assert len(common) > 40 and (got.loc[common].values == expected.loc[common].values).all(), "bear flag mismatch"
print(f"1. bear_flags equals brute force on {len(common)} months; flagged {int(got.sum())}; "
      f"flag for month m uses only data through the end of month m-1")
# look-ahead check: truncating the data after month m-1 must not change the flag for month m
cut = idx[idx <= pd.Timestamp("2012-03-30")]
a = bear_flags(spy.loc[cut]); b = bear_flags(spy)
assert (a.loc[a.index[:-1]] == b.loc[a.index[:-1]]).all()
print("   flags computed on truncated history match the full-history flags (no look-ahead)")

# 2. month_end / monthly_returns by hand
eq = pd.Series([100, 101, 103, 102, 105, 110], index=pd.to_datetime(["2020-01-30", "2020-01-31", "2020-02-27", "2020-02-28", "2020-03-30", "2020-03-31"]))
m = monthly_returns(eq)
assert np.allclose(m.values, [102 / 101 - 1, 110 / 102 - 1]) and list(m.index) == list(pd.to_datetime(["2020-02-29", "2020-03-31"]))
print("2. monthly_returns matches hand calculation")

# 3. monthly_rf compounding
rfd = pd.Series(0.0001, index=pd.bdate_range("2020-01-01", "2020-03-31"))
rm = monthly_rf(rfd)
n_jan = (rfd.index.month == 1).sum()
assert abs(rm.iloc[0] - ((1.0001) ** n_jan - 1)) < 1e-15
print("3. monthly_rf compounds daily RF correctly")

# 4. H1 recovers a planted convexity coefficient, and finds none when absent
n = 400; mi = pd.date_range("1990-01-31", periods=n, freq="ME")
r_m = pd.Series(rng.normal(0.006, 0.04, n), index=mi); rf_m = pd.Series(0.002, index=mi)
rs = 0.5 * (r_m - rf_m) + 0.4 * np.maximum(-(r_m - rf_m), 0) + rng.normal(0, 0.01, n) + rf_m
res = h1_convexity(rs, r_m, rf_m)
assert abs(res["gamma"] - 0.4) < 0.1 and res["p_one_sided"] < 0.01 and abs(res["beta"] - 0.5) < 0.08
rs0 = 0.5 * (r_m - rf_m) + rng.normal(0, 0.01, n) + rf_m
res0 = h1_convexity(rs0, r_m, rf_m)
assert abs(res0["gamma"]) < 0.1 and res0["p_one_sided"] > 0.01
print("4. H1: planted gamma 0.40 -> %.2f (p=%.4f); no convexity -> gamma %.2f (p=%.2f)" %
      (res["gamma"], res["p_one_sided"], res0["gamma"], res0["p_one_sided"]))

# 5. H2: planted regime difference vs none; flags in persistent blocks like real regimes
n = 320; mi = pd.date_range("1995-01-31", periods=n, freq="ME")
flag = np.zeros(n, bool)
for s in (30, 120, 200, 270):
    flag[s:s + 14] = True
noise = rng.normal(0, 0.02, n)
act = pd.Series(noise + 0.012 * flag, index=mi)
h = h2_regime_diff(act, pd.Series(flag, index=mi), n_boot=4000)
print("5. H2 planted D=1.2%%: estimate %.2f%%, 95%% CI [%.2f%%, %.2f%%], p=%.3f, regime months %d" %
      (h["D"] * 100, h["ci_low"] * 100, h["ci_high"] * 100, h["p_one_sided"], h["n_regime"]))
assert abs(h["D"] - 0.012) < 0.012 and h["ci_low"] < 0.012 < h["ci_high"]
null = h2_regime_diff(pd.Series(noise, index=mi), pd.Series(flag, index=mi), n_boot=4000)
assert null["ci_low"] < 0 < null["ci_high"] and null["p_one_sided"] > 0.02
print("   H2 null: D=%.2f%%, CI [%.2f%%, %.2f%%], p=%.2f (CI contains 0)" % (null["D"] * 100, null["ci_low"] * 100, null["ci_high"] * 100, null["p_one_sided"]))
big = h2_regime_diff(pd.Series(noise + 0.05 * flag, index=mi), pd.Series(flag, index=mi), n_boot=4000)
assert big["p_one_sided"] < 0.01
empty = h2_regime_diff(act, pd.Series(np.zeros(n, bool), index=mi), n_boot=100)
assert np.isnan(empty["D"])
print("   large effect -> p<0.01; no regime months -> NaN (handled, no crash)")

# 6. describe()
d = describe(pd.Series([0.02, -0.05, 0.01, 0.03], index=mi[:4]), pd.Series([True, True, False, False], index=mi[:4]))
assert d["regime"]["n"] == 2 and abs(d["regime"]["mean"] + 0.015) < 1e-12 and d["regime"]["worst"] == -0.05 and d["other"]["hit_rate"] == 1.0
print("6. describe(): regime/other splits correct")

# 7. B2c weights
s = SixtyFortyCash(); w = s.target_weights(None, None) * s.target_total_weight
assert abs(w["SPY"] - 0.588) < 1e-12 and abs(w["SHY"] - 0.392) < 1e-12
print("7. B2c = 58.8% SPY / 39.2% cash")
print("ALL REGIME TESTS PASSED")
