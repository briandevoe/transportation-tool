"""Shared schema for the travel network layer (layer2_network).

Every network dataset (OSM roads, TIGER roads, and eventually sidewalks,
bike lanes, transit) gets its own prep script per source, but all of them
must emit the same edge/node columns so the routing engine downstream never
needs to change per network source -- same pattern as origins/destinations
in ../transportation2/v2_archive/code/lib/schema.py.

Fields that only some sources can populate (e.g. TIGER has no routing
topology or speed attributes) stay optional rather than required-non-null.
"""

# Standardized taxonomy every source's native road classification maps into.
HIGHWAY_CLASSES = [
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "residential", "service", "unclassified", "living_street", "other",
]

NETWORK_EDGE_REQUIRED_COLUMNS = [
    "edge_id", "geometry", "highway_class", "length_m",
    "network_type", "source", "vintage", "state_fips",
]
NETWORK_EDGE_OPTIONAL_COLUMNS = [
    "from_node", "to_node", "oneway", "speed_kph", "name",
]
NETWORK_EDGE_COLUMNS = NETWORK_EDGE_REQUIRED_COLUMNS + NETWORK_EDGE_OPTIONAL_COLUMNS

NETWORK_NODE_COLUMNS = ["node_id", "lat", "lon", "state_fips"]

# Explicit per-column dtypes, enforced on every source's output here rather
# than left to whatever a given source's raw values happen to infer as --
# without this, e.g. OSM's numeric from_node/to_node and TIGER's all-null
# from_node/to_node round-trip to different Parquet/pandas dtypes even though
# both satisfy the schema, defeating the point of a "uniform" output. Nullable
# pandas extension dtypes (string/boolean) so sources that can't populate a
# field (TIGER has no routing topology or speed data) store real nulls
# instead of stringified "None".
NETWORK_EDGE_DTYPES = {
    "edge_id": "string",
    "highway_class": "string",
    "length_m": "float64",
    "network_type": "string",
    "source": "string",
    "vintage": "string",
    "state_fips": "string",
    "from_node": "string",
    "to_node": "string",
    "oneway": "boolean",
    "speed_kph": "float64",
    "name": "string",
}
NETWORK_NODE_DTYPES = {
    "node_id": "string",
    "lat": "float64",
    "lon": "float64",
    "state_fips": "string",
}


def validate_network_edges(gdf):
    missing = [c for c in NETWORK_EDGE_REQUIRED_COLUMNS if c not in gdf.columns]
    if missing:
        raise ValueError(f"Network edge table missing required columns: {missing}")
    gdf = gdf.copy()
    for col in NETWORK_EDGE_OPTIONAL_COLUMNS:
        if col not in gdf.columns:
            gdf[col] = None
    gdf = gdf[NETWORK_EDGE_COLUMNS]
    for col, dtype in NETWORK_EDGE_DTYPES.items():
        gdf[col] = gdf[col].astype(dtype)
    return gdf


def validate_network_nodes(df):
    missing = [c for c in NETWORK_NODE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Network node table missing required columns: {missing}")
    df = df[NETWORK_NODE_COLUMNS].copy()
    for col, dtype in NETWORK_NODE_DTYPES.items():
        df[col] = df[col].astype(dtype)
    return df
