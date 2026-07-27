"""
Analysis: accessibility metrics for every Child Opportunity Index "top 100"
metro area (the in_top100_metro flag on layer5_reference's COI file) --
population-weighted bike path density, plus network-routed travel time to
schools and hospitals, broken out by race/ethnicity and by COI score.

Metro membership, metro name, and COI score all come straight from Layer 5's
COI file (layer5_reference/01_prepare_coi.py, which now carries metro_fips/
metro_name/metro_type/in_top100_metro alongside the COI score) -- this
script doesn't invent its own metro definition. Origins are restricted to
individual TRACTS flagged in_top100_metro, not to whole states -- a state
that contains part of a top-100 metro still has plenty of non-metro rural
tracts that have no business being swept in.

Two metrics, two different coverage stories:
  - Bike path density needs no network at all -- same method as
    03_compute_bike_path_density.py (buffer + clip against raw TIGER MTFCC
    S1820 geometry, already cached nationally). Runs for every top-100
    metro today, full stop.
  - Travel time to schools/hospitals needs a routable network -- same
    method as 02_compute_travel_time_metrics.py. Only runs for the states
    that already have an OSM network built
    (layer2_network/01_download_osm_roads.py). A metro whose tracts span
    both a covered and an uncovered state will only get the covered
    state's population counted -- the coverage report printed at the end
    says exactly which metros/states are missing rather than silently
    averaging over whoever happens to be available.

Usage:
    python 04_compute_metro_accessibility.py                        # both metrics, whatever's covered today
    python 04_compute_metro_accessibility.py --metric bike_path
    python 04_compute_metro_accessibility.py --metric travel_time --dest-set hospitals
"""
import argparse
import re
import sys
from pathlib import Path

import geopandas as gpd
import igraph as ig
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.analysis_schema import validate_metrics
from lib.reference_data import attach_reference_attributes

REPO_ROOT = Path(__file__).parent.parent.parent
ORIGIN_DIRS = {
    "block_group_weighted": REPO_ROOT / "data" / "layer3_population" / "block_group_weighted" / "processed",
    "block_weighted": REPO_ROOT / "data" / "layer3_population" / "block_weighted" / "processed",
}
COI_DIR = REPO_ROOT / "data" / "layer5_reference" / "coi" / "processed"
NETWORK_DIR = REPO_ROOT / "data" / "layer2_network" / "roads" / "osm" / "processed"
TIGER_ROADS_RAW_DIR = REPO_ROOT / "data" / "layer2_network" / "roads" / "tiger" / "raw"
OUT_DIR = REPO_ROOT / "data" / "analysis" / "processed" / "metro"

BIKE_PATH_MTFCC = "S1820"
ORIGIN_CRS = "EPSG:4269"
LENGTH_CRS = "EPSG:5070"
MILES_TO_METERS = 1609.34
DISTANCE_METHOD = "osm_network_dijkstra"

DEST_SETS = {
    "schools": {
        "national": True,
        "dir": REPO_ROOT / "data" / "layer4_destination" / "schools" / "processed",
        "types": {
            "school_highschool": "highschools_{dest_year}.parquet",
            "school_elementary_middle": "elementary_middle_{dest_year}.parquet",
        },
    },
    "hospitals": {
        "national": False,
        "dir": REPO_ROOT / "data" / "layer4_destination" / "hospitals" / "processed",
        "types": {"hospital": "hospitals_osm.parquet"},
    },
}


# ---------- Metro membership (Layer 5 COI) ----------

def load_metro_tracts():
    matches = sorted(COI_DIR.glob("coi_tract_*.parquet"))
    if not matches:
        raise SystemExit(f"No processed COI file found in {COI_DIR} -- run layer5_reference/01_prepare_coi.py first.")
    coi = pd.read_parquet(matches[-1])
    metro = coi[coi["in_top100_metro"] == True].copy()  # noqa: E712 (nullable boolean, `is True` mis-handles NA)
    print(f"Loaded {matches[-1].name}: {metro['metro_fips'].nunique()} top-100 metros, "
          f"{len(metro):,} tracts, {metro['GEOID'].str[:2].nunique()} states")
    return metro


