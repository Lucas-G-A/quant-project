"""
Factor attribution: how much of each strategy's return is alpha vs. exposure to known factors?

Regresses daily excess returns on the Fama-French 5 factors + momentum (Ken French data library):
    (r - RF) = alpha + b1*Mkt-RF + b2*SMB + b3*HML + b4*RMW + b5*CMA + b6*MOM + e
Standard errors are Newey-West (HAC), 5 lags. Alpha is annualized (x252).

Reads the equity curves written by analysis/risk_controls_experiment.py, so run that first.
Needs internet access to download the factor files from Ken French's site, or pass two local files:
    python analysis/factor_attribution.py
    python analysis/factor_attribution.py FF5_daily.csv MOM_daily.csv

Caveat: French's data is published with a lag (often a month or more), so recent live periods
are usually not covered. This script is for the backtest periods.
"""
import io
import os
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
import pandas as pd

BASE_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FF5_URL = BASE_URL + "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip"
MOM_URL = BASE_URL + "F-F_Momentum_Factor_daily_CSV.zip"
FACTORS = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "MOM"]
PERIOD_TAGS = ["2015-2024", "2007-2012"]


def parse_french_csv(text: str) -> pd.DataFrame:
    """Parses Ken French's daily CSV format: description lines, a header line starting with a
    comma, then YYYYMMDD rows, then a blank line / annual section we ignore."""
    cols, rows, started = None, [], False
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        is_data = len(parts[0]) == 8 and parts[0].isdigit()
        if not started:
            if parts[0] == "" and len(parts) >= 2 and any(parts[1:]):
                cols = parts[1:]
            if not is_data:
                continue
            started = True
        if not is_data:
            break
        rows.append(parts)
    if cols is None or not rows:
        raise ValueError("Could not parse factor file")
    index = pd.to_datetime([r[0] for r in rows], format="%Y%m%d")
    data = [[float(x) for x in r[1:1 + len(cols)]] for r in rows]
    return pd.DataFrame(data, index=index, columns=cols)


def load_french(source: str) -> pd.DataFrame:
    """source: a URL to a zip, or a path to a local .csv / .zip."""
    if source.startswith("http"):
        raw = urllib.request.urlopen(source, timeout=60).read()
        zf = zipfile.ZipFile(io.BytesIO(raw))
        text = zf.read(zf.namelist()[0]).decode("latin-1")
    elif source.lower().endswith(".zip"):
        zf = zipfile.ZipFile(source)
        text = zf.read(zf.namelist()[0]).decode("latin-1")
    else:
        text = open(source, encoding="latin-1").read()
    return parse_french_csv(text)


def ols_hac(y: np.ndarray, X: np.ndarray, lags: int = 5) -> dict:
    """OLS with an intercept and Newey-West standard errors. Returns coefficients, t-stats, R^2."""
    X = np.column_stack([np.ones(len(X)), X])
    xtx_inv = np.linalg.inv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    u = y - X @ beta
    Xu = X * u[:, None]
    S = Xu.T @ Xu
    for lag in range(1, lags + 1):
        w = 1 - lag / (lags + 1)
        G = Xu[lag:].T @ Xu[:-lag]
        S += w * (G + G.T)
    cov = xtx_inv @ S @ xtx_inv
    se = np.sqrt(np.diag(cov))
    r2 = 1 - (u @ u) / ((y - y.mean()) @ (y - y.mean()))
    return {"beta": beta, "t": beta / se, "r2": r2, "n": len(y)}


def attribute(equity: pd.Series, factors: pd.DataFrame, lags: int = 5):
    rets = equity.pct_change().dropna().rename("r")
    df = pd.concat([rets, factors], axis=1, join="inner").dropna()
    if len(df) < 250:
        return None
    res = ols_hac((df["r"] - df["RF"]).values, df[FACTORS].values, lags)
    out = {"Alpha (ann.)": res["beta"][0] * 252, "Alpha t": res["t"][0]}
    for i, f in enumerate(FACTORS, start=1):
        out[f"b_{f}"] = res["beta"][i]
        out[f"t_{f}"] = res["t"][i]
    out["R2"] = res["r2"]
    out["N days"] = res["n"]
    return out


def main():
    if len(sys.argv) == 3:
        ff5, mom = load_french(sys.argv[1]), load_french(sys.argv[2])
    else:
        print("Downloading factor files from Ken French's data library...")
        ff5, mom = load_french(FF5_URL), load_french(MOM_URL)
    mom.columns = ["MOM"]
    factors = ff5.join(mom, how="inner") / 100.0          # percent -> decimal
    print(f"Factor data: {factors.index[0].date()} -> {factors.index[-1].date()}")

    all_rows = {}
    for tag in PERIOD_TAGS:
        path = os.path.join(ROOT, "analysis", "output", f"equity_curves_{tag}.csv")
        curves = pd.read_csv(path, index_col=0, parse_dates=True)
        window = curves["Benchmark"].dropna().index          # aligned evaluation window
        print(f"\n=== {tag} ===")
        rows = {}
        for col in curves.columns:
            res = attribute(curves.loc[window, col], factors)
            if res is None:
                print(f"  {col}: factor data does not cover enough of this window; skipped")
                continue
            rows[col] = res
            all_rows[(tag, col)] = res
        if rows:
            table = pd.DataFrame(rows).T
            show = table.copy()
            show["Alpha (ann.)"] = show["Alpha (ann.)"].map("{:.1%}".format)
            for c in show.columns:
                if c.startswith(("b_", "t_")) or c in ("Alpha t", "R2"):
                    show[c] = show[c].map("{:.2f}".format)
            print(show.to_string())
    if all_rows:
        pd.DataFrame(all_rows).T.to_csv(os.path.join(ROOT, "analysis", "output", "factor_attribution.csv"))
        print("\nSaved analysis/output/factor_attribution.csv")
        print("Read it as: alpha t-stat above ~2 suggests alpha not explained by these factors; "
              "a large b_MOM with ~0 alpha means the strategy is mostly the known momentum factor.")


if __name__ == "__main__":
    main()
