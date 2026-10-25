"""
Runs the full pre-registered protocol (research/etf_momentum_protocol.md) in one go and writes
every result to analysis/output/etf_*.csv. Nothing is selected or filtered: all 13 configurations
and 3 benchmarks are reported.

    python analysis/run_etf_experiment.py              # real data (run ONCE, after the protocol commit)
    python analysis/run_etf_experiment.py --selftest   # synthetic data, writes to a temp folder
"""
import contextlib
import io
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
import pandas as pd

from analysis.etf_eval import (alpha_regression, bootstrap_sharpe_diff, deflated_sharpe,
                               evidence_of_alpha, moments, sharpe)
from backtester.engine import Backtester
from strategies.etf_strategies import (BuyAndHold, CrossSectionalMomentum, DualMomentum,
                                       EqualWeightUniverse, RiskManagedDualMomentum, SixtyForty,
                                       TimeSeriesTrend, first_rebalance_date)

DESIGN_END = pd.Timestamp("2016-12-31")
LOOKBACK_DAYS = {3: 63, 6: 126, 9: 189, 12: 252}
SKIP = 21
STRATS = {"S1": CrossSectionalMomentum, "S2": TimeSeriesTrend, "S3": DualMomentum, "S4": RiskManagedDualMomentum}
CONFIGS = [(f"{s}_{m}m", s, m) for s in ("S1", "S2", "S3") for m in (3, 6, 9, 12)] + [("S4_12m", "S4", 12)]
CORE = ["S1_12m", "S2_12m", "S3_12m", "S4_12m"]
BENCH = {"B1": (BuyAndHold, {}), "B2": (SixtyForty, {}), "B3": (EqualWeightUniverse, {})}
N_TRIALS = len(CONFIGS)          # 13, pre-registered
PERIODS = ("full", "design", "holdout")


def period_slice(s, period):
    if period == "full":
        return s
    return s.loc[:DESIGN_END] if period == "design" else s.loc[DESIGN_END + pd.Timedelta(days=1):]


def run_one(prices, cls, kwargs, bps, lag, first_rb, eval_start):
    strat = cls(signal_lag=lag, earliest_trade_date=first_rb, **kwargs)
    bt = Backtester(prices, strat, starting_cash=100_000, commission_pct=0.0, slippage_pct=bps / 10_000)
    traded = []
    original = bt.portfolio.execute_trade

    def counted(ticker, shares, price, side):
        before = bt.portfolio.cash
        original(ticker=ticker, shares=shares, price=price, side=side)
        if bt.portfolio.cash != before:
            traded.append(shares * price)

    bt.portfolio.execute_trade = counted
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        hist = bt.run()
    eq = hist["total_value"].loc[eval_start:]
    return eq, float(sum(traded)), buf.getvalue().count("Insufficient")


def price_metrics(r):
    eq = (1 + r).cumprod()
    years = len(r) / 252
    mdd = (eq / eq.cummax() - 1).min()
    cagr = eq.iloc[-1] ** (1 / years) - 1
    return {"Total return": eq.iloc[-1] - 1, "CAGR": cagr, "Ann. vol": r.std() * np.sqrt(252),
            "Max drawdown": mdd, "Calmar": cagr / abs(mdd) if mdd < 0 else np.nan,
            "Worst 10-day": (eq / eq.shift(10) - 1).min()}


