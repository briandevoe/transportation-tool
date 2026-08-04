"""
Convenience runner for 01_download_tiger.py -- edit the config values below
and hit Run on this file instead of typing flags into a terminal.

This doesn't replace argparse -- it builds the same command-line flags
01_download_tiger.py already expects and runs it as a subprocess, so
01_download_tiger.py itself doesn't change and can still be run directly
with its own flags if you prefer that.

Usage:
    python 01_run_download_tiger.py
"""
import subprocess
import sys
from pathlib import Path

# --- Config: edit these, then run this file ---
YEAR = 2020
GEOGRAPHY = ["tract", "bg", "block", "zcta"]   # subset ok, e.g. ["tract"]
REGION = None                                   # "all" or "conus_ak_hi" -- set this to run many states at once
STATE_FIPS = ["25"]                             # e.g. ["25", "36"] -- default: Massachusetts only, for a quick test
# ------------------------------------------------

SCRIPT = Path(__file__).parent / "01_download_tiger.py"


def main():
    cmd = [sys.executable, str(SCRIPT), "--year", str(YEAR), "--geography", *GEOGRAPHY]
    cmd += ["--state-fips", *STATE_FIPS] if STATE_FIPS else ["--region", REGION]

    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
