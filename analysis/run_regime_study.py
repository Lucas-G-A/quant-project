"""
Regime study v2 (research/regime_study_protocol.md): do the v1 trend/momentum strategies behave differently
when the market is in a bear regime, and is that difference reliable?

    python analysis/run_regime_study.py              # real data, run ONCE after the protocol commit
    python analysis/run_regime_study.py --selftest   # synthetic data, temp output folder
"""
import os
import sys
import tempfile
from statistics import NormalDist

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
import pandas as pd

from analysis.etf_eval import _stationary_indices
from analysis.factor_attribution import ols_hac
from analysis.run_etf_experiment import STRATS, run_one
from strategies.etf_regime_benchmarks import SixtyFortyCash
from strategies.etf_strategies import BuyAndHold, SixtyForty, first_rebalance_date

STRAT_IDS = ["S1", "S2", "S3", "S4"]
PRIMARY = "S2"
ALPHA_ONE_SIDED = 0.025          # Bonferroni for 2 confirmatory tests
CONF_MIN_ETFS = 15
N_BOOT = 10_000


# ------------------------------------------------------------------ helpers ---------------------------
def month_end(s: pd.Series) -> pd.Series:
    g = s.groupby([s.index.year, s.index.month]).last()
    g.index = pd.to_datetime([f"{y}-{m:02d}-01" for y, m in g.index]) + pd.offsets.MonthEnd(0)
    return g


def monthly_returns(eq: pd.Series) -> pd.Series:
    return month_end(eq).pct_change(fill_method=None).dropna()


def monthly_rf(rf_daily: pd.Series) -> pd.Series:
    g = (1 + rf_daily).groupby([rf_daily.index.year, rf_daily.index.month]).prod() - 1
    g.index = pd.to_datetime([f"{y}-{m:02d}-01" for y, m in g.index]) + pd.offsets.MonthEnd(0)
    return g


def bear_flags(spy: pd.Series) -> pd.Series:
    """BEAR at month-end m (applied to month m+1): SPY >= 10% below its running peak AND trailing
    12-month (252 trading day) return negative."""
    dd = month_end(spy / spy.cummax() - 1)
    r12 = month_end(spy / spy.shift(252) - 1)
    return ((dd <= -0.10) & (r12 < 0)).shift(1).dropna().astype(bool)


def rates_up_flags(ief: pd.Series) -> pd.Series:
    """RATES-UP at month-end m (applied to month m+1): IEF trailing 12-month return negative."""
    r12 = month_end(ief / ief.shift(252) - 1)
    return (r12 < 0).shift(1).dropna().astype(bool)


def h1_convexity(r_s: pd.Series, r_spy: pd.Series, rf_m: pd.Series, lags: int = 3) -> dict:
    d = pd.concat([r_s - rf_m.reindex(r_s.index), r_spy.reindex(r_s.index) - rf_m.reindex(r_s.index)],
                  axis=1, join="inner").dropna()
    d.columns = ["y", "m"]
    res = ols_hac(d["y"].values, np.column_stack([d["m"].values, np.maximum(-d["m"].values, 0)]), lags)
    return {"alpha_m": res["beta"][0], "beta": res["beta"][1], "gamma": res["beta"][2],
            "t_gamma": res["t"][2], "p_one_sided": 1 - NormalDist().cdf(res["t"][2]), "n_months": res["n"]}


