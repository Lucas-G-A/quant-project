# live/scheduler.py
import time
import subprocess
import sys
import os
from datetime import datetime

RUN_HOUR = 17
RUN_MINUTE = 30

# Use the same Python interpreter this scheduler itself is running under
# (the venv's python), rather than relying on inherited PATH/environment.
PYTHON_EXECUTABLE = sys.executable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    last_run_date = None
    print(f"Scheduler started. Will run daily at {RUN_HOUR:02d}:{RUN_MINUTE:02d}.", flush=True)
    while True:
        now = datetime.now()
        if now.hour == RUN_HOUR and now.minute == RUN_MINUTE and now.date() != last_run_date:
            print(f"[{now}] Triggering run_daily...", flush=True)
            log_path = os.path.join(PROJECT_ROOT, "live", "logs", "run_daily_output.log")
            with open(log_path, "a") as logfile:
                subprocess.run(
                    [PYTHON_EXECUTABLE, "-m", "live.run_daily"],
                    cwd=PROJECT_ROOT,
                    stdout=logfile,
                    stderr=subprocess.STDOUT,
                )
            last_run_date = now.date()
        time.sleep(30)

if __name__ == "__main__":
    main()