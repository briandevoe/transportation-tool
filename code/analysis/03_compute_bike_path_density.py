"""
Analysis (test run): bike path infrastructure density within fixed 1/3/5-mile
radii of population-weighted tract centroids, by race/ethnicity, subset to
urban tracts via RUCA. Deliberately no destination and no network routing --
this measures INFRASTRUCTURE SUPPLY ("how much bike path exists nearby"), not
access to a specific place. docs/reference.md and 01_compute_distance_metrics.py
already established "no network, just distance/density" as a legitimate
first-pass method, not a shortcut.

Bike path geometry comes directly from the RAW TIGER ROADS county zips
already cached (data/layer2_network/roads/tiger/raw/<year>/), filtered to
MTFCC "S1820" ("Bike Path or Trail") -- NOT from layer2's already-standardized
edges.parquet, which collapses S1820 together with walkway/stairway/alley/
bridle path (S1710/S1720/S1730/S1830) into one "other" highway_class and so
can't isolate bike paths specifically. This script reads the raw zips
independently; it does not touch or change 02_download_tiger_roads.py, its
schema, or its output.

Urban subsetting uses RUCA codes 1-3 by default ("Metropolitan area core" --
the standard grouping used in health/equity research for an urban/
metropolitan definition; --ruca-urban-codes for a different cutoff). RUCA
comes from the existing Layer 5 join (lib/reference_data.py).

Radius-based length, not distance-to-nearest: for each origin, buffer by
each of --radius-miles (default 1, 3, 5), clip the bike path network to that
buffer, and sum the clipped length -- a segment that's only partially inside
the buffer counts its in-buffer portion, not its full length or zero.

Usage:
    python 03_compute_bike_path_density.py                    # MA, RUCA 1-3 (urban), radii 1/3/5
    python 03_compute_bike_path_density.py --state-fips 25 36
    python 03_compute_bike_path_density.py --radius-miles 0.5 1 2
    python 03_compute_bike_path_density.py --ruca-urban-codes 1
"""
import argparse
import re
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.reference_data import attach_reference_attributes

REPO_ROOT = Path(__file__).parent.parent.parent
ORIGIN_DIRS = {
    "block_group_weighted": REPO_ROOT / "data" / "layer3_population" / "block_group_weighted" / "processed",
    "block_weighted": REPO_ROOT / "data" / "layer3_population" / "block_weighted" / "processed",
}
TIGER_ROADS_RAW_DIR = REPO_ROOT / "data" / "layer2_network" / "roads" / "tiger" / "raw"
OUT_DIR = REPO_ROOT / "data" / "analysis" / "processed"

BIKE_PATH_MTFCC = "S1820"
ORIGIN_CRS = "EPSG:4269"    # NAD83 -- matches TIGER's own native CRS, same convention used throughout layer1/layer2
LENGTH_CRS = "EPSG:5070"    # CONUS Albers equal-area/equal-distance, for accurate mile-radius buffering and length math
MILES_TO_METERS = 1609.34


def load_origins(origin_source, state_fips, year):
    """Same tolerance-for-missing-states pattern as 01_compute_distance_metrics.py,
    but unambiguous about WHICH file: layer3 now writes multiple origin files per
    state (default coi_5/k=1 at the bare origins_<year>.parquet, plus suffixed
    variants like origins_<year>_k2.parquet or origins_<year>_simplified_5.parquet
    for non-default runs). A plain "origins_*.parquet" glob would silently match
    and pick whichever suffixed variant happens to sort first -- confirmed this
    live, it grabbed a leftover _k2 test file instead of the intended default.
    When year is None, this matches ONLY the bare default-scheme/k=1 filename."""
    if year is None:
        state_dir = ORIGIN_DIRS[origin_source] / state_fips
        matches = [p for p in state_dir.glob("origins_*.parquet") if re.fullmatch(r"origins_\d{4}\.parquet", p.name)]
    else:
        matches = [ORIGIN_DIRS[origin_source] / state_fips / f"origins_{year}.parquet"]
    matches = [p for p in matches if p.exists()]
    if not matches:
        print(f"  [{state_fips}] No default-scheme origins file found for --origin-source {origin_source}, year {year} -- skipping.")
        return None
    df = pd.read_parquet(matches[0])
    before = len(df)
    df = df.dropna(subset=["lat", "lon"])
    print(f"  [{state_fips}] {matches[0].relative_to(REPO_ROOT)}: {len(df):,} origins with a centroid ({before - len(df):,} dropped, zero population)")
    return df


