# Quant Trading Lab

A from-scratch, event-driven backtesting engine used to research and evaluate two structurally different systematic trading strategies: a **momentum** strategy and a **pairs trading (statistical arbitrage)** strategy. Built to understand market mechanics and risk from first principles, not to rely on an existing framework like `backtrader` or `zipline`.

## Why event-driven, not vectorized

Most quick backtests compute signals and returns across an entire dataset in one vectorized pass. This is fast, but dangerously easy to get wrong: subtle bugs can let a strategy's decision on day *N* be computed using information only available on day *N+5* — a mistake known as **look-ahead bias**, and one of the most common ways backtests silently overstate performance.

This engine instead steps through history one day at a time. On each day, the strategy is handed a slice of price data containing only information up to and including that day (`price_data.iloc[:i+1]`), and must decide what to do with only that information — structurally identical to how a live trading system would operate. This is slower and more code than a vectorized approach, but it's the standard more rigorous quant research shops actually use, and it makes look-ahead bias close to impossible rather than merely "avoided if you're careful."

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
└── run_backtest*.py         # Entry-point scripts for each strategy/experiment
```

**Design principle:** both strategies plug into the same `Strategy` abstract base class and the same `Backtester` engine — the engine has no knowledge of which strategy it's running. This "strategy-agnostic" design meant adding a second, structurally very different strategy (long/short, event-driven entries) required zero changes to the core engine.

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

## Bugs found and fixed along the way

Documenting these deliberately, since debugging process is as informative as final results:

1. **Insufficient cash-buffer errors**: setting `target_total_weight` close to 1.0 (fully invested) occasionally caused trades to fail, since slippage and commission push actual execution cost slightly above the computed target. Fixed by leaving a larger cash buffer (0.90 instead of 0.95).
2. **Hedge ratio recalculating mid-trade**: the pairs trading hedge ratio was originally recalculated on a fixed schedule regardless of position state. This caused the *definition* of the spread to shift while a trade was open, producing artificial one-day z-score jumps that looked like (but were not) genuine mean reversion. Fixed by freezing the hedge ratio for the duration of any open position, only recalculating between trades.

## Known limitations

- **Survivorship bias**: the universe is built from a snapshot of current S&P 500 constituents, meaning companies that were delisted, went bankrupt, or were removed from the index during the backtest period are excluded. This causes both strategies' backtests to look better than a fully historically accurate universe would.
- **No short-selling costs**: borrow fees and margin requirements are not modeled for the pairs trading strategy.
- **Data source**: prices sourced via `yfinance` (Yahoo Finance), which can have minor data quality issues (occasional missing tickers, adjusted-close conventions) — not a fully professional-grade data feed.
- **Period-dependency**: results are shown across two distinct regimes specifically to surface this issue, but no backtest fully generalizes beyond the periods tested.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python data/fetch_data.py          # pulls historical price data
python run_backtest.py              # momentum, 2015–2024
python run_backtest_crisis.py       # momentum, 2007–2012
python analysis/find_pairs.py       # cointegration pair discovery
python run_backtest_pairs.py        # pairs trading, MA–V
```

## Possible future work

- Live paper trading via Alpaca's API to validate strategies against real-time execution
- A lower-liquidity, less-arbitraged pair to test whether pairs trading edge is more exploitable outside of heavily-monitored large caps
- Position-weight capping as a middle ground between equal-weight and momentum-score weighting in the momentum strategy
- Cointegration re-testing over rolling windows, rather than a single full-sample test, to check pair stability over time
