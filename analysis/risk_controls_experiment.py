"""
Fixed-variant experiment: does capping concentration / de-risking on drawdowns help MomentumStrategy?

The four variants and their parameters were chosen BEFORE running and are not tuned.
All variants are reported, including the ones that look worse.

Evaluation window starts on the day BEFORE the strategy's first possible trade (after the
252+21 day warm-up) for the strategies AND the buy-and-hold benchmark, so both are invested
over the same dates. (The original README comparison included the cash-only warm-up for the
strategies but not the benchmark.)

Run from the project root:  python analysis/risk_controls_experiment.py
"""
import contextlib
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
import pandas as pd

from backtester.engine import Backtester
from data.sectors import SECTORS
from strategies.momentum import MomentumStrategy

PERIODS = {
    "2015-2024 (bull)": "data/prices.csv",
    "2007-2012 (crisis, holdout)": "data/prices_crisis.csv",
}
BASE = dict(lookback_days=252, skip_days=21, top_pct=0.15,
            target_total_weight=0.90, weighting="momentum_score")
CAPS = dict(max_position_weight=0.10, max_sector_weight=0.30, sector_map=SECTORS)
VARIANTS = {
    "A. Baseline (no controls)": {},
    "B. Position cap 10%": dict(max_position_weight=0.10),
    "C. B + sector cap 30%": dict(CAPS),
    "D. C + drawdown rule": dict(CAPS, drawdown_trigger=0.10, drawdown_scale=0.5, drawdown_reentry=0.05),
}
STARTING_CASH = 100_000
WARMUP = BASE["lookback_days"] + BASE["skip_days"] + 1   # rows needed before first trade


def metrics(equity: pd.Series) -> dict:
    rets = equity.pct_change().dropna()
    years = len(rets) / 252
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1
    mdd = (equity / equity.cummax() - 1).min()
    worst_10d = (equity / equity.shift(10) - 1).min()
    return {
        "Total return": equity.iloc[-1] / equity.iloc[0] - 1,
        "CAGR": cagr,
        "Sharpe": rets.mean() / rets.std() * np.sqrt(252) if rets.std() > 0 else 0.0,
        "Ann. vol": rets.std() * np.sqrt(252),
        "Max drawdown": mdd,
        "Calmar": cagr / abs(mdd) if mdd < 0 else np.nan,
        "Worst 10-day": worst_10d,
    }


def run_variant(prices, params):
    strategy = MomentumStrategy(**BASE, **params)
    bt = Backtester(prices, strategy, starting_cash=STARTING_CASH)
    traded = []
    original = bt.portfolio.execute_trade

    def counted(ticker, shares, price, side):
        cash_before = bt.portfolio.cash
        original(ticker=ticker, shares=shares, price=price, side=side)
        if bt.portfolio.cash != cash_before:          # trade actually executed
            traded.append(shares * price)

    bt.portfolio.execute_trade = counted
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        equity = bt.run()["total_value"]
    return equity, strategy, traded, buf.getvalue().count("Insufficient")


def main():
    os.makedirs(os.path.join(ROOT, "analysis", "output"), exist_ok=True)
    for period, path in PERIODS.items():
        prices = pd.read_csv(os.path.join(ROOT, path), index_col=0, parse_dates=True)
        start = WARMUP - 2            # last all-cash day (0-based index) before the first trade
        rows, curves = {}, {}
        for name, params in VARIANTS.items():
            equity, strat, traded, skipped = run_variant(prices, params)
            window = equity.iloc[start:]
            m = metrics(window)
            years = (len(window) - 1) / 252
            m["Trades"] = len(traded)
            m["Turnover / yr"] = sum(traded) / window.mean() / years
            m["Skipped (cash)"] = skipped
            m["De-risk events"] = strat.derisk_events
            m["Days de-risked"] = strat.derisk_days
            rows[name] = m
            curves[name] = equity
            if name.startswith("A."):
                full_original = equity.iloc[-1] / STARTING_CASH - 1

        # equal-weight buy-and-hold benchmark, invested from the same start date
        px = prices.iloc[start:]
        shares = (STARTING_CASH / px.shape[1]) / px.iloc[0]
        bench = (px * shares).sum(axis=1)
        rows["Benchmark: equal-weight buy & hold"] = metrics(bench)
        curves["Benchmark"] = bench

        table = pd.DataFrame(rows).T
        tag = period.split()[0]
        table.to_csv(os.path.join(ROOT, "analysis", "output", f"risk_controls_{tag}.csv"))
        pd.DataFrame(curves).to_csv(os.path.join(ROOT, "analysis", "output", f"equity_curves_{tag}.csv"))

        print(f"\n{'=' * 100}\n{period}   window: {px.index[0].date()} -> {px.index[-1].date()} "
              f"({prices.shape[1]} tickers)\n{'=' * 100}")
        pct = ["Total return", "CAGR", "Ann. vol", "Max drawdown", "Worst 10-day"]
        shown = table.copy()
        for c in pct:
            shown[c] = shown[c].map("{:.1%}".format)
        shown["Sharpe"] = shown["Sharpe"].map("{:.2f}".format)
        shown["Calmar"] = shown["Calmar"].map("{:.2f}".format)
        shown["Turnover / yr"] = shown["Turnover / yr"].map(lambda v: "" if pd.isna(v) else f"{v:.1f}x")
        for c in ["Trades", "Skipped (cash)", "De-risk events", "Days de-risked"]:
            shown[c] = shown[c].map(lambda v: "" if pd.isna(v) else f"{int(v)}")
        print(shown.to_string())
        print(f"\n(Original full-period method, baseline: {full_original:.1%} total return, "
              f"including the cash-only warm-up.)")


if __name__ == "__main__":
    main()
