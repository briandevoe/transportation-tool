"""
Analysis: network-routed travel-time accessibility metrics from
population-weighted tract centroids (layer3) to schools (layer4), using the
OSM road network already built in layer2.

Same three metrics, same shape, as 01_compute_distance_metrics.py -- see
lib/analysis_schema.py's method-agnostic columns (nearest_value,
avg_k_nearest_value, avg_within_threshold_value, n_within_threshold) --
just computed via routing (minutes) instead of haversine (miles), so the
two outputs are directly comparable/concatenable.

Unlike script 01, destinations are filtered to the SAME state as the road
network (state_fips column on the layer4 files) -- a state-scoped network
can't route to an out-of-state school, so a national destination set
wouldn't make sense here. Known limitation, not solved this pass: a border
tract's true nearest school by road might be just across the state line and
won't be found.

Graph build: a directed igraph.Graph from layer2's persisted edges/nodes
(data/layer2_network/roads/osm/processed/<state>/) -- already correctly
directional (osmnx expands two-way streets into a directed edge pair when
the network was built), so from_node/to_node is used as-is, no extra oneway
handling needed. Edge weight = length_m / speed_kph / 1000 * 60 (minutes).

Routing: batched multi-source Dijkstra via igraph.Graph.distances() -- the
approach docs/reference.md and ../transportation2's old routing code both
converged on -- one call per dest_type covering every (unique snapped origin
node) x (unique snapped destination node) pair at once. Simpler than the old
code here because the graph is already built and persisted (no per-chunk PBF
re-parsing, which is what forced that code's chunking complexity).

Also attaches COI/RUCA/redlining tract attributes (lib/reference_data.py),
same as script 01.

Usage:
    python 02_compute_travel_time_metrics.py                         # MA, 2024-25 schools (default)
    python 02_compute_travel_time_metrics.py --time-threshold-min 20
    python 02_compute_travel_time_metrics.py --origin-source block_weighted
"""
import argparse
import re
import sys
from pathlib import Path

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
# osm = real OSM-derived network (01_download_osm_roads.py) -- accurate but
# only built for a handful of states so far. tiger_routable = fallback graph
# reconstructed from TIGER geometry (03_build_routable_tiger_network.py) --
# nationally available fast, but flat MTFCC-based default speeds and no
# oneway/turn data, so its travel times are coarser. See that script's
# docstring for the full list of accepted tradeoffs.
NETWORK_DIRS = {
    "osm": REPO_ROOT / "data" / "layer2_network" / "roads" / "osm" / "processed",
    "tiger_routable": REPO_ROOT / "data" / "layer2_network" / "roads" / "tiger_routable" / "processed",
}
OUT_DIR = REPO_ROOT / "data" / "analysis" / "processed"

# Same shape as 01_compute_distance_metrics.py's DEST_SETS -- "national" dest
# sets (schools) read one nationwide file and filter to this state; per-state
# sets (hospitals, grocery) read that state's own extract directly. Kept as
# its own copy rather than importing from script 01 -- these are two
# standalone analysis entry points by design, not a shared module, and the
# dict is small enough that duplicating it is cheaper than coupling them.
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
    "grocery": {
        "national": False,
        "dir": REPO_ROOT / "data" / "layer4_destination" / "grocery" / "processed",
        "types": {"grocery": "grocery_osm.parquet"},
    },
}

DISTANCE_METHOD_BY_SOURCE = {
    "osm": "osm_network_dijkstra",
    "tiger_routable": "tiger_routable_network_dijkstra",
}


def load_origins(origin_source, state_fips, year):
    """When year is None, matches ONLY the bare default-scheme/k=1 filename --
    layer3 now writes multiple origin files per state (default coi_5/k=1 at
    origins_<year>.parquet, plus suffixed variants like origins_<year>_k2.parquet
    or origins_<year>_simplified_5.parquet for non-default runs), and a plain
    "origins_*.parquet" glob would silently match and pick whichever suffixed
    variant the filesystem happens to return first (confirmed live elsewhere in
    this project -- it grabbed a leftover _k2 test file instead of the intended
    default)."""
    if year is None:
        state_dir = ORIGIN_DIRS[origin_source] / state_fips
        matches = [p for p in state_dir.glob("origins_*.parquet") if re.fullmatch(r"origins_\d{4}\.parquet", p.name)]
    else:
        matches = [ORIGIN_DIRS[origin_source] / state_fips / f"origins_{year}.parquet"]
    matches = [p for p in matches if p.exists()]
    if not matches:
        raise SystemExit(f"No default-scheme origins file found for --origin-source {origin_source}, state {state_fips}, year {year}")
    df = pd.read_parquet(matches[0])
    before = len(df)
    df = df.dropna(subset=["lat", "lon"])
    print(f"Loaded {matches[0].relative_to(REPO_ROOT)}: {len(df):,} origins with a centroid ({before - len(df):,} dropped, zero population)")
    return df


def build_graph(state_fips, network_source):
    network_dir = NETWORK_DIRS[network_source]
    edges_path = network_dir / state_fips / "edges.parquet"
    nodes_path = network_dir / state_fips / "nodes.parquet"
    if not edges_path.exists() or not nodes_path.exists():
        raise SystemExit(f"Missing layer2 {network_source} network for state FIPS {state_fips} in {network_dir} (run layer2 first)")

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
    print(f"Built graph: {g.vcount():,} nodes, {g.ecount():,} edges")
    return g, nodes


