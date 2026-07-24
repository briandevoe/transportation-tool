"""
Layer 4 (Destinations): grocery store destinations from OSM.

Sourced from OSM rather than a federal dataset (USDA/HRSA) -- reuses the
Geofabrik .pbf already cached by layer2_network/01_download_osm_roads.py
(downloads it via the same lib/osm_pbf.py helper if not already cached for
this state).

Scoped to shop=supermarket / shop=grocery specifically, not shop=convenience
-- convenience stores are a materially different food-access category
(docs/reference.md already lists them separately), not a smaller version of
the same thing. category preserves the real supermarket-vs-grocery
distinction rather than collapsing it into one label.

Usage:
    python 02_prepare_grocery_osm.py                  # Massachusetts (default)
    python 02_prepare_grocery_osm.py --state-fips 36   # New York
    python 02_prepare_grocery_osm.py --state-fips all  # 49 states + DC (excludes AK), skips states already done
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.destination_schema import validate_destinations
from lib.osm_pbf import STATE_FIPS_TO_PLACE, get_pbf_path
from lib.osm_poi_client import extract_pois
from lib.state_lists import STATE_FIPS_49

REPO_ROOT = Path(__file__).parent.parent.parent
PBF_RAW_DIR = REPO_ROOT / "data" / "layer2_network" / "roads" / "osm" / "raw"
OUT_DIR = REPO_ROOT / "data" / "layer4_destination" / "grocery" / "processed"

TAG_FILTER = {"shop": ["supermarket", "grocery"]}


def match_fn(row):
    return row.get("shop") in ("supermarket", "grocery")


def category_fn(row):
    return row.get("shop")


def process_state(state_fips):
    place = STATE_FIPS_TO_PLACE.get(state_fips, f"state FIPS {state_fips}")

    out_path = OUT_DIR / state_fips / "grocery_osm.parquet"
    if out_path.exists():
        print(f"[{state_fips}] {place} — already processed, skipping.")
        return

    print(f"[{state_fips}] {place}")
    pbf_path = get_pbf_path(state_fips, PBF_RAW_DIR)

    print("  Extracting grocery/supermarket POIs...")
    df = extract_pois(pbf_path, TAG_FILTER, match_fn, category_fn, "grocery", state_fips)
    if df.empty:
        print(f"  No grocery/supermarket POIs found for state FIPS {state_fips} -- skipping.")
        return

    df = validate_destinations(df)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)
    print(f"  Wrote {len(df):,} rows -> {out_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-fips", nargs="+", default=["25"],
                         help="One or more state FIPS codes, or 'all' for the 49 states + DC default set "
                              "(excludes AK; default: 25, Massachusetts)")
    args = parser.parse_args()

    states = STATE_FIPS_49 if args.state_fips == ["all"] else args.state_fips
    for state_fips in states:
        try:
            process_state(state_fips)
        except SystemExit as e:
            # e.g. Hawaii has no Geofabrik extract mapping at all -- a single
            # state's hard failure shouldn't kill a 49-state batch.
            print(f"[{state_fips}] failed ({e}), skipping.")


if __name__ == "__main__":
    main()
