"""
Layer 2 (Network): download and standardize Census TIGER/Line road geometry.

Secondary/reference road source -- not routable. Unlike OSM, TIGER's ROADS
files carry no oneway/speed/lanes/turn-restriction attributes, only geometry
plus a road-class code (MTFCC). Two things make it worth having anyway:
  - It's vintage-locked to the same year as the geography layer (this repo
    already flagged a 2010-vs-2020 tract mismatch as a real past bug), so
    it's a reliable apples-to-apples reference when auditing OSM coverage.
  - Its MTFCC classes separately identify walkways, stairways, and bike
    paths (S1710/S1720/S1820/...) -- a lead worth having on file for the
    sidewalk/bike-lane layer scripts later, even though OSM tagging quality
    for those is inconsistent.

TIGER's "ROADS" directory (all roads, MTFCC S11xx-S18xx) is published per
COUNTY, not per state -- confirmed against the live directory listing, e.g.
https://www2.census.gov/geo/tiger/TIGER2020/ROADS/tl_2020_25019_roads.zip
(Nantucket county, MA). This differs from PRISECROADS (primary/secondary
only, one file per state) -- PRISECROADS would miss the walkway/bike-path
classes that are the actual reason to keep TIGER around, so this script
enumerates and downloads every county in the target state instead.

Output is standardized to the same schema as 01_download_osm_roads.py (see
code/lib/network_schema.py), combined into one file per state:
    data/layer2_network/roads/tiger/processed/<state_fips>/edges.parquet

Usage:
    python 02_download_tiger_roads.py                     # Massachusetts, 2020 (default)
    python 02_download_tiger_roads.py --state-fips 36 42   # New York and Pennsylvania, 2020
    python 02_download_tiger_roads.py --region all          # all 56 states/territories, 2020
    python 02_download_tiger_roads.py --year 2022          # a different TIGER vintage
"""
import argparse
import re
import sys
import time
import urllib.request
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.network_schema import validate_network_edges
from lib.tiger_download import REGION_PRESETS
from lib.tiger_download import download_one as tiger_download_one
from lib.tiger_download import fmt_elapsed

REPO_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = REPO_ROOT / "data" / "layer2_network" / "roads" / "tiger"
BASE_URL = "https://www2.census.gov/geo/tiger/TIGER{year}/ROADS"

# MTFCC (MAF/TIGER Feature Class Code) -> standardized highway_class (see
# lib/network_schema.py). Verified against a live county file's value_counts,
# not guessed. Anything not listed here falls back to "other".
MTFCC_MAP = {
    "S1100": "primary",       # Primary road
    "S1200": "secondary",     # Secondary road
    "S1400": "residential",   # Local neighborhood road / rural road / city street
    "S1500": "service",       # Vehicular trail (4WD)
    "S1630": "service",       # Ramp
    "S1640": "service",       # Service drive alongside a limited-access highway
    "S1740": "service",       # Private road for service vehicles
    "S1780": "service",       # Parking lot road
    "S1710": "other",         # Walkway / pedestrian trail
    "S1720": "other",         # Stairway
    "S1730": "other",         # Alley
    "S1820": "other",         # Bike path
    "S1830": "other",         # Bridle path
}

LENGTH_CRS = "EPSG:5070"   # CONUS Albers equal-area, for length_m -- not valid for AK/HI/territories
STORAGE_CRS = "EPSG:4326"  # match the OSM edges output for a directly comparable geometry CRS


def list_county_files(year, state_fips):
    """Scrape the live ROADS directory listing for every county file under a
    state, rather than hand-maintaining a state->county FIPS list."""
    index_url = f"{BASE_URL.format(year=year)}/"
    with urllib.request.urlopen(index_url) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
    pattern = rf"tl_{year}_{state_fips}\d{{3}}_roads\.zip"
    return sorted(set(re.findall(pattern, html)))


def download_one_county(filename, year, raw_dir):
    # Delegates to lib.tiger_download's hardened download_one (zip-signature
    # validation + 429 retry-backoff) instead of a bare urlretrieve -- with
    # ~3,234 counties nationally instead of the ~56 per-state requests
    # everything else here makes, the WAF-block-page and rate-limit issues
    # already hit once are far more likely to recur unnoticed at this scale.
    dest_path = raw_dir / filename
    url = f"{BASE_URL.format(year=year)}/{filename}"
    result = tiger_download_one(url, dest_path)
    return dest_path, result


def map_highway_class(mtfcc):
    return MTFCC_MAP.get(mtfcc, "other")


def standardize(county_paths, state_fips, year):
    pieces = [gpd.read_file(f"zip://{p}") for p in county_paths]
    gdf = pd.concat(pieces, ignore_index=True)
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=pieces[0].crs)

    gdf["length_m"] = gdf.geometry.to_crs(LENGTH_CRS).length
    gdf = gdf.to_crs(STORAGE_CRS)

    gdf["edge_id"] = gdf["LINEARID"]
    gdf["highway_class"] = gdf["MTFCC"].apply(map_highway_class)
    gdf["name"] = gdf["FULLNAME"]
    gdf["network_type"] = "roads"
    gdf["source"] = "tiger"
    gdf["vintage"] = year
    gdf["state_fips"] = state_fips

    return validate_network_edges(gdf)


def process_state(state_fips, year):
    out_dir = DATA_DIR / "processed" / state_fips
    edges_path = out_dir / "edges.parquet"
    if edges_path.exists():
        print(f"[{state_fips}] {year} — already processed, skipping.")
        return

    print(f"[{state_fips}] TIGER {year} ROADS")
    filenames = list_county_files(year, state_fips)
    if not filenames:
        print(f"  No ROADS files found for state FIPS {state_fips}, year {year} -- skipping.")
        return
    print(f"  {len(filenames)} counties found")

    raw_dir = DATA_DIR / "raw" / str(year)
    county_paths = []
    counts = {"downloaded": 0, "skipped": 0, "failed": 0}
    t0 = time.time()
    for filename in filenames:
        path, result = download_one_county(filename, year, raw_dir)
        counts[result] += 1
        if result != "skipped":
            time.sleep(0.3)  # avoid tripping the server's rate limit on back-to-back requests
        if result != "failed":
            county_paths.append(path)
    print(f"  {counts['downloaded']} downloaded, {counts['skipped']} already present, "
          f"{counts['failed']} failed ({fmt_elapsed(time.time() - t0)})")

    if not county_paths:
        print(f"  No usable county files for state FIPS {state_fips} -- skipping standardization.")
        return

    print("  Standardizing...")
    edges_gdf = standardize(county_paths, state_fips, year)

    out_dir.mkdir(parents=True, exist_ok=True)
    edges_gdf.to_parquet(edges_path)
    print(f"  Wrote {len(edges_gdf):,} edges -> {edges_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-fips", nargs="+", default=["25"],
                         help="State FIPS code(s) (default: 25, Massachusetts) -- overridden by --region if given")
    parser.add_argument("--region", choices=list(REGION_PRESETS), default=None,
                         help="'all' = 56 states/territories, 'conus_ak_hi' = 50 states + DC, no territories -- "
                              "use this instead of --state-fips to run many states in one invocation")
    parser.add_argument("--year", type=int, default=2020, help="TIGER/Line vintage year (default: 2020, matches layer1)")
    args = parser.parse_args()

    states = REGION_PRESETS[args.region] if args.region else args.state_fips

    for state_fips in states:
        process_state(state_fips, args.year)

    print("\nDone.")


if __name__ == "__main__":
    main()
