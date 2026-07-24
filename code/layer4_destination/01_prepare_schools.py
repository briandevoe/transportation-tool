"""
Layer 4 (Destinations): standardize NCES public school data into two
destination sets -- highschools, and elementary-to-middle schools -- filtered
to "typical" schools (excludes special education, alternative, vocational,
and charter schools).

Two NCES sources, joined on NCESSCH:
  - EDGE Geocode (data/layer4_destination/schools/EDGE_GEOCODE_PUBLICSCH_*.zip):
    location only -- name, address, lat/lon. No school type, charter, or
    grade-span info (confirmed by inspecting the raw columns -- the only
    school-specific code it carries is LOCALE, an urbanicity classification,
    not grade level).
  - CCD school directory (data/layer4_destination/schools/ccd_sch_029_*.zip):
    attributes -- SCH_TYPE_TEXT, CHARTER_TEXT, GSLO/GSHI (grade span),
    SY_STATUS_TEXT (operational status). This is what makes the filtering
    possible; the old ../transportation2 prep script never had it and only
    ever produced unfiltered location data.

Filters applied (each drop count is printed, not silent):
  - SCH_TYPE_TEXT == "Regular School" -- excludes Special Education,
    Alternative, and Career/Technical schools in one filter.
  - CHARTER_TEXT == "No" -- excludes charter schools (and "Not applicable",
    which isn't a typical regular school either).
  - SY_STATUS_TEXT == "Open" -- excludes closed/inactive/future schools.

Grade-span classification (GSHI = highest grade offered decides it, so a
combined middle/high school lands in the highschool file -- a family near a
6-12 school would send their high-school-age kids there):
  - highschool:         GSHI in {09, 10, 11, 12}
  - elementary_middle:  GSHI in {01, ..., 08}
  - anything else (GSHI of PK/KG/13/UG/AE/M or blank -- i.e. never reaches
    grade 1, or ungraded/adult-ed) is excluded from both, matching "typical
    schools that service grades 1-12."

Usage:
    python 01_prepare_schools.py                  # 2024-25 (default)
    python 01_prepare_schools.py --year 2324       # a different downloaded vintage
"""
import argparse
import zipfile
from pathlib import Path

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.destination_schema import validate_destinations

REPO_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = REPO_ROOT / "data" / "layer4_destination" / "schools"
OUT_DIR = DATA_DIR / "processed"

# Column layout for NCES EDGE_GEOCODE_PUBLICSCH pipe-delimited files (no
# header row) -- ported from ../transportation2's 03_prepare_school_points.py.
EDGE_COLUMNS = [
    "NCESSCH", "LEAID", "SCH_NAME", "STABNO", "LSTREET1", "LCITY", "LSTATE",
    "LZIP", "FIPST", "CONUM", "NMCNTY", "ULOCALE", "LAT", "LON",
    "CBSA", "CBSANAME", "CSA", "CSANAME", "SDLEA", "SDSEC", "SDUNI", "CDCODE", "SCHOOL_YEAR",
]

CCD_COLUMNS = ["NCESSCH", "SCH_TYPE_TEXT", "CHARTER_TEXT", "GSLO", "GSHI", "SY_STATUS_TEXT", "FIPST"]

HS_GRADES = {"09", "10", "11", "12"}
EM_GRADES = {"01", "02", "03", "04", "05", "06", "07", "08"}


def read_zipped(path, columns=None, **kwargs):
    """Read the single .TXT or .csv member of a zip, whichever it contains."""
    with zipfile.ZipFile(path) as z:
        member = next(n for n in z.namelist() if n.upper().endswith((".TXT", ".CSV")))
        with z.open(member) as f:
            if columns:
                return pd.read_csv(f, sep="|", names=columns, dtype=str, low_memory=False, **kwargs)
            return pd.read_csv(f, dtype=str, low_memory=False, **kwargs)


def classify(gshi):
    if gshi in HS_GRADES:
        return "school_highschool"
    if gshi in EM_GRADES:
        return "school_elementary_middle"
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", default="2425", choices=["2122", "2223", "2324", "2425"],
                         help="Which downloaded vintage to use (default: 2425, i.e. 2024-25)")
    args = parser.parse_args()

    edge_path = DATA_DIR / f"EDGE_GEOCODE_PUBLICSCH_{args.year}.zip"
    ccd_matches = list(DATA_DIR.glob(f"ccd_sch_029_{args.year}_*.zip"))
    if not edge_path.exists() or not ccd_matches:
        raise SystemExit(f"Missing EDGE Geocode or CCD directory file for vintage {args.year} in {DATA_DIR}")
    ccd_path = ccd_matches[0]

    print(f"Reading {edge_path.name}...")
    edge = read_zipped(edge_path, columns=EDGE_COLUMNS)
    print(f"  {len(edge):,} schools (location)")

    print(f"Reading {ccd_path.name}...")
    ccd = read_zipped(ccd_path, usecols=CCD_COLUMNS)
    print(f"  {len(ccd):,} schools (attributes)")

    year_label = edge["SCHOOL_YEAR"].iloc[0] if len(edge) else args.year

    df = edge.merge(ccd, on="NCESSCH", how="inner", suffixes=("", "_ccd"))
    print(f"Joined on NCESSCH: {len(df):,} (dropped {len(edge) - len(df):,} location-only, "
          f"{len(ccd) - len(df):,} attributes-only)")

    for label, mask in [
        ('SCH_TYPE_TEXT == "Regular School"', df["SCH_TYPE_TEXT"] == "Regular School"),
    ]:
        before = len(df)
        df = df[mask]
        print(f"  {label}: kept {len(df):,} (dropped {before - len(df):,})")

    before = len(df)
    df = df[df["CHARTER_TEXT"] == "No"]
    print(f'  CHARTER_TEXT == "No": kept {len(df):,} (dropped {before - len(df):,})')

    before = len(df)
    df = df[df["SY_STATUS_TEXT"] == "Open"]
    print(f'  SY_STATUS_TEXT == "Open": kept {len(df):,} (dropped {before - len(df):,})')

    df["dest_type"] = df["GSHI"].apply(classify)
    excluded = df["dest_type"].isna().sum()
    print(f"  Grade-span classification: excluded {excluded:,} (GSHI not in 01-12, e.g. PK/KG/UG/AE-only)")
    df = df.dropna(subset=["dest_type"])

    df["dest_id"] = df["NCESSCH"]
    df["name"] = df["SCH_NAME"]
    df["lat"] = pd.to_numeric(df["LAT"], errors="coerce")
    df["lon"] = pd.to_numeric(df["LON"], errors="coerce")
    df["category"] = df["GSLO"] + "-" + df["GSHI"]
    df["state_fips"] = df["FIPST"].str.zfill(2)
    df["source"] = "NCES CCD+EDGE"
    df["year"] = year_label
    df["address"] = df["LSTREET1"]
    df["city"] = df["LCITY"]
    df["state"] = df["LSTATE"]

    before = len(df)
    df = df.dropna(subset=["lat", "lon"])
    if before - len(df):
        print(f"  Dropped {before - len(df):,} schools with missing coordinates")

    df = validate_destinations(df)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for dest_type, filename in [
        ("school_highschool", f"highschools_{args.year}.parquet"),
        ("school_elementary_middle", f"elementary_middle_{args.year}.parquet"),
    ]:
        subset = df[df["dest_type"] == dest_type]
        out_path = OUT_DIR / filename
        subset.to_parquet(out_path)
        print(f"Wrote {len(subset):,} rows -> {out_path}")


if __name__ == "__main__":
    main()
