"""
Reference data: assign each census tract its historical HOLC redlining grade
(A/B/C/D), via spatial overlay -- NOT a GEOID join, unlike COI/RUCA.

Source: data/layer5_reference/redlining/mappinginequality.json (Mapping Inequality
project, HOLC "security maps"), confirmed live: 10,154 polygon features
nationally with a `grade` property (A/B/C/D) and `residential`/`commercial`/
`industrial` boolean flags -- filtered here to residential==True, since grade
is specifically a residential lending-risk classification.

HOLC only surveyed ~239 cities in the 1930s, so most tracts nationally
overlap NO HOLC polygon at all. That's correct, expected sparse coverage --
this script only outputs rows for tracts that overlap something, rather than
padding out a full state tract list with nulls (engine/reference_data.py's join
naturally leaves every other tract null when it merges this in).

Method: reproject both the HOLC polygons and layer1's tract polygons to
EPSG:5070 (equal-area, same CRS layer2's TIGER-roads script already uses for
length, for the same reason -- accurate area comparison), intersect, and
assign each tract the grade with the LARGEST area of overlap (a tract
straddling two HOLC zones gets whichever one covers more of it).

Usage:
    python 03_prepare_redlining.py                  # Massachusetts (default)
    python 03_prepare_redlining.py --state-fips 36   # New York
"""
import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd

REPO_ROOT = Path(__file__).parent.parent.parent
REDLINING_PATH = REPO_ROOT / "data" / "layer5_reference" / "redlining" / "mappinginequality.json"
OUT_DIR = REPO_ROOT / "data" / "layer5_reference" / "redlining" / "processed"
AREA_CRS = "EPSG:5070"

# USPS abbreviation by state FIPS -- mappinginequality.json's "state" property
# uses USPS codes, not FIPS, so this is needed purely to pre-filter the
# 10,154 national HOLC features down to the one state being processed.
FIPS_TO_USPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY", "72": "PR",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-fips", default="25", help="State FIPS code (default: 25, Massachusetts)")
    args = parser.parse_args()

    state_fips = args.state_fips
    usps = FIPS_TO_USPS.get(state_fips)
    if usps is None:
        raise SystemExit(f"No USPS abbreviation mapping for state FIPS {state_fips}")

    tract_path = REPO_ROOT / "data" / "layer1_geography" / "raw" / "2020" / "tract" / f"tl_2020_{state_fips}_tract.zip"
    if not tract_path.exists():
        raise SystemExit(f"Missing layer1 tract file for state FIPS {state_fips}: {tract_path} (run layer1 first)")

    print(f"[{state_fips}] Loading tracts and HOLC polygons...")
    tracts = gpd.read_file(f"zip://{tract_path}")[["GEOID", "geometry"]].to_crs(AREA_CRS)

    holc = gpd.read_file(REDLINING_PATH)
    holc = holc[(holc["state"] == usps) & (holc["residential"] == True) & holc["grade"].notna()]
    holc = holc[["grade", "category", "geometry"]].to_crs(AREA_CRS)
    print(f"  {len(holc)} residential HOLC polygons in {usps}")

    if holc.empty:
        print(f"  No HOLC-surveyed areas found in {usps} -- writing an empty lookup.")
        out = pd.DataFrame(columns=["GEOID", "redlining_grade", "redlining_category", "overlap_area_pct", "redlining_vintage"])
    else:
        overlap = gpd.overlay(tracts, holc, how="intersection")
        overlap["overlap_area_m2"] = overlap.geometry.area

        tract_area = tracts.set_index("GEOID").geometry.area

        # Keep only the largest-overlap grade per tract.
        overlap = overlap.sort_values("overlap_area_m2", ascending=False).drop_duplicates(subset="GEOID")
        overlap["overlap_area_pct"] = overlap["overlap_area_m2"] / overlap["GEOID"].map(tract_area) * 100

        out = overlap[["GEOID", "grade", "category", "overlap_area_pct"]].rename(
            columns={"grade": "redlining_grade", "category": "redlining_category"}
        )
        out["redlining_vintage"] = "1930s"
        print(f"  {len(out)} tracts overlap a HOLC-graded area (of {len(tracts):,} total tracts in {usps})")

    out["GEOID"] = out["GEOID"].astype("string")
    out["redlining_grade"] = out["redlining_grade"].astype("string")
    out["redlining_category"] = out["redlining_category"].astype("string")
    out["redlining_vintage"] = out["redlining_vintage"].astype("string")
    out["overlap_area_pct"] = pd.to_numeric(out["overlap_area_pct"], errors="coerce")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"redlining_tract_{state_fips}.parquet"
    out.to_parquet(out_path)
    print(f"Wrote {len(out):,} rows -> {out_path}")


if __name__ == "__main__":
    main()
