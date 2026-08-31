# live/health_check.py
import json
import os
from datetime import datetime, timedelta

path = "live/state/last_successful_run.json"

if not os.path.exists(path):
    print("⚠️  No successful run has ever been recorded.")
else:
    with open(path) as f:
        data = json.load(f)
    last_run = datetime.fromisoformat(data["timestamp"])
    gap = datetime.now() - last_run
    print(f"Last successful run: {last_run}")
    print(f"Time since last run: {gap}")
    if gap > timedelta(days=2):  # generous buffer for a weekend
        print("⚠️  This is longer than expected — check the scheduler and logs.")
    else:
        print("✅ Looks healthy.")