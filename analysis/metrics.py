import numpy as np
import pandas as pd

def compute_returns(equity_curve: pd.Series) -> pd.Series:
    """Daily percentage returns from a series of portfolio values."""
    return equity_curve.pct_change().dropna()

def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0, periods_per_year: int = 252) -> float:
    """
    252 = number of trading days in a year (the standard annualization convention).
    risk_free_rate: what you could've earned doing nothing risky (e.g., T-bills).
                     We'll default to 0 for simplicity, but it's worth knowing this exists.
    """
    excess_returns = returns - (risk_free_rate / periods_per_year)
    if excess_returns.std() == 0:
        return 0.0
    return (excess_returns.mean() / excess_returns.std()) * np.sqrt(periods_per_year)

def max_drawdown(equity_curve: pd.Series) -> float:
    """
    Returns the max drawdown as a negative percentage (e.g., -0.25 = -25%).
    """
    running_max = equity_curve.cummax()
    drawdown = (equity_curve - running_max) / running_max
    return drawdown.min()

def total_return(equity_curve: pd.Series) -> float:
    return (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1

def summarize_performance(equity_curve: pd.Series, label: str = "Strategy") -> dict:
    returns = compute_returns(equity_curve)
    return {
        "label": label,
        "total_return": total_return(equity_curve),
        "sharpe_ratio": sharpe_ratio(returns),
        "max_drawdown": max_drawdown(equity_curve),
        "annualized_volatility": returns.std() * np.sqrt(252),
    }