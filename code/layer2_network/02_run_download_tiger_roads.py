"""
Convenience runner for 02_download_tiger_roads.py -- edit the config values
below and hit Run on this file instead of typing flags into a terminal.

This doesn't replace argparse -- it builds the same command-line flags
02_download_tiger_roads.py already expects and runs it as a subprocess, so
that script itself doesn't change (and still defaults to just Massachusetts
if run directly, unlike this runner) and can still be run directly with its
own flags if you prefer that.

This is a much bigger job than the layer1_geography runners: TIGER ROADS is
published per COUNTY, so "all states" means enumerating and downloading
~3,234 individual county files, not 56 -- expect a long runtime.

Usage:
    python 02_run_download_tiger_roads.py
"""
import subprocess
import sys
from pathlib import Path

# --- Config: edit these, then run this file ---
REGION = "all"    # "all" (56 states/territories) or "conus_ak_hi" (50 states + DC, no territories)
YEAR = 2020        # TIGER/Line vintage year
# ------------------------------------------------

SCRIPT = Path(__file__).parent / "02_download_tiger_roads.py"


def main():
    cmd = [sys.executable, str(SCRIPT), "--region", REGION, "--year", str(YEAR)]

    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
