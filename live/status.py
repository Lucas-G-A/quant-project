# live/status.py
import os
import pandas as pd
from analysis.metrics import summarize_performance
from live.alpaca_client import trading_client
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

def load_history(name):
    path = f"live/state/{name}_history.csv"
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None).dt.normalize()
    # manual re-runs on the same day create duplicate rows; keep the last
    return df.drop_duplicates("date", keep="last").set_index("date")["total_value"]

shadow_total = 0
for name in ["momentum", "pairs"]:
    s = load_history(name)
    print(f"\n=== {name.upper()} ===")
    if s is None or len(s) < 3:
        print("Not enough history yet.")
        continue
    shadow_total += s.iloc[-1]
    print(f"Period: {s.index[0].date()} -> {s.index[-1].date()} ({len(s)} data points)")
    expected = pd.bdate_range(s.index[0], s.index[-1])
    missing = expected.difference(s.index)
    print(f"Missing weekdays (includes holidays like Labor Day): {[d.date().isoformat() for d in missing]}")
    summary = summarize_performance(s, label=name)
    print(f"Start ${s.iloc[0]:,.0f} -> Now ${s.iloc[-1]:,.0f}")
    print(f"Return since first data point: {summary['total_return']:.2%}")
    if len(s) >= 20 and s.index.to_series().diff().dt.days.max() <= 4:
        print(f"Max drawdown {summary['max_drawdown']:.2%} | Ann. vol {summary['annualized_volatility']:.2%} | Sharpe {summary['sharpe_ratio']:.2f}")
    else:
        print("Risk stats suppressed: need 20+ points with no multi-day gaps.")

print("\n=== ALPACA (real paper account) ===")
acct = trading_client.get_account()
print(f"Equity: ${float(acct.equity):,.2f} | Cash: ${float(acct.cash):,.2f}")
print(f"Shadow portfolios combined: ${shadow_total:,.2f}  (should be close to Alpaca equity)")

positions = trading_client.get_all_positions()
print(f"Open positions on Alpaca: {len(positions)}")

orders = trading_client.get_orders(GetOrdersRequest(status=QueryOrderStatus.ALL, limit=200))
counts = {}
for o in orders:
    counts[str(o.status)] = counts.get(str(o.status), 0) + 1
print(f"Order statuses: {counts}")