def main(prices, factors_pct, out_dir, n_boot=10_000):
    os.makedirs(out_dir, exist_ok=True)
    factors = factors_pct / 100.0
    rf, mom, rf_end = factors["RF"], factors["MOM"], factors.index[-1]

    first_rb = first_rebalance_date(prices)
    i0 = prices.index.get_loc(first_rb)
    eval_start = prices.index[i0 - 1]
    print(f"Prices {prices.index[0].date()} -> {prices.index[-1].date()} | {prices.shape[1]} ETFs")
    print(f"First rebalance {first_rb.date()} | evaluation start (close before) {eval_start.date()} | "
          f"factor/RF data ends {rf_end.date()} | design <= {DESIGN_END.date()} < holdout | N_trials = {N_TRIALS}")

    # ---- base runs: 13 configurations + 3 benchmarks, 5 bps, one-day lag -------------------------
    curves, turnover, skipped = {}, {}, {}
    for name, sid, m in CONFIGS:
        curves[name], turnover[name], skipped[name] = run_one(
            prices, STRATS[sid], {"lookback": LOOKBACK_DAYS[m], "skip": SKIP}, 5, 1, first_rb, eval_start)
    for b, (cls, kw) in BENCH.items():
        curves[b], turnover[b], skipped[b] = run_one(prices, cls, kw, 5, 1, first_rb, eval_start)
    rets = {k: v.pct_change().dropna() for k, v in curves.items()}
    names = [c[0] for c in CONFIGS] + list(BENCH)
    print(f"Rejected (insufficient cash) trades across all base runs: {sum(skipped.values())}")

    spy_r, ief_r = prices["SPY"].pct_change(), prices["IEF"].pct_change()

    def excess(r):
        return (r - rf.reindex(r.index)).dropna()

    # ---- metrics by period ----------------------------------------------------------------------
    rows = []
    for name in names:
        for period in PERIODS:
            r = period_slice(rets[name], period)
            m = price_metrics(r)
            ex = excess(r)
            m.update({"Sharpe (excess RF)": sharpe(ex.values), "name": name, "period": period,
                      "Turnover / yr": (turnover[name] / curves[name].mean() / (len(rets[name]) / 252)
                                        if period == "full" else np.nan),
                      "Corr SPY": r.corr(spy_r.reindex(r.index)),
                      "Corr 60/40": r.corr(rets["B2"].reindex(r.index))})
            rows.append(m)
    metrics = pd.DataFrame(rows).set_index(["name", "period"])
    metrics.to_csv(os.path.join(out_dir, "etf_metrics.csv"))
    pd.DataFrame(curves).to_csv(os.path.join(out_dir, "etf_equity_curves.csv"))

    # ---- alpha regressions R1-R3 -----------------------------------------------------------------
    def regressions(ret_series, period):
        y = period_slice(excess(ret_series), period)
        spy_ex, ief_ex = excess(spy_r), excess(ief_r)
        X2 = pd.DataFrame({"SPY": spy_ex, "IEF": ief_ex})
        out = {"R2": alpha_regression(y, period_slice(X2.dropna(), period)),
               "R3": alpha_regression(y, period_slice(pd.concat([X2, mom.rename("MOM")], axis=1).dropna(), period))}
        b2_ex = excess(rets["B2"])
        out["R1"] = alpha_regression(y, period_slice(pd.DataFrame({"B2": b2_ex}), period)) if ret_series is not rets["B2"] else None
        # R4: strategy excess on the equal-weight-universe excess = alpha beyond simply holding everything
        out["R4"] = (alpha_regression(y, period_slice(pd.DataFrame({"B3": excess(rets["B3"])}), period))
                     if ret_series is not rets["B3"] else None)
        return out

    alpha_rows, reg = [], {}
    for name in names:
        for period in PERIODS:
            reg[(name, period)] = regressions(rets[name], period)
            for model, res in reg[(name, period)].items():
                if res is None:
                    continue
                alpha_rows.append({"name": name, "period": period, "model": model, **res})
    alpha = pd.DataFrame(alpha_rows)
    alpha.to_csv(os.path.join(out_dir, "etf_alpha.csv"), index=False)

    # ---- bootstrap CIs for the Sharpe difference (core strategies vs B1 and B2) ------------------
    boot = []
    for period in PERIODS:
        strategies = {c: period_slice(excess(rets[c]), period) for c in CORE}
        benchmarks = {b: period_slice(excess(rets[b]), period) for b in ("B1", "B2")}
        df = bootstrap_sharpe_diff(strategies, benchmarks, n_boot=n_boot)
        df["period"] = period
        boot.append(df)
    boot = pd.concat(boot, ignore_index=True)
    boot.to_csv(os.path.join(out_dir, "etf_bootstrap.csv"), index=False)

    # ---- sensitivities: 10 bps (all), 25 bps (core + benchmarks), no lag (core) ------------------
    sens_curves = {}
    for name, sid, m in CONFIGS:
        sens_curves[(name, "10bps")] = run_one(prices, STRATS[sid], {"lookback": LOOKBACK_DAYS[m], "skip": SKIP},
                                               10, 1, first_rb, eval_start)[0]
    for b, (cls, kw) in BENCH.items():
        for bps in (10, 25):
            sens_curves[(b, f"{bps}bps")] = run_one(prices, cls, kw, bps, 1, first_rb, eval_start)[0]
    for name, sid, m in CONFIGS:
        if name in CORE:
            kw = {"lookback": LOOKBACK_DAYS[m], "skip": SKIP}
            sens_curves[(name, "25bps")] = run_one(prices, STRATS[sid], kw, 25, 1, first_rb, eval_start)[0]
            sens_curves[(name, "no lag")] = run_one(prices, STRATS[sid], kw, 5, 0, first_rb, eval_start)[0]
    sens_rows = []
    for name in names:
        variants = {"base (5bps, lag 1)": curves[name]}
        variants.update({v: c for (n, v), c in sens_curves.items() if n == name})
        for v, c in variants.items():
            r = c.pct_change().dropna()
            ex = excess(r)
            pm = price_metrics(r)
            res = regressions(r, "full")["R2"]
            sens_rows.append({"name": name, "variant": v, "CAGR": pm["CAGR"], "Max drawdown": pm["Max drawdown"],
                              "Sharpe (excess RF)": sharpe(ex.values), "R2 alpha": res["alpha"], "R2 alpha t": res["alpha_t"]})
    sens = pd.DataFrame(sens_rows)
    sens.to_csv(os.path.join(out_dir, "etf_sensitivity.csv"), index=False)

    # ---- deflated Sharpe + pre-registered criterion ---------------------------------------------
    ex_full = {c[0]: excess(rets[c[0]]) for c in CONFIGS}
    sr_trials = [e.mean() / e.std(ddof=1) for e in ex_full.values()]
    crit_rows = []
    for name, _, _ in CONFIGS:
        e = ex_full[name]
        sk, ku = moments(e.values)
        dsr = deflated_sharpe(e.mean() / e.std(ddof=1), len(e), sk, ku, sr_trials, N_TRIALS)
        r10 = regressions(sens_curves[(name, "10bps")].pct_change().dropna(), "full")["R2"]
        verdict = evidence_of_alpha(reg[(name, "full")]["R2"], reg[(name, "design")]["R2"],
                                    reg[(name, "holdout")]["R2"], dsr, r10)
        crit_rows.append({"name": name, "R2 alpha (full)": reg[(name, "full")]["R2"]["alpha"],
                          "R2 t (full)": reg[(name, "full")]["R2"]["alpha_t"],
                          "R2 alpha design": reg[(name, "design")]["R2"]["alpha"],
                          "R2 alpha holdout": reg[(name, "holdout")]["R2"]["alpha"],
                          "DSR": dsr, "R2 t @10bps": r10["alpha_t"],
                          **{k: v for k, v in verdict["checks"].items()}, "EVIDENCE OF ALPHA": verdict["passes_all"],
                          "R4 alpha (full)": reg[(name, "full")]["R4"]["alpha"],
                          "R4 t (full)": reg[(name, "full")]["R4"]["alpha_t"]})
    crit = pd.DataFrame(crit_rows)
    crit.to_csv(os.path.join(out_dir, "etf_criterion.csv"), index=False)

    # ---- crisis windows (price-only) -------------------------------------------------------------
    windows = {"2008 (calendar yr)": ("2007-12-31", "2008-12-31"), "COVID crash (Feb 19-Mar 23 2020)": ("2020-02-19", "2020-03-23"),
               "2022 (calendar yr)": ("2021-12-31", "2022-12-30")}
    crisis = pd.DataFrame({k: {n: curves[n].asof(pd.Timestamp(b)) / curves[n].asof(pd.Timestamp(a)) - 1 for n in names}
                           for k, (a, b) in windows.items()})
    crisis.to_csv(os.path.join(out_dir, "etf_crisis_windows.csv"))

    report(metrics, alpha, boot, sens, crit, crisis, names, eval_start, prices)
    return dict(metrics=metrics, alpha=alpha, boot=boot, sens=sens, crit=crit, crisis=crisis)


