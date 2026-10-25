# Quant Trading Lab

A from-scratch, event-driven backtesting engine used to research and evaluate two structurally different systematic trading strategies: a **momentum** strategy and a **pairs trading (statistical arbitrage)** strategy — extended from backtested research into a live, automated paper-trading system. Built to understand market mechanics and risk from first principles, not to rely on an existing framework like `backtrader` or `zipline`.

## Why event-driven, not vectorized

Most quick backtests compute signals and returns across an entire dataset in one vectorized pass. This is fast, but dangerously easy to get wrong: subtle bugs can let a strategy's decision on day *N* be computed using information only available on day *N+5* — a mistake known as **look-ahead bias**, and one of the most common ways backtests silently overstate performance.

This engine instead steps through history one day at a time. On each day, the strategy is handed a slice of price data containing only information up to and including that day (`price_data.iloc[:i+1]`), and must decide what to do with only that information — structurally identical to how a live trading system would operate. This is slower and more code than a vectorized approach, but it's the standard more rigorous quant research shops actually use, and it makes look-ahead bias close to impossible rather than merely "avoided if you're careful." This design choice paid off directly: the same `Strategy.decide()` interface built for backtesting was reused, almost unchanged, to drive the live trading system described below.

## Architecture

```
quant_proj/
├── backtester/
│   ├── portfolio.py     # Tracks cash, positions (incl. shorts), applies commission/slippage
│   ├── strategy.py      # Abstract base class — the contract every strategy implements
│   └── engine.py         # The day-by-day event loop tying Portfolio + Strategy together
├── strategies/
│   ├── momentum.py        # Cross-sectional momentum, configurable weighting schemes
│   └── pairs_trading.py   # Cointegration-based statistical arbitrage
├── analysis/
│   ├── metrics.py         # Sharpe ratio, max drawdown, total return, volatility
│   └── find_pairs.py       # Engle-Granger cointegration testing across the universe
├── data/
│   └── fetch_data.py       # Historical price data via yfinance (hardcoded ticker snapshot)
├── live/
│   ├── alpaca_client.py     # Alpaca Trading + Data API wrapper (batched, with retry logic)
│   ├── shadow_portfolio.py   # Per-strategy portfolio tracking that persists between daily runs
│   ├── strategy_state.py     # Persists each strategy's internal state between runs
│   ├── run_daily.py           # Daily entry point: pulls data, runs both strategies, submits orders
│   ├── scheduler.py            # Lightweight always-on loop that triggers run_daily at a fixed time
│   └── health_check.py         # Reports time since the last successful run
└── run_backtest*.py         # Entry-point scripts for each backtest experiment
```

**Design principle:** both strategies plug into the same `Strategy` abstract base class and the same `Backtester` engine — the engine has no knowledge of which strategy it's running. This "strategy-agnostic" design meant adding a second, structurally very different strategy (long/short, event-driven entries) required zero changes to the core engine, and later meant the live system could drive both strategies through one shared code path too.

### Realism built in from day one, not bolted on later
- **Commission**: applied as a percentage of trade value, on every trade (both entry and exit)
- **Slippage**: buy orders execute slightly worse (higher) than the quoted price, sell orders slightly worse (lower) — modeling the real-world cost of moving the market with your own order
- **Short-selling support**: the `Portfolio` class supports negative positions, required for the market-neutral pairs trading strategy. *(Simplification: no borrow costs or margin requirements are modeled — reasonable for signal validation, not for a live short-selling system.)*

## Strategy 1: Momentum

**Core idea:** stocks with strong recent performance tend to keep outperforming for a period, before eventually mean-reverting. This is one of the most replicated anomalies in empirical finance.

**Implementation details:**
- **12-1 lookback**: ranks stocks by their return over the trailing 12 months, *skipping* the most recent 1 month — a standard academic refinement (Jegadeesh & Titman) that avoids contamination from short-term reversal effects
- Monthly rebalancing into the top 15% of a ~98-stock large-cap universe
- Three configurable position-sizing schemes, tested against each other:
  - **Equal weight** — simple, evenly split across selected names
  - **Inverse-volatility weight** — a risk-parity-style approach, sizing positions inversely to recent volatility
  - **Momentum-score weight** — sizing proportional to the strength of the momentum signal itself
- A "no-trade band" (skip rebalances worth <0.5% of portfolio value) to avoid paying transaction costs on economically meaningless adjustments

### Results

Tested across two very different regimes: a trending bull market (2015–2024) and a crisis period spanning the 2008 financial crash (2007–2012).

