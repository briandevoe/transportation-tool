"""
Layer 2 (Network): build a ROUTABLE road network from Census TIGER/Line
ROADS geometry, as a fallback for states where the OSM network
(01_download_osm_roads.py) hasn't been built yet.

Motivation: building the OSM network state-by-state (pyrosm/osmnx, PBF
parsing + tiling) is slow and highly variable -- New Mexico alone took 17
hours. TIGER's raw county ROADS zips are already downloaded nationally (see
02_download_tiger_roads.py --region all), so this script does no network
I/O at all -- pure local geometry processing, orders of magnitude faster.
The tradeoff is real and worth stating plainly:
  - TIGER carries no speed-limit, lane-count, or turn-restriction data at
    all -- speed_kph below is a flat default per MTFCC class (see
    SPEED_KPH_BY_CLASS), not anything measured.
  - TIGER carries no oneway attribute either -- every edge is treated as
    two-way (emitted as two directed rows, matching how OSM's already-
    directed edges are consumed downstream).
  - Node topology doesn't exist in the ROADS cartographic extract as
    published -- this script reconstructs it by snapping coincident segment
    endpoints (rounded to 7 decimal degrees, ~1cm) into shared node ids.
    TIGER intersections are derived from the same underlying MTDB vertices,
    so exact-coordinate snapping is reliable for true intersections; it will
    NOT catch a gap where two roads cross without a mapped junction (rare,
    not solved here).
This makes routing results here strictly less accurate than an OSM-based
build -- use this for coverage where OSM isn't available yet, not as a
long-term replacement.

Excludes non-drivable MTFCC classes (walkway/stairway/alley/bike path/
bridle path -- S1710/S1720/S1730/S1820/S1830) from the graph entirely; a car
can't route through a bike path.

Output (same schema as the OSM builder, see lib/network_schema.py), in its
own subtree so it never collides with either the OSM network or the
existing non-routable TIGER reference edges:
    data/layer2_network/roads/tiger_routable/processed/<state_fips>/edges.parquet
    data/layer2_network/roads/tiger_routable/processed/<state_fips>/nodes.parquet

Usage:
    python 03_build_routable_tiger_network.py                    # MA (default)
    python 03_build_routable_tiger_network.py --state-fips 25 44 22 13 35
    python 03_build_routable_tiger_network.py --region conus_ak_hi
"""
import argparse
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.network_schema import validate_network_edges, validate_network_nodes
from lib.tiger_download import REGION_PRESETS, fmt_elapsed

REPO_ROOT = Path(__file__).parent.parent.parent
RAW_DIR = REPO_ROOT / "data" / "layer2_network" / "roads" / "tiger" / "raw"
OUT_DIR = REPO_ROOT / "data" / "layer2_network" / "roads" / "tiger_routable" / "processed"

LENGTH_CRS = "EPSG:5070"   # CONUS Albers -- matches 02_download_tiger_roads.py's length convention
STORAGE_CRS = "EPSG:4326"  # matches OSM edges output
SNAP_DECIMALS = 7          # ~1.1cm at the equator -- tight enough to avoid false merges, loose enough for float noise

# MTFCC -> (standardized highway_class, default speed_kph). Only drivable
# classes are listed; anything else (walkway/stairway/alley/bike/bridle path)
# is dropped before graph construction. Speeds are flat US rule-of-thumb
# defaults by road class, not measured data -- see module docstring.
DRIVABLE_MTFCC = {
    "S1100": ("primary", 89.0),      # Primary road (~55mph)
    "S1200": ("secondary", 72.0),    # Secondary road (~45mph)
    "S1400": ("residential", 40.0),  # Local/neighborhood/rural road (~25mph)
    "S1500": ("service", 24.0),      # Vehicular trail (4WD) (~15mph)
    "S1630": ("service", 40.0),      # Ramp
    "S1640": ("service", 24.0),      # Service drive alongside a limited-access highway
    "S1740": ("service", 16.0),      # Private service road (~10mph)
    "S1780": ("service", 16.0),      # Parking lot road (~10mph)
}


def load_county_zips(state_fips, year):
    raw_dir = RAW_DIR / str(year)
    return sorted(raw_dir.glob(f"tl_{year}_{state_fips}*_roads.zip"))


def endpoint_key(geom):
    coords = geom.coords
    p0 = f"{round(coords[0][0], SNAP_DECIMALS):.7f}|{round(coords[0][1], SNAP_DECIMALS):.7f}"
    p1 = f"{round(coords[-1][0], SNAP_DECIMALS):.7f}|{round(coords[-1][1], SNAP_DECIMALS):.7f}"
    return p0, p1


