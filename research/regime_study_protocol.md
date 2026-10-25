# Regime Study (v2): Do Trend and Momentum Help When the Market Is Down? Pre-Registered Protocol

Written 2026-10-24, **before any v2 strategy run or regime test on real data.** Commit this file before
running anything. Changes made after results are seen go in "Deviations" at the bottom. The v1 study
(`research/etf_momentum_protocol.md` and its results) is frozen and is not modified by v2.

## Question

Not "will there be a recession" (that cannot be forecast here), but: **historically, did the v1 strategies
behave differently when the market was in a bear regime, and is that difference reliable?**

## Honest framing of the evidence

- Hypotheses below were motivated partly by v1 outputs I have already seen (S2 lost less in 2008 and 2020,
  S1 gained in 2022). The 2005-2026 sample is therefore **exploratory**. It cannot confirm anything.
- The **confirmatory** sample is 2000-02 to 2004-12 (ETF history that no analysis of ours has touched). It
  contains **one bear-market episode** (the dot-com bust), so statistical power is low. A non-significant
  confirmatory result means "not established", not "no effect".
- Regime-conditional results rest on very few independent episodes (about 4 to 5 across both samples).

## Data (all prices already downloaded; no strategy results viewed for the confirmatory sample)

- Exploratory: `data/prices_etf.csv`, v1 equity curves in `analysis/output/etf_equity_curves.csv`
  (S1-S4 12-month and B1, B2 are NOT re-run), evaluation 2005-02-28 to 2026-10-23.
- Confirmatory: `data/prices_etf_pre2005.csv` (adjusted closes, 1993 to 2004-12-31). ETFs that did not yet
  exist are NaN and join the universe when they have a full lookback. SHY did not exist before 2002-07, so
  **SHY is replaced by a T-bill index built from Ken French's daily RF for the whole confirmatory sample**
  (`data/ff_factors_daily.csv`). Bonds (TLT, IEF, LQD, AGG, TIP) enter 2002-2004; no commodity or REIT ETFs.
- Because tiny universes make "top 5" meaningless, the confirmatory run requires **at least 15 eligible ETFs**
  before the first rebalance (v1 used 5). First rebalance is 2000-02-01 with 17 ETFs; 59 monthly returns.
- Data checks done before registering: large daily moves checked against known events (EWW 1997-10-27,
  QQQ 2001-01-03, EWY 2001-09-17 are real; no cleaning applied). Early country ETFs trade thinly: 8% to 15%
  of days have an unchanged close (SPY 1.5%). Disclosed as a limitation, no adjustment made.
- Not used: macro data (inflation, unemployment, GDP, yields from FRED). The download failed and those series
  are revised after publication, so they need point-in-time vintages. Deferred to a separate v3 protocol.

## Strategies and benchmarks (unchanged code from v1; same costs: 5 bps slippage, zero commission, one-day lag)

S1, S2, S3, S4 at the 12-month lookback exactly as in v1. Benchmarks: B1 SPY buy and hold; **B2c = 60% SPY /
40% cash (SHY or the T-bill index)**; B2 = 60% SPY / 40% IEF (exploratory sample only, IEF starts 2002).
No lookback grid in v2. The only new code is B2c (`strategies/etf_regime_benchmarks.py`) and the study runner.

## Regime definitions (fixed now, known at the prior month-end, no look-ahead)

- **BEAR** at month-end m: SPY is at least 10% below its running peak AND SPY's trailing 12-month return is
  negative. Applied to month m+1's return. (A peak-only rule was rejected because it flagged the whole
  2003-2004 recovery; I saw that by counting SPY-only flagged months, never strategy returns.)
  Counts: confirmatory 30 of 59 months (2000: 1, 2001: 12, 2002: 11, 2003: 6); exploratory 33 of 260 months
  (2008: 10, 2009: 10, 2019: 1, 2020: 1, 2022: 7, 2023: 4).
- **RATES-UP** at month-end m: IEF's trailing 12-month total return is negative. Exploratory sample only.

## Hypotheses and tests (monthly returns; excess returns use French RF; primary strategy is S2)

- **H1 (convexity, confirmatory):** regress S2's monthly excess return on SPY's monthly excess return and a
  down-market term: `r_S2 = a + b*r_SPY + g*max(-r_SPY, 0) + e`. Prediction: **g > 0** (less downside than
  upside exposure). Newey-West standard errors, 3 monthly lags, one-sided test.
- **H2 (bear-regime outperformance, confirmatory):** active return `a_t = r_S2 - r_B2c`. Statistic
  `D = mean(a_t | BEAR) - mean(a_t | not BEAR)`. Prediction: **D > 0**. Inference by stationary bootstrap
  (mean block 12 months, 10,000 resamples, seed 2026) resampling `(a_t, BEAR_t)` pairs jointly; one-sided
  p = share of resamples with D <= 0. Also report the 95% interval.
- **H3 (rising-rate regime, exploratory only, no clean holdout possible):** same statistic as H2 using the
  RATES-UP flag and active return vs B2 (SPY/IEF), for S2 and S1. Reported, not tested for significance.

**Confirmatory rule:** H1 and H2 are the only two confirmatory tests. Multiple-testing correction: each must
reach **one-sided p <= 0.025** (Bonferroni for 2 tests) in the confirmatory sample AND have the same sign in
the exploratory sample to count as "confirmed". Anything else is "not established". The pooled 2000-2026
estimate is reported as a summary but does not decide confirmation.

## What I will not claim

- No forecast of recessions or of future returns. Current regime status may be shown as a descriptive readout.
- "Works when the market is down" is claimed only if H2 is confirmed as defined above. Descriptive tables
  (mean, volatility, worst month, hit rate by regime for S1-S4, B1, B2c) are for context, never as discoveries.
- S1, S3, S4 results are secondary and will be labelled as such.

## Process rules

- Pipeline tested on synthetic data only (`--selftest`); the real run is executed once, after this file is committed.
- All results reported, including failures. Bugs found after results are fixed, everything re-run, fix logged below.

## Deviations

(none yet)
