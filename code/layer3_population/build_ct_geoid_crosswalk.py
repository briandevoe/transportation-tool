"""
One-time build script for data/layer3_population/ct_geoid_crosswalk.csv --
NOT part of the regular pipeline, not meant to be re-run except to audit or
regenerate the crosswalk itself. See code/lib/ct_geoid_crosswalk.py for how
the output is actually used (applied to every ACS fetch, unconditionally).

Builds the crosswalk from data already in this repo (Layer 1's standardized
2020 tract list) plus one live ACS query, matching Connecticut's old
(county-based) and new (planning-region-based) tract GEOIDs on their
trailing 6-digit tract code -- see docs/COI 3.0 Technical Documentation
20250724.pdf, Appendix 6, for why this works (tract boundaries never moved,
only the county-FIPS segment of the GEOID did) and for the 3 hardcoded
exceptions below, which reuse COI's own published resolution since they
required spatial analysis to resolve, not just code-matching.

Usage:
    python build_ct_geoid_crosswalk.py
"""
import os
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

REPO_ROOT = Path(__file__).parent.parent.parent

# COI 3.0's own resolution for 3 of the 4 ambiguous tracts (Appendix 6,
# Table A6.2) -- obtained by them via spatial analysis, not code-matching.
# The 4th ambiguous old tract, 09001990000, is fully covered by water and
# split into two new-vintage tracts in 2022 -- COI drops it entirely rather
# than pick an arbitrary counterpart, and so do we.
COI_RESOLVED_EXCEPTIONS = {
    "09170990000": "09009990000",
    "09130990100": "09007990100",
    "09180990100": "09011990100",
}
DROPPED_OLD_TRACT = "09001990000"


def main():
    old_tracts = gpd.read_parquet(REPO_ROOT / "data/layer1_geography/processed/2020/tract.parquet")
    old_ct = old_tracts[old_tracts["state_fips"] == "09"][["GEOID"]].copy()
    old_ct["tractce"] = old_ct["GEOID"].str[-6:]

    api_key = os.environ.get("CENSUS_API_KEY")
    resp = requests.get(
        "https://api.census.gov/data/2022/acs/acs5",
        params={"get": "B01001_001E", "for": "tract:*", "in": "state:09", "key": api_key},
        timeout=60,
    )
    resp.raise_for_status()
    rows = resp.json()
    df = pd.DataFrame(rows[1:], columns=rows[0])
    df["GEOID"] = df["state"] + df["county"] + df["tract"]
    new_ct = df[["GEOID"]].copy()
    new_ct["tractce"] = new_ct["GEOID"].str[-6:]

    merged = old_ct.merge(new_ct, on="tractce", how="inner", suffixes=("_old", "_new"))
    counts = merged["tractce"].value_counts()
    ambiguous_codes = set(counts[counts > 1].index)
    clean = merged[~merged["tractce"].isin(ambiguous_codes)]

    exceptions = pd.DataFrame(
        [{"GEOID_new": new, "GEOID_old": old} for new, old in COI_RESOLVED_EXCEPTIONS.items()]
    )

    final = pd.concat([clean[["GEOID_new", "GEOID_old"]], exceptions], ignore_index=True)
    final = final.rename(columns={"GEOID_new": "geoid_new", "GEOID_old": "geoid_old"})

    assert DROPPED_OLD_TRACT not in final["geoid_old"].values
    assert final["geoid_old"].is_unique
    assert final["geoid_new"].is_unique
    assert len(final) == len(old_ct) - 1, f"expected {len(old_ct) - 1} mapped tracts, got {len(final)}"

    out_path = REPO_ROOT / "data" / "layer3_population" / "ct_geoid_crosswalk.csv"
    final.sort_values("geoid_old").to_csv(out_path, index=False)
    print(f"Wrote {len(final)} rows -> {out_path} ({len(old_ct)} total old CT tracts, "
          f"1 dropped: {DROPPED_OLD_TRACT} -- fully covered by water, split in 2022)")


if __name__ == "__main__":
    main()
