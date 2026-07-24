"""
Analysis: straight-line (haversine) distance accessibility metrics from
population-weighted tract centroids (layer3) to layer4 destinations --
hospitals by default, or schools/grocery via --dest-set (can pass more than
one). Schools is a single national file per dest_type (NCES); grocery and
hospitals are per-state OSM extracts, concatenated across whichever states
--state-fips resolves to, same tolerance-for-missing-states load_origins()
already has for a multi-state batch.

Deliberately the simplest possible metric -- no road network -- as an
end-to-end sanity check that layers 1-4 actually join together correctly
before investing in network-routing-based metrics later.
docs/reference.md already documents "no network, just distance" as a
legitimate first-pass method, not a shortcut.

Three metrics per (tract x race_ethnicity x characteristic x dest_type),
using the method-agnostic column names in lib/analysis_schema.py (shared
with 02_compute_travel_time_metrics.py, so the two are directly comparable
and concatenable -- distinguished by distance_method/distance_unit, not by
different column names):
  - nearest_value: distance (miles) to the single closest school.
  - avg_k_nearest_value: mean distance to the k_nearest closest (--k-nearest).
  - avg_within_threshold_value / n_within_threshold: mean distance to (and
    count of) every school within threshold_value miles (--radius-miles).
    The average is null when the count is 0 -- genuinely undefined, not zero.

Candidate search reuses the proven approach from
../transportation2/v2_archive/code/05_compute_school_travel_times.py's
route_chunk(): a scipy.spatial.cKDTree over destination lon/lat scaled by
cos(mean origin lat) for a fast equirectangular-approximate candidate set,
then exact haversine distance for everything actually reported.

Also attaches COI/RUCA/redlining tract attributes (lib/reference_data.py)
so metrics can be grouped by e.g. COI opportunity level x race, or RUCA code
x race, directly from this output.

Usage:
    python 01_compute_distance_metrics.py                        # MA, hospitals (default -- hospitals is MA-only so far)
    python 01_compute_distance_metrics.py --dest-set schools grocery hospitals --state-fips 25
    python 01_compute_distance_metrics.py --origin-source block_weighted
    python 01_compute_distance_metrics.py --state-fips all --dest-set schools   # schools has full coverage; --state-fips 25 36 for a specific subset

Note: any state without a layer3 origins file yet is silently skipped (with
a printed warning) rather than aborting the run -- run
layer3_population/01+02 (and layer5_reference/03_prepare_redlining.py) for a state
first if it's missing from the output.

Known gap: Connecticut (state FIPS 09) drops out entirely (0 origins survive
the lat/lon dropna in load_origins()) -- not zero population, a real
geography-vintage mismatch. CT abolished its 8 counties in favor of 9
Planning Regions as of 2022-vintage Census geography; layer1's TIGER
download is 2020-vintage (old counties), so ACS 2022's planning-region-coded
GEOIDs never match layer1's county-coded block-group file, and every CT
origin's weighted centroid comes back null. Fix would be re-downloading
layer1 TIGER for state 09 at --year 2022 and rebuilding its layer3 origins;
not done -- CT is excluded from national runs until that happens.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.analysis_schema import validate_metrics
from lib.reference_data import attach_reference_attributes
from lib.state_lists import STATE_FIPS_49 as STATE_FIPS_DEFAULT

REPO_ROOT = Path(__file__).parent.parent.parent
MILES_PER_DEGREE_LAT = 69.0  # constant; used only to size the KDTree radius query, exact distances are haversine

ORIGIN_DIRS = {
    "block_group_weighted": REPO_ROOT / "data" / "layer3_population" / "block_group_weighted" / "processed",
    "block_weighted": REPO_ROOT / "data" / "layer3_population" / "block_weighted" / "processed",
}
OUT_DIR = REPO_ROOT / "data" / "analysis" / "processed"

# Destination sets: "schools" is a single national file per dest_type (NCES
# publishes one nationwide file); "grocery"/"hospitals" are per-state OSM
# extracts (data/layer4_destination/{grocery,hospitals}/processed/<state>/),
# since they're built one state's PBF at a time -- same reason origins are
# concatenated across states. load_destinations() below handles both shapes.
DEST_SETS = {
    "schools": {
        "national": True,
        "dir": REPO_ROOT / "data" / "layer4_destination" / "schools" / "processed",
        "types": {
            "school_highschool": "highschools_{dest_year}.parquet",
            "school_elementary_middle": "elementary_middle_{dest_year}.parquet",
        },
    },
    "grocery": {
        "national": False,
        "dir": REPO_ROOT / "data" / "layer4_destination" / "grocery" / "processed",
        "types": {"grocery": "grocery_osm.parquet"},
    },
    "hospitals": {
        "national": False,
        "dir": REPO_ROOT / "data" / "layer4_destination" / "hospitals" / "processed",
        "types": {"hospital": "hospitals_osm.parquet"},
    },
}

DISTANCE_METHOD = "euclidean_haversine"


def haversine_miles(lat1, lon1, lat2, lon2):
    """lat1/lon1: scalar origin. lat2/lon2: array of candidate destinations."""
    R = 3958.8
    lat1r, lat2r = np.radians(lat1), np.radians(lat2)
    dlat = lat2r - lat1r
    dlon = np.radians(np.asarray(lon2) - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2) ** 2
    return R * 2 * np.arcsin(np.sqrt(a))


def load_origins(origin_source, state_fips, year):
    """Returns None (with a printed warning) if this state has no layer3
    origins file yet, rather than aborting -- lets a multi-state batch skip
    states that haven't been built instead of failing the whole run."""
    matches = list((ORIGIN_DIRS[origin_source] / state_fips).glob("origins_*.parquet")) if year is None \
        else [ORIGIN_DIRS[origin_source] / state_fips / f"origins_{year}.parquet"]
    matches = [p for p in matches if p.exists()]
    if not matches:
        print(f"  [{state_fips}] No origins file found for --origin-source {origin_source}, year {year} -- skipping.")
        return None
    df = pd.read_parquet(matches[0])
    before = len(df)
    df = df.dropna(subset=["lat", "lon"])
    print(f"  [{state_fips}] {matches[0].relative_to(REPO_ROOT)}: {len(df):,} origins with a centroid ({before - len(df):,} dropped, zero population)")
    return df


