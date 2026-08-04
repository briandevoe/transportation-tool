"""

Layer 4 (Destinations): hospital destinations from OSM.

Sourced from OSM rather than a federal dataset (HRSA/CMS) -- reuses the
Geofabrik .pbf already cached by layer2_network/01_download_osm_roads.py
(downloads it via the same lib/osm_pbf.py helper if not already cached for
this state).

Matches amenity=hospital OR healthcare=hospital (a newer/alternate OSM
tagging convention) -- confirmed live against the MA extract that
healthcare=hospital contributes zero *additional* matches beyond
amenity=hospital there, but kept since other states' tagging may differ.
Single "hospital" category throughout -- unlike grocery stores, OSM doesn't
reliably distinguish hospital sub-types.

Usage:
    python 03_prepare_hospitals_osm.py                  # 49 states + DC, excludes AK (default), skips states already done
    python 03_prepare_hospitals_osm.py --state-fips 36   # just New York
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
OUT_DIR = REPO_ROOT / "data" / "layer4_destination" / "hospitals" / "processed"

TAG_FILTER = {"amenity": ["hospital"], "healthcare": ["hospital"]}


def match_fn(row):
    return row.get("amenity") == "hospital" or row.get("healthcare") == "hospital"


def category_fn(row):
    return "hospital"


def process_state(state_fips):
    place = STATE_FIPS_TO_PLACE.get(state_fips, f"state FIPS {state_fips}")

    out_path = OUT_DIR / state_fips / "hospitals_osm.parquet"
    if out_path.exists():
        print(f"[{state_fips}] {place} — already processed, skipping.")
        return

    print(f"[{state_fips}] {place}")
    pbf_path = get_pbf_path(state_fips, PBF_RAW_DIR)

    print("  Extracting hospital POIs...")
    df = extract_pois(pbf_path, TAG_FILTER, match_fn, category_fn, "hospital", state_fips)
    if df.empty:
        print(f"  No hospital POIs found for state FIPS {state_fips} -- skipping.")
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