# ---------- Origins ----------

def load_origins(origin_source, state_fips, year):
    if year is None:
        state_dir = ORIGIN_DIRS[origin_source] / state_fips
        if not state_dir.exists():
            return None
        matches = [p for p in state_dir.glob("origins_*.parquet") if re.fullmatch(r"origins_\d{4}\.parquet", p.name)]
    else:
        matches = [ORIGIN_DIRS[origin_source] / state_fips / f"origins_{year}.parquet"]
    matches = [p for p in matches if p.exists()]
    if not matches:
        return None
    df = pd.read_parquet(matches[0])
    return df.dropna(subset=["lat", "lon"])


def load_metro_origins(origin_source, year, metro_tracts):
    states = sorted(metro_tracts["GEOID"].str[:2].unique())
    frames = []
    for state_fips in states:
        df = load_origins(origin_source, state_fips, year)
        if df is None:
            print(f"  [{state_fips}] No origins file found -- skipping.")
            continue
        frames.append(df)
    if not frames:
        raise SystemExit("No origins found for any state touched by a top-100 metro.")
    origins = pd.concat(frames, ignore_index=True)
    origins = attach_reference_attributes(origins)
    origins = origins[origins["in_top100_metro"] == True].reset_index(drop=True)  # noqa: E712
    print(f"Metro-restricted origins: {len(origins):,} rows across {origins['state_fips'].nunique()} states")
    return origins


# ---------- Bike path density (no network needed) ----------

def load_bike_paths(state_fips, tiger_year=2020):
    county_zips = sorted((TIGER_ROADS_RAW_DIR / str(tiger_year)).glob(f"tl_{tiger_year}_{state_fips}*_roads.zip"))
    if not county_zips:
        return None
    pieces = [gpd.read_file(f"zip://{zpath}") for zpath in county_zips]
    pieces = [p[p["MTFCC"] == BIKE_PATH_MTFCC][["MTFCC", "geometry"]] for p in pieces]
    pieces = [p for p in pieces if len(p)]
    if not pieces:
        return None
    bike_paths = gpd.GeoDataFrame(pd.concat(pieces, ignore_index=True), geometry="geometry", crs=pieces[0].crs)
    return bike_paths.to_crs(LENGTH_CRS)


def bike_path_length_within_radius(origins, bike_paths, radius_miles_list):
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


def compute_bike_path_metric(origins, radius_miles_list, tiger_year=2020):
    all_metrics = []
    for state_fips in sorted(origins["state_fips"].unique()):
        state_origins = origins[origins["state_fips"] == state_fips]
        bike_paths = load_bike_paths(state_fips, tiger_year)
        if bike_paths is None or bike_paths.empty:
            print(f"  [{state_fips}] No bike path segments found -- skipping ({len(state_origins):,} origins affected).")
            continue
        metrics = bike_path_length_within_radius(state_origins, bike_paths, radius_miles_list)
        merged = state_origins.reset_index().rename(columns={"index": "_origin_index"}).merge(metrics, on="_origin_index")
        all_metrics.append(merged)
        print(f"  [{state_fips}] {len(state_origins):,} metro origins x {len(radius_miles_list)} radii")

    df = pd.concat(all_metrics, ignore_index=True)
    df["bike_path_length_mi"] = df["bike_path_length_m"] / MILES_TO_METERS
    df["tiger_year"] = tiger_year

    out_cols = [
        "GEOID", "geography_level", "state_fips", "race_ethnicity", "characteristic", "population",
        "centroid_index", "centroid_k", "dispersion_m", "lat", "lon",
        "metro_fips", "metro_name", "metro_type", "in_top100_metro",
        "coi_level_nat", "coi_score_nat", "coi_vintage",
        "ruca_code", "ruca_description",
        "radius_miles", "bike_path_length_m", "bike_path_length_mi", "tiger_year",
    ]
    return df[out_cols]