def load_destinations(dest_set_name, dest_year, states):
    """Returns {dest_type: (DataFrame, valid_states)}. "national" dest sets
    (schools) read one file and valid_states=None, meaning "covers whatever
    origins are passed in, no filtering needed". Per-state sets (grocery,
    hospitals) concatenate across `states`, skipping (with a printed
    warning) any state not yet built -- same tolerance load_origins() has --
    and valid_states is the set that actually contributed, so the caller can
    restrict origins to the same states rather than measuring e.g. a
    California origin against only-Massachusetts destinations (that mismatch
    is exactly what produced 1000+ mile "nearest hospital" garbage before
    this fix)."""
    spec = DEST_SETS[dest_set_name]
    result = {}
    for dest_type, filename_template in spec["types"].items():
        filename = filename_template.format(dest_year=dest_year)
        if spec["national"]:
            path = spec["dir"] / filename
            if not path.exists():
                raise SystemExit(f"Missing destinations file: {path}")
            result[dest_type] = (pd.read_parquet(path), None)
        else:
            frames, valid_states = [], set()
            for s in states:
                path = spec["dir"] / s / filename
                if path.exists():
                    frames.append(pd.read_parquet(path))
                    valid_states.add(s)
                else:
                    print(f"  [{dest_type}] No file for state {s} -- skipping.")
            if not frames:
                raise SystemExit(f"No {dest_type} destination files found for any requested state.")
            result[dest_type] = (pd.concat(frames, ignore_index=True), valid_states)
    return result


