"""
Statistical tools for the pre-registered ETF protocol (research/etf_momentum_protocol.md):
HAC alpha regressions, stationary bootstrap of Sharpe differences, deflated Sharpe ratio,
and the four-part "evidence of alpha" criterion.
"""
import os
import sys
from statistics import NormalDist

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from analysis.factor_attribution import ols_hac

EULER_GAMMA = 0.5772156649015329


def alpha_regression(y: pd.Series, X: pd.DataFrame, lags: int = 5) -> dict:
    """y and the columns of X are daily EXCESS returns. Returns annualised alpha, its HAC t-stat,
    the betas, R^2 and N."""
    df = pd.concat([y.rename("y"), X], axis=1, join="inner").dropna()
    res = ols_hac(df["y"].values, df[list(X.columns)].values, lags)
    out = {"alpha": res["beta"][0] * 252, "alpha_t": res["t"][0], "r2": res["r2"], "n": res["n"]}
    for i, c in enumerate(X.columns, start=1):
        out[f"beta_{c}"] = res["beta"][i]
    return out


def sharpe(excess: np.ndarray, periods: int = 252) -> float:
    s = excess.std(ddof=1)
    return excess.mean() / s * np.sqrt(periods) if s > 0 else 0.0


def _stationary_indices(n: int, n_boot: int, mean_block: int, rng) -> np.ndarray:
    """Politis-Romano stationary bootstrap index paths (geometric block lengths)."""
    p = 1.0 / mean_block
    idx = np.empty((n_boot, n), dtype=np.int32)
    idx[:, 0] = rng.integers(0, n, n_boot)
    jump = rng.random((n_boot, n)) < p
    new = rng.integers(0, n, (n_boot, n))
    for t in range(1, n):
        idx[:, t] = np.where(jump[:, t], new[:, t], (idx[:, t - 1] + 1) % n)
    return idx


def bootstrap_sharpe_diff(strategies: dict, benchmarks: dict, n_boot: int = 10_000,
                          mean_block: int = 21, seed: int = 2026, chunk: int = 1000) -> pd.DataFrame:
    """
    strategies / benchmarks: {name: daily excess return Series} on a COMMON date index.
    The same resampled date paths are used for every series, so differences are paired.
    Returns, for every strategy x benchmark: observed annualised Sharpe difference, 95% CI, and the
    share of resamples with difference <= 0.
    """
    names = list(strategies) + list(benchmarks)
    frame = pd.concat([pd.Series(v, name=k) for k, v in {**strategies, **benchmarks}.items()], axis=1).dropna()
    data = frame.values
    n = len(frame)
    rng = np.random.default_rng(seed)
    diffs = {(s, b): [] for s in strategies for b in benchmarks}
    pos = {k: i for i, k in enumerate(frame.columns)}
    done = 0
    while done < n_boot:
        m = min(chunk, n_boot - done)
        idx = _stationary_indices(n, m, mean_block, rng)
        sr = {}
        for k, j in pos.items():
            x = data[:, j][idx]                                   # m x n resampled path
            sd = x.std(axis=1, ddof=1)
            sr[k] = np.where(sd > 0, x.mean(axis=1) / sd * np.sqrt(252), 0.0)
        for (s, b) in diffs:
            diffs[(s, b)].append(sr[s] - sr[b])
        done += m
    rows = []
    for (s, b), parts in diffs.items():
        d = np.concatenate(parts)
        obs = sharpe(frame[s].values) - sharpe(frame[b].values)
        rows.append({"strategy": s, "benchmark": b, "sharpe_diff": obs,
                     "ci_low": np.percentile(d, 2.5), "ci_high": np.percentile(d, 97.5),
                     "share_le_0": float((d <= 0).mean())})
    return pd.DataFrame(rows)


def expected_max_sharpe(sr_trials, n_trials: int) -> float:
    """SR0: the Sharpe ratio expected from the best of n_trials skill-less trials (daily units)."""
    if n_trials <= 1:
        return 0.0
    nd = NormalDist()
    v = float(np.var(np.asarray(sr_trials, dtype=float), ddof=1))
    return np.sqrt(v) * ((1 - EULER_GAMMA) * nd.inv_cdf(1 - 1 / n_trials)
                         + EULER_GAMMA * nd.inv_cdf(1 - 1 / (n_trials * np.e)))


def deflated_sharpe(sr: float, T: int, skew: float, kurt: float, sr_trials, n_trials: int) -> float:
    """
    Bailey & Lopez de Prado (2014). All Sharpe ratios in DAILY units; kurt is raw kurtosis (normal=3).
    Returns the probability that the true Sharpe exceeds the best-of-n_trials noise level SR0.
    """
    sr0 = expected_max_sharpe(sr_trials, n_trials)
    denom = np.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr ** 2))
    return NormalDist().cdf((sr - sr0) * np.sqrt(T - 1) / denom)


def moments(x: np.ndarray):
    z = (x - x.mean()) / x.std(ddof=0)
    return float((z ** 3).mean()), float((z ** 4).mean())


def evidence_of_alpha(r2_full, r2_design, r2_holdout, dsr, r2_10bps) -> dict:
    """Pre-registered four-part criterion. Each input is an alpha_regression() dict (or a float for dsr)."""
    checks = {
        "1. R2 alpha>0 and HAC t>=2.0 (full)": r2_full["alpha"] > 0 and r2_full["alpha_t"] >= 2.0,
        "2. R2 alpha>0 in design AND holdout": r2_design["alpha"] > 0 and r2_holdout["alpha"] > 0,
        "3. Deflated Sharpe prob >= 0.95": dsr >= 0.95,
        "4. R2 alpha>0 and t>=2.0 at 10bps": r2_10bps["alpha"] > 0 and r2_10bps["alpha_t"] >= 2.0,
    }
    return {"checks": checks, "passes_all": all(checks.values())}