def pct(x):
    return "" if pd.isna(x) else f"{x:.1%}"


def report(metrics, alpha, boot, sens, crit, crisis, names, eval_start, prices):
    core_rows = CORE + list(BENCH)
    for period in PERIODS:
        t = metrics.xs(period, level="period").loc[core_rows]
        print(f"\n{'=' * 110}\nMETRICS: {period.upper()} (core 12-month strategies and benchmarks)\n{'=' * 110}")
        show = pd.DataFrame({"Total": t["Total return"].map(pct), "CAGR": t["CAGR"].map(pct),
                             "Sharpe(ex RF)": t["Sharpe (excess RF)"].map("{:.2f}".format),
                             "Vol": t["Ann. vol"].map(pct), "MaxDD": t["Max drawdown"].map(pct),
                             "Calmar": t["Calmar"].map("{:.2f}".format), "Worst10d": t["Worst 10-day"].map(pct),
                             "Corr SPY": t["Corr SPY"].map("{:.2f}".format), "Corr 60/40": t["Corr 60/40"].map("{:.2f}".format)})
        if period == "full":
            show["Turnover/yr"] = t["Turnover / yr"].map(lambda v: f"{v:.1f}x")
        print(show.to_string())
    g = metrics.xs("full", level="period").loc[[c[0] for c in CONFIGS]]
    print(f"\n{'=' * 110}\nLOOKBACK GRID, full period (reported, never used to pick a winner)\n{'=' * 110}")
    print(pd.DataFrame({"CAGR": g["CAGR"].map(pct), "Sharpe(ex RF)": g["Sharpe (excess RF)"].map("{:.2f}".format),
                        "MaxDD": g["Max drawdown"].map(pct)}).to_string())
    a = alpha[alpha.model == "R2"].pivot(index="name", columns="period", values=["alpha", "alpha_t"]).loc[names]
    print(f"\n{'=' * 110}\nR2 ALPHA (vs SPY + IEF excess returns), annualised, HAC t-stat\n{'=' * 110}")
    print(pd.DataFrame({f"{p} alpha": a[("alpha", p)].map(pct) for p in PERIODS}
                       | {f"{p} t": a[("alpha_t", p)].map("{:.2f}".format) for p in PERIODS}).to_string())
    print(f"\n{'=' * 110}\nBOOTSTRAP 95% CI of Sharpe difference (stationary bootstrap, mean block 21d)\n{'=' * 110}")
    b = boot.copy()
    for c in ("sharpe_diff", "ci_low", "ci_high"):
        b[c] = b[c].map("{:.2f}".format)
    b["share_le_0"] = b["share_le_0"].map("{:.3f}".format)
    print(b[["period", "strategy", "benchmark", "sharpe_diff", "ci_low", "ci_high", "share_le_0"]].to_string(index=False))
    print(f"\n{'=' * 110}\nPRE-REGISTERED CRITERION (all four checks required)\n{'=' * 110}")
    c = crit.copy()
    for col in ("R2 alpha (full)", "R2 alpha design", "R2 alpha holdout"):
        c[col] = c[col].map(pct)
    c["R2 t (full)"] = c["R2 t (full)"].map("{:.2f}".format)
    c["R2 t @10bps"] = c["R2 t @10bps"].map("{:.2f}".format)
    c["DSR"] = c["DSR"].map("{:.3f}".format)
    for col in c.columns[7:11]:
        c[col] = c[col].map(lambda v: "yes" if v else "NO")
    c["EVIDENCE OF ALPHA"] = c["EVIDENCE OF ALPHA"].map(lambda v: "YES" if v else "no")
    c["R4 alpha (full)"] = c["R4 alpha (full)"].map(pct)
    c["R4 t (full)"] = c["R4 t (full)"].map("{:.2f}".format)
    c.columns = [x[:3] + "..." if x[:2] in ("1.", "2.", "3.", "4.") else x for x in c.columns]
    print(c.to_string(index=False))
    print(f"\n{'=' * 110}\nSENSITIVITY: cost and execution lag (full period)\n{'=' * 110}")
    s = sens[sens.name.isin(CORE + list(BENCH))].copy()
    s["CAGR"] = s["CAGR"].map(pct); s["Max drawdown"] = s["Max drawdown"].map(pct)
    s["Sharpe (excess RF)"] = s["Sharpe (excess RF)"].map("{:.2f}".format)
    s["R2 alpha"] = s["R2 alpha"].map(pct); s["R2 alpha t"] = s["R2 alpha t"].map("{:.2f}".format)
    print(s.to_string(index=False))
    print(f"\n{'=' * 110}\nSTRESS WINDOWS (price-only returns)\n{'=' * 110}")
    print(crisis.loc[core_rows].map(pct).to_string())