def h2_regime_diff(active: pd.Series, flag: pd.Series, n_boot: int = N_BOOT, mean_block: int = 12, seed: int = 2026) -> dict:
    df = pd.concat([active.rename("a"), flag.rename("f")], axis=1, join="inner").dropna()
    a, f = df["a"].values, df["f"].values.astype(float)
    n, nb_obs = len(df), int(f.sum())
    nan = {"D": np.nan, "ci_low": np.nan, "ci_high": np.nan, "p_one_sided": np.nan, "n_months": n, "n_regime": nb_obs,
           "mean_in": np.nan, "mean_out": np.nan}
    if nb_obs in (0, n):
        return nan
    D = a[f == 1].mean() - a[f == 0].mean()
    idx = _stationary_indices(n, n_boot, mean_block, np.random.default_rng(seed))
    A, F = a[idx], f[idx]
    nb, nn = F.sum(1), n - F.sum(1)
    ok = (nb > 0) & (nn > 0)
    Dstar = ((A * F).sum(1)[ok] / nb[ok]) - ((A * (1 - F)).sum(1)[ok] / nn[ok])
    return {"D": D, "ci_low": np.percentile(Dstar, 2.5), "ci_high": np.percentile(Dstar, 97.5),
            "p_one_sided": float((Dstar <= 0).mean()), "n_months": n, "n_regime": nb_obs,
            "mean_in": a[f == 1].mean(), "mean_out": a[f == 0].mean()}


def describe(ret: pd.Series, flag: pd.Series) -> dict:
    df = pd.concat([ret.rename("r"), flag.rename("f")], axis=1, join="inner").dropna()
    out = {}
    for label, mask in (("regime", df["f"]), ("other", ~df["f"])):
        r = df.loc[mask, "r"]
        out[label] = {"n": len(r), "mean": r.mean(), "std": r.std(), "worst": r.min(), "hit_rate": (r > 0).mean()} if len(r) else \
                     {"n": 0, "mean": np.nan, "std": np.nan, "worst": np.nan, "hit_rate": np.nan}
    return out


# ------------------------------------------------------------------ the study -------------------------------
def build_curves(prices, rf_daily, v1_curves, kind, verify_v1):
    """Equity curves (daily, from the close before the first rebalance) for S1-S4, B1, B2c (+ B2 if exploratory)."""
    if kind == "confirmatory":
        p = prices.copy()
        p = p.drop(columns=[c for c in p.columns if p[c].isna().all()])
        p["SHY"] = 100 * (1 + rf_daily.reindex(p.index).fillna(0)).cumprod()          # T-bill index
        kw = {"lookback": 252, "skip": 21, "min_eligible": CONF_MIN_ETFS}
        first = first_rebalance_date(p, min_eligible=CONF_MIN_ETFS)
        bkw = {"min_eligible": CONF_MIN_ETFS}
    else:
        p = prices
        kw, bkw = {"lookback": 252, "skip": 21}, {}
        first = first_rebalance_date(p)
    start = p.index[p.index.get_loc(first) - 1]
    curves = {}
    if kind == "exploratory" and v1_curves is not None:
        for sid in STRAT_IDS:
            curves[sid] = v1_curves[f"{sid}_12m"].dropna()
        curves["B1"], curves["B2"] = v1_curves["B1"].dropna(), v1_curves["B2"].dropna()
        if verify_v1:      # prove the frozen v1 curves equal what the current code produces
            for name, cls, k in (("S2", STRATS["S2"], kw), ("B1", BuyAndHold, bkw)):
                rerun = run_one(p, cls, k, 5, 1, first, start)[0]
                assert np.allclose(rerun.values, curves[name].values, rtol=1e-9, atol=1e-6), f"v1 curve {name} does not reproduce"
            print("v1 equity curves reproduced exactly by the current code (S2_12m, B1)")
    else:
        for sid in STRAT_IDS:
            curves[sid] = run_one(p, STRATS[sid], kw, 5, 1, first, start)[0]
        curves["B1"] = run_one(p, BuyAndHold, bkw, 5, 1, first, start)[0]
        if kind == "exploratory":
            curves["B2"] = run_one(p, SixtyForty, bkw, 5, 1, first, start)[0]
    curves["B2c"] = run_one(p, SixtyFortyCash, bkw, 5, 1, first, start)[0]
    return p, curves, first, start


