# live/scheduler.py
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

RUN_HOUR, RUN_MINUTE = 17, 30
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEARTBEAT = os.path.join(PROJECT_ROOT, "live", "state", "last_successful_run.json")
LOG = os.path.join(PROJECT_ROOT, "live", "logs", "run_daily_output.log")

def ran_today() -> bool:
    try:
        with open(HEARTBEAT) as f:
            ts = datetime.fromisoformat(json.load(f)["timestamp"])
        return ts.date() == datetime.now().date()
    except Exception:
        return False

def run_daily():
    with open(LOG, "a") as logfile:
        logfile.write(f"\n--- {datetime.now()} ---\n")
        logfile.flush()
        subprocess.run(
            [sys.executable, "-m", "live.run_daily"],
            cwd=PROJECT_ROOT,
            stdin=subprocess.DEVNULL,      # the missing piece
            stdout=logfile,
            stderr=subprocess.STDOUT,
        )

def main():
    last_attempt = None
    print(f"Scheduler started. Runs weekdays after {RUN_HOUR:02d}:{RUN_MINUTE:02d}.", flush=True)
    while True:
        now = datetime.now()
        due = now.weekday() < 5 and (now.hour, now.minute) >= (RUN_HOUR, RUN_MINUTE)
        can_retry = last_attempt is None or now - last_attempt > timedelta(hours=1)
        if due and not ran_today() and can_retry:
            print(f"[{now}] Triggering run_daily...", flush=True)
            last_attempt = now
            run_daily()
            print(f"[{datetime.now()}] Finished. Ran today: {ran_today()}", flush=True)
        time.sleep(30)

if __name__ == "__main__":
    main()