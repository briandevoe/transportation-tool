"""
Convenience runner for 02_download_congressional_dist.py -- edit the config
values below and hit Run on this file instead of typing flags into a
terminal.

This doesn't replace argparse -- it builds the same command-line flags
02_download_congressional_dist.py already expects and runs it as a
subprocess, so that script itself doesn't change and can still be run
directly with its own flags if you prefer that.

Usage:
    python 02_run_download_congressional_dist.py
"""
import subprocess
import sys
from pathlib import Path

# --- Config: edit these, then run this file ---
CONGRESS = [113, 118]   # 113 = first map based on the 2010 census, 118 = first based on the 2020 census
REGION = "all"           # "all" or "conus_ak_hi"
STATE_FIPS = None        # e.g. ["25", "36"] -- overrides REGION if set
# ------------------------------------------------

SCRIPT = Path(__file__).parent / "02_download_congressional_dist.py"


def main():
    cmd = [sys.executable, str(SCRIPT), "--congress", *[str(c) for c in CONGRESS]]
    cmd += ["--state-fips", *STATE_FIPS] if STATE_FIPS else ["--region", REGION]

    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