def study(prices_exp, prices_conf, rf_daily, v1_curves, n_boot, out_dir, real=True):
    os.makedirs(out_dir, exist_ok=True)
    p_e, cur_e, first_e, start_e = build_curves(prices_exp, rf_daily, v1_curves, "exploratory", verify_v1=real)
    p_c, cur_c, first_c, start_c = build_curves(prices_conf, rf_daily, None, "confirmatory", False)
    print(f"Exploratory: first rebalance {first_e.date()}, evaluation start {start_e.date()}")
    print(f"Confirmatory: first rebalance {first_c.date()} (>= {CONF_MIN_ETFS} ETFs), evaluation start {start_c.date()}")

    rf_m = monthly_rf(rf_daily)
    ret = {"exploratory": {k: monthly_returns(v) for k, v in cur_e.items()},
           "confirmatory": {k: monthly_returns(v) for k, v in cur_c.items()}}
    spy_m = {"exploratory": month_end(p_e["SPY"]).pct_change(fill_method=None).dropna(),
             "confirmatory": month_end(p_c["SPY"]).pct_change(fill_method=None).dropna()}
    bear = {"exploratory": bear_flags(p_e["SPY"]), "confirmatory": bear_flags(p_c["SPY"])}
    for s in bear:
        bear[s] = bear[s].reindex(ret[s]["S2"].index).fillna(False)
        # restrict SPY returns to each sample's own evaluation months (the two price files overlap in 2004,
        # so pooling the unrestricted series would duplicate those months)
        spy_m[s] = spy_m[s].reindex(ret[s]["S2"].index)
        assert spy_m[s].notna().all() and spy_m[s].index.is_unique
    print(f"Months: exploratory {len(bear['exploratory'])} (BEAR {int(bear['exploratory'].sum())}), "
          f"confirmatory {len(bear['confirmatory'])} (BEAR {int(bear['confirmatory'].sum())})")
    if real:
        assert (len(bear["exploratory"]), int(bear["exploratory"].sum())) == (260, 33), "differs from protocol"
        assert (len(bear["confirmatory"]), int(bear["confirmatory"].sum())) == (59, 30), "differs from protocol"
        print("Month and BEAR counts match the committed protocol (260/33 and 59/30)")

    def pooled(fn):       # concatenate the two non-overlapping samples
        out = pd.concat([fn("confirmatory"), fn("exploratory")]).sort_index()
        assert out.index.is_unique, "samples overlap in time"
        return out

    samples = ["confirmatory", "exploratory", "pooled"]
    h1_rows, h2_rows = [], []
    for sid in STRAT_IDS:
        for smp in samples:
            if smp == "pooled":
                r_s = pooled(lambda k: ret[k][sid]); r_m = pooled(lambda k: spy_m[k])
                act = pooled(lambda k: ret[k][sid] - ret[k]["B2c"]); fl = pooled(lambda k: bear[k].astype(float)).astype(bool)
            else:
                r_s, r_m = ret[smp][sid], spy_m[smp]
                act, fl = ret[smp][sid] - ret[smp]["B2c"], bear[smp]
            h1_rows.append({"strategy": sid, "sample": smp, "role": "PRIMARY" if sid == PRIMARY and smp != "pooled" else "secondary", **h1_convexity(r_s, r_m, rf_m)})
            h2_rows.append({"strategy": sid, "sample": smp, "role": "PRIMARY" if sid == PRIMARY and smp != "pooled" else "secondary",
                            **h2_regime_diff(act.dropna(), fl, n_boot)})
    h1, h2 = pd.DataFrame(h1_rows), pd.DataFrame(h2_rows)

    # H3: exploratory only, rates-up regime, active return vs B2 (SPY/IEF)
    rates = rates_up_flags(p_e["IEF"]).reindex(ret["exploratory"]["S2"].index).fillna(False)
    h3 = pd.DataFrame([{"strategy": sid, "sample": "exploratory", "role": "EXPLORATORY", **h2_regime_diff(
        (ret["exploratory"][sid] - ret["exploratory"]["B2"]).dropna(), rates, n_boot)} for sid in ("S2", "S1")])
    print(f"RATES-UP months (exploratory): {int(rates.sum())} of {len(rates)}")

    # descriptive tables by regime
    desc = []
    for smp in ("confirmatory", "exploratory"):
        for name, r in ret[smp].items():
            d = describe(r, bear[smp])
            for lab in ("regime", "other"):
                desc.append({"sample": smp, "series": name, "BEAR": lab == "regime", **d[lab]})
    desc = pd.DataFrame(desc)

    # pre-registered confirmation decision (S2 only)
    def pick(df, smp, col):
        return df[(df.strategy == PRIMARY) & (df["sample"] == smp)][col].iloc[0]
    decision = pd.DataFrame([
        {"hypothesis": "H1 convexity (g>0)", "confirmatory estimate": pick(h1, "confirmatory", "gamma"), "confirmatory p": pick(h1, "confirmatory", "p_one_sided"),
         "exploratory estimate": pick(h1, "exploratory", "gamma"), "pooled estimate": pick(h1, "pooled", "gamma"),
         "CONFIRMED": bool(pick(h1, "confirmatory", "p_one_sided") <= ALPHA_ONE_SIDED and pick(h1, "confirmatory", "gamma") > 0 and pick(h1, "exploratory", "gamma") > 0)},
        {"hypothesis": "H2 bear outperformance (D>0)", "confirmatory estimate": pick(h2, "confirmatory", "D"), "confirmatory p": pick(h2, "confirmatory", "p_one_sided"),
         "exploratory estimate": pick(h2, "exploratory", "D"), "pooled estimate": pick(h2, "pooled", "D"),
         "CONFIRMED": bool(pick(h2, "confirmatory", "p_one_sided") <= ALPHA_ONE_SIDED and pick(h2, "confirmatory", "D") > 0 and pick(h2, "exploratory", "D") > 0)}])

    monthly = pd.concat({f"{smp}:{k}": v for smp in ret for k, v in ret[smp].items()}, axis=1)
    monthly.to_csv(os.path.join(out_dir, "regime_monthly_returns.csv"))
    for name, df in (("h1", h1), ("h2", h2), ("h3", h3), ("descriptive", desc), ("decision", decision)):
        df.to_csv(os.path.join(out_dir, f"regime_{name}.csv"), index=False)
    report(h1, h2, h3, desc, decision)
    return dict(h1=h1, h2=h2, h3=h3, desc=desc, decision=decision)


