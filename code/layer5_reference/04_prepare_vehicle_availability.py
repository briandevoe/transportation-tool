"""
Layer 5 (Reference data): household vehicle availability, tract-level, from
ACS table B25044 (Tenure by Vehicles Available). Filed here rather than in
layer3_population despite docs/notes.md's original TODO placement, because
B25044 has no race/ethnicity iteration at all (verified live against
https://api.census.gov/data/2022/acs/acs5/groups/B25044.json -- it's a
tenure/housing-unit table, not part of the race-iterated family like
B01001A-I) -- so it can't be sliced by race the way layer3's population
characteristics are, and it joins onto any GEOID-keyed output as a single
tract-level rate, exactly like COI/RUCA/redlining already do.

Confirmed live at tract level directly (state:{fips} county:* tract:*) --
no need to fetch block group and aggregate up, since every downstream join
target (origins' GEOID) is already tract-level.

zero_vehicle_households = owner-occupied-no-vehicle (B25044_003E) +
renter-occupied-no-vehicle (B25044_010E), out of total occupied households
(B25044_001E). "No vehicle available" is ACS's own household-level measure
of car access -- not a perfect proxy for individual car access within a
household, but the standard one available at this geography.

Requires a free Census API key: https://api.census.gov/data/key_signup.html
Set via the CENSUS_API_KEY env var, or pass --api-key.

Usage:
    python 04_prepare_vehicle_availability.py                    # MA, 2022 (default)
    python 04_prepare_vehicle_availability.py --state-fips 17 36
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.acs_client import get_api_key
from lib.ct_geoid_crosswalk import fix_ct_geoids

REPO_ROOT = Path(__file__).parent.parent.parent
OUT_DIR = REPO_ROOT / "data" / "layer5_reference" / "vehicle_availability" / "processed"

B25044_VARS = ["B25044_001E", "B25044_003E", "B25044_010E"]  # total, owner-no-vehicle, renter-no-vehicle


def fetch_vehicle_availability(state_fips, year, api_key):
    resp = requests.get(
        f"https://api.census.gov/data/{year}/acs/acs5",
        params={"get": ",".join(B25044_VARS), "for": "tract:*", "in": f"state:{state_fips} county:*", "key": api_key},
        timeout=60,
    )
    resp.raise_for_status()
    rows = resp.json()
    df = pd.DataFrame(rows[1:], columns=rows[0])
    for v in B25044_VARS:
        df[v] = pd.to_numeric(df[v], errors="coerce")
    df["GEOID"] = df[["state", "county", "tract"]].agg("".join, axis=1)
    df = fix_ct_geoids(df)  # ACS 2022+ uses CT's new planning-region county codes; Layer 1 geometry doesn't

    df["total_households"] = df["B25044_001E"]
    df["zero_vehicle_households"] = df["B25044_003E"] + df["B25044_010E"]
    df["pct_zero_vehicle_households"] = (df["zero_vehicle_households"] / df["total_households"]).where(df["total_households"] > 0)
    return df[["GEOID", "total_households", "zero_vehicle_households", "pct_zero_vehicle_households"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-fips", nargs="+", default=["25"], help="State FIPS code(s) (default: 25, Massachusetts)")
    parser.add_argument("--year", type=int, default=2022, help="ACS 5-year vintage (default: 2022)")
    parser.add_argument("--api-key", default=None, help="Census API key (default: CENSUS_API_KEY env var)")
    args = parser.parse_args()

    api_key = get_api_key(args.api_key)
    for state_fips in args.state_fips:
        out_path = OUT_DIR / f"vehicle_availability_tract_{state_fips}_{args.year}.parquet"
        if out_path.exists():
            print(f"[{state_fips}] {args.year} — already built, skipping.")
            continue
        print(f"[{state_fips}] Fetching ACS {args.year} 5-year B25044 (Tenure by Vehicles Available)...")
        df = fetch_vehicle_availability(state_fips, args.year, api_key)
        df["state_fips"] = state_fips
        df["vehicle_availability_vintage"] = str(args.year)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_path)
        print(f"  Wrote {len(df):,} rows -> {out_path}")


if __name__ == "__main__":
    main()
