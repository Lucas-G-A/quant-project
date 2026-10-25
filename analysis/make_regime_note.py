"""Builds research/regime_study_results.md and research/figures/regime_h1_scatter.png from analysis/output/regime_*.csv."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from analysis.run_regime_study import bear_flags, month_end, monthly_rf

O = os.path.join(ROOT, "analysis", "output")
h1, h2, h3 = (pd.read_csv(f"{O}/regime_{n}.csv") for n in ("h1", "h2", "h3"))
desc, dec = pd.read_csv(f"{O}/regime_descriptive.csv"), pd.read_csv(f"{O}/regime_decision.csv")
mon = pd.read_csv(f"{O}/regime_monthly_returns.csv", index_col=0, parse_dates=True)
pc = lambda x: "" if pd.isna(x) else f"{x:.2%}"

def md(df):
    cols = list(df.columns)
    out = ["| " + " | ".join([df.index.name or ""] + cols) + " |", "|" + "---|" * (len(cols) + 1)]
    out += ["| " + " | ".join([str(i)] + [str(v) for v in r]) + " |" for i, r in df.iterrows()]
    return "\n".join(out)

NICE = {"S1": "S1 Cross-sectional momentum", "S2": "S2 Time-series trend", "S3": "S3 Dual momentum", "S4": "S4 Risk-managed dual momentum"}
SMP = {"confirmatory": "Confirmatory 2000-2004 (59 mo)", "exploratory": "Exploratory 2005-2026 (260 mo)", "pooled": "Pooled (319 mo)"}

def h1_table(strats):
    d = h1[h1.strategy.isin(strats)].copy()
    t = pd.DataFrame({"gamma (convexity)": d["gamma"].map("{:+.2f}".format), "beta": d["beta"].map("{:.2f}".format),
                      "t(gamma)": d["t_gamma"].map("{:+.2f}".format), "one-sided p (gamma>0)": d["p_one_sided"].map("{:.3f}".format)})
    t.index = [f"{NICE[s]}: {SMP[m]}" for s, m in zip(d.strategy, d["sample"])]; t.index.name = "Strategy: sample"
    return md(t)

def h2_table(strats, h=h2):
    d = h[h.strategy.isin(strats)].copy()
    t = pd.DataFrame({"D (bear minus other)": d["D"].map(pc), "95% interval": [f"[{pc(a)}, {pc(b)}]" for a, b in zip(d.ci_low, d.ci_high)],
                      "one-sided p (D>0)": d["p_one_sided"].map("{:.3f}".format), "bear months": d["n_regime"].astype(int)})
    t.index = [f"{NICE[s]}: {SMP[m]}" for s, m in zip(d.strategy, d["sample"])]; t.index.name = "Strategy: sample"
    return md(t)

ds = desc[desc.series.isin(["S2", "B1", "B2c"])].copy()
ds["Regime"] = ds["BEAR"].map({True: "BEAR", False: "other"})
dt = pd.DataFrame({"n": ds["n"], "mean/mo": ds["mean"].map(pc), "vol/mo": ds["std"].map(pc), "worst month": ds["worst"].map(pc)})
LAB = {"S2": "S2 trend", "B1": "SPY", "B2c": "60/40 cash"}
dt.index = [f"{r.sample[:4]}. {LAB[r.series]} {r.Regime}" for r in ds.itertuples()]; dt.index.name = "Sample, series, regime"

dd = dec.copy()
for c in ("confirmatory estimate", "exploratory estimate", "pooled estimate"):
    dd[c] = dd[c].map("{:+.4f}".format)
dd["confirmatory p"] = dd["confirmatory p"].map("{:.3f}".format)
dd["CONFIRMED"] = dd["CONFIRMED"].map(lambda v: "YES" if v else "not established")
dd = dd.set_index("hypothesis")

pre = pd.read_csv(os.path.join(ROOT, "data", "prices_etf_pre2005.csv"), index_col=0, parse_dates=True)
fl = bear_flags(pre["SPY"])
ctx = {}
for name in ("S1", "S2", "B1", "B2c"):
    r = mon[f"confirmatory:{name}"].dropna(); f = fl.reindex(r.index).fillna(False)
    ctx[name] = (np.prod(1 + r) - 1, np.prod(1 + r[f]) - 1, np.prod(1 + r[~f]) - 1)

from analysis.factor_attribution import ols_hac
_rf = pd.read_csv(os.path.join(ROOT, "data", "ff_factors_daily.csv"), index_col=0, parse_dates=True)["RF"] / 100
_rfm = monthly_rf(_rf)
_ex = pd.read_csv(os.path.join(ROOT, "data", "prices_etf.csv"), index_col=0, parse_dates=True)
_spy = pd.concat([month_end(pre["SPY"]).pct_change(), month_end(_ex["SPY"]).pct_change()])
_spy = _spy[~_spy.index.duplicated(keep="last")]

def gamma_pooled(sid, drop_worst=0):
    y = pd.concat([mon[f"confirmatory:{sid}"], mon[f"exploratory:{sid}"]]).dropna()
    y = y[~y.index.duplicated()]
    d = pd.concat([y - _rfm.reindex(y.index), _spy.reindex(y.index) - _rfm.reindex(y.index)], axis=1).dropna()
    d.columns = ["y", "x"]
    d = d.drop(index=d["x"].sort_values().index[:drop_worst])
    r = ols_hac(d["y"].values, np.column_stack([d["x"], np.maximum(-d["x"], 0)]), 3)
    return r["beta"][2], r["t"][2]

rob = {k: gamma_pooled("S1", k) for k in (0, 1, 3)}
p_s1 = h1[(h1.strategy == "S1") & (h1["sample"] == "pooled")].iloc[0]
p_s3d = h2[(h2.strategy == "S3") & (h2["sample"] == "pooled")].iloc[0]
p_s4d = h2[(h2.strategy == "S4") & (h2["sample"] == "pooled")].iloc[0]
s2c1 = h1[(h1.strategy == "S2") & (h1["sample"] == "confirmatory")].iloc[0]
s2e1 = h1[(h1.strategy == "S2") & (h1["sample"] == "exploratory")].iloc[0]
s2c2 = h2[(h2.strategy == "S2") & (h2["sample"] == "confirmatory")].iloc[0]
s2e2 = h2[(h2.strategy == "S2") & (h2["sample"] == "exploratory")].iloc[0]
vol = lambda smp, ser, bear: desc[(desc["sample"] == smp) & (desc.series == ser) & (desc.BEAR == bear)].iloc[0]

note = f"""# Regime Study (v2): Results