def report(h1, h2, h3, desc, decision):
    pc = lambda x: "" if pd.isna(x) else f"{x:.2%}"
    f2 = lambda x: "" if pd.isna(x) else f"{x:.2f}"
    print("\n" + "=" * 100 + "\nH1: CONVEXITY  r_s = a + b*r_SPY + g*max(-r_SPY,0)   (monthly excess returns; g>0 predicted)\n" + "=" * 100)
    s = h1.copy()
    for c in ("alpha_m", "beta", "gamma"):
        s[c] = s[c].map(f2)
    s["t_gamma"] = s["t_gamma"].map(f2); s["p_one_sided"] = s["p_one_sided"].map("{:.3f}".format)
    print(s.to_string(index=False))
    print("\n" + "=" * 100 + "\nH2: BEAR-REGIME OUTPERFORMANCE vs 60/40-cash   D = mean(active | BEAR) - mean(active | not BEAR)\n" + "=" * 100)
    s = h2.copy()
    for c in ("D", "ci_low", "ci_high", "mean_in", "mean_out"):
        s[c] = s[c].map(pc)
    s["p_one_sided"] = s["p_one_sided"].map("{:.3f}".format)
    print(s.to_string(index=False))
    print("\n" + "=" * 100 + "\nH3 (EXPLORATORY ONLY): RATES-UP regime, active return vs 60/40 SPY/IEF\n" + "=" * 100)
    s = h3.copy()
    for c in ("D", "ci_low", "ci_high", "mean_in", "mean_out"):
        s[c] = s[c].map(pc)
    s["p_one_sided"] = s["p_one_sided"].map("{:.3f}".format)
    print(s.to_string(index=False))
    print("\n" + "=" * 100 + "\nDESCRIPTIVE: monthly returns inside vs outside BEAR months (context only, not tests)\n" + "=" * 100)
    s = desc.copy()
    for c in ("mean", "std", "worst"):
        s[c] = s[c].map(pc)
    s["hit_rate"] = s["hit_rate"].map(lambda v: "" if pd.isna(v) else f"{v:.0%}")
    print(s.to_string(index=False))
    print("\n" + "=" * 100 + "\nPRE-REGISTERED DECISION (S2; confirmatory one-sided p <= 0.025 AND same sign in exploratory)\n" + "=" * 100)
    s = decision.copy()
    for c in ("confirmatory estimate", "exploratory estimate", "pooled estimate"):
        s[c] = s[c].map(lambda v: f"{v:.4f}")
    s["confirmatory p"] = s["confirmatory p"].map("{:.3f}".format)
    s["CONFIRMED"] = s["CONFIRMED"].map(lambda v: "YES" if v else "not established")
    print(s.to_string(index=False))


