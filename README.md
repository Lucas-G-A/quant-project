# quant-project

"Inverse-volatility weighting, while reducing portfolio volatility, was found to systematically underweight the highest-momentum names during this period, since strong momentum stocks (e.g., mega-cap tech) also tended to exhibit high volatility — highlighting a real tension between risk-parity-style construction and momentum-chasing strategies."

the crisis-period test uses a further-reduced universe due to data availability, introducing additional survivorship bias beyond the base sample.

"No single weighting scheme dominated across market regimes. Momentum-score weighting maximized returns in a trending bull market (2015-2024) but produced the worst drawdown of all variants during the 2007-2012 crisis, confirming that concentrating into high-momentum names amplifies both upside and downside. Inverse-volatility weighting sacrificed returns in the bull market but delivered genuine risk reduction during the crisis, achieving a smaller max drawdown than even a passive buy-and-hold benchmark — illustrating the classic risk/return tradeoff in position-sizing scheme design."

With 98 tickers, we ran 4,753 pairwise tests at a 5% significance threshold. If none of these pairs were actually cointegrated (pure random noise), we'd still expect roughly 238 "significant" results purely by chance (5% of 4,753). We found 380 — meaningfully more than the 238 we'd expect from noise alone, which suggests there's real signal in there, but it also means a large chunk of our 380 (potentially 200+) could still be false positives. This is precisely the multiple testing problem in action,

"Rather than trading purely on statistical significance, pairs were filtered to require a plausible economic relationship, given known risks of spurious cointegration in large-scale pairwise testing."