**Pre-registered.** Protocol `research/regime_study_protocol.md` committed in `0e8cb32` (2026-10-24 23:20 local time) before any v2 test was run; the study was run once as written.
The runner code (`analysis/run_regime_study.py`, `strategies/etf_regime_benchmarks.py`) was written after the protocol commit and committed after the run, unlike the v1 study where code was committed first; it has not been modified since the run.
Pipeline checks passed on the real data before results were used: the saved v1 equity curves were reproduced exactly by the current code, and the month and bear-month counts matched the numbers fixed in the protocol (260/33 and 59/30).

## Question

Historically, did the trend and momentum strategies from the v1 ETF study behave differently when the market was in a bear regime
(SPY at least 10% below its peak with a negative trailing 12-month return, known at the prior month-end), and is the difference reliable?
This describes how the strategies behaved in past regimes. It does not forecast recessions or future returns.

## Headline

**Neither pre-registered hypothesis is confirmed, and the point estimates point the opposite way.**
The time-series trend strategy (S2) did not show convex payoffs against SPY (H1) and did not do better relative to a 60/40 stock/cash portfolio in bear months than in other months (H2).
The idea "when the market is down, this algorithm works" is not supported by the data.
Because the confirmatory sample contains one bear market (the dot-com bust), "not confirmed" here means "not established", and I cannot rule out smaller effects.

## Pre-registered decision

{md(dd)}

Rule: confirmed only if the confirmatory one-sided p <= 0.025 (Bonferroni for two tests) and the exploratory estimate has the same sign.

## H1: convexity (g > 0 predicted)

