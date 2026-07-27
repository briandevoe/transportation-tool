"""Shared schema for code/analysis -- accessibility metrics that merge an
origins table (layer3) against a destinations table (layer4), plus
reference-data attributes (code/lib/reference_data.py).

Same validate_*()/explicit-dtype pattern as every other layer (CSV
round-trips silently discard dtype info; output is Parquet).

Column names are method-agnostic (nearest_value, not nearest_dist_mi) so
01_compute_distance_metrics.py (haversine, miles) and
02_compute_travel_time_metrics.py (network routing, minutes) emit the exact
same shape -- distinguished by distance_method + distance_unit, not by
having different column names. That's what makes it possible to concatenate
both outputs and compare them directly (verification step in the plan), and
matches every other layer's "same columns regardless of source" rule.
"""

METRICS_COLUMNS = [
    "GEOID", "geography_level", "state_fips", "race_ethnicity", "characteristic",
    "population", "dest_type",
    "distance_method", "distance_unit",
    "nearest_value", "avg_k_nearest_value", "k_nearest",
    "avg_within_threshold_value", "n_within_threshold", "threshold_value",
    "coi_level_nat", "coi_score_nat", "coi_vintage",
    "metro_fips", "metro_name", "metro_type", "in_top100_metro",
    "ruca_code", "ruca_description", "ruca_vintage",
    "redlining_grade", "redlining_category", "redlining_vintage",
]

METRICS_DTYPES = {
    "GEOID": "string",
    "geography_level": "string",
    "state_fips": "string",
    "race_ethnicity": "string",
    "characteristic": "string",
    "population": "float64",
    "dest_type": "string",
    "distance_method": "string",
    "distance_unit": "string",
    "nearest_value": "float64",
    "avg_k_nearest_value": "float64",
    "k_nearest": "int64",
    "avg_within_threshold_value": "float64",  # nullable: undefined (not zero) when n_within_threshold == 0
    "n_within_threshold": "int64",
    "threshold_value": "float64",
    "coi_level_nat": "string",
    "coi_score_nat": "float64",
    "coi_vintage": "string",
    "metro_fips": "string",
    "metro_name": "string",
    "metro_type": "string",
    "in_top100_metro": "boolean",
    "ruca_code": "float64",
    "ruca_description": "string",
    "ruca_vintage": "string",
    "redlining_grade": "string",
    "redlining_category": "string",
    "redlining_vintage": "string",
}


def validate_metrics(df):
    missing = [c for c in METRICS_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Metrics table missing required columns: {missing}")
    df = df[METRICS_COLUMNS].copy()
    for col, dtype in METRICS_DTYPES.items():
        df[col] = df[col].astype(dtype)
    return df
