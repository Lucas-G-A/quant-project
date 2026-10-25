# ETF Momentum / Trend Research: Pre-Registered Protocol

Written 2026-10-24, **before any strategy was backtested on the ETF data.** Committing this file
before running results is what makes later claims about alpha verifiable. Any change after results
are seen must be listed in a "Deviations" section at the bottom, with the reason, and results
before and after the change must both be reported.

## Purpose

Test whether simple, literature-standard momentum and trend strategies on a liquid ETF universe
produce alpha, meaning return that is not explained by market exposure, bond exposure or known
factors, after realistic costs and after accounting for the number of variants tried. A clean
"no evidence of alpha" is an acceptable and reportable outcome.

## Data (inspected for quality only, no strategy results viewed)

- `data/prices_etf.csv`: yfinance adjusted daily closes (dividends reinvested), 38 ETFs,
  2004-01-02 to 2026-10-23. No gaps, no non-positive prices; extreme daily moves checked against
  known events and cross-asset consistency.
- **Cash / safe asset:** SHY. It is excluded from every risky universe and used only to park
  unallocated weight.
- **Risky universe (37 ETFs):** XLB XLE XLF XLI XLK XLP XLU XLV XLY SPY QQQ IWM MDY IWD IWF
  EFA EEM EWJ EWZ EWW EWG EWU EWC EWA FXI EWY TLT IEF LQD AGG TIP HYG GLD SLV DBC USO VNQ.
- An ETF becomes eligible only once it has a full 12-1 lookback of its own history, so the universe
  grows over time (HYG, DBC, SLV, USO enter 2006-2007 plus lookback).
- **Known residual bias:** the ETF list was chosen today from funds that are large and liquid
  today. This is far milder than single-stock survivorship but not zero.
- Factor data: Ken French daily FF5 + momentum, saved to `data/ff_factors_daily.csv`.
  The factor file ends 2026-08-31 (French publishes with a lag), so the holdout's last two months
  have prices but no factor or RF data. **Alpha regressions, bootstrap and Sharpe ratios that use RF
  are computed through 2026-08-31 only; price-only metrics (returns, drawdown, turnover) use data
  through 2026-10-23.** This was decided before any ETF strategy result was seen.

## Strategies (parameters from the literature, fixed, not tuned)

Common rules: rebalance on the first trading day of each month; **signals use closes through the
prior day, trades execute at the rebalance day's close (one-day lag)**; signal = 12-1 month return
(252-day lookback, skip the most recent 21 days); 98% target invested, remainder cash; cost
5 bps slippage per trade, zero commission; starting capital 100,000; no-trade band 0.5% of
portfolio value.

| ID | Strategy | Rule |
|---|---|---|
| S1 | Cross-sectional momentum | Hold the top 5 eligible ETFs by 12-1 return, equal weight. |
| S2 | Time-series trend | Split capital equally across all eligible ETFs; hold an ETF only if its 12-1 return > 0, otherwise that slice goes to SHY. |
| S3 | Dual momentum | Top 5 by 12-1 return, equal weight; any of them with 12-1 return <= 0 is replaced by SHY. |
| S4 | Risk-managed S3 | S3 selection, weights proportional to 1 / 63-day volatility (prior-close data) across the 5 selected; failed slices go to SHY. |

**Robustness grid (reported, never used to pick a winner):** lookback in {3, 6, 9, 12} months
(63, 126, 189, 252 trading days, always skipping 21) for S1, S2, S3. That adds 9 configurations
beyond the 12-month core.
**Total configurations tried: N_trials = 13** (S1-S4 at 12 months plus 9 grid variants).

## Benchmarks (same engine, same costs, same start date)

- B1: SPY buy and hold
- B2: 60/40, 60% SPY / 40% IEF, rebalanced monthly
- B3: equal-weight of all eligible risky ETFs, rebalanced monthly

**Common evaluation start:** the close before the first rebalance at which at least 5 risky ETFs
are eligible. Strategies and benchmarks are all evaluated from that same date.

## Periods

- Design period: start to 2016-12-31. Used for debugging and sanity checks only.
- Holdout period: 2017-01-01 to 2026-10-23. No parameter may be changed after seeing holdout results.
- Full period is also reported. Both sub-periods are always shown.

## Alpha tests (annualized alpha, Newey-West HAC standard errors, 5 lags, excess returns over French RF)

- R1: strategy excess return on 60/40 excess return
- R2: strategy excess return on SPY and IEF excess returns (market and duration exposure)
- R3: R2 plus the Fama-French momentum factor (informational: is it more than known momentum?)
- Stationary bootstrap (mean block 21 days, 10,000 resamples, seed 2026): 95% CI for the Sharpe
  difference of each strategy vs B1 and vs B2.
- Deflated Sharpe ratio (Bailey and Lopez de Prado), using N_trials = 13 and the cross-trial
  variance of Sharpe ratios.

## Pre-registered criterion for claiming "evidence of alpha" for a strategy

ALL must hold:
1. R2 alpha > 0 with HAC t-stat >= 2.0 over the full period.
2. R2 alpha positive in both the design period and the holdout period.
3. Deflated Sharpe ratio probability >= 0.95 with N_trials = 13.
4. R2 alpha still positive with t >= 2.0 when slippage is raised to 10 bps.

If no strategy meets all four, the conclusion is "no evidence of alpha under this protocol."
Results are still reported in full.

## Secondary outcomes (reported, not claimed as alpha)

Sharpe, annualized volatility, max drawdown, Calmar, worst 10-day return, turnover, correlation
with SPY and 60/40, and drawdown behavior in 2008, 2020 and 2022.

## Sensitivities (reported, not counted as extra trials)

Slippage 10 and 25 bps; no execution lag (signal and trade on the same close, as in the earlier
stock-momentum work).

## Rules for staying honest

- All configurations are reported, including failures. No ETF is dropped after seeing results.
- Code bugs found after results are seen are fixed, everything is re-run, and the fix is logged below.
- The prior single-stock momentum work informs the expectation that momentum has positive loadings
  on the known factor, but no parameter here was chosen from those results.

## Deviations

(none yet)
