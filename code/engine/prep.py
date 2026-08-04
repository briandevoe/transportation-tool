"""Layer accessors: load already-processed layer output into memory for
analysis. Fast, repeatable "assemble already-prepared layers" calls --
downloading/building stays the job of the layer1-4 CLI scripts (see each
layer's README.md).

See docs/function_design.md. Covers the vertical slice exercised by
tests/test_smoke_ma_hospitals.py (tract geography, coi_5 population,
OSM network, hospital/grocery destinations) -- other geography types,
race schemes, and destination types will raise NotImplementedError until
someone actually needs them and extends this.
"""
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .network import Network

REPO_ROOT = Path(__file__).parent.parent.parent
DATA_ROOT = REPO_ROOT / "data"

# dest_type -> (relative path template, per_state). Per-state files are
# state-scoped at the source (see layer4_destination/README.md); national
# files (schools) get filtered to state_fips after loading.
_DESTINATION_PATHS = {
    "hospital": ("layer4_destination/hospitals/processed/{state_fips}/hospitals_osm.parquet", True),
    "grocery": ("layer4_destination/grocery/processed/{state_fips}/grocery_osm.parquet", True),
    "school_highschool": ("layer4_destination/schools/processed/highschools_2425.parquet", False),
    "school_elementary_middle": ("layer4_destination/schools/processed/elementary_middle_2425.parquet", False),
}


def get_geography(state_fips="25", geography_type="tract", vintage="2020"):
    """Load data/layer1_geography/processed/<vintage>/<geography_type>.parquet,
    filtered to state_fips. Returns a GeoDataFrame.

    Only handles the single-national-file geography types (tract, bg, zcta,
    county, school districts, ...) -- `block` is stored one file per state
    (see layer1_geography/README.md) and isn't handled here yet."""
    if geography_type == "block":
        raise NotImplementedError("block geography is stored per-state -- not wired up here yet")
    path = DATA_ROOT / "layer1_geography" / "processed" / vintage / f"{geography_type}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} -- run layer1_geography's download/standardize scripts first")
    gdf = gpd.read_parquet(path)
    return gdf[gdf["state_fips"] == state_fips].reset_index(drop=True)


def get_population(state_fips="25", race_scheme="coi_5", characteristics=("N/A",), year=2022):
    """Load the population-weighted origins table for state_fips (columns:
    lib/population_schema.py's ORIGIN_COLUMNS), filtered to the requested
    characteristic(s). Returns a DataFrame.

    coi_5 (the default scheme) keeps the bare `origins_<year>.parquet`
    filename; other schemes get a `_<scheme>` suffix -- same convention
    layer3_population's own scripts use (see their README.md)."""
    origin_dir = DATA_ROOT / "layer3_population" / "block_group_weighted" / "processed" / state_fips
    suffix = "" if race_scheme == "coi_5" else f"_{race_scheme}"
    path = origin_dir / f"origins_{year}{suffix}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} -- run layer3_population's scripts for this state/year/scheme first")
    df = pd.read_parquet(path)
    df = df[df["characteristic"].isin(characteristics)]
    df = df.dropna(subset=["lat", "lon"]).reset_index(drop=True)
    return df


def get_network(state_fips="25", source="osm"):
    """Load edges.parquet/nodes.parquet for state_fips and wrap them in a
    Network (see engine/network.py). Returns a Network."""
    network_dir = DATA_ROOT / "layer2_network" / "roads" / source / "processed" / state_fips
    edges_path, nodes_path = network_dir / "edges.parquet", network_dir / "nodes.parquet"
    if not edges_path.exists() or not nodes_path.exists():
        raise FileNotFoundError(f"{network_dir} -- run layer2_network's download script for this state first")
    edges = pd.read_parquet(edges_path).dropna(subset=["from_node", "to_node", "length_m", "speed_kph"])
    nodes = pd.read_parquet(nodes_path)
    return Network(edges, nodes)


def get_destinations(dest_type="hospital", state_fips="25"):
    """Load the standardized destination table for dest_type (columns:
    lib/destination_schema.py's DESTINATION_COLUMNS). Returns a DataFrame.

    Covers hospital, grocery, school_highschool, school_elementary_middle
    (see _DESTINATION_PATHS above) -- add a new entry there for any other
    destination type layer4_destination grows."""
    if dest_type not in _DESTINATION_PATHS:
        raise NotImplementedError(f"Unknown dest_type '{dest_type}' -- add it to _DESTINATION_PATHS")
    template, per_state = _DESTINATION_PATHS[dest_type]
    path = DATA_ROOT / template.format(state_fips=state_fips)
    if not path.exists():
        raise FileNotFoundError(f"{path} -- run the matching layer4_destination script first")
    df = pd.read_parquet(path)
    if not per_state:
        df = df[df["state_fips"] == state_fips].reset_index(drop=True)
    return df