| Period | Scheme | Total Return | Sharpe | Max Drawdown |
|---|---|---|---|---|
| 2015–2024 | Inverse-vol | 257% | 0.75 | -30.4% |
| 2015–2024 | Equal-weight | 342% | 0.82 | -30.7% |
| 2015–2024 | Momentum-score | **779%** | **1.03** | -31.4% |
| 2015–2024 | Buy & Hold (benchmark) | 736% | 1.09 | -35.7% |
| 2007–2012 | Inverse-vol | 36% | 0.35 | **-42.6%** |
| 2007–2012 | Equal-weight | 50% | 0.41 | -44.7% |
| 2007–2012 | Momentum-score | 59% | 0.44 | -50.0% |
| 2007–2012 | Buy & Hold (benchmark) | 87% | 0.55 | -47.0% |

**Key finding:** no single weighting scheme dominates across regimes. Momentum-score weighting maximized returns in the trending bull market — even edging out a passive benchmark on raw return — but produced the *worst* drawdown of all variants during the 2008 crisis, since concentrating into the highest-momentum names amplifies both upside and downside. Inverse-volatility weighting sacrificed returns during the bull run but delivered genuine risk reduction during the crisis, achieving a smaller max drawdown than even the passive benchmark. This is a direct, testable illustration of the tension between risk-parity-style position sizing and momentum-chasing.

**Live deployment:** the momentum-score-weighted variant (the strongest bull-market performer) is running live on paper trading — see Live Deployment below.

## Strategy 2: Pairs Trading (Statistical Arbitrage)

**Core idea:** rather than betting on market direction, find two stocks with a historically stable price relationship (cointegration) and bet on temporary divergences reverting to normal — long the relatively cheap leg, short the relatively expensive one. Designed to be market-neutral: broad market moves should largely cancel out between the long and short leg.

**Implementation details:**
- **Pair discovery**: Engle-Granger cointegration testing (`statsmodels`) across all ~4,750 pairwise combinations in the universe
- **Multiple testing awareness**: at a 5% significance threshold across ~4,750 tests, roughly 238 "significant" pairs would be expected from pure chance alone; 380 were found, indicating real signal but also a meaningful false-positive risk. Candidate pairs were therefore filtered for economic rationale (plausible business relationship), not p-value alone
- **Pair selected**: Mastercard (MA) / Visa (V) — the strongest statistically (p < 0.0001) and most economically defensible pair (direct competitors, nearly identical business model and macro exposure)
- Hedge ratio estimated via linear regression, recalculated quarterly **only between trades** (see bug #2 below)
- Entry/exit on a rolling z-score of the spread: enter at |z| > 2.0, exit at |z| < 0.5 (avoiding "flickering" trades right at the mean)

### Results (MA–V, 2015–2024)

| Metric | Value |
|---|---|
| Total return | +1.2% |
| Sharpe ratio | 0.05 |
| Annualized volatility | 3.6% |
| Max drawdown | -7.5% |

**Key finding:** the strategy is essentially flat after realistic transaction costs, despite the pair being strongly cointegrated and behaving as expected mechanically (average entry z-score of 2.5, clean mean-reverting exits). This is a legitimate and expected result, not a failed implementation: MA/V is exactly the kind of highly liquid, heavily-monitored pair that professional statistical arbitrage desks compete over intensely, compressing away most easily-capturable edge. Annualized volatility of 3.6% (vs. ~20% for the momentum strategies) does confirm the market-neutral property held as designed — the strategy achieves genuine diversification from market direction, even without generating excess return in this particular pair.

**Live deployment:** running live on paper trading alongside momentum — see below.

## Bugs found and fixed along the way

Documenting these deliberately, since debugging process is as informative as final results:

1. **Insufficient cash-buffer errors**: setting `target_total_weight` close to 1.0 (fully invested) occasionally caused trades to fail, since slippage and commission push actual execution cost slightly above the computed target. Fixed by leaving a larger cash buffer (0.90 instead of 0.95).
2. **Hedge ratio recalculating mid-trade**: the pairs trading hedge ratio was originally recalculated on a fixed schedule regardless of position state. This caused the *definition* of the spread to shift while a trade was open, producing artificial one-day z-score jumps that looked like (but were not) genuine mean reversion. Fixed by freezing the hedge ratio for the duration of any open position, only recalculating between trades.
3. **Ticker format mismatches across data providers**: Yahoo Finance (`yfinance`) and Alpaca use different conventions for share-class tickers (`BRK-B` vs. `BRK.B`). Solved with a small conversion function applied only at the Alpaca API boundary, keeping the core universe list provider-agnostic.
4. **Silent state loss between daily runs**: the live system runs as a fresh process each day, so any strategy state held only in memory (e.g., last rebalance month, whether a pairs position is currently open) would silently reset every run — causing momentum to attempt a rebalance every single day instead of monthly. Fixed by persisting the minimal necessary state to disk between runs.
5. **API request batching and transient failures**: a single request for ~100 tickers' worth of historical bars occasionally failed with a dropped connection. Fixed by batching requests into smaller groups with retry-with-backoff logic — a necessary robustness measure for any unattended daily script.

## Live Deployment

Both strategies run live on an Alpaca paper-trading account (real market conditions and execution, simulated capital), each allocated a $50,000 notional "sleeve" tracked independently.

**Architecture:**
- A daily script (`live/run_daily.py`) pulls current market data, runs both strategies through the same `Strategy.decide()` interface used in backtesting, and submits any resulting orders to Alpaca
- Since an Alpaca paper account is a single pool of capital rather than natively supporting independently-tracked sub-strategies, a lightweight **shadow portfolio** layer (`live/shadow_portfolio.py`) tracks each strategy's notional cash and positions separately, persisting to disk between runs — a simplified version of the "sleeve accounting" pattern real multi-strategy funds use to track individual strategies' P&L within one consolidated account
- A background scheduler (`live/scheduler.py`) checks the time every 30 seconds and triggers the daily run automatically, after market close
- A heartbeat file, updated at the end of every successful run, allows a simple health check (`live/health_check.py`) to confirm the system is actually running correctly rather than assuming it is

**A practical lesson worth noting:** the original automation plan used macOS's native `launchd` scheduler. After extended troubleshooting (correctly-configured jobs silently failing to trigger, likely due to macOS's background task approval system throttling repeated reloads during testing), this was replaced with a simpler, fully transparent Python loop run via `nohup`. This was a deliberate engineering trade-off: less "proper" than an OS-level scheduler, but fully debuggable and observable — when it fails, it fails visibly rather than silently, which mattered more for a system meant to run unattended for weeks.

