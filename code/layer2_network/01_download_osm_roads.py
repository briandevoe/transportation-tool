"""
Layer 2 (Network): build a routable road network from OpenStreetMap.

Primary/routable road source. Downloads a state's Geofabrik .osm.pbf extract
and parses it locally with pyrosm (not osmnx/Overpass -- osmnx's
graph_from_xml() can't read the protobuf format Geofabrik serves, and the
public Overpass API rate-limits/blocks repeated heavy queries). This mirrors
the approach validated in ../transportation2, with one deliberate change:
that version conflated network *building* with *routing* (it re-parsed the
PBF per geographic chunk sized to match a batch of origin tracts). This
script only builds and standardizes the network -- routing is a separate,
later concern that consumes this output.

Geographic tiling, independent of any origin set: a whole-state
osm.to_graph() call -- even for a state as small as Massachusetts -- can
exceed available memory. pyrosm's own connectivity step (inside to_graph(),
not the initial parse) explodes row count well past what get_network() alone
returns; this was never actually exercised at whole-state scale even in the
old proven code, which only ever built small buffered regions (roughly half
a state) at a time and never persisted a full state's network. Each tile is
built, simplified, and standardized independently via pyrosm's bounding_box
restriction, then all tiles are concatenated and deduplicated by OSM node id
(stable across tiles, so a way parsed by two overlapping tiles collapses back
to one row). The one accepted quality cost: simplify_graph() runs per tile,
so a long road straddling a tile seam may end up as two simplified edges
instead of one -- cosmetic, not a connectivity problem.

pyrosm's default "driving" filter is far more permissive than it looks (kept
service/track/path ways that inflated one state's graph ~15x versus the
equivalent osmnx/Overpass network) -- DRIVABLE_HIGHWAY_FILTER below restricts
to the standard drivable-highway tag set instead. It's applied via
filter_type="keep": this pyrosm version defaults a plain-dict custom_filter
to "exclude" (Overpass exclude-these-ways semantics), which silently keeps
every *non*-drivable way instead -- verified directly against a real extract,
not assumed from pyrosm's docs.

Output is split into two standardized Parquet files per state (schema in
code/lib/network_schema.py) so later network types (sidewalks, bike lanes,
transit) can slot into the same columns regardless of source:
    data/layer2_network/roads/osm/processed/<state_fips>/edges.parquet
    data/layer2_network/roads/osm/processed/<state_fips>/nodes.parquet

Usage:
    python 01_download_osm_roads.py                    # Massachusetts (default)
    python 01_download_osm_roads.py --state-fips 36     # New York
"""
import argparse
import sys
import time
from datetime import date
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pandas as pd
from pyrosm import OSM

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.network_schema import validate_network_edges, validate_network_nodes
from lib.osm_pbf import STATE_FIPS_TO_PLACE, get_pbf_path

REPO_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = REPO_ROOT / "data" / "layer2_network" / "roads" / "osm"

ox.settings.timeout = 300

# Grid of TILE_GRID x TILE_GRID bounding-box tiles to keep each pyrosm/osmnx
# to_graph() call's memory footprint well within a modest machine's headroom
# (confirmed 6.9GB free was not enough for a whole-Massachusetts build).
# Fixed for now; a larger state will need this sized to its area rather than
# a flat constant -- not solved here.
TILE_GRID = 3
TILE_BUFFER_DEG = 0.05  # ~5.5km margin so roads near a tile seam aren't clipped mid-way

DRIVABLE_HIGHWAY_FILTER = {
    "highway": [
        "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
        "residential", "motorway_link", "trunk_link", "primary_link",
        "secondary_link", "tertiary_link", "living_street",
    ]
}

# OSM highway tag -> standardized highway_class (see lib/network_schema.py).
# *_link variants collapse into their parent class; anything not listed here
# (e.g. pyrosm's generic "road" fallback) maps to "other".
HIGHWAY_TAG_MAP = {
    "motorway": "motorway", "motorway_link": "motorway",
    "trunk": "trunk", "trunk_link": "trunk",
    "primary": "primary", "primary_link": "primary",
    "secondary": "secondary", "secondary_link": "secondary",
    "tertiary": "tertiary", "tertiary_link": "tertiary",
    "residential": "residential",
    "unclassified": "unclassified",
    "living_street": "living_street",
    "service": "service",
}

