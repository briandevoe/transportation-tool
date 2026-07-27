"""
Layer 3 (Population): population-weighted tract centroids using 2020
Decennial (PL 94-171) block-level race/ethnicity data as weights -- the
finer-geography alternative to 02_build_centroids_block_group.py.

Fully self-contained on one Census product (no ACS involved at all, unlike
script 02): PL 94-171 has no age/disability breakdown, so there's no
characteristic-specific population count to attach here the way script 02
attaches ACS tract-level counts. Per user decision, this produces one row per
(GEOID, race_ethnicity) -- `characteristic="N/A"` (a literal sentinel, not
null, since the dimension genuinely doesn't apply to this source) and
`population` is the Decennial race population itself.

Block locations: TIGER block files carry the same INTPTLAT20/INTPTLON20
internal-point convention as tracts/block groups -- already on disk from
layer1 (data/layer1_geography/raw/2020/block/), same pattern as script 02's use
of the block-group file for TIGER internal points (no Gazetteer equivalent
exists at block level anyway).

A tract with zero population of some race_ethnicity gets a null lat/lon, not
a fallback point -- same reasoning as script 02.

--k: how many population-weighted centroids to compute per (tract,
race_ethnicity) group instead of always collapsing to one (see
lib/weighted_centroids.py). Default 1 reproduces the original single-
centroid output exactly. Unlike script 02, there's no separate authoritative
population total to rescale against here -- the block-level sum IS the
population figure, so each centroid's population is used directly. k>1
output is written to a separate file (origins_2020_k<k>.parquet) so it never
collides with or silently replaces the k=1 default.

Requires a free Census API key: https://api.census.gov/data/key_signup.html
Set via the CENSUS_API_KEY env var, or pass --api-key.

Usage:
    python 03_build_centroids_block.py
    python 03_build_centroids_block.py --state-fips 36
    python 03_build_centroids_block.py --k 2
"""
import argparse
import glob
import sys
from pathlib import Path

import geopandas as gpd

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.decennial_client import fetch_block_race_totals
from lib.acs_client import get_api_key
from lib.population_schema import validate_population_origins
from lib.race_ethnicity_schemes import DECENNIAL_WEIGHT_SCHEMES, get_decennial_weight_scheme
from lib.weighted_centroids import weighted_centroid_clusters

REPO_ROOT = Path(__file__).parent.parent.parent
OUT_DIR = REPO_ROOT / "data" / "layer3_population" / "block_weighted" / "processed"
DECENNIAL_YEAR = "2020"  # only vintage PL 94-171 supports today


def get_block_internal_points(state_fips):
    matches = glob.glob(str(REPO_ROOT / "data" / "layer1_geography" / "raw" / "2020" / "block" / f"tl_2020_{state_fips}*_tabblock20.zip"))
    if not matches:
        raise SystemExit(f"Missing layer1 block file for state FIPS {state_fips} (run layer1 first)")
    gdf = gpd.read_file(f"zip://{matches[0]}")
    points = gdf[["GEOID20", "INTPTLAT20", "INTPTLON20"]].rename(columns={"GEOID20": "GEOID"})
    points["lat"] = points["INTPTLAT20"].astype(float)
    points["lon"] = points["INTPTLON20"].astype(float)
    return points[["GEOID", "lat", "lon"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-fips", default="25", help="State FIPS code (default: 25, Massachusetts)")
    parser.add_argument("--race-scheme", default="coi_5", choices=list(DECENNIAL_WEIGHT_SCHEMES),
                         help="Race/ethnicity category scheme (default: coi_5, matching COI's own breakdown)")
    parser.add_argument("--k", type=int, default=1,
                         help="Population-weighted centroids per (tract, race_ethnicity) group (default: 1)")
    parser.add_argument("--api-key", default=None, help="Census API key (default: CENSUS_API_KEY env var)")
    args = parser.parse_args()

    api_key = get_api_key(args.api_key)
    state_fips = args.state_fips
    weight_scheme = get_decennial_weight_scheme(args.race_scheme)

    # Filename must include both the race scheme and k -- see
    # 02_build_centroids_block_group.py for why. Defaults keep the original
    # filename so existing files/callers aren't disturbed.
    scheme_suffix = "" if args.race_scheme == "coi_5" else f"_{args.race_scheme}"
    k_suffix = "" if args.k == 1 else f"_k{args.k}"
    out_path = OUT_DIR / state_fips / f"origins_{DECENNIAL_YEAR}{scheme_suffix}{k_suffix}.parquet"
    if out_path.exists():
        print(f"[{state_fips}] {DECENNIAL_YEAR} {args.race_scheme} k={args.k} — already built, skipping.")
        return

    print(f"[{state_fips}] Fetching 2020 Decennial (PL 94-171) block-level race population...")
    block_population = fetch_block_race_totals(state_fips, DECENNIAL_YEAR, weight_scheme, api_key)
    block_points = get_block_internal_points(state_fips)

    print("  Computing population-weighted centroids...")
    df = weighted_centroid_clusters(block_population, block_points, ["race_ethnicity"], k=args.k)

    df["geography_level"] = "tract"
    df["state_fips"] = state_fips
    df["characteristic"] = "N/A"
    df["population_source"] = "dec2020_pl94171"
    df["population_vintage"] = DECENNIAL_YEAR
    df["centroid_source"] = "dec2020_pl94171_block"
    df["centroid_vintage"] = DECENNIAL_YEAR
    df = validate_population_origins(df)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)
    print(f"  Wrote {len(df):,} rows -> {out_path}")


if __name__ == "__main__":
    main()