def load_bike_paths(state_fips, tiger_year):
    county_zips = sorted((TIGER_ROADS_RAW_DIR / str(tiger_year)).glob(f"tl_{tiger_year}_{state_fips}*_roads.zip"))
    if not county_zips:
        print(f"  [{state_fips}] No raw TIGER ROADS files found for year {tiger_year} "
              f"-- run layer2_network/02_download_tiger_roads.py first.")
        return None
    pieces = [gpd.read_file(f"zip://{zpath}") for zpath in county_zips]
    pieces = [p[p["MTFCC"] == BIKE_PATH_MTFCC][["MTFCC", "geometry"]] for p in pieces]
    bike_paths = gpd.GeoDataFrame(pd.concat(pieces, ignore_index=True), geometry="geometry", crs=pieces[0].crs)
    print(f"  [{state_fips}] {len(bike_paths):,} bike path (MTFCC {BIKE_PATH_MTFCC}) segments across {len(county_zips)} counties")
    return bike_paths.to_crs(LENGTH_CRS)


def bike_path_length_within_radius(origins, bike_paths, radius_miles_list):
    """origins: DataFrame with lat/lon (degrees, ORIGIN_CRS). bike_paths: GeoDataFrame
    already in LENGTH_CRS (meters). Returns one row per (origin index, radius) with
    bike_path_length_m -- a fixed-radius analog of 01_compute_distance_metrics.py's
    within-threshold metric, measuring total length instead of nearest/count."""
    origin_points = gpd.GeoSeries(
        gpd.points_from_xy(origins["lon"], origins["lat"]), crs=ORIGIN_CRS, index=origins.index
    ).to_crs(LENGTH_CRS)

    sindex = bike_paths.sindex
    rows = []
    for idx, point in origin_points.items():
        for radius_miles in radius_miles_list:
            buffer = point.buffer(radius_miles * MILES_TO_METERS)
            candidate_idx = list(sindex.query(buffer))
            length_m = bike_paths.geometry.iloc[candidate_idx].intersection(buffer).length.sum() if candidate_idx else 0.0
            rows.append({"_origin_index": idx, "radius_miles": radius_miles, "bike_path_length_m": length_m})
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-fips", nargs="+", default=["25"], help="State FIPS code(s) (default: 25, Massachusetts)")
    parser.add_argument("--origin-source", default="block_group_weighted", choices=list(ORIGIN_DIRS),
                         help="Which layer3 centroid method to use (default: block_group_weighted)")
    parser.add_argument("--origin-year", default=None, help="Origins file vintage (default: whatever's on disk)")
    parser.add_argument("--tiger-year", type=int, default=2020, help="TIGER ROADS vintage to pull bike paths from (default: 2020)")
    parser.add_argument("--radius-miles", type=float, nargs="+", default=[1.0, 3.0, 5.0],
                         help="Radius/radii in miles to compute bike path length within (default: 1 3 5)")
    parser.add_argument("--ruca-urban-codes", type=float, nargs="+", default=[1.0, 2.0, 3.0],
                         help="RUCA codes considered 'urban' for subsetting (default: 1 2 3, the standard "
                              "Metropolitan-area-core grouping)")
    args = parser.parse_args()

    print(f"Loading origins for {len(args.state_fips)} state(s)...")
    origin_frames = [load_origins(args.origin_source, s, args.origin_year) for s in args.state_fips]
    origin_frames = [f for f in origin_frames if f is not None]
    if not origin_frames:
        raise SystemExit("No origins found for any requested state.")
    origins = pd.concat(origin_frames, ignore_index=True)

    origins = attach_reference_attributes(origins)
    before_urban = len(origins)
    origins = origins[origins["ruca_code"].isin(args.ruca_urban_codes)].reset_index(drop=True)
    print(f"Urban subset (RUCA in {args.ruca_urban_codes}): {len(origins):,} / {before_urban:,} origins")
    if origins.empty:
        raise SystemExit("No origins left after RUCA urban subsetting.")

    all_metrics = []
    for state_fips in args.state_fips:
        state_origins = origins[origins["state_fips"] == state_fips]
        if state_origins.empty:
            continue
        bike_paths = load_bike_paths(state_fips, args.tiger_year)
        if bike_paths is None or bike_paths.empty:
            print(f"  [{state_fips}] No bike path segments found -- skipping.")
            continue
        metrics = bike_path_length_within_radius(state_origins, bike_paths, args.radius_miles)
        merged = state_origins.reset_index().rename(columns={"index": "_origin_index"}).merge(metrics, on="_origin_index")
        all_metrics.append(merged)

    if not all_metrics:
        raise SystemExit("No bike path metrics computed for any requested state.")

    df = pd.concat(all_metrics, ignore_index=True)
    df["bike_path_length_mi"] = df["bike_path_length_m"] / MILES_TO_METERS
    df["tiger_year"] = args.tiger_year

    out_cols = [
        "GEOID", "geography_level", "state_fips", "race_ethnicity", "characteristic", "population",
        "centroid_index", "centroid_k", "dispersion_m", "lat", "lon",
        "ruca_code", "ruca_description",
        "radius_miles", "bike_path_length_m", "bike_path_length_mi", "tiger_year",
    ]
    df = df[out_cols]

    state_label = "_".join(sorted(args.state_fips))
    out_path = OUT_DIR / f"bike_path_density_{state_label}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)
    print(f"Wrote {len(df):,} rows -> {out_path}")


if __name__ == "__main__":
    main()
