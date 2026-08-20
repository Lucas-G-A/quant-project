from abc import ABC, abstractmethod

class Strategy(ABC):
    @abstractmethod
    def decide(self, date, price_history, portfolio) -> list[dict]:
        """
        price_history: all price data UP TO AND INCLUDING today (never future data)
        portfolio: current Portfolio object, so the strategy can see current holdings/cash
        
        Returns a list of trade instructions, e.g.:
        [{"ticker": "AAPL", "shares": 10, "side": "buy"}, ...]
        """
        pass