def build_state_network(state_fips, year):
    county_zips = load_county_zips(state_fips, year)
    if not county_zips:
        print(f"  [{state_fips}] No cached raw TIGER ROADS zips for year {year} -- "
              f"run 02_download_tiger_roads.py first.")
        return None

    pieces = []
    for zpath in county_zips:
        gdf = gpd.read_file(f"zip://{zpath}")
        gdf = gdf[gdf["MTFCC"].isin(DRIVABLE_MTFCC)][["MTFCC", "LINEARID", "FULLNAME", "geometry"]]
        if len(gdf):
            pieces.append(gdf)
    if not pieces:
        print(f"  [{state_fips}] No drivable-class segments found across {len(county_zips)} counties.")
        return None

    gdf = pd.concat(pieces, ignore_index=True)
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=pieces[0].crs)
    print(f"  [{state_fips}] {len(gdf):,} drivable segments across {len(county_zips)} counties")

    # Node topology: snap coincident endpoints into shared node ids. Keys are
    # "lon|lat" strings (not raw coordinate tuples) so pd.factorize hashes
    # each point as one object -- np.unique on a list of tuples instead
    # flattens them into a plain 2D array and silently returns the wrong shape.
    endpoints = gdf.geometry.apply(endpoint_key)
    p0s = [e[0] for e in endpoints]
    p1s = [e[1] for e in endpoints]
    n = len(gdf)
    codes, unique_keys = pd.factorize(np.array(p0s + p1s, dtype=object))
    from_idx, to_idx = codes[:n], codes[n:]
    node_ids = [f"{state_fips}_tigernode_{i}" for i in range(len(unique_keys))]
    unique_points = [tuple(float(v) for v in k.split("|")) for k in unique_keys]

    gdf["from_node"] = [node_ids[i] for i in from_idx]
    gdf["to_node"] = [node_ids[i] for i in to_idx]
    gdf["highway_class"] = gdf["MTFCC"].map(lambda m: DRIVABLE_MTFCC[m][0])
    gdf["speed_kph"] = gdf["MTFCC"].map(lambda m: DRIVABLE_MTFCC[m][1])
    gdf["length_m"] = gdf.geometry.to_crs(LENGTH_CRS).length
    gdf["name"] = gdf["FULLNAME"]
    gdf["network_type"] = "roads"
    gdf["source"] = "tiger_routable"
    gdf["vintage"] = str(year)
    gdf["state_fips"] = state_fips
    gdf["oneway"] = False

    # TIGER has no directionality data -- treat every edge as two-way by
    # emitting both directions explicitly, so downstream routing code (which
    # takes from_node/to_node as-is, same as OSM's already-directed edges)
    # needs no special-case handling for an undirected source.
    fwd = gdf.copy()
    fwd["edge_id"] = fwd["LINEARID"] + "_fwd"
    rev = gdf.copy()
    rev["edge_id"] = rev["LINEARID"] + "_rev"
    rev["from_node"], rev["to_node"] = gdf["to_node"], gdf["from_node"]
    edges = pd.concat([fwd, rev], ignore_index=True)
    edges = gpd.GeoDataFrame(edges, geometry="geometry", crs=gdf.crs).to_crs(STORAGE_CRS)
    edges = validate_network_edges(edges)

    node_lon = np.array([p[0] for p in unique_points])
    node_lat = np.array([p[1] for p in unique_points])
    nodes = pd.DataFrame({"node_id": node_ids, "lat": node_lat, "lon": node_lon, "state_fips": state_fips})
    nodes = validate_network_nodes(nodes)

    return edges, nodes


def process_state(state_fips, year):
    out_dir = OUT_DIR / state_fips
    edges_path = out_dir / "edges.parquet"
    nodes_path = out_dir / "nodes.parquet"
    if edges_path.exists() and nodes_path.exists():
        print(f"[{state_fips}] already processed, skipping.")
        return

    print(f"[{state_fips}] TIGER {year} -> routable network")
    t0 = time.time()
    result = build_state_network(state_fips, year)
    if result is None:
        return
    edges, nodes = result

    out_dir.mkdir(parents=True, exist_ok=True)
    edges.to_parquet(edges_path)
    nodes.to_parquet(nodes_path)
    print(f"  Wrote {len(edges):,} edges, {len(nodes):,} nodes -> {out_dir} ({fmt_elapsed(time.time() - t0)})")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-fips", nargs="+", default=["25"], help="State FIPS code(s) (default: 25, Massachusetts)")
    parser.add_argument("--region", choices=list(REGION_PRESETS), default=None,
                         help="'all' = 56 states/territories, 'conus_ak_hi' = 50 states + DC -- overrides --state-fips")
    parser.add_argument("--year", type=int, default=2020, help="TIGER/Line vintage year (default: 2020, matches layer1)")
    args = parser.parse_args()

    states = REGION_PRESETS[args.region] if args.region else args.state_fips
    for state_fips in states:
        process_state(state_fips, args.year)

    print("\nDone.")


if __name__ == "__main__":
    main()
