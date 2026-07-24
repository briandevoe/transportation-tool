"""Attach the processed reference datasets (code/layer5_reference/*.py output)
onto any GEOID-keyed DataFrame -- used by both code/analysis scripts so a
groupby on COI level / RUCA code / redlining grade works identically
regardless of which distance method produced the metrics.

All three are left-joins: a tract with no COI/RUCA/redlining match keeps its
row with null reference columns rather than being dropped. COI and RUCA are
single national lookup files; redlining is processed per-state (see
code/layer5_reference/03_prepare_redlining.py), so its loader globs whatever
states have been run so far rather than requiring a fixed list.
"""
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).parent.parent.parent
COI_DIR = REPO_ROOT / "data" / "layer5_reference" / "coi" / "processed"
RUCA_DIR = REPO_ROOT / "data" / "layer5_reference" / "ruca" / "processed"
REDLINING_DIR = REPO_ROOT / "data" / "layer5_reference" / "redlining" / "processed"

REFERENCE_COLUMNS = [
    "coi_level_nat", "coi_score_nat", "coi_vintage",
    "ruca_code", "ruca_description", "ruca_vintage",
    "redlining_grade", "redlining_category", "redlining_vintage",
]


def _latest(pattern, directory):
    matches = sorted(directory.glob(pattern))
    return matches[-1] if matches else None


def attach_reference_attributes(df):
    df = df.copy()

    coi_path = _latest("coi_tract_*.parquet", COI_DIR)
    if coi_path:
        coi = pd.read_parquet(coi_path)[["GEOID", "coi_level_nat", "coi_score_nat", "coi_vintage"]]
        df = df.merge(coi, on="GEOID", how="left")

    ruca_path = _latest("ruca_tract_*.parquet", RUCA_DIR)
    if ruca_path:
        ruca = pd.read_parquet(ruca_path)[["GEOID", "ruca_code", "ruca_description", "ruca_vintage"]]
        df = df.merge(ruca, on="GEOID", how="left")

    redlining_paths = sorted(REDLINING_DIR.glob("redlining_tract_*.parquet"))
    if redlining_paths:
        redlining = pd.concat([pd.read_parquet(p) for p in redlining_paths], ignore_index=True)
        redlining = redlining[["GEOID", "redlining_grade", "redlining_category", "redlining_vintage"]]
        df = df.merge(redlining, on="GEOID", how="left")

    for col in REFERENCE_COLUMNS:
        if col not in df.columns:
            df[col] = None

    return df