## Update (Oct 2026): window-alignment correction and risk-controls experiment

### Correction to the comparison tables above

The tables above compare strategy equity curves that include a 273-trading-day cash-only warm-up (the 12-1 signal needs about a year of history) against a buy-and-hold benchmark that is invested from day one, so strategies and benchmark were not measured over the same dates. Everything below measures both from the same start date (the day before the strategy's first trade): 2016-02-02 for the 2015-2024 run and 2008-02-01 for the 2007-2012 run. Re-running the unchanged baseline strategy reproduces the earlier strategy numbers exactly; only the benchmark window and the Sharpe/volatility denominators change.

With aligned windows, the baseline momentum-score strategy beats the equal-weight benchmark on total return in both periods (779% vs 659%; 58.6% vs 52.6%). Its Sharpe is slightly lower in the bull run (1.09 vs 1.14) and about equal in the crisis run (0.49 vs 0.47). Its maximum drawdown is smaller than the benchmark's in the bull run (-31.4% vs -35.8%) but worse in the crisis run (-50.0% vs -45.4%). The earlier statement that buy-and-hold clearly won the 2007-2012 period on return and Sharpe (87% / 0.55) does not survive alignment.

### Risk controls: position cap, sector cap, drawdown rule

`MomentumStrategy` gained three optional controls, all off by default (default behavior verified identical to the original on all six weighting/period combinations): `max_position_weight`, `max_sector_weight` (with the sector map in `data/sectors.py`) and a daily drawdown rule (`drawdown_trigger`, `drawdown_scale`, `drawdown_reentry`). Four variants were fixed before running and not tuned; all are reported. Momentum-score weighting, 90% target exposure, costs included (turnover roughly 4x to 6x per year depending on the variant).

**2015-2024 (aligned window 2016-02-02 to 2024-12-30, 98 tickers)**

| Variant | Total return | CAGR | Sharpe | Ann. vol | Max drawdown | Worst 10-day | Calmar |
|---|---|---|---|---|---|---|---|
| A. Baseline (no controls) | 779.1% | 27.7% | 1.09 | 25.4% | -31.4% | -24.1% | 0.88 |
| B. Position cap 10% | 465.9% | 21.5% | 0.95 | 23.3% | -31.0% | -24.0% | 0.69 |
| C. B + sector cap 30% | 414.3% | 20.2% | 0.96 | 21.7% | -30.9% | -24.1% | 0.65 |
| D. C + drawdown rule | 188.2% | 12.6% | 0.85 | 15.4% | -20.7% | -12.1% | 0.61 |
| Benchmark: equal-weight buy & hold | 659.3% | 25.6% | 1.14 | 22.2% | -35.8% | -23.8% | 0.72 |
| Control: baseline held at 45% invested | 214.2% | 13.7% | 1.08 | 12.6% | -16.5% | -12.2% | 0.83 |

**2007-2012 holdout (aligned window 2008-02-01 to 2012-12-28, 88 tickers)**

| Variant | Total return | CAGR | Sharpe | Ann. vol | Max drawdown | Worst 10-day | Calmar |
|---|---|---|---|---|---|---|---|
| A. Baseline (no controls) | 58.6% | 9.9% | 0.49 | 26.2% | -50.0% | -22.0% | 0.20 |
| B. Position cap 10% | 47.9% | 8.3% | 0.44 | 25.0% | -45.7% | -22.0% | 0.18 |
| C. B + sector cap 30% | 45.6% | 8.0% | 0.43 | 24.9% | -45.7% | -22.0% | 0.17 |
| D. C + drawdown rule | 12.7% | 2.5% | 0.24 | 14.5% | -31.2% | -11.0% | 0.08 |
| Benchmark: equal-weight buy & hold | 52.6% | 9.0% | 0.47 | 25.3% | -45.4% | -23.4% | 0.20 |
| Control: baseline held at 45% invested | 28.6% | 5.3% | 0.45 | 13.2% | -30.7% | -11.1% | 0.17 |

**Findings**

1. **The caps reduced return more than they reduced risk.** In the bull run the 10% position cap cut CAGR from 27.7% to 21.5% and Sharpe from 1.09 to 0.95 while max drawdown moved only from -31.4% to -31.0%; the worst 10-day loss stayed near -24% in variants A to C, because it comes from market-wide crashes that caps cannot diversify away. In the crisis holdout the caps trimmed max drawdown from -50.0% to -45.7% at a cost of 11 to 13 points of total return.
2. **The drawdown rule, as specified, did not work.** It cut max drawdown (-31.4% to -20.7%; -50.0% to -31.2%) but spent 57% of days (bull) and 81% of days (crisis) at half exposure, with single stretches of 2.1 and 2.6 years, because re-entry requires recovering to within 5% of the all-time peak while holding half the book. A control that simply holds the baseline at 45% invested had higher return, higher Sharpe and higher Calmar than the rule in both periods, so the rule was dominated by just running a smaller position.
3. **No variant improved risk-adjusted return over the uncapped baseline.** The caps and the rule act as risk dials, not free improvements.

**Caveats.** The universe has survivorship bias (stocks that were later successful are in the sample), which probably flatters the uncapped, concentrated version and overstates the cost of the caps. Results come from one historical path per period, two periods only, and a current-snapshot sector map. The drawdown rule's state (peak value, de-risk flag) is not persisted by the live runner, so it must not be deployed as is. None of this is deployed: the live paper-trading strategy is unchanged.

**Reproduce:** `python analysis/risk_controls_experiment.py` (writes `analysis/output/`). Attribution of returns to market/size/value/profitability/investment/momentum factors: `python analysis/factor_attribution.py` (downloads Ken French's factor files). Live sleeve vs SPY, equal-weight universe and a semiconductor basket: `python analysis/live_benchmark.py` (read-only, needs Alpaca keys in `.env`).

## Known limitations

- **Survivorship bias**: the universe is built from a snapshot of current S&P 500 constituents, meaning companies that were delisted, went bankrupt, or were removed from the index during the backtest period are excluded. This causes both strategies' backtests to look better than a fully historically accurate universe would.
- **No short-selling costs**: borrow fees and margin requirements are not modeled for the pairs trading strategy, in either backtest or live deployment.
- **Data source**: prices sourced via `yfinance` (Yahoo Finance) for backtesting, which can have minor data quality issues (occasional missing tickers, adjusted-close conventions) — not a fully professional-grade data feed.
- **Period-dependency**: results are shown across two distinct regimes specifically to surface this issue, but no backtest fully generalizes beyond the periods tested.
- **Live system uptime**: the scheduler depends on the host machine staying awake and the background process staying alive; it does not currently recover automatically from a full machine restart, so live performance may include gaps corresponding to downtime rather than deliberate no-trade decisions.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Backtesting
python data/fetch_data.py          # pulls historical price data
python run_backtest.py              # momentum, 2015–2024
python run_backtest_crisis.py       # momentum, 2007–2012
python analysis/find_pairs.py       # cointegration pair discovery
python run_backtest_pairs.py        # pairs trading, MA–V

# Live paper trading
# 1. Create a free Alpaca account and generate PAPER trading API keys
# 2. Add ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL to a local .env file (never committed)
python -m live.test_connection      # confirms API keys and connectivity
python -m live.run_daily             # one manual run of both strategies
nohup python -m live.scheduler > live/logs/scheduler.log 2>&1 &   # starts unattended daily execution
python -m live.health_check          # confirms the system is running correctly
```

## Possible future work

- A Streamlit dashboard visualizing live equity curves for both strategies against their original backtest expectations
- A lower-liquidity, less-arbitraged pair to test whether pairs trading edge is more exploitable outside of heavily-monitored large caps
- Position-weight capping as a middle ground between equal-weight and momentum-score weighting in the momentum strategy
- Cointegration re-testing over rolling windows, rather than a single full-sample test, to check pair stability over time
- Automatic recovery of the live scheduler after a machine restart (e.g., revisiting a properly-configured OS-level scheduler, or a small watchdog process)