# ---------- Travel time to schools/hospitals (needs a routable network) ----------

def states_with_network():
    return {p.name for p in NETWORK_DIR.glob("*") if (p / "edges.parquet").exists() and (p / "nodes.parquet").exists()}


def build_graph(state_fips):
    edges_path = NETWORK_DIR / state_fips / "edges.parquet"
    nodes_path = NETWORK_DIR / state_fips / "nodes.parquet"
    nodes = pd.read_parquet(nodes_path)
    edges = pd.read_parquet(edges_path).dropna(subset=["from_node", "to_node", "length_m", "speed_kph"])

    node_index = {nid: i for i, nid in enumerate(nodes["node_id"])}
    u_idx = edges["from_node"].map(node_index)
    v_idx = edges["to_node"].map(node_index)
    valid = u_idx.notna() & v_idx.notna()
    edges, u_idx, v_idx = edges[valid], u_idx[valid].astype(int), v_idx[valid].astype(int)

    travel_time_min = (edges["length_m"].astype(float) / 1000) / edges["speed_kph"].astype(float) * 60
    g = ig.Graph(n=len(nodes), edges=list(zip(u_idx, v_idx)), directed=True)
    g.es["weight"] = travel_time_min.values
    return g, nodes


def snap_to_nearest_node(lats, lons, node_lat, node_lon, lon_scale):
    tree = cKDTree(np.column_stack([node_lon * lon_scale, node_lat]))
    _, idx = tree.query(np.column_stack([np.asarray(lons) * lon_scale, np.asarray(lats)]), k=1)
    return np.atleast_1d(idx)


def travel_time_metrics(origin_node_idx, dest_node_idx, g, k_nearest, threshold_min):
    unique_o, o_inverse = np.unique(origin_node_idx, return_inverse=True)
    unique_d, d_inverse = np.unique(dest_node_idx, return_inverse=True)
    dist_matrix = np.array(g.distances(source=list(unique_o), target=list(unique_d), weights="weight"))
    dist_matrix[np.isinf(dist_matrix)] = np.nan

    rows = []
    for i in range(len(origin_node_idx)):
        times = dist_matrix[o_inverse[i], d_inverse]
        finite = times[~np.isnan(times)]
        if len(finite) == 0:
            rows.append({"nearest_value": np.nan, "avg_k_nearest_value": np.nan,
                         "avg_within_threshold_value": None, "n_within_threshold": 0})
            continue
        k_smallest = np.sort(finite)[:k_nearest]
        within = finite[finite <= threshold_min]
        rows.append({
            "nearest_value": float(k_smallest.min()),
            "avg_k_nearest_value": float(k_smallest.mean()),
            "avg_within_threshold_value": float(within.mean()) if len(within) else None,
            "n_within_threshold": int(len(within)),
        })
    return pd.DataFrame(rows)


def load_destinations_for_state(dest_set_name, dest_year, state_fips):
    spec = DEST_SETS[dest_set_name]
    result = {}
    for dest_type, filename_template in spec["types"].items():
        filename = filename_template.format(dest_year=dest_year)
        if spec["national"]:
            path = spec["dir"] / filename
            if not path.exists():
                continue
            dests = pd.read_parquet(path)
            dests = dests[dests["state_fips"] == state_fips].reset_index(drop=True)
        else:
            path = spec["dir"] / state_fips / filename
            if not path.exists():
                continue
            dests = pd.read_parquet(path)
        if not dests.empty:
            result[dest_type] = dests
    return result


