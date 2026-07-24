"""Shared schema for the population layer (layer3_population).

Two schemas: a lighter "population counts" table (what
01_download_acs_population.py produces on its own -- no location) and the
full "origin" table (what the centroid-building scripts produce -- adds
lat/lon plus how the centroid was computed). Same validate_*/explicit-dtype
pattern as lib/network_schema.py, for the same reason: force identical
columns AND dtypes across every source/script that emits one of these
tables, not just matching column names.
"""

POPULATION_COUNT_COLUMNS = [
    "GEOID", "geography_level", "state_fips", "race_ethnicity", "characteristic",
    "population", "population_source", "population_vintage",
]
POPULATION_COUNT_DTYPES = {
    "GEOID": "string",
    "geography_level": "string",
    "state_fips": "string",
    "race_ethnicity": "string",
    "characteristic": "string",
    "population": "float64",
    "population_source": "string",
    "population_vintage": "string",
}

ORIGIN_REQUIRED_COLUMNS = POPULATION_COUNT_COLUMNS + ["centroid_source", "centroid_vintage"]
ORIGIN_OPTIONAL_COLUMNS = ["lat", "lon"]  # null when a tract has zero population of that group (0/0 case)
ORIGIN_COLUMNS = ORIGIN_REQUIRED_COLUMNS + ORIGIN_OPTIONAL_COLUMNS
ORIGIN_DTYPES = {
    **POPULATION_COUNT_DTYPES,
    "centroid_source": "string",
    "centroid_vintage": "string",
    "lat": "float64",
    "lon": "float64",
}


def validate_population_counts(df):
    missing = [c for c in POPULATION_COUNT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Population count table missing required columns: {missing}")
    df = df[POPULATION_COUNT_COLUMNS].copy()
    for col, dtype in POPULATION_COUNT_DTYPES.items():
        df[col] = df[col].astype(dtype)
    return df


def validate_population_origins(df):
    missing = [c for c in ORIGIN_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Population origin table missing required columns: {missing}")
    df = df.copy()
    for col in ORIGIN_OPTIONAL_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[ORIGIN_COLUMNS]
    for col, dtype in ORIGIN_DTYPES.items():
        df[col] = df[col].astype(dtype)
    return df
