import pandas as pd
from backtester.portfolio import Portfolio

class Backtester:
    def __init__(self, price_data: pd.DataFrame, strategy, starting_cash: float = 100_000,
                 commission_pct: float = 0.001, slippage_pct: float = 0.0005):
        """
        price_data: DataFrame indexed by date, columns = tickers, values = closing prices
        strategy: an instance of a Strategy subclass
        """
        self.price_data = price_data
        self.strategy = strategy
        self.portfolio = Portfolio(starting_cash, commission_pct, slippage_pct)

    def run(self):
        for i in range(len(self.price_data)):
            date = self.price_data.index[i]

            # CRITICAL: slice only up to and including today (iloc[:i+1])
            # This is what makes look-ahead bias structurally impossible —
            # the strategy never receives rows beyond "today."
            price_history_so_far = self.price_data.iloc[: i + 1]

            prices_today = price_history_so_far.iloc[-1].to_dict()

            decisions = self.strategy.decide(date, price_history_so_far, self.portfolio)

            for trade in decisions:
                ticker = trade["ticker"]
                price = prices_today[ticker]
                self.portfolio.execute_trade(
                    ticker=ticker,
                    shares=trade["shares"],
                    price=price,
                    side=trade["side"],
                )

            self.portfolio.record(date, prices_today)

        return pd.DataFrame(self.portfolio.history).set_index("date")