def compute_travel_time_metric(origins, dest_sets, dest_year, k_nearest, threshold_min):
    covered_states = sorted(set(origins["state_fips"]) & states_with_network())
    uncovered_states = sorted(set(origins["state_fips"]) - states_with_network())
    if uncovered_states:
        n_affected = origins[origins["state_fips"].isin(uncovered_states)]["GEOID"].nunique()
        print(f"  No OSM network yet for state(s) {uncovered_states} -- "
              f"{n_affected:,} metro tracts skipped for travel time this run.")
    if not covered_states:
        return None

    all_metrics = []
    for state_fips in covered_states:
        state_origins = origins[origins["state_fips"] == state_fips].reset_index(drop=True)
        g, nodes = build_graph(state_fips)
        node_lat, node_lon = nodes["lat"].values, nodes["lon"].values
        lon_scale = np.cos(np.radians(state_origins["lat"].mean()))
        origin_node_idx = snap_to_nearest_node(state_origins["lat"].values, state_origins["lon"].values, node_lat, node_lon, lon_scale)

        for dest_set_name in dest_sets:
            dest_frames = load_destinations_for_state(dest_set_name, dest_year, state_fips)
            for dest_type, dests in dest_frames.items():
                dest_node_idx = snap_to_nearest_node(dests["lat"].values, dests["lon"].values, node_lat, node_lon, lon_scale)
                metrics = travel_time_metrics(origin_node_idx, dest_node_idx, g, k_nearest, threshold_min)
                metrics.index = state_origins.index
                chunk = pd.concat([state_origins, metrics], axis=1)
                chunk["dest_type"] = dest_type
                chunk["distance_method"] = DISTANCE_METHOD
                chunk["distance_unit"] = "minutes"
                chunk["k_nearest"] = k_nearest
                chunk["threshold_value"] = threshold_min
                all_metrics.append(chunk)
        print(f"  [{state_fips}] {len(state_origins):,} metro origins routed")

    if not all_metrics:
        return None
    return pd.concat(all_metrics, ignore_index=True)


def print_metro_coverage(metro_tracts):
    covered = states_with_network()
    by_metro = metro_tracts.groupby("metro_fips")["GEOID"].apply(lambda s: set(s.str[:2]))
    full = sum(1 for states in by_metro if states <= covered)
    partial = sum(1 for states in by_metro if states & covered and not states <= covered)
    none_ = sum(1 for states in by_metro if not states & covered)
    print(f"\nTravel-time coverage: {full}/{len(by_metro)} metros fully covered, "
          f"{partial} partially covered, {none_} not covered yet (OSM network not built for their state(s)).")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--metric", nargs="+", default=["bike_path", "travel_time"], choices=["bike_path", "travel_time"])
    parser.add_argument("--origin-source", default="block_group_weighted", choices=list(ORIGIN_DIRS))
    parser.add_argument("--origin-year", default=None)
    parser.add_argument("--radius-miles", type=float, nargs="+", default=[1.0, 3.0, 5.0])
    parser.add_argument("--dest-set", nargs="+", default=["schools", "hospitals"], choices=list(DEST_SETS))
    parser.add_argument("--dest-year", default="2425")
    parser.add_argument("--k-nearest", type=int, default=5)
    parser.add_argument("--time-threshold-min", type=float, default=15.0)
    args = parser.parse_args()

    metro_tracts = load_metro_tracts()
    print_metro_coverage(metro_tracts)
    origins = load_metro_origins(args.origin_source, args.origin_year, metro_tracts)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if "bike_path" in args.metric:
        print("\n=== Bike path density (metro) ===")
        df = compute_bike_path_metric(origins, args.radius_miles)
        out_path = OUT_DIR / "bike_path_density_metro.parquet"
        df.to_parquet(out_path)
        print(f"Wrote {len(df):,} rows -> {out_path}")

    if "travel_time" in args.metric:
        print("\n=== Travel time to schools/hospitals (metro) ===")
        df = compute_travel_time_metric(origins, args.dest_set, args.dest_year, args.k_nearest, args.time_threshold_min)
        if df is None:
            print("No states with a built OSM network among this run's metro states -- nothing written.")
        else:
            df = validate_metrics(df)
            dest_label = "_".join(sorted(args.dest_set))
            out_path = OUT_DIR / f"travel_time_metrics_{dest_label}_{args.dest_year}_metro.parquet"
            df.to_parquet(out_path)
            print(f"Wrote {len(df):,} rows -> {out_path}")


if __name__ == "__main__":
    main()
