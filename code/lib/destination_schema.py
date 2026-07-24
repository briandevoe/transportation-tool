"""Shared schema for the destinations layer (layer4_destination).

Every destination dataset (schools, hospitals, grocery stores, ...) gets its
own prep script per source, but all of them must emit the same columns so
the routing engine never needs to change per destination type -- same
pattern as origins/destinations in
../transportation2/v2_archive/code/lib/schema.py, generalized here with the
explicit-dtype validate_*() pattern from lib/network_schema.py and
lib/population_schema.py (CSV round-trips silently discard dtype info;
Parquet doesn't).
"""

DESTINATION_REQUIRED_COLUMNS = ["dest_id", "dest_type", "name", "lat", "lon"]
DESTINATION_OPTIONAL_COLUMNS = [
    "weight", "category", "state_fips", "source", "year", "address", "city", "state",
]
DESTINATION_COLUMNS = DESTINATION_REQUIRED_COLUMNS + DESTINATION_OPTIONAL_COLUMNS

DESTINATION_DTYPES = {
    "dest_id": "string",
    "dest_type": "string",
    "name": "string",
    "lat": "float64",
    "lon": "float64",
    "weight": "float64",
    "category": "string",
    "state_fips": "string",
    "source": "string",
    "year": "string",
    "address": "string",
    "city": "string",
    "state": "string",
}


def validate_destinations(df):
    missing = [c for c in DESTINATION_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Destination table missing required columns: {missing}")
    df = df.copy()
    for col in DESTINATION_OPTIONAL_COLUMNS:
        if col not in df.columns:
            df[col] = None
    if df["weight"].isna().all():
        df["weight"] = 1.0
    df = df[DESTINATION_COLUMNS]
    for col, dtype in DESTINATION_DTYPES.items():
        df[col] = df[col].astype(dtype)
    return df
