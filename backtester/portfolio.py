class Portfolio:
    def __init__(self, starting_cash: float, commission_pct: float = 0.001, slippage_pct: float = 0.0005):
        self.cash = starting_cash
        self.positions = {}          # ticker -> number of shares
        self.commission_pct = commission_pct   # 0.001 = 0.1% per trade
        self.slippage_pct = slippage_pct       # 0.0005 = 0.05% adverse price move
        self.history = []            # list of dicts: {date, cash, positions_value, total_value}

    def _execution_price(self, price: float, side: str) -> float:
        """Apply slippage: buys execute slightly worse (higher), sells slightly worse (lower)."""
        if side == "buy":
            return price * (1 + self.slippage_pct)
        elif side == "sell":
            return price * (1 - self.slippage_pct)
        raise ValueError(f"Unknown side: {side}")

    def execute_trade(self, ticker: str, shares: float, price: float, side: str):
        exec_price = self._execution_price(price, side)
        trade_value = shares * exec_price
        commission = trade_value * self.commission_pct

        if side == "buy":
            # "buy" can mean: opening a long, OR covering (closing) a short
            total_cost = trade_value + commission
            if total_cost > self.cash:
                print(f"Insufficient cash to buy {shares} {ticker}, skipping.")
                return
            self.cash -= total_cost
            self.positions[ticker] = self.positions.get(ticker, 0) + shares

        elif side == "sell":
            # "sell" can mean: closing a long, OR opening a short
            current_shares = self.positions.get(ticker, 0)
            proceeds = trade_value - commission

            if shares > current_shares:
                # Selling more than we hold = going short on the difference
                # (allow this now, since pairs trading requires it)
                pass  # no restriction anymore — see note below

            self.cash += proceeds
            self.positions[ticker] = self.positions.get(ticker, 0) - shares
            if self.positions.get(ticker) == 0:
                del self.positions[ticker]

    def total_value(self, prices_today: dict) -> float:
        """prices_today: dict of ticker -> current price"""
        positions_value = sum(
            shares * prices_today[ticker]
            for ticker, shares in self.positions.items()
        )
        return self.cash + positions_value

    def record(self, date, prices_today: dict):
        self.history.append({
            "date": date,
            "cash": self.cash,
            "positions_value": self.total_value(prices_today) - self.cash,
            "total_value": self.total_value(prices_today),
        })