# ------------------------------------------------------------------ synthetic self-test ---------------------
def synthetic():
    rng = np.random.default_rng(11)

    def spy_path(idx, bears):
        r = rng.normal(0.0005, 0.010, len(idx))
        for a, b in bears:
            m = (idx >= a) & (idx <= b)
            r[m] = rng.normal(-0.0015, 0.015, m.sum())
        return 100 * np.exp(np.cumsum(r))

    def universe(idx, bears, n_etf, listed_from):
        cols = {"SPY": spy_path(idx, bears), "IEF": 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.004, len(idx)))),
                "SHY": 100 * np.exp(np.cumsum(rng.normal(0.0001, 0.0006, len(idx))))}
        for i in range(n_etf):
            x = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.011, len(idx))))
            x[: listed_from[i]] = np.nan
            cols[f"E{i}"] = x
        return pd.DataFrame(cols, index=idx)

    idx_c = pd.bdate_range("1996-01-02", "2004-12-31")
    idx_e = pd.bdate_range("2004-01-02", "2016-12-30")
    conf = universe(idx_c, [(pd.Timestamp("2000-06-01"), pd.Timestamp("2002-10-01"))], 22, [0] * 8 + [700] * 8 + [900] * 6)
    expl = universe(idx_e, [(pd.Timestamp("2008-03-01"), pd.Timestamp("2009-03-01"))], 22, [0] * 22)
    allidx = idx_c.union(idx_e)
    rf = pd.Series(0.00008, index=allidx)
    return expl, conf, rf


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        expl, conf, rf = synthetic()
        out = tempfile.mkdtemp(prefix="regime_selftest_")
        res = study(expl, conf, rf, None, 500, out, real=False)
        files = sorted(os.listdir(out))
        assert len(files) == 6 and len(res["h1"]) == 12 and len(res["h2"]) == 12 and res["decision"].shape[0] == 2
        assert res["h1"]["gamma"].notna().all()
        print(f"\nSELFTEST OK: wrote {files}")
    else:
        prices_e = pd.read_csv(os.path.join(ROOT, "data", "prices_etf.csv"), index_col=0, parse_dates=True)
        prices_c = pd.read_csv(os.path.join(ROOT, "data", "prices_etf_pre2005.csv"), index_col=0, parse_dates=True)
        ff = pd.read_csv(os.path.join(ROOT, "data", "ff_factors_daily.csv"), index_col=0, parse_dates=True)
        v1 = pd.read_csv(os.path.join(ROOT, "analysis", "output", "etf_equity_curves.csv"), index_col=0, parse_dates=True)
        study(prices_e, prices_c, ff["RF"] / 100.0, v1, N_BOOT, os.path.join(ROOT, "analysis", "output"), real=True)