def nearest_and_radius_metrics(origins, dests, k_nearest, radius_miles):
    lon_scale = np.cos(np.radians(origins["lat"].mean()))
    dest_xy = np.column_stack([dests["lon"].values * lon_scale, dests["lat"].values])
    tree = cKDTree(dest_xy)
    dest_lat, dest_lon = dests["lat"].values, dests["lon"].values

    # Buffered radius in the same scaled-degree space as the tree, then
    # filtered to the exact haversine radius below -- the buffer absorbs the
    # equirectangular approximation's error near the query boundary.
    radius_deg_buffered = (radius_miles / MILES_PER_DEGREE_LAT) * 1.15

    rows = []
    for lat_o, lon_o in zip(origins["lat"].values, origins["lon"].values):
        query_xy = [lon_o * lon_scale, lat_o]

        _, idx_k = tree.query(query_xy, k=k_nearest)
        idx_k = np.atleast_1d(idx_k)
        exact_k = haversine_miles(lat_o, lon_o, dest_lat[idx_k], dest_lon[idx_k])

        idx_r = tree.query_ball_point(query_xy, r=radius_deg_buffered)
        if idx_r:
            exact_r = haversine_miles(lat_o, lon_o, dest_lat[idx_r], dest_lon[idx_r])
            within = exact_r[exact_r <= radius_miles]
        else:
            within = np.array([])

        rows.append({
            "nearest_value": float(exact_k.min()),
            "avg_k_nearest_value": float(exact_k.mean()),
            "avg_within_threshold_value": float(within.mean()) if len(within) else None,
            "n_within_threshold": int(len(within)),
        })
    return pd.DataFrame(rows, index=origins.index)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-fips", nargs="+", default=["all"],
                         help="One or more state FIPS codes, or 'all' for the 49 states + DC default set (excludes AK; "
                              "default: all -- for non-national dest sets like hospitals/grocery, origins are "
                              "auto-scoped to whichever states actually have that destination data built)")
    parser.add_argument("--origin-source", default="block_group_weighted",
                         choices=list(ORIGIN_DIRS), help="Which layer3 centroid method to use (default: block_group_weighted)")
    parser.add_argument("--origin-year", default=None, help="Origins file vintage (default: whatever's on disk)")
    parser.add_argument("--dest-set", nargs="+", default=["hospitals"], choices=list(DEST_SETS),
                         help="Which destination set(s) to compute against: schools, grocery, hospitals (default: hospitals)")
    parser.add_argument("--dest-year", default="2425", help="Schools destinations file vintage (default: 2425; ignored by grocery/hospitals)")
    parser.add_argument("--k-nearest", type=int, default=5, help="K for the average-of-K-nearest metric (default: 5)")
    parser.add_argument("--radius-miles", type=float, default=10.0, help="Radius for the within-radius metric (default: 10)")
    args = parser.parse_args()

    states = STATE_FIPS_DEFAULT if args.state_fips == ["all"] else args.state_fips

    print(f"Loading origins for {len(states)} state(s)...")
    origin_frames = [load_origins(args.origin_source, s, args.origin_year) for s in states]
    origin_frames = [f for f in origin_frames if f is not None]
    if not origin_frames:
        raise SystemExit("No origins found for any requested state.")
    origins = pd.concat(origin_frames, ignore_index=True)
    print(f"Total: {len(origins):,} origins across {len(origin_frames)} state(s)")

    dest_frames = {}
    for dest_set_name in args.dest_set:
        dest_frames.update(load_destinations(dest_set_name, args.dest_year, states))

    all_metrics = []
    for dest_type, (dests, valid_states) in dest_frames.items():
        if valid_states is None:
            dest_origins = origins
        else:
            dest_origins = origins[origins["state_fips"].isin(valid_states)]
            excluded = sorted(set(states) - valid_states)
            if excluded:
                print(f"[{dest_type}] Scoping origins to {sorted(valid_states)} -- excluded (no destinations there yet): {excluded}")
        print(f"[{dest_type}] {len(dests):,} destinations, {len(dest_origins):,} origins")

        metrics = nearest_and_radius_metrics(dest_origins, dests, args.k_nearest, args.radius_miles)
        chunk = pd.concat([dest_origins[["GEOID", "geography_level", "state_fips", "race_ethnicity", "characteristic", "population"]].reset_index(drop=True), metrics.reset_index(drop=True)], axis=1)
        chunk["dest_type"] = dest_type
        chunk["distance_method"] = DISTANCE_METHOD
        chunk["distance_unit"] = "miles"
        chunk["k_nearest"] = args.k_nearest
        chunk["threshold_value"] = args.radius_miles
        all_metrics.append(chunk)

    df = pd.concat(all_metrics, ignore_index=True)
    df = attach_reference_attributes(df)
    df = validate_metrics(df)

    dest_label = "_".join(sorted(args.dest_set))
    out_dir = OUT_DIR / (states[0] if len(states) == 1 else "national")
    out_path = out_dir / f"distance_metrics_{dest_label}_{args.dest_year}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)
    print(f"Wrote {len(df):,} rows -> {out_path}")


if __name__ == "__main__":
    main()