def snap_to_nearest_node(lats, lons, node_lat, node_lon, lon_scale):
    tree = cKDTree(np.column_stack([node_lon * lon_scale, node_lat]))
    _, idx = tree.query(np.column_stack([np.asarray(lons) * lon_scale, np.asarray(lats)]), k=1)
    return np.atleast_1d(idx)


def travel_time_metrics(origin_node_idx, dest_node_idx, g, k_nearest, threshold_min):
    unique_o, o_inverse = np.unique(origin_node_idx, return_inverse=True)
    unique_d, d_inverse = np.unique(dest_node_idx, return_inverse=True)

    dist_matrix = np.array(g.distances(source=list(unique_o), target=list(unique_d), weights="weight"))
    dist_matrix[np.isinf(dist_matrix)] = np.nan  # unreachable (e.g. disconnected component), not an error

    rows = []
    for i in range(len(origin_node_idx)):
        times = dist_matrix[o_inverse[i], d_inverse]  # one value per destination (nan if unreachable)
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
    """Returns {dest_type: DataFrame} for this one state -- "national" dest
    sets (schools) read the one nationwide file and filter to state_fips;
    per-state sets (hospitals, grocery) read that state's own extract
    directly. Single-state version of 01_compute_distance_metrics.py's
    load_destinations(), since this script routes against one state's graph
    at a time rather than a multi-state batch."""
    spec = DEST_SETS[dest_set_name]
    result = {}
    for dest_type, filename_template in spec["types"].items():
        filename = filename_template.format(dest_year=dest_year)
        if spec["national"]:
            path = spec["dir"] / filename
            if not path.exists():
                raise SystemExit(f"Missing destinations file: {path}")
            dests = pd.read_parquet(path)
            dests = dests[dests["state_fips"] == state_fips].reset_index(drop=True)
            print(f"[{dest_type}] {len(dests):,} destinations in state {state_fips} (national file filtered to this state)")
        else:
            path = spec["dir"] / state_fips / filename
            if not path.exists():
                print(f"[{dest_type}] No {dest_set_name} file for state {state_fips} -- skipping.")
                continue
            dests = pd.read_parquet(path)
            print(f"[{dest_type}] {len(dests):,} destinations in state {state_fips}")
        if dests.empty:
            print("  No destinations in this state, skipping.")
            continue
        result[dest_type] = dests
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-fips", default="25", help="State FIPS code (default: 25, Massachusetts)")
    parser.add_argument("--network-source", default="osm", choices=list(NETWORK_DIRS),
                         help="Which layer2 network to route on: osm (accurate, limited state coverage) "
                              "or tiger_routable (nationally available, coarser speed assumptions) (default: osm)")
    parser.add_argument("--origin-source", default="block_group_weighted",
                         choices=list(ORIGIN_DIRS), help="Which layer3 centroid method to use (default: block_group_weighted)")
    parser.add_argument("--origin-year", default=None, help="Origins file vintage (default: whatever's on disk)")
    parser.add_argument("--dest-set", nargs="+", default=["schools"], choices=list(DEST_SETS),
                         help="Which destination set(s) to compute against: schools, hospitals, grocery (default: schools)")
    parser.add_argument("--dest-year", default="2425", help="Schools destinations file vintage (default: 2425; ignored by hospitals/grocery)")
    parser.add_argument("--k-nearest", type=int, default=5, help="K for the average-of-K-nearest metric (default: 5)")
    parser.add_argument("--time-threshold-min", type=float, default=15.0, help="Threshold for the within-time metric (default: 15)")
    args = parser.parse_args()

    state_fips = args.state_fips
    origins = load_origins(args.origin_source, state_fips, args.origin_year)
    g, nodes = build_graph(state_fips, args.network_source)
    distance_method = DISTANCE_METHOD_BY_SOURCE[args.network_source]

    node_lat, node_lon = nodes["lat"].values, nodes["lon"].values
    lon_scale = np.cos(np.radians(origins["lat"].mean()))
    origin_node_idx = snap_to_nearest_node(origins["lat"].values, origins["lon"].values, node_lat, node_lon, lon_scale)

    all_metrics = []
    for dest_set_name in args.dest_set:
        dest_frames = load_destinations_for_state(dest_set_name, args.dest_year, state_fips)
        for dest_type, dests in dest_frames.items():
            dest_node_idx = snap_to_nearest_node(dests["lat"].values, dests["lon"].values, node_lat, node_lon, lon_scale)
            metrics = travel_time_metrics(origin_node_idx, dest_node_idx, g, args.k_nearest, args.time_threshold_min)
            metrics.index = origins.index

            chunk = pd.concat([origins[["GEOID", "geography_level", "state_fips", "race_ethnicity", "characteristic", "population"]], metrics], axis=1)
            chunk["dest_type"] = dest_type
            chunk["distance_method"] = distance_method
            chunk["distance_unit"] = "minutes"
            chunk["k_nearest"] = args.k_nearest
            chunk["threshold_value"] = args.time_threshold_min
            all_metrics.append(chunk)

    if not all_metrics:
        raise SystemExit("No destinations found for any requested dest-set in this state.")

    df = pd.concat(all_metrics, ignore_index=True)
    df = attach_reference_attributes(df)
    df = validate_metrics(df)

    dest_label = "_".join(sorted(args.dest_set))
    # network_source suffix omitted for the "osm" default so existing output
    # filenames/paths from before --network-source existed stay unchanged.
    source_suffix = "" if args.network_source == "osm" else f"_{args.network_source}"
    out_path = OUT_DIR / state_fips / f"travel_time_metrics_{dest_label}_{args.dest_year}{source_suffix}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)
    print(f"Wrote {len(df):,} rows -> {out_path}")


if __name__ == "__main__":
    main()