Monthly excess returns regressed on SPY and a down-market term: r_strategy = a + b * r_SPY + g * max(-r_SPY, 0). Newey-West standard errors, normal approximation for p.

{h1_table(["S2"])}

For S2 the estimate is slightly negative in both samples, with t about -0.6. Secondary strategies:

{h1_table(["S1", "S3", "S4"])}

## H2: bear-regime outperformance vs 60/40 cash

D = mean(active return | bear) - mean(active return | other months), active = strategy minus (60% SPY, 40% cash). Stationary bootstrap, mean block 12 months, 10,000 resamples.

{h2_table(["S2"])}

Secondary strategies:

{h2_table(["S1", "S3", "S4"])}

## H3 (exploratory only): rising-rate regime

IEF's trailing 12-month return negative at the prior month-end (80 of 260 months), active return vs a 60/40 SPY/IEF portfolio.

{h2_table(["S2", "S1"], h3)}

No evidence of a rising-rate advantage for either strategy.

## Descriptive context (not tests)

{md(dt)}

Over the confirmatory window (Feb 2000 to Dec 2004) the cumulative return of S2 was {ctx['S2'][0]:+.1%} against {ctx['B1'][0]:+.1%} for SPY and {ctx['B2c'][0]:+.1%} for 60/40 cash.
Inside the bear months only, S2 returned {ctx['S2'][1]:+.1%} against {ctx['B1'][1]:+.1%} for SPY and {ctx['B2c'][1]:+.1%} for 60/40 cash; in the other months S2 returned {ctx['S2'][2]:+.1%} against {ctx['B1'][2]:+.1%} and {ctx['B2c'][2]:+.1%}.
So S2 limited losses relative to SPY during the dot-com bust but did about as well as a plain 60/40 cash portfolio there; its edge in this window came from the months outside the bear regime. This was not a pre-registered test and rests on one episode.

## What the results say

1. **S2 was defensive, not convex.** Its monthly volatility in bear months was {pc(vol('confirmatory','S2',True)['std'])} (confirmatory) and {pc(vol('exploratory','S2',True)['std'])} (exploratory), against {pc(vol('confirmatory','B1',True)['std'])} and {pc(vol('exploratory','B1',True)['std'])} for SPY, and its worst bear-month loss was far smaller ({pc(vol('confirmatory','S2',True)['worst'])} and {pc(vol('exploratory','S2',True)['worst'])} against {pc(vol('confirmatory','B1',True)['worst'])} and {pc(vol('exploratory','B1',True)['worst'])} for SPY). Relative to a 60/40 cash portfolio it was about the same in the confirmatory bear months and worse in the exploratory ones.
2. **A plausible but untested explanation:** a monthly rebalance on a 12-1 month signal reacts slowly, so it may exit only after much of a fast decline has happened, which would fit the absence of convexity. I did not test this.
3. **Post-results observation (not pre-registered): the cross-sectional momentum strategies look anti-convex.** For S1, S3 and S4 the down-market coefficient is about -0.4 in every sample (pooled t = {p_s1.t_gamma:+.2f} for S1), i.e. they lose more per unit of market decline when the market is falling than they gain when it rises. In the pooled sample their active return in bear months is also lower than in other months (S3 D = {pc(p_s3d.D)} with a 95% interval of [{pc(p_s3d.ci_low)}, {pc(p_s3d.ci_high)}], S4 D = {pc(p_s4d.D)} with [{pc(p_s4d.ci_low)}, {pc(p_s4d.ci_high)}]). This is consistent with the "momentum crash" literature (Daniel and Moskowitz, 2016). The study reports 12 H1 and 12 H2 strategy-sample combinations in total, so treat it as a hypothesis for a future pre-registered study, not a finding. Post-hoc robustness check: excluding October 2008 (S1 lost 24.6% when SPY fell 16.5%) moves S1's coefficient from {rob[0][0]:+.2f} (t = {rob[0][1]:+.2f}; this check uses the 316 months with complete data, hence the small difference from the table above) to {rob[1][0]:+.2f} (t = {rob[1][1]:+.2f}), and excluding the three worst SPY months gives {rob[3][0]:+.2f} (t = {rob[3][1]:+.2f}). The sign is stable, but the significance is borderline and leans on a few crisis months.

