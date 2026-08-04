"""Schema for accessibility metrics output: one row per (GEOID, race/
ethnicity, characteristic, dest_type, algorithm). Originally used by the
one-off analysis scripts archived at ../archive/transportation-tool-
analysis-visualization-scripts/ -- revised for the accessibility function
suite design (see docs/function_design.md) to be flexible where it doesn't
need to be rigid.

Only the identity/join spine below is required and validated. Deliberately
NOT part of a fixed, pre-declared list:
  - The metric value(s) a given computation produces -- nearest_time_min,
    gravity_value, n_within_5mi, avg_k_nearest_time_min, whatever a new
    model needs. Name columns descriptively with the unit baked into the
    name rather than relying on a shared distance_unit column, since a
    single row can carry several differently-unitted metrics side by side
    (this mirrors the naming style code/analysis/05_build_simple_model.py
    already used, e.g. hospital_nearest_time_min,
    bike_path_length_mi_r{radius}). Adding a new metric never requires
    editing this file.
  - Layer 5 reference columns (coi_level_nat, ruca_code, redlining_grade,
    ...) attached afterward by engine/reference_data.py -- that module
    discovers whatever reference sources exist rather than this schema
    declaring them, so it never needs updating when a new reference source
    (crash data, transit frequency, ...) shows up either.

`population` is expected to almost always be present too (carried over from
whichever origins table the metric was computed against) -- not enforced
here since it's an attribute, not an identity/join key, but downstream code
that weights or aggregates by population should expect it.
"""

SPINE_REQUIRED_COLUMNS = [
    "GEOID", "geography_level", "state_fips",
    "race_ethnicity", "characteristic", "dest_type", "algorithm",
]
SPINE_DTYPES = {
    "GEOID": "string",
    "geography_level": "string",
    "state_fips": "string",
    "race_ethnicity": "string",
    "characteristic": "string",
    "dest_type": "string",
    "algorithm": "string",
}


def validate_metrics(df):
    """Require and type the identity spine only. Every other column --
    metric values, reference-data columns, anything else a caller added --
    passes through exactly as given, no fixed list to maintain."""
    missing = [c for c in SPINE_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Metrics table missing required spine columns: {missing}")
    df = df.copy()
    for col, dtype in SPINE_DTYPES.items():
        df[col] = df[col].astype(dtype)
    return df
