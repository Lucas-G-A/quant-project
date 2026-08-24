# live/scheduler.py
import time
import subprocess
from datetime import datetime

RUN_HOUR = 17
RUN_MINUTE = 30

def main():
    last_run_date = None
    print(f"Scheduler started. Will run daily at {RUN_HOUR:02d}:{RUN_MINUTE:02d}.", flush=True)
    while True:
        now = datetime.now()
        if now.hour == RUN_HOUR and now.minute == RUN_MINUTE and now.date() != last_run_date:
            print(f"[{now}] Triggering run_daily...", flush=True)
            subprocess.run(["python", "-m", "live.run_daily"])
            last_run_date = now.date()
        time.sleep(30)

if __name__ == "__main__":
    main()