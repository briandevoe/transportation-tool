"""
Convenience runner for 01_download_osm_roads.py -- checks which of a fixed
list of target states already have a built OSM network, prints that status,
then processes only the remaining ones, one at a time, streaming each
state's own progress output live (tile-by-tile) as it runs.

Edit TARGET_STATES below to change the state list. This doesn't replace
01_download_osm_roads.py's own --state-fips flag -- it builds the same
command and runs it as a subprocess, so that script itself doesn't change.

Usage:
    python 01_run_download_osm_roads.py
"""
import subprocess
import sys
import time
from pathlib import Path

# --- Config: edit this, then run this file ---
TARGET_STATES = [
    ("06", "California"),
    ("17", "Illinois"),
    ("36", "New York"),
    ("25", "Massachusetts"),
    ("13", "Georgia"),
    ("26", "Michigan"),
    ("55", "Wisconsin"),
    ("42", "Pennsylvania"),
]
# ------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPT = Path(__file__).parent / "01_download_osm_roads.py"
NETWORK_DIR = REPO_ROOT / "data" / "layer2_network" / "roads" / "osm" / "processed"


def fmt_elapsed(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s" if h else (f"{m}m {s:02d}s" if m else f"{s}s")


def is_done(state_fips):
    out_dir = NETWORK_DIR / state_fips
    return (out_dir / "edges.parquet").exists() and (out_dir / "nodes.parquet").exists()


def main():
    print(f"Checking {len(TARGET_STATES)} target states...")
    done, pending = [], []
    for state_fips, name in TARGET_STATES:
        (done if is_done(state_fips) else pending).append((state_fips, name))

    print()
    print("Status:")
    for state_fips, name in TARGET_STATES:
        status = "DONE" if (state_fips, name) in done else "PENDING"
        print(f"  [{state_fips}] {name:<15} {status}")
    print()

    if not pending:
        print("All target states already built. Nothing to do.")
        return

    print(f"{len(done)} already done, {len(pending)} to process: "
          f"{', '.join(name for _, name in pending)}")
    print()

    run_start = time.time()
    for n, (state_fips, name) in enumerate(pending, start=1):
        print(f"=== [{n}/{len(pending)}] {name} (FIPS {state_fips}) -- starting ===", flush=True)
        t0 = time.time()
        cmd = [sys.executable, str(SCRIPT), "--state-fips", state_fips]
        result = subprocess.run(cmd)
        elapsed = fmt_elapsed(time.time() - t0)
        if result.returncode == 0:
            print(f"=== [{n}/{len(pending)}] {name} -- done ({elapsed}) ===\n", flush=True)
        else:
            print(f"=== [{n}/{len(pending)}] {name} -- FAILED, exit code {result.returncode} ({elapsed}) ===\n", flush=True)

    print(f"All requested states processed ({fmt_elapsed(time.time() - run_start)} total).")
    print()
    print("Final status:")
    for state_fips, name in TARGET_STATES:
        print(f"  [{state_fips}] {name:<15} {'DONE' if is_done(state_fips) else 'STILL MISSING'}")


if __name__ == "__main__":
    main()