# ---- synthetic self-test ---------------------------------------------------------------------------
def synthetic():
    rng = np.random.default_rng(5)
    idx = pd.bdate_range("2005-01-03", "2019-12-31")
    n = len(idx)
    cols = {}
    for i in range(10):
        cols[f"E{i}"] = 100 * np.exp(np.cumsum(rng.normal(0.0003 - 0.00004 * i, 0.009 + 0.001 * i, n)))
    cols["SPY"] = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.010, n)))
    cols["IEF"] = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.004, n)))
    cols["SHY"] = 100 * np.exp(np.cumsum(rng.normal(0.00008, 0.0006, n)))
    late = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, n)))
    late[:900] = np.nan
    cols["LATE"] = late
    prices = pd.DataFrame(cols, index=idx)
    fidx = idx[idx <= "2019-06-28"]
    f = pd.DataFrame({"Mkt-RF": rng.normal(0.03, 1.0, len(fidx)), "SMB": rng.normal(0, 0.5, len(fidx)),
                      "HML": rng.normal(0, 0.5, len(fidx)), "RMW": rng.normal(0, 0.4, len(fidx)),
                      "CMA": rng.normal(0, 0.4, len(fidx)), "RF": 0.01, "MOM": rng.normal(0.02, 0.7, len(fidx))}, index=fidx)
    return prices, f


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        prices, f = synthetic()
        out = tempfile.mkdtemp(prefix="etf_selftest_")
        res = main(prices, f, out, n_boot=400)
        files = sorted(os.listdir(out))
        assert len(files) == 7 and len(res["crit"]) == 13 and res["alpha"]["alpha"].notna().all()
        assert res["alpha"][res["alpha"].model == "R4"]["alpha"].notna().all() and res["boot"]["ci_low"].notna().all() and res["metrics"]["Total return"].notna().all()
        print(f"\nSELFTEST OK: wrote {files} to {out}")
    else:
        prices = pd.read_csv(os.path.join(ROOT, "data", "prices_etf.csv"), index_col=0, parse_dates=True)
        factors = pd.read_csv(os.path.join(ROOT, "data", "ff_factors_daily.csv"), index_col=0, parse_dates=True)
        main(prices, factors, os.path.join(ROOT, "analysis", "output"))