## Limitations

- **One bear market in the confirmatory sample.** A non-significant confirmatory result is inconclusive. Across both samples there are about 4 to 5 independent bear episodes.
- **The exploratory sample was already seen** in the v1 study and partly motivated the hypotheses, so it cannot confirm anything.
- **The regime definition** (SPY drawdown plus negative 12-month return) was chosen after counting SPY-only flagged months, never strategy returns, but it remains one of several reasonable definitions.
- **Early country ETFs trade thinly** (8% to 15% of days with an unchanged close), the confirmatory universe has no bonds before mid-2002 and no commodities or REITs, and cash before 2002 is a T-bill index built from Ken French's risk-free rate.
- **p-values for H1 use a normal approximation** with 59 and 258 monthly observations; H2 uses a bootstrap p-value from the resampled estimator.
- **Macro data** (inflation, unemployment, growth) was deliberately not used; it needs point-in-time vintages and is deferred.

## Conclusion

Under a protocol fixed in advance, trend and momentum on liquid ETFs did not provide a measurable advantage in bear regimes. The trend strategy reduced volatility and tail losses without outperforming a simple 60/40 cash portfolio inside bear months, and the momentum strategies appear to do relatively worse in bear regimes. This is a second negative result, and the momentum-crash pattern is a candidate hypothesis for follow-up.

![Monthly returns vs SPY with fitted convexity line](figures/regime_h1_scatter.png)
"""
open(os.path.join(ROOT, "research", "regime_study_results.md"), "w").write(note)

# ---- figure: scatter of monthly excess returns vs SPY, pooled, with the fitted kinked line
rf = pd.read_csv(os.path.join(ROOT, "data", "ff_factors_daily.csv"), index_col=0, parse_dates=True)["RF"] / 100
rfm = monthly_rf(rf)
ex = pd.read_csv(os.path.join(ROOT, "data", "prices_etf.csv"), index_col=0, parse_dates=True)
spy_all = pd.concat([month_end(pre["SPY"]).pct_change(), month_end(ex["SPY"]).pct_change()])
spy_all = spy_all[~spy_all.index.duplicated(keep="last")]
fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharex=True)
for ax, sid in zip(axes, ["S2", "S1"]):
    y = pd.concat([mon[f"confirmatory:{sid}"], mon[f"exploratory:{sid}"]]).dropna()
    y = y[~y.index.duplicated()]
    d = pd.concat([y - rfm.reindex(y.index), spy_all.reindex(y.index) - rfm.reindex(y.index)], axis=1).dropna(); d.columns = ["y", "x"]
    A = np.column_stack([np.ones(len(d)), d["x"], np.maximum(-d["x"], 0)])
    c = np.linalg.lstsq(A, d["y"].values, rcond=None)[0]
    xs = np.linspace(d["x"].min(), d["x"].max(), 200)
    ax.scatter(d["x"], d["y"], s=10, alpha=0.45, color="#555555")
    ax.plot(xs, c[0] + c[1] * xs + c[2] * np.maximum(-xs, 0), color="#d95f0e", lw=2, label="fitted line with down-market term")
    ax.plot(xs, c[0] + c[1] * xs, color="#2c7fb8", lw=1, ls="--", label="upside slope extended (no kink)")
    ax.legend(fontsize=7, loc="upper left")
    ax.axhline(0, color="k", lw=0.5); ax.axvline(0, color="k", lw=0.5)
    row = h1[(h1.strategy == sid) & (h1["sample"] == "pooled")].iloc[0]
    ax.set_title(f"{NICE[sid]}\nconvexity gamma = {row.gamma:+.2f} (t = {row.t_gamma:+.2f}; positive would mean convex)", fontsize=9)
    ax.set_xlabel("SPY monthly excess return"); ax.grid(alpha=0.3)
axes[0].set_ylabel("Strategy monthly excess return")
plt.tight_layout(); plt.savefig(os.path.join(ROOT, "research", "figures", "regime_h1_scatter.png"), dpi=130)
print("wrote note and figure")
