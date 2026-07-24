"""
Layer 3 (Population): population-weighted tract centroids using ACS
block-group data as weights. Hybrid, per the best precision actually
available at block group (verified live, not assumed -- see below):

  - race_ethnicity="total" rows: weighted by the plain, non-race-iterated
    B01001 (age) / B18101 (disability) tables, which DO publish at block
    group -- so these get true characteristic-specific centroids (e.g.
    "where do children live," any race).
  - The 5 scheme-specific race categories: weighted by B03002 (Hispanic
    Origin by Race) general population instead -- the race-ITERATED age/
    disability tables (B01001A-I, B18101A-I) do not publish at block group
    at all (confirmed live: B01001H_001E -- White NH, the largest group in
    MA, just the grand-total row, no age breakdown -- returned null for
    every one of Massachusetts's 5,116 block groups). So these rows share
    one centroid across every characteristic for that race -- same
    granularity as 03_build_centroids_block.py's decennial approach, just
    at block-group instead of block resolution. B03002 is a genuine
    improvement over the letter tables for weighting specifically: it gives
    true "not Hispanic" figures for every category, not just White (the
    letter tables only have an NH-exact version for White/H).

Generalizes ../transportation2/v2_archive/code/02_build_weighted_centroids.py's
build_race_centroids() (same Σ(population_i * coord_i)/Σ(population_i)
weighting math).

Block-group locations: the old code downloaded Census Gazetteer block-group
internal points -- confirmed live that this file no longer exists (checked
every Gazetteer vintage 2015-2024; block group is not among the published
geographies at any of them). Uses TIGER block-group INTPTLAT/INTPTLON
instead -- same internal-point convention, already on disk from layer1
(data/layer1_geography/raw/2020/bg/).

A tract with zero population of some slice gets a null lat/lon, not a
fallback point -- the weighting is genuinely undefined (0/0), and a fake
fallback would misrepresent an absence as a location.

Requires a free Census API key: https://api.census.gov/data/key_signup.html
Set via the CENSUS_API_KEY env var, or pass --api-key.

Usage:
    python 02_build_centroids_block_group.py
    python 02_build_centroids_block_group.py --characteristics under_18 disability
    python 02_build_centroids_block_group.py --state-fips 36 --year 2023
"""
import argparse
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.acs_characteristics import CHARACTERISTICS
from lib.acs_client import fetch_population, fetch_race_totals, get_api_key
from lib.population_schema import validate_population_origins
from lib.race_ethnicity_schemes import SCHEMES, get_scheme, get_weight_scheme

REPO_ROOT = Path(__file__).parent.parent.parent
OUT_DIR = REPO_ROOT / "data" / "layer3_population" / "block_group_weighted" / "processed"


def get_bg_internal_points(state_fips):
    bg_path = REPO_ROOT / "data" / "layer1_geography" / "raw" / "2020" / "bg" / f"tl_2020_{state_fips}_bg.zip"
    if not bg_path.exists():
        raise SystemExit(f"Missing layer1 block-group file for state FIPS {state_fips}: {bg_path} (run layer1 first)")
    gdf = gpd.read_file(f"zip://{bg_path}")
    points = gdf[["GEOID", "INTPTLAT", "INTPTLON"]].copy()
    points["lat"] = points["INTPTLAT"].astype(float)
    points["lon"] = points["INTPTLON"].astype(float)
    return points[["GEOID", "lat", "lon"]]


def weighted_centroids(bg_population, bg_points, group_keys):
    """group_keys: which columns (beyond GEOID) to compute one centroid per
    -- ["race_ethnicity", "characteristic"] for the total-row path,
    ["race_ethnicity"] only for the B03002 race-totals path (no
    characteristic dimension there)."""
    df = bg_population.merge(bg_points, on="GEOID", how="inner")
    df["GEOID_tract"] = df["GEOID"].str[:11]
    df["_wx"] = df["population"] * df["lon"]
    df["_wy"] = df["population"] * df["lat"]

    grouped = df.groupby(["GEOID_tract"] + group_keys, as_index=False).agg(
        _wx=("_wx", "sum"), _wy=("_wy", "sum"), population=("population", "sum"),
    )
    grouped["lon"] = grouped["_wx"] / grouped["population"]
    grouped["lat"] = grouped["_wy"] / grouped["population"]
    grouped.loc[grouped["population"] == 0, ["lat", "lon"]] = None  # 0/0: undefined, not a fallback point

    return grouped.rename(columns={"GEOID_tract": "GEOID"})[["GEOID"] + group_keys + ["lat", "lon"]]


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
    scheme = get_scheme(args.race_scheme)
    weight_scheme = get_weight_scheme(args.race_scheme)

    out_path = OUT_DIR / state_fips / f"origins_{args.year}.parquet"
    if out_path.exists():
        print(f"[{state_fips}] {args.year} — already built, skipping.")
        return

    bg_points = get_bg_internal_points(state_fips)

    # Only characteristics whose plain (non-race-iterated) table actually
    # publishes at block group (verified per-characteristic in
    # lib/acs_characteristics.py -- age does, disability doesn't) can get
    # characteristic-specific weighting for race_ethnicity="total". Anything
    # else -- and every non-total race, always, since the race-iterated
    # tables never publish below tract regardless of table family -- falls
    # back to general-population weighting via B03002.
    bg_capable = [c for c in args.characteristics if CHARACTERISTICS[c]["bg_available"]]
    bg_fallback = [c for c in args.characteristics if not CHARACTERISTICS[c]["bg_available"]]
    if bg_fallback:
        print(f"  Note: {bg_fallback} not available at block-group geography -- "
              f"race_ethnicity=\"total\" falls back to general-population weighting for these too.")

    print(f"[{state_fips}] Fetching block-group race totals for weighting (B03002, general population)...")
    bg_race = fetch_race_totals(state_fips, args.year, "block group", weight_scheme, api_key)
    centroids_general = weighted_centroids(bg_race, bg_points, ["race_ethnicity"])

    if bg_capable:
        print(f"[{state_fips}] Fetching block-group population for weighting (total, characteristic-specific)...")
        bg_total = fetch_population(state_fips, args.year, "block group", {}, bg_capable, api_key)
        centroids_specific = weighted_centroids(bg_total, bg_points, ["race_ethnicity", "characteristic"])
    else:
        centroids_specific = None

    print(f"[{state_fips}] Fetching tract-level ACS population...")
    tract_population = fetch_population(state_fips, args.year, "tract", scheme, args.characteristics, api_key)

    use_specific = (
        tract_population["race_ethnicity"].eq("total") & tract_population["characteristic"].isin(bg_capable)
        if centroids_specific is not None else pd.Series(False, index=tract_population.index)
    )
    general_rows = tract_population[~use_specific].merge(centroids_general, on=["GEOID", "race_ethnicity"], how="left")
    if centroids_specific is not None:
        specific_rows = tract_population[use_specific].merge(centroids_specific, on=["GEOID", "race_ethnicity", "characteristic"], how="left")
        df = pd.concat([specific_rows, general_rows], ignore_index=True)
    else:
        df = general_rows

    df["geography_level"] = "tract"
    df["state_fips"] = state_fips
    df["population_source"] = "acs5"
    df["population_vintage"] = str(args.year)
    df["centroid_source"] = "acs5_blockgroup_tiger_intpt"
    df["centroid_vintage"] = str(args.year)
    df = validate_population_origins(df)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)
    print(f"  Wrote {len(df):,} rows -> {out_path}")


if __name__ == "__main__":
    main()
