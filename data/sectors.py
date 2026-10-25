"""
Ticker -> GICS sector map for the 100-stock universe in data/fetch_data.py.

NOTE: this is a hand-assigned snapshot of *current* GICS sectors (not point-in-time),
so historical backtests inherit the same survivorship/classification caveat as the
universe itself. Spot-check before relying on any single assignment.

Semiconductors (AMD, AMAT, ADI, LRCX, MU, NVDA, AVGO, QCOM, TXN) sit inside
Information Technology, so a sector cap on IT limits semis + software combined.
"""

SECTORS = {
    # Information Technology
    **{t: "Information Technology" for t in [
        "AAPL", "MSFT", "NVDA", "AVGO", "ADBE", "CRM", "ORCL", "AMD", "ACN", "CSCO",
        "TXN", "INTU", "IBM", "NOW", "QCOM", "AMAT", "ADI", "MU", "LRCX", "PANW"]},
    # Communication Services
    **{t: "Communication Services" for t in ["GOOGL", "META", "NFLX", "T"]},
    # Consumer Discretionary
    **{t: "Consumer Discretionary" for t in ["AMZN", "TSLA", "HD", "LOW", "MCD", "BKNG", "TJX"]},
    # Consumer Staples
    **{t: "Consumer Staples" for t in ["PG", "COST", "KO", "PEP", "WMT", "MDLZ", "PM", "MO"]},
    # Energy
    **{t: "Energy" for t in ["XOM", "CVX", "SLB", "EOG"]},
    # Financials
    **{t: "Financials" for t in [
        "BRK-B", "JPM", "V", "MA", "BAC", "WFC", "SPGI", "GS", "BLK", "SCHW", "CB",
        "MMC", "FI", "PGR", "AON", "CME", "USB", "PYPL"]},
    # Health Care
    **{t: "Health Care" for t in [
        "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "DHR", "AMGN", "ISRG", "SYK", "MDT",
        "ELV", "VRTX", "GILD", "REGN", "CI", "BSX", "ZTS", "HUM"]},
    # Industrials
    **{t: "Industrials" for t in [
        "CAT", "GE", "UNP", "HON", "DE", "ADP", "ETN", "ITW", "WM", "CSX", "FDX", "NOC"]},
    # Materials
    **{t: "Materials" for t in ["LIN", "APD", "SHW"]},
    # Real Estate
    **{t: "Real Estate" for t in ["PLD", "EQIX"]},
    # Utilities
    **{t: "Utilities" for t in ["NEE", "SO", "DUK"]},
}


def get_sector(ticker: str) -> str:
    """Looks up a ticker in either yfinance ('BRK-B') or Alpaca ('BRK.B') format."""
    return SECTORS.get(ticker.replace(".", "-"), "Unknown")
