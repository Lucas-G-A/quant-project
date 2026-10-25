"""Additional benchmark for the v2 regime study. v1 code (etf_strategies.py) is not modified."""
import pandas as pd

from strategies.etf_strategies import ETFRebalancer


class SixtyFortyCash(ETFRebalancer):      # B2c: 60% SPY / 40% cash (SHY or the T-bill index)
    def target_weights(self, hist, scores):
        return pd.Series({"SPY": 0.6, "SHY": 0.4})
