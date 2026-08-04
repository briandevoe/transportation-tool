"""Attach every processed Layer 5 reference dataset onto any GEOID-keyed
DataFrame -- by discovery, not a hardcoded list of sources (revised for the
accessibility function suite design, see docs/function_design.md).

The one convention every layer5_reference/*.py script already follows: write
a GEOID-keyed parquet -- one national file, or one per state -- to
data/layer5_reference/<name>/processed/. This function finds every such
folder, concatenates whatever's inside it (handles COI/RUCA's single
national file and redlining/vehicle_availability's per-state files
identically), and left-joins each source onto GEOID in turn -- a tract with
no match in a given source keeps its row with null columns for that source,
rather than being dropped.

Adding a new reference source (crash data, transit frequency, ...) requires
ZERO changes to this file -- land a GEOID-keyed parquet in the right folder
and it's picked up automatically. The one convention to follow so two
sources never collide when joined back to back: prefix ambiguous column
names with the source's own name (coi_vintage, not vintage) -- already true
of every source today (coi_vintage, ruca_vintage, redlining_vintage,
vehicle_availability_vintage).
"""
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).parent.parent.parent
REFERENCE_ROOT = REPO_ROOT / "data" / "layer5_reference"


def attach_reference_attributes(df):
    df = df.copy()
    if not REFERENCE_ROOT.exists():
        return df

    attached = []
    for source_dir in sorted(p for p in REFERENCE_ROOT.iterdir() if p.is_dir()):
        processed_dir = source_dir / "processed"
        if not processed_dir.is_dir():
            continue
        parquet_files = sorted(processed_dir.glob("*.parquet"))
        if not parquet_files:
            continue

        source = pd.concat([pd.read_parquet(p) for p in parquet_files], ignore_index=True)
        if "GEOID" not in source.columns:
            print(f"  Skipping Layer 5 source '{source_dir.name}': no GEOID column in its processed output")
            continue

        source = source.drop_duplicates(subset="GEOID")
        df = df.merge(source, on="GEOID", how="left")
        attached.append(source_dir.name)

    if attached:
        print(f"  Attached Layer 5 sources: {', '.join(attached)}")
    return df