def fmt_elapsed(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def get_state_bbox(state_fips):
    """Reuse the already-downloaded layer1 tract file for the state's extent
    instead of hand-maintaining per-state bounding boxes. CRS is EPSG:4269
    (NAD83), numerically close enough to WGS84 for a buffered bbox filter."""
    tract_path = REPO_ROOT / "data" / "layer1_geography" / "raw" / "2020" / "tract" / f"tl_2020_{state_fips}_tract.zip"
    if not tract_path.exists():
        raise SystemExit(f"Missing layer1 tract file for state FIPS {state_fips}: {tract_path} (run layer1 first)")
    return gpd.read_file(f"zip://{tract_path}").total_bounds  # (minx, miny, maxx, maxy)


def make_tiles(bounds, grid=TILE_GRID, buffer_deg=TILE_BUFFER_DEG):
    minx, miny, maxx, maxy = bounds
    dx = (maxx - minx) / grid
    dy = (maxy - miny) / grid
    tiles = []
    for i in range(grid):
        for j in range(grid):
            x0, x1 = minx + i * dx, minx + (i + 1) * dx
            y0, y1 = miny + j * dy, miny + (j + 1) * dy
            tiles.append((x0 - buffer_deg, y0 - buffer_deg, x1 + buffer_deg, y1 + buffer_deg))
    return tiles


def parse_state_network(pbf_path):
    """Parse the whole state's PBF exactly once. PBF is a sequential,
    block-compressed format with no spatial index -- passing a different
    bounding_box to a fresh OSM(...) call per tile (the old approach) forces
    pyrosm to re-decode the entire file from scratch each time, multiplying
    parse cost by the tile count for no benefit. Confirmed live against
    Rhode Island: filtering this one in-memory parse per tile (below)
    produces an identical graph (same node/edge sets, post-simplify) to the
    old per-tile bounding_box approach, at ~15x less wall-clock time."""
    osm = OSM(str(pbf_path))
    result = osm.get_network(
        network_type="driving", nodes=True, custom_filter=DRIVABLE_HIGHWAY_FILTER, filter_type="keep"
    )
    if result is None:
        return None, None, None
    nodes, edges = result
    if nodes is None or edges is None or len(edges) == 0:
        return None, None, None
    return osm, nodes, edges


def build_tile_graph(osm, nodes, edges, bbox):
    """Slice the already-parsed state-wide edges/nodes to one tile (cheap
    in-memory geopandas filter) instead of re-parsing the PBF. Node subset is
    derived from the filtered edges' u/v references, not an independent bbox
    filter on nodes -- guarantees every node an edge needs is present even if
    it sits just outside the tile (the buffered tile margin already accounts
    for roads near a seam; this avoids a second, inconsistent cutoff)."""
    minx, miny, maxx, maxy = bbox
    edges_tile = edges.cx[minx:maxx, miny:maxy]
    if edges_tile is None or len(edges_tile) == 0:
        return None
    node_ids_needed = set(edges_tile["u"]).union(edges_tile["v"])
    nodes_tile = nodes[nodes["id"].isin(node_ids_needed)]
    G = osm.to_graph(nodes_tile, edges_tile, graph_type="networkx")
    G = ox.simplify_graph(G)
    ox.add_edge_speeds(G)
    ox.add_edge_travel_times(G)
    return G


def map_highway_class(value):
    if isinstance(value, list):
        value = value[0] if value else None
    return HIGHWAY_TAG_MAP.get(value, "other")


def first_if_list(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def normalize_oneway(value):
    # simplify_graph() consolidates parallel original edges and lists
    # attribute values that differ across them (same treatment "highway" and
    # "name" need) -- an edge counts as oneway only if every merged segment was.
    if isinstance(value, list):
        return bool(all(value)) if value else None
    if pd.isna(value):
        return None
    return bool(value)


def standardize(G, state_fips, vintage):
    nodes_gdf, edges_gdf = ox.graph_to_gdfs(G)

    edges_gdf = edges_gdf.reset_index()  # u, v, key -> columns
    edges_gdf["edge_id"] = (
        edges_gdf["u"].astype(str) + "_" + edges_gdf["v"].astype(str) + "_" + edges_gdf["key"].astype(str)
    )
    edges_gdf["from_node"] = edges_gdf["u"]
    edges_gdf["to_node"] = edges_gdf["v"]
    edges_gdf["highway_class"] = edges_gdf["highway"].apply(map_highway_class)
    edges_gdf["length_m"] = edges_gdf["length"]
    edges_gdf["name"] = edges_gdf["name"].apply(first_if_list) if "name" in edges_gdf.columns else None
    edges_gdf["oneway"] = edges_gdf["oneway"].apply(normalize_oneway) if "oneway" in edges_gdf.columns else None
    edges_gdf["network_type"] = "roads"
    edges_gdf["source"] = "osm"
    edges_gdf["vintage"] = vintage
    edges_gdf["state_fips"] = state_fips
    edges_gdf = validate_network_edges(edges_gdf)

    # Don't reset_index() here: pyrosm-built graphs carry an "osmid" node
    # attribute in addition to using it as the index, so reset_index() would
    # try to insert a column that already exists. Pull the index directly.
    nodes_gdf = nodes_gdf.copy()
    nodes_gdf["node_id"] = nodes_gdf.index
    nodes_gdf["lat"] = nodes_gdf["y"]
    nodes_gdf["lon"] = nodes_gdf["x"]
    nodes_gdf["state_fips"] = state_fips
    nodes_df = validate_network_nodes(pd.DataFrame(nodes_gdf.drop(columns="geometry")))

    return edges_gdf, nodes_df


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-fips", default="25", help="State FIPS code (default: 25, Massachusetts)")
    args = parser.parse_args()

    state_fips = args.state_fips
    place = STATE_FIPS_TO_PLACE.get(state_fips, f"state FIPS {state_fips}")

    out_dir = DATA_DIR / "processed" / state_fips
    edges_path = out_dir / "edges.parquet"
    nodes_path = out_dir / "nodes.parquet"
    if edges_path.exists() and nodes_path.exists():
        print(f"[{state_fips}] {place} — already processed, skipping.")
        return

    print(f"[{state_fips}] {place}")
    pbf_path = get_pbf_path(state_fips, DATA_DIR / "raw")

    bounds = get_state_bbox(state_fips)
    tiles = make_tiles(bounds)
    vintage = date.today().isoformat()

    print("  Parsing PBF (once for the whole state)...")
    t0 = time.time()
    osm, state_nodes, state_edges = parse_state_network(pbf_path)
    if osm is None:
        raise SystemExit("No drivable road network found in this state's PBF.")
    print(f"  Parsed {len(state_edges):,} candidate edges, {len(state_nodes):,} candidate nodes "
          f"({fmt_elapsed(time.time() - t0)})")

    print(f"  Building road graph in {len(tiles)} tiles (pyrosm + osmnx)...")
    all_edges, all_nodes = [], []
    t0 = time.time()
    for i, bbox in enumerate(tiles, start=1):
        try:
            G = build_tile_graph(osm, state_nodes, state_edges, bbox)
        except Exception as e:
            print(f"  Tile {i}/{len(tiles)}: failed ({type(e).__name__}: {e}), skipping.")
            continue
        if G is None or G.number_of_edges() == 0:
            print(f"  Tile {i}/{len(tiles)}: no road network, skipping.")
            continue
        edges_gdf, nodes_df = standardize(G, state_fips, vintage)
        all_edges.append(edges_gdf)
        all_nodes.append(nodes_df)
        print(f"  Tile {i}/{len(tiles)}: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

    if not all_edges:
        raise SystemExit("No road network found in any tile.")

    edges_gdf = pd.concat(all_edges, ignore_index=True)
    edges_gdf = gpd.GeoDataFrame(edges_gdf, geometry="geometry", crs=all_edges[0].crs)
    # OSM node ids are stable across tiles, so a way parsed by two
    # overlapping (buffered) tiles produces the same edge_id in both --
    # dedupe rather than double-count it.
    edges_gdf = edges_gdf.drop_duplicates(subset="edge_id").reset_index(drop=True)
    nodes_df = pd.concat(all_nodes, ignore_index=True).drop_duplicates(subset="node_id").reset_index(drop=True)
    print(f"  Combined: {len(edges_gdf):,} edges, {len(nodes_df):,} nodes ({fmt_elapsed(time.time() - t0)})")

    out_dir.mkdir(parents=True, exist_ok=True)
    edges_gdf.to_parquet(edges_path)
    nodes_df.to_parquet(nodes_path)
    print(f"  Wrote {len(edges_gdf):,} edges -> {edges_path}")
    print(f"  Wrote {len(nodes_df):,} nodes -> {nodes_path}")


if __name__ == "__main__":
    main()
