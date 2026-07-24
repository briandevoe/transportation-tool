"""
Layer 3 (Population): download ACS 5-year tract-level population, by
race/ethnicity and by "characteristic" (age bracket, disability status, ...).

Standalone population counts, not yet the full origin table -- no location.
Useful on its own for anyone who just wants population counts; the
centroid-building scripts (02_build_centroids_block_group.py etc.) call the
same lib/acs_client.py fetch logic directly (at block-group geography, for
weighting) and join this script's tract-level output back in for the
`population` column of the final origin table.

race_ethnicity always includes "total" (all races combined) automatically,
in addition to whatever the active scheme (lib/race_ethnicity_schemes.py)
defines. characteristic defaults to "N/A" (no age/disability filter --
population by race/ethnicity only) rather than auto-including every
characteristic; pass --characteristics to add under_18/65_plus/disability.

Requires a free Census API key: https://api.census.gov/data/key_signup.html
Set via the CENSUS_API_KEY env var, or pass --api-key.

Usage:
    python 01_download_acs_population.py                                    # MA, 2022, population by race/ethnicity only
    python 01_download_acs_population.py --characteristics under_18 disability
    python 01_download_acs_population.py --state-fips 36 --year 2023
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.acs_characteristics import CHARACTERISTICS
from lib.acs_client import fetch_population, get_api_key
from lib.population_schema import validate_population_counts
from lib.race_ethnicity_schemes import SCHEMES, get_scheme

REPO_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = REPO_ROOT / "data" / "layer3_population" / "acs" / "processed"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-fips", default="25", help="State FIPS code (default: 25, Massachusetts)")
    parser.add_argument("--year", type=int, default=2022, help="ACS 5-year vintage (default: 2022)")
    parser.add_argument("--characteristics", nargs="+", default=["N/A"], choices=list(CHARACTERISTICS),
                         help="Characteristic(s) to pull (default: N/A -- no age/disability filter)")
    parser.add_argument("--race-scheme", default="simplified_5", choices=list(SCHEMES),
                         help="Race/ethnicity category scheme (default: simplified_5)")
    parser.add_argument("--api-key", default=None, help="Census API key (default: CENSUS_API_KEY env var)")
    args = parser.parse_args()

    api_key = get_api_key(args.api_key)
    state_fips = args.state_fips

    out_path = DATA_DIR / state_fips / f"population_{args.year}.parquet"
    if out_path.exists():
        print(f"[{state_fips}] {args.year} — already downloaded, skipping.")
        return

    print(f"[{state_fips}] ACS {args.year} 5-year: {args.characteristics} x {args.race_scheme}")
    df = fetch_population(state_fips, args.year, "tract", get_scheme(args.race_scheme), args.characteristics, api_key)

    df["geography_level"] = "tract"
    df["state_fips"] = state_fips
    df["population_source"] = "acs5"
    df["population_vintage"] = str(args.year)
    df = validate_population_counts(df)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)
    print(f"  Wrote {len(df):,} rows -> {out_path}")


if __name__ == "__main__